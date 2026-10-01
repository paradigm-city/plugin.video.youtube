# -*- coding: utf-8 -*-
"""
Unit tests for the subscriptions route handlers (yt_subscriptions):
- Sign-in redirect and unknown commands
- Listing own subscriptions and caching their subscribed status
- Subscribing via parameters or list item properties
- Unsubscribing by subscription id or channel id
"""
import pytest

from youtube_plugin.kodion import KodionException
from youtube_plugin.kodion.items import UriItem
from youtube_plugin.youtube.helper import yt_subscriptions
from youtube_plugin.youtube.provider import Provider


class StubClient(object):
    """Records calls made by the subscription handlers."""

    def __init__(self, logged_in=True, subscription_data=None,
                 subscribe_result=None, unsubscribe_result=True):
        self.logged_in = logged_in
        self.subscription_data = subscription_data
        self.subscribe_result = (
            {'id': 'new_subscription'}
            if subscribe_result is None else
            subscribe_result
        )
        self.unsubscribe_result = unsubscribe_result
        self.calls = []
        self.status = {}

    def get_subscription(self, channel_id, page_token=''):
        self.calls.append(('get_subscription', channel_id, page_token))
        return self.subscription_data

    def subscribe(self, channel_id):
        self.calls.append(('subscribe', channel_id))
        return self.subscribe_result

    def unsubscribe(self, subscription_id):
        self.calls.append(('unsubscribe', subscription_id))
        return self.unsubscribe_result

    def unsubscribe_channel(self, channel_id):
        self.calls.append(('unsubscribe_channel', channel_id))
        return self.unsubscribe_result

    def set_subscription_status(self, channel_id, subscribed):
        self.status[channel_id] = subscribed


class StubUI(object):
    def __init__(self, properties=None):
        self.properties = properties or {}
        self.notifications = []

    def get_listitem_property(self, name, *_args, **_kwargs):
        return self.properties.get(name, '')

    def show_notification(self, message, *_args, **_kwargs):
        self.notifications.append(message)


class Match(object):
    def __init__(self, command):
        self._command = command

    def group(self, name):
        assert name == 'command'
        return self._command


@pytest.fixture
def provider():
    return Provider()


@pytest.fixture
def ui(mock_context, monkeypatch):
    stub_ui = StubUI()
    monkeypatch.setattr(mock_context, 'get_ui', lambda: stub_ui)
    return stub_ui


def run(provider, context, client, command, monkeypatch):
    monkeypatch.setattr(provider, 'get_client', lambda _context: client)
    return yt_subscriptions.process(provider, context, Match(command))


# ============================================================================
# Routing
# ============================================================================

def test_not_logged_in_redirects_to_sign_in(provider, mock_context, ui, monkeypatch):
    client = StubClient(logged_in=False)

    result = run(provider, mock_context, client, 'add', monkeypatch)

    assert isinstance(result, UriItem)
    assert 'sign/in' in result.get_uri()
    assert client.calls == []


def test_unknown_command_raises(provider, mock_context, ui, monkeypatch):
    with pytest.raises(KodionException):
        run(provider, mock_context, StubClient(), 'rename', monkeypatch)


# ============================================================================
# List
# ============================================================================

def test_list_marks_listed_channels_as_subscribed(provider, mock_context, ui, monkeypatch):
    client = StubClient(subscription_data={
        'items': [
            {'snippet': {'resourceId': {'channelId': 'UC_ONE'}}},
            {'snippet': {'resourceId': {'channelId': 'UC_TWO'}}},
            {'snippet': {'resourceId': {}}},
            {'snippet': None},
            'not a dict',
        ],
    })
    monkeypatch.setattr(
        yt_subscriptions.v3,
        'response_to_items',
        lambda _provider, _context, json_data: ['item'] * len(json_data['items']),
    )

    items, options = run(provider, mock_context, client, 'list', monkeypatch)

    assert client.calls == [('get_subscription', 'mine', '')]
    assert client.status == {'UC_ONE': True, 'UC_TWO': True}
    assert len(items) == 5
    assert provider.CONTENT_TYPE in options


def test_list_passes_page_token(provider, mock_context, ui, monkeypatch):
    mock_context.set_params(page_token='NEXT_PAGE')
    client = StubClient(subscription_data={'items': []})
    monkeypatch.setattr(yt_subscriptions.v3, 'response_to_items', lambda *_args: [])

    run(provider, mock_context, client, 'list', monkeypatch)

    assert client.calls == [('get_subscription', 'mine', 'NEXT_PAGE')]


