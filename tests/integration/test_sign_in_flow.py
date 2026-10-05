# -*- coding: utf-8 -*-
"""
Integration tests for the one screen sign-in flow (yt_login):
- All device codes are requested up front and polled in parallel
- Approval in any order, partial sign-in, cancel, denial, slow_down, expiry
- Offering, opening and declining the sign-in page in a web browser
- Codes shared with the HTTP server and their cleanup
- Sign-in page URLs for this device and the local network
"""
import json

import pytest
import xbmcgui

from youtube_plugin.kodion.constants import ADDON_ID, SIGN_IN_CODES
from youtube_plugin.youtube.client.login_client import YouTubeLoginClient
from youtube_plugin.youtube.helper import yt_login
from youtube_plugin.youtube.youtube_exceptions import LoginException


PENDING = {'error': 'authorization_pending'}
SLOW_DOWN = {'error': 'slow_down'}
PROPERTY = '-'.join((ADDON_ID, SIGN_IN_CODES))
LOCAL_URL = 'http://127.0.0.1:50152/youtube/sign_in?t='
REMOTE_URL = 'http://192.168.1.2:50152/youtube/sign_in?t='


def token(name):
    return {'access_token': 'at-' + name,
            'refresh_token': 'rt-' + name,
            'expires_in': 3599}


class FakeClient(object):
    """Device flow client with scripted token responses per client index"""

    def __init__(self, responses, configured=(0, 1, 2), expires_in=1800):
        self.responses = responses
        self.configured = configured
        self.expires_in = expires_in
        self.polls = []
        self.revoked = []
        self.clock = None

    def internet_available(self):
        return True

    def request_device_and_user_code(self, token_idx):
        if token_idx not in self.configured:
            return None
        return {
            'device_code': 'device-%d' % token_idx,
            'user_code': 'ABCD-000%d' % token_idx,
            'verification_url': 'https://www.google.com/device',
            'interval': 5,
            'expires_in': self.expires_in,
        }

    def request_access_token(self, token_idx, device_code):
        assert device_code == 'device-%d' % token_idx
        self.polls.append((self.clock.now, token_idx))
        responses = self.responses[token_idx]
        response = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(response, Exception):
            raise response
        return response

    def revoke(self, refresh_token):
        self.revoked.append(refresh_token)


class FakeProvider(object):
    FORCE_REFRESH = 'refresh'

    def __init__(self, client):
        self.client = client
        self.reset = []

    def get_client(self, context):
        return self.client

    def reset_client(self, **kwargs):
        self.reset.append(kwargs)


class FakeAccessManager(object):
    def __init__(self, access_tokens=(), refresh_tokens=()):
        self.access_tokens = list(access_tokens)
        self.refresh_tokens = list(refresh_tokens)
        self.saved = None

    def get_access_tokens(self):
        return self.access_tokens, len(self.access_tokens), 1234

    def get_refresh_tokens(self):
        return self.refresh_tokens, len(self.refresh_tokens)

    def update_access_token(self, addon_id, *args, **kwargs):
        self.saved = (args, kwargs)


class FakeFunctionCache(object):
    ONE_MINUTE = 60

    def __init__(self, online=True):
        self.online = online

    def run(self, func, *_args, **_kwargs):
        return self.online and func()


