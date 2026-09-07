# -*- coding: utf-8 -*-
"""
    Integration tests for YouTubeLoginClient:
    - Token conversion and login state tracking
    - OAuth2 device code flow (request device/user code, poll token)
    - Token refresh and invalid_grant handling
    - Token revocation
"""

import pytest

from resources.lib.youtube_plugin.youtube.client.login_client import YouTubeLoginClient
from resources.lib.youtube_plugin.youtube.youtube_exceptions import InvalidGrant


@pytest.fixture(autouse=True)
def reset_login_client_state():
    """Ensure clean class-level state for YouTubeLoginClient across tests."""
    YouTubeLoginClient._configs = {
        'dev': {},
        'user': {},
        'tv': {},
        'vr': {},
    }
    YouTubeLoginClient._access_tokens = {
        'dev': None,
        'user': None,
        'tv': None,
        'vr': None,
    }
    YouTubeLoginClient._initialised = False
    YouTubeLoginClient._logged_in = False
    yield
    YouTubeLoginClient._configs = {
        'dev': {},
        'user': {},
        'tv': {},
        'vr': {},
    }
    YouTubeLoginClient._access_tokens = {
        'dev': None,
        'user': None,
        'tv': None,
        'vr': None,
    }
    YouTubeLoginClient._initialised = False
    YouTubeLoginClient._logged_in = False


@pytest.fixture
def login_client(mock_context):
    configs = {
        'user': {
            'key': 'AIzaSy_TEST_USER_KEY',
            'id': 'test-user-id.apps.googleusercontent.com',
            'secret': 'test-user-secret',
        },
        'tv': {
            'key': 'AIzaSy_TEST_TV_KEY',
            'id': 'test-tv-id.apps.googleusercontent.com',
            'secret': 'test-tv-secret',
        },
    }
    return YouTubeLoginClient(context=mock_context, configs=configs)


class TestLoginClientTokenState:
    """Tests for token storage, conversion, and login status calculation."""

    def test_init_configs(self, login_client):
        assert login_client.initialised is True
        assert YouTubeLoginClient._configs['user']['id'] == 'test-user-id.apps.googleusercontent.com'

    def test_convert_access_tokens_list_to_dict(self):
        tokens_list = ['tv_tok', 'user_tok', 'vr_tok', 'dev_tok']
        as_dict = YouTubeLoginClient.convert_access_tokens(tokens_list, to_dict=True)
        assert as_dict == {
            'tv': 'tv_tok',
            'user': 'user_tok',
            'vr': 'vr_tok',
            'dev': 'dev_tok',
        }

    def test_convert_access_tokens_dict_to_list(self):
        tokens_dict = {
            'tv': 'tv_tok',
            'user': 'user_tok',
        }
        as_list = YouTubeLoginClient.convert_access_tokens(tokens_dict, to_list=True)
        assert as_list == ['tv_tok', 'user_tok', None, None]

    def test_set_access_token_fully_logged_in(self, login_client):
        login_client.set_access_token({
            'tv': 'token_tv',
            'user': 'token_user',
            'vr': 'token_vr',
        })
        assert login_client.logged_in == 'fully'

    def test_set_access_token_partially_logged_in(self, login_client):
        login_client.set_access_token({
            'user': 'token_user',
        })
        assert login_client.logged_in == 'partially'

    def test_set_access_token_empty_logged_out(self, login_client):
        login_client.set_access_token(None)
        assert login_client.logged_in is False