def test_list_without_response_returns_empty(provider, mock_context, ui, monkeypatch):
    client = StubClient(subscription_data=None)

    assert run(provider, mock_context, client, 'list', monkeypatch) == []
    assert client.status == {}


# ============================================================================
# Add
# ============================================================================

def test_add_subscribes_and_refreshes(provider, mock_context, ui, monkeypatch):
    mock_context.set_params(subscription_id='UC_TARGET')
    client = StubClient()

    result = run(provider, mock_context, client, 'add', monkeypatch)

    assert result == (True, {provider.FORCE_REFRESH: True})
    assert client.calls == [('subscribe', 'UC_TARGET')]
    assert client.status == {'UC_TARGET': True}
    assert len(ui.notifications) == 1


@pytest.mark.parametrize('listitem_id', ['UC_FROM_LISTITEM', 'uc_lowercase_prefix'])
def test_add_falls_back_to_channel_listitem_property(provider, mock_context, ui,
                                                     monkeypatch, listitem_id):
    ui.properties['subscription_id'] = listitem_id
    client = StubClient()

    result = run(provider, mock_context, client, 'add', monkeypatch)

    assert result[0] is True
    assert client.calls == [('subscribe', listitem_id)]


def test_add_ignores_non_channel_listitem_property(provider, mock_context, ui, monkeypatch):
    ui.properties['subscription_id'] = 'PL_NOT_A_CHANNEL'
    client = StubClient()

    assert run(provider, mock_context, client, 'add', monkeypatch) is False
    assert client.calls == []


def test_add_failure_does_not_update_status(provider, mock_context, ui, monkeypatch):
    mock_context.set_params(subscription_id='UC_TARGET')
    client = StubClient(subscribe_result={})

    assert run(provider, mock_context, client, 'add', monkeypatch) is False
    assert client.status == {}
    assert ui.notifications == []


# ============================================================================
# Remove
# ============================================================================

def test_remove_by_subscription_id_updates_channel_status(provider, mock_context, ui, monkeypatch):
    mock_context.set_params(subscription_id='sub_123', channel_id='UC_TARGET')
    client = StubClient()

    result = run(provider, mock_context, client, 'remove', monkeypatch)

    assert result == (True, {provider.FORCE_REFRESH: True})
    assert client.calls == [('unsubscribe', 'sub_123')]
    assert client.status == {'UC_TARGET': False}
    assert len(ui.notifications) == 1


def test_remove_by_channel_id_only(provider, mock_context, ui, monkeypatch):
    mock_context.set_params(channel_id='UC_TARGET')
    client = StubClient()

    result = run(provider, mock_context, client, 'remove', monkeypatch)

    assert result[0] is True
    assert client.calls == [('unsubscribe_channel', 'UC_TARGET')]
    assert client.status == {'UC_TARGET': False}


def test_remove_uses_listitem_properties(provider, mock_context, ui, monkeypatch):
    ui.properties.update(subscription_id='sub_456', channel_id='UC_LISTITEM')
    client = StubClient()

    run(provider, mock_context, client, 'remove', monkeypatch)

    assert client.calls == [('unsubscribe', 'sub_456')]
    assert client.status == {'UC_LISTITEM': False}


def test_remove_with_channel_id_as_subscription_id(provider, mock_context, ui, monkeypatch):
    # A channel id passed as subscription_id is used for the status update,
    # but the unsubscribe request is still made with it as a subscription id.
    mock_context.set_params(subscription_id='UC_PASSED_AS_SUB')
    client = StubClient()

    run(provider, mock_context, client, 'remove', monkeypatch)

    assert client.calls == [('unsubscribe', 'UC_PASSED_AS_SUB')]
    assert client.status == {'UC_PASSED_AS_SUB': False}


def test_remove_failure_returns_false_without_status_update(provider, mock_context, ui, monkeypatch):
    mock_context.set_params(subscription_id='sub_123', channel_id='UC_TARGET')
    client = StubClient(unsubscribe_result=False)

    assert run(provider, mock_context, client, 'remove', monkeypatch) == (False, None)
    assert client.status == {}
    assert ui.notifications == []


def test_remove_without_ids_does_nothing(provider, mock_context, ui, monkeypatch):
    client = StubClient()

    assert run(provider, mock_context, client, 'remove', monkeypatch) == (False, None)
    assert client.calls == []