class Clock(object):
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class SignIn(object):
    """Runs yt_login.process(SIGN_IN) against fakes, recording UI calls"""

    def __init__(self, context, monkeypatch, responses,
                 access_manager=None, configured=(0, 1, 2),
                 page_urls=(None, None), confirm=True, browser_opens=True,
                 online=True, on_tick=None, expires_in=1800):
        self.context = context
        self.client = FakeClient(responses, configured, expires_in)
        self.provider = FakeProvider(self.client)
        self.access_manager = access_manager or FakeAccessManager()
        self.clock = self.client.clock = Clock()
        self.on_tick = on_tick
        self.dialogs = []
        self.prompts = []
        self.opened = []
        self.notifications = []
        self.ok_dialogs = []
        self.shared = []

        ui = context.get_ui()
        monkeypatch.setattr(yt_login, 'default_timer', self.clock)
        monkeypatch.setattr(yt_login, '_sign_in_page_urls',
                            lambda _context, _token: tuple(
                                url + _token if url else url
                                for url in page_urls
                            ))
        monkeypatch.setattr(context, 'get_access_manager',
                            lambda: self.access_manager)
        monkeypatch.setattr(context, 'get_function_cache',
                            lambda: FakeFunctionCache(online))
        monkeypatch.setattr(context, 'sleep', self.sleep)
        monkeypatch.setattr(ui, 'on_yes_no_input', self.yes_no)
        monkeypatch.setattr(ui, 'on_ok',
                            lambda *args: self.ok_dialogs.append(args))
        monkeypatch.setattr(ui, 'show_notification',
                            lambda *args, **kwargs:
                            self.notifications.append(args))
        monkeypatch.setattr(ui, 'open_in_browser',
                            lambda url: (self.opened.append(url),
                                         browser_opens)[1])
        create_dialog = ui.create_qr_code_dialog

        def record_dialog(**kwargs):
            dialog = create_dialog(**kwargs)
            self.dialogs.append((dialog, kwargs))
            return dialog

        monkeypatch.setattr(ui, 'create_qr_code_dialog', record_dialog)
        self.confirm = confirm

    def yes_no(self, title, text, nolabel='', yeslabel=''):
        self.prompts.append(text)
        return self.confirm

    def sleep(self, timeout=None):
        self.clock.now += timeout or 0
        data = xbmcgui.Window(10000).getProperty(PROPERTY)
        if data:
            self.shared.append(json.loads(data))
        if self.on_tick:
            self.on_tick(self)
        return False

    def run(self):
        return yt_login.process(yt_login.SIGN_IN, self.provider, self.context)

    @property
    def dialog(self):
        return self.dialogs[-1][0]

    @property
    def dialog_options(self):
        return self.dialogs[-1][1]

    @property
    def saved_tokens(self):
        access_tokens, expiry, refresh_tokens = self.access_manager.saved[0]
        return access_tokens, refresh_tokens

    def polls_for(self, token_idx):
        return [now for now, idx in self.client.polls if idx == token_idx]


@pytest.fixture
def sign_in(mock_context, monkeypatch):
    def factory(responses, **kwargs):
        return SignIn(mock_context, monkeypatch, responses, **kwargs)

    return factory


def press_back(sign_in):
    sign_in.dialog._window.onAction(xbmcgui.Action(92))


class TestPolling:
    def test_all_approved_in_any_order(self, sign_in):
        flow = sign_in({
            0: [PENDING, PENDING, token('tv')],
            1: [token('user')],
            2: [PENDING, PENDING, PENDING, token('vr')],
        })
        signed_in, options = flow.run()

        assert signed_in is True
        assert options == {FakeProvider.FORCE_REFRESH: True}
        assert flow.saved_tokens == (('at-tv', 'at-user', 'at-vr', ''),
                                     ('rt-tv', 'rt-user', 'rt-vr', ''))
        assert flow.provider.reset[-1]['access_tokens'] == {
            'tv': 'at-tv', 'user': 'at-user', 'vr': 'at-vr', 'dev': '',
        }
        # One dialog for every client, closed once all were approved
        assert len(flow.dialogs) == 1
        assert len(flow.dialog_options['entries']) == 3
        assert flow.dialog.is_aborted()

    def test_each_client_polled_at_its_interval(self, sign_in):
        flow = sign_in({
            0: [PENDING] * 3 + [token('tv')],
            1: [token('user')],
            2: [PENDING] * 5 + [token('vr')],
        })
        flow.run()
        for token_idx in (0, 2):
            times = flow.polls_for(token_idx)
            assert all(b - a >= 5 for a, b in zip(times, times[1:])), times
        assert len(flow.polls_for(1)) == 1

    def test_slow_down_increases_interval(self, sign_in):
        flow = sign_in({
            0: [SLOW_DOWN, PENDING, token('tv')],
            1: [token('user')],
            2: [token('vr')],
        })
        flow.run()
        times = flow.polls_for(0)
        assert times[1] - times[0] >= 10
        assert flow.saved_tokens[0] == ('at-tv', 'at-user', 'at-vr', '')

    def test_only_missing_clients_are_shown(self, sign_in):
        flow = sign_in(
            {1: [token('user')], 2: [token('vr')]},
            access_manager=FakeAccessManager(['old-tv', '', ''],
                                             ['old-rt', '', '']),
        )
        flow.run()
        titles = [entry['title'] for entry in flow.dialog_options['entries']]
        assert 'YouTube TV' not in titles and 'YouTube VR' in titles
        assert flow.saved_tokens[0] == ('old-tv', 'at-user', 'at-vr', '')

    def test_unconfigured_clients_are_skipped(self, sign_in):
        flow = sign_in({0: [token('tv')]}, configured=(0,))
        flow.run()
        assert len(flow.dialog_options['entries']) == 1
        assert flow.saved_tokens[0] == ('at-tv', '', '', '')

    def test_nothing_to_sign_in(self, sign_in):
        flow = sign_in({}, configured=())
        signed_in, _ = flow.run()
        assert signed_in is True
        assert flow.dialogs == []
        assert flow.saved_tokens[0] == ('', '', '', '')

    def test_offline(self, sign_in):
        flow = sign_in({0: [token('tv')]}, online=False)
        signed_in, _ = flow.run()
        assert signed_in is False
        assert flow.dialogs == []
        assert flow.access_manager.saved is None

    def test_cancel_keeps_approved_clients(self, sign_in):
        flow = sign_in({0: [token('tv')], 1: [PENDING], 2: [PENDING]},
                       on_tick=press_back)
        signed_in, _ = flow.run()
        assert signed_in is True
        assert flow.saved_tokens == (('at-tv', '', '', ''),
                                     ('rt-tv', '', '', ''))

    def test_codes_expire(self, sign_in):
        flow = sign_in({0: [PENDING], 1: [PENDING], 2: [PENDING]},
                       expires_in=60)
        flow.run()
        assert flow.clock.now >= 1000 + 60
        assert flow.saved_tokens[0] == ('', '', '', '')
        assert flow.dialog.is_aborted()

    def test_denied_signs_out(self, sign_in):
        flow = sign_in({
            0: [PENDING, LoginException('access_denied')],
            1: [PENDING],
            2: [PENDING],
        })
        signed_in, options = flow.run()
        assert signed_in is False
        assert options == {FakeProvider.FORCE_REFRESH: False}
        assert len(flow.ok_dialogs) == 1
        assert flow.access_manager.saved[1]['access_token'] == ''
        assert flow.dialog.is_aborted()

    def test_slow_down_is_not_a_login_error(self):
        exc = LoginException('slow_down')
        exc.json_data = {'error': 'slow_down'}
        response = YouTubeLoginClient._login_error_hook(exc=exc)
        assert response[3] == {'error': 'slow_down'}
        assert response[4] is False


