# -*- coding: utf-8 -*-
"""
Integration tests for channel subscription status detection in
YouTubeDataClient using mocked HTTP responses:
- get_subscription() request parameters for forChannelId lookups
- get_subscription_status() batching, in-memory and persistent caching
- set_subscription_status() updates and per-user cache keys
- Behaviour when the Data API returns an error
"""
import json
import os

try:
    from urllib.parse import parse_qs, urlparse
except ImportError:  # pragma: no cover
    from urlparse import parse_qs, urlparse

import pytest

from youtube_plugin.youtube.client.data_client import YouTubeDataClient


FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'v3_api'))
SUBSCRIPTIONS_URL = 'https://www.googleapis.com/youtube/v3/subscriptions'
CHANNELS_URL = 'https://www.googleapis.com/youtube/v3/channels'

CONFIGS = {
    'user': {
        'key': 'AIzaSy_TEST_API_KEY_1234567890',
        'id': 'test-client-id.apps.googleusercontent.com',
        'secret': 'test-client-secret',
    },
    'tv': {
        'key': 'AIzaSy_TEST_API_KEY_1234567890',
        'id': 'test-tv-id.apps.googleusercontent.com',
        'secret': 'test-tv-secret',
    },
}


def load_v3_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), 'r', encoding='utf-8') as f:
        return json.load(f)


def subscriptions_response(*channel_ids):
    return {
        'kind': 'youtube#subscriptionListResponse',
        'items': [
            {
                'kind': 'youtube#subscription',
                'id': 'sub_' + channel_id,
                'snippet': {
                    'resourceId': {
                        'kind': 'youtube#channel',
                        'channelId': channel_id,
                    },
                },
            }
            for channel_id in channel_ids
        ],
    }


def subscription_requests(requests_mock):
    return [
        request
        for request in requests_mock.request_history
        if request.url.startswith(SUBSCRIPTIONS_URL)
    ]


def query_params(request):
    return parse_qs(urlparse(request.url).query)


@pytest.fixture(autouse=True)
def clean_caches(mock_context):
    mock_context.get_requests_cache().clear()
    mock_context.get_data_cache().clear()
    yield
    mock_context.get_requests_cache().clear()
    mock_context.get_data_cache().clear()


@pytest.fixture
def data_client(mock_context):
    """Client that is not logged in."""
    return YouTubeDataClient(context=mock_context, configs=CONFIGS)


@pytest.fixture
def logged_in_client(mock_context, requests_mock):
    """Authenticated client with OAuth2 access tokens."""
    requests_mock.get(CHANNELS_URL, json={'items': [{'id': 'UC_MINE_CHANNEL_ID'}]})
    client = YouTubeDataClient(context=mock_context, configs=CONFIGS)
    client.set_access_token({'user': 'mock_user_token', 'tv': 'mock_tv_token'})
    return client


# ============================================================================
# get_subscription() request parameters
# ============================================================================

class TestGetSubscriptionParams:

    def test_for_channel_id_list_queries_mine_without_order(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response())

        logged_in_client.get_subscription('mine', for_channel_id=['UC_A', 'UC_B'])

        params = query_params(subscription_requests(requests_mock)[-1])
        assert sorted(params['forChannelId'][0].split(',')) == ['UC_A', 'UC_B']
        assert [value.lower() for value in params['mine']] == ['true']
        assert params['maxResults'] == ['2']
        assert 'order' not in params
        assert 'channelId' not in params

    def test_for_channel_id_single_value(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response())

        logged_in_client.get_subscription(for_channel_id='UC_SINGLE')

        params = query_params(subscription_requests(requests_mock)[-1])
        assert params['forChannelId'] == ['UC_SINGLE']
        assert [value.lower() for value in params['mine']] == ['true']
        assert params['maxResults'] == ['50']

    def test_default_listing_still_uses_order_and_mine(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=load_v3_fixture('subscriptions_list.json'))

        logged_in_client.get_subscription()

        params = query_params(subscription_requests(requests_mock)[-1])
        assert [value.lower() for value in params['mine']] == ['true']
        assert params['order'] == ['alphabetical']
        assert 'forChannelId' not in params


# ============================================================================
# get_subscription_status()
# ============================================================================