class TestOAuth2DeviceFlow:
    """Tests for OAuth2 Device Flow request and polling."""

    def test_request_device_and_user_code_success(self, requests_mock, login_client):
        user_token_type = YouTubeLoginClient.TOKEN_TYPES['user']  # 1
        mock_response = {
            'device_code': 'device_code_xyz123',
            'user_code': 'ABCD-WXYZ',
            'verification_url': 'https://www.google.com/device',
            'expires_in': 1800,
            'interval': 5,
        }
        requests_mock.post(
            YouTubeLoginClient.DEVICE_CODE_URL,
            json=mock_response,
        )

        result = login_client.request_device_and_user_code(user_token_type)
        assert result is not None
        assert result['device_code'] == 'device_code_xyz123'
        assert result['user_code'] == 'ABCD-WXYZ'
        assert result['verification_url'] == 'https://www.google.com/device'

        # Verify POST payload sent
        last_request = requests_mock.last_request
        assert 'client_id=test-user-id.apps.googleusercontent.com' in last_request.text
        assert 'scope=' in last_request.text

    def test_request_device_and_user_code_missing_client(self, login_client):
        # 'dev' client was not configured with an ID
        dev_token_type = YouTubeLoginClient.TOKEN_TYPES['dev']  # 3
        result = login_client.request_device_and_user_code(dev_token_type)
        assert result is None


class TestOAuth2TokenExchange:
    """Tests for token acquisition, refresh, and error states."""

    def test_request_access_token_success(self, requests_mock, login_client):
        user_token_type = YouTubeLoginClient.TOKEN_TYPES['user']
        mock_response = {
            'access_token': 'ya29.mock_access_token_123',
            'token_type': 'Bearer',
            'expires_in': 3600,
            'refresh_token': '1//mock_refresh_token_456',
        }
        requests_mock.post(
            YouTubeLoginClient.TOKEN_URL,
            json=mock_response,
        )

        result = login_client.request_access_token(user_token_type, code='device_code_xyz123')
        assert result is not None
        assert result['access_token'] == 'ya29.mock_access_token_123'
        assert result['refresh_token'] == '1//mock_refresh_token_456'

        last_request = requests_mock.last_request
        assert 'grant_type=http%3A%2F%2Foauth.net%2Fgrant_type%2Fdevice%2F1.0' in last_request.text
        assert 'code=device_code_xyz123' in last_request.text

    def test_request_access_token_authorization_pending(self, requests_mock, login_client):
        user_token_type = YouTubeLoginClient.TOKEN_TYPES['user']
        mock_response = {
            'error': 'authorization_pending',
        }
        requests_mock.post(
            YouTubeLoginClient.TOKEN_URL,
            status_code=400,
            json=mock_response,
        )

        # authorization_pending should return the error JSON without raising an exception
        result = login_client.request_access_token(user_token_type, code='device_code_xyz123')
        assert result is not None
        assert result.get('error') == 'authorization_pending'

    def test_refresh_token_success(self, requests_mock, login_client):
        user_token_type = YouTubeLoginClient.TOKEN_TYPES['user']
        mock_response = {
            'access_token': 'ya29.new_refreshed_token',
            'token_type': 'Bearer',
            'expires_in': 3600,
        }
        requests_mock.post(
            YouTubeLoginClient.TOKEN_URL,
            json=mock_response,
        )

        result = login_client.refresh_token(user_token_type, refresh_token='existing_refresh_token')
        assert result is not None
        assert result['access_token'] == 'ya29.new_refreshed_token'

        last_request = requests_mock.last_request
        assert 'grant_type=refresh_token' in last_request.text
        assert 'refresh_token=existing_refresh_token' in last_request.text

    def test_refresh_token_invalid_grant_raises(self, requests_mock, login_client):
        user_token_type = YouTubeLoginClient.TOKEN_TYPES['user']
        mock_response = {
            'error': 'invalid_grant',
            'code': 400,
            'error_description': 'Token has been expired or revoked.',
        }
        requests_mock.post(
            YouTubeLoginClient.TOKEN_URL,
            status_code=400,
            json=mock_response,
        )

        with pytest.raises(InvalidGrant):
            login_client.refresh_token(user_token_type, refresh_token='revoked_refresh_token')

    def test_revoke_token_success(self, requests_mock, login_client):
        requests_mock.post(
            YouTubeLoginClient.REVOKE_URL,
            status_code=200,
            json={},
        )

        login_client.revoke(refresh_token='token_to_revoke')
        last_request = requests_mock.last_request
        assert 'token=token_to_revoke' in last_request.text