class TestDialog:
    def test_entries(self, sign_in, mock_context):
        flow = sign_in({0: [token('tv')], 1: [token('user')],
                        2: [token('vr')]})
        flow.run()
        entries = flow.dialog_options['entries']
        assert [entry['title'] for entry in entries] == [
            'YouTube TV', mock_context.localize('sign.client.user'),
            'YouTube VR',
        ]
        assert entries[0]['qr'] == (
            'https://www.google.com/device?user_code=ABCD-0000'
        )
        assert entries[0]['lines'] == ('google.com/device',
                                       '[B]ABCD-0000[/B]')

    def test_approved_status_and_footer(self, sign_in, mock_context):
        flow = sign_in({0: [token('tv')], 1: [PENDING, token('user')],
                        2: [token('vr')]})
        flow.run()
        approved = mock_context.localize('sign.status.approved')
        assert all(approved in label.getLabel()
                   for label in flow.dialog._status_labels)


class TestBrowser:
    def test_no_page_no_prompt(self, sign_in, mock_context):
        flow = sign_in({0: [token('tv')]}, configured=(0,))
        flow.run()
        assert flow.prompts == [] and flow.opened == []
        assert flow.dialog_options['message'] == (
            mock_context.localize('sign.qr.text')
        )
        assert 'qr' not in flow.dialog_options

    def test_opened_in_browser(self, sign_in, mock_context):
        flow = sign_in({0: [token('tv')]}, configured=(0,),
                       page_urls=(LOCAL_URL, REMOTE_URL))
        flow.run()
        assert flow.prompts == [mock_context.localize('sign.browser.confirm')]
        assert len(flow.opened) == 1
        assert flow.opened[0].startswith(LOCAL_URL)
        assert flow.dialog_options['message'] == (
            mock_context.localize('sign.qr.browser_text')
        )
        # Phone page offered as an alternative
        assert flow.dialog_options['qr'].startswith(REMOTE_URL)
        assert flow.dialog_options['qr_lines'] == ('192.168.1.2:50152',)

    def test_declined(self, sign_in, mock_context):
        flow = sign_in({0: [token('tv')]}, configured=(0,),
                       page_urls=(LOCAL_URL, REMOTE_URL), confirm=False)
        flow.run()
        assert len(flow.prompts) == 1 and flow.opened == []
        assert flow.dialog_options['message'] == (
            mock_context.localize('sign.qr.page_text')
        )

    def test_no_browser_available(self, sign_in, mock_context):
        flow = sign_in({0: [token('tv')]}, configured=(0,),
                       page_urls=(LOCAL_URL, None), browser_opens=False)
        flow.run()
        assert len(flow.opened) == 1
        assert flow.notifications == [
            (mock_context.localize('sign.browser.failed'),)
        ]
        assert flow.dialog_options['message'] == (
            mock_context.localize('sign.qr.text')
        )
        assert 'qr' not in flow.dialog_options