class TestGetSubscriptionStatus:

    def test_not_logged_in_returns_empty_without_request(self, requests_mock, data_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response('UC_A'))

        assert data_client.get_subscription_status({'UC_A'}) == {}
        assert subscription_requests(requests_mock) == []

    @pytest.mark.parametrize('channel_ids', [None, set(), {None, ''}, {123}])
    def test_no_valid_channel_ids_returns_empty_without_request(self, requests_mock,
                                                                logged_in_client, channel_ids):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response('UC_A'))

        assert logged_in_client.get_subscription_status(channel_ids) == {}
        assert subscription_requests(requests_mock) == []

    def test_marks_found_channels_as_subscribed(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response('UC_SUBBED'))

        result = logged_in_client.get_subscription_status({'UC_SUBBED', 'UC_OTHER'})

        assert result == {'UC_SUBBED': True, 'UC_OTHER': False}
        assert len(subscription_requests(requests_mock)) == 1

    def test_second_call_is_served_from_memory(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response('UC_SUBBED'))

        logged_in_client.get_subscription_status({'UC_SUBBED', 'UC_OTHER'})
        result = logged_in_client.get_subscription_status({'UC_SUBBED', 'UC_OTHER'})

        assert result == {'UC_SUBBED': True, 'UC_OTHER': False}
        assert len(subscription_requests(requests_mock)) == 1

    def test_status_persists_in_data_cache_across_clients(self, requests_mock, mock_context,
                                                          logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response('UC_SUBBED'))
        logged_in_client.get_subscription_status({'UC_SUBBED', 'UC_OTHER'})

        new_client = YouTubeDataClient(context=mock_context, configs=CONFIGS)
        new_client.set_access_token({'user': 'mock_user_token', 'tv': 'mock_tv_token'})
        result = new_client.get_subscription_status({'UC_SUBBED', 'UC_OTHER'})

        assert result == {'UC_SUBBED': True, 'UC_OTHER': False}
        assert len(subscription_requests(requests_mock)) == 1

    def test_only_uncached_channels_are_requested(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response())
        logged_in_client.set_subscription_status('UC_KNOWN', True)

        result = logged_in_client.get_subscription_status({'UC_KNOWN', 'UC_NEW'})

        assert result == {'UC_KNOWN': True, 'UC_NEW': False}
        requests = subscription_requests(requests_mock)
        assert len(requests) == 1
        assert query_params(requests[0])['forChannelId'] == ['UC_NEW']

    def test_large_requests_are_batched_by_fifty(self, requests_mock, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response())
        channel_ids = {'UC_{0:03d}'.format(index) for index in range(120)}

        result = logged_in_client.get_subscription_status(channel_ids)

        assert set(result) == channel_ids
        requests = subscription_requests(requests_mock)
        batch_sizes = sorted(
            len(query_params(request)['forChannelId'][0].split(','))
            for request in requests
        )
        assert batch_sizes == [20, 50, 50]
        requested = set()
        for request in requests:
            requested.update(query_params(request)['forChannelId'][0].split(','))
        assert requested == channel_ids

    def test_set_access_token_resets_memory_cache(self, logged_in_client):
        logged_in_client.set_subscription_status('UC_A', True)
        assert logged_in_client._subscription_status == {'UC_A': True}

        logged_in_client.set_access_token({'user': 'mock_user_token', 'tv': 'mock_tv_token'})

        assert logged_in_client._subscription_status is None

    @pytest.mark.xfail(
        strict=True,
        reason='Known bug: an API error payload is treated as a valid response,'
               ' so every channel in the batch is cached as not subscribed for'
               ' a day. Remove this marker once get_subscription_status()'
               ' skips error responses.',
    )
    def test_api_error_is_not_cached_as_unsubscribed(self, requests_mock, mock_context,
                                                     logged_in_client):
        requests_mock.get(
            SUBSCRIPTIONS_URL,
            [
                {'json': load_v3_fixture('quota_exceeded.json'), 'status_code': 403},
                {'json': subscriptions_response('UC_SUBBED')},
            ],
        )

        logged_in_client.get_subscription_status({'UC_SUBBED'})

        cache_key = logged_in_client._get_user_sub_cache_key('UC_SUBBED')
        assert mock_context.get_data_cache().get_item(cache_key) is None

        logged_in_client._subscription_status = None
        result = logged_in_client.get_subscription_status({'UC_SUBBED'})
        assert result == {'UC_SUBBED': True}


# ============================================================================
# set_subscription_status() and cache keys
# ============================================================================

class TestSetSubscriptionStatus:

    def test_updates_memory_and_data_cache(self, requests_mock, mock_context, logged_in_client):
        requests_mock.get(SUBSCRIPTIONS_URL, json=subscriptions_response())

        logged_in_client.set_subscription_status('UC_A', 1)

        assert logged_in_client._subscription_status['UC_A'] is True
        cache_key = logged_in_client._get_user_sub_cache_key('UC_A')
        assert mock_context.get_data_cache().get_item(cache_key) is True
        assert logged_in_client.get_subscription_status({'UC_A'}) == {'UC_A': True}
        assert subscription_requests(requests_mock) == []

    def test_unsubscribe_overrides_cached_status(self, logged_in_client):
        logged_in_client.set_subscription_status('UC_A', True)
        logged_in_client.set_subscription_status('UC_A', False)

        assert logged_in_client.get_subscription_status({'UC_A'}) == {'UC_A': False}

    def test_empty_channel_id_is_ignored(self, logged_in_client):
        logged_in_client.set_subscription_status('', True)
        logged_in_client.set_subscription_status(None, True)

        assert not logged_in_client._subscription_status

    def test_cache_key_is_scoped_to_user_channel(self, logged_in_client):
        key = logged_in_client._get_user_sub_cache_key('UC_TARGET')
        assert key == 'sub_status:{0}:UC_TARGET'.format(logged_in_client.channel_id)

        original_channel_id = logged_in_client.channel_id
        logged_in_client.channel_id = 'UC_OTHER_USER'
        try:
            other_key = logged_in_client._get_user_sub_cache_key('UC_TARGET')
        finally:
            logged_in_client.channel_id = original_channel_id
        assert other_key != key