class TestSharedCodes:
    def test_statuses_shared_while_waiting(self, sign_in):
        flow = sign_in({
            0: [PENDING, PENDING, token('tv')],
            1: [token('user')],
            2: [PENDING] * 4 + [token('vr')],
        }, page_urls=(LOCAL_URL, None))
        flow.run()

        first = flow.shared[0]
        assert len(first['token']) == 16
        assert [entry['code'] for entry in first['entries']] == [
            'ABCD-0000', 'ABCD-0001', 'ABCD-0002',
        ]
        assert first['entries'][0]['url'] == (
            'https://www.google.com/device?user_code=ABCD-0000'
        )
        seen = [[entry['status'] for entry in shared['entries']]
                for shared in flow.shared]
        assert seen[0] == ['pending', 'approved', 'pending']
        assert ['approved', 'approved', 'pending'] in seen
        assert flow.opened[0] == LOCAL_URL + first['token']

    def test_final_state_kept_briefly_after_success(self, sign_in):
        flow = sign_in({0: [token('tv')], 1: [token('user')],
                        2: [token('vr')]})
        flow.run()
        shared = json.loads(xbmcgui.Window(10000).getProperty(PROPERTY))
        assert [entry['status'] for entry in shared['entries']] == (
            ['approved'] * 3
        )
        assert shared['expires'] > 0

    @pytest.mark.parametrize('responses,on_tick', (
        ({0: [token('tv')], 1: [PENDING], 2: [PENDING]}, press_back),
        ({0: [PENDING], 1: [PENDING], 2: [PENDING]}, None),
    ), ids=('cancelled', 'expired'))
    def test_cleared_when_not_completed(self, sign_in, responses, on_tick):
        flow = sign_in(responses, on_tick=on_tick, expires_in=60)
        flow.run()
        assert flow.shared, 'codes must be shared while waiting'
        assert xbmcgui.Window(10000).getProperty(PROPERTY) == ''

    def test_cleared_when_denied(self, sign_in):
        flow = sign_in({0: [LoginException('access_denied')],
                        1: [PENDING], 2: [PENDING]})
        flow.run()
        assert xbmcgui.Window(10000).getProperty(PROPERTY) == ''


class TestSignInPageUrls:
    @pytest.fixture
    def urls(self, mock_context, monkeypatch):
        def factory(listen, server_running=True,
                    status_url='http://{host}:50152/youtube/sign_in?t=abc'):
            settings = mock_context.get_settings()
            monkeypatch.setattr(settings, 'httpd_listen', lambda: listen)
            monkeypatch.setattr(mock_context, 'ipc_exec',
                                lambda *args, **kwargs: server_running)
            host = {'0.0.0.0': '192.168.1.2'}.get(listen, listen)
            monkeypatch.setattr(
                yt_login, 'httpd_status',
                lambda context, path=None, query=None: (
                    status_url.format(host=host) if status_url else False
                ),
            )
            return yt_login._sign_in_page_urls(mock_context, 'abc')

        return factory

    def test_server_not_running(self, urls):
        assert urls('0.0.0.0', server_running=False) == (None, None)

    def test_server_not_responding(self, urls):
        assert urls('0.0.0.0', status_url=None) == (None, None)

    def test_loopback_only(self, urls):
        assert urls('127.0.0.1') == (
            'http://127.0.0.1:50152/youtube/sign_in?t=abc', None,
        )

    def test_all_interfaces(self, urls):
        # Loopback is used locally, as browsers treat it as a secure context
        assert urls('0.0.0.0') == (
            'http://127.0.0.1:50152/youtube/sign_in?t=abc',
            'http://192.168.1.2:50152/youtube/sign_in?t=abc',
        )

    def test_specific_address(self, urls):
        assert urls('192.168.1.2') == (
            'http://192.168.1.2:50152/youtube/sign_in?t=abc',
            'http://192.168.1.2:50152/youtube/sign_in?t=abc',
        )
