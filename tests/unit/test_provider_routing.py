# -*- coding: utf-8 -*-
"""
Unit tests for Provider route matching, dispatching, and error handling.
"""
import pytest

from youtube_plugin.kodion.context.xbmc.xbmc_context import XbmcContext
from youtube_plugin.kodion.exceptions import KodionException
from youtube_plugin.kodion.items.uri_item import UriItem
from youtube_plugin.youtube.provider import Provider


@pytest.fixture
def provider():
    return Provider()


def test_provider_root_route_navigation(provider, mock_context):
    mock_context.get_settings().set_bool(mock_context.get_settings().SHOW_SIGN_IN, True)
    mock_context._path = '/'

    result, options = provider.navigate(mock_context)
    assert isinstance(result, list)
    assert len(result) >= 1

    # Verify sign-in item is present in root menu
    first_item = result[0]
    assert 'sign/in' in first_item.get_uri()
    assert options.get(provider.CACHE_TO_DISC) is False


def test_provider_play_route_dispatch(provider):
    ctx = XbmcContext(path='/play/', params={'video_id': 'sample_play_123'})
    result, options = provider.navigate(ctx)

    assert isinstance(result, UriItem)
    assert 'PlayMedia' in result.get_uri()
    assert 'video_id=sample_play_123' in result.get_uri()


def test_provider_video_rate_route_validation(provider):
    # Route to /video/rate/ without video_id should raise KodionException
    ctx = XbmcContext(path='/video/rate/')
    with pytest.raises(KodionException) as exc_info:
        provider.navigate(ctx)

    assert 'missing video_id' in str(exc_info.value)


def test_provider_video_more_route_dispatch(provider):
    # Route to /video/more/ with video_id and item_name opens contextual selector
    ctx = XbmcContext(path='/video/more/', params={'video_id': 'sample_123', 'item_name': 'Sample Title'})
    result, options = provider.navigate(ctx)
    # Returns True/False indicating completion of the dialog selection
    assert isinstance(result, bool)


def test_provider_subscriptions_route_not_logged_in_redirects(provider):
    # Subscriptions list without authentication redirects to sign in
    ctx = XbmcContext(path='/subscriptions/list/')
    result, options = provider.navigate(ctx)

    assert isinstance(result, UriItem)
    assert 'sign/in' in result.get_uri()


def test_provider_search_route_dispatch(provider, monkeypatch):
    called = []

    def mock_on_search_run(context, query=None):
        called.append(query)
        return ['search_result_item'], {'custom_opt': True}

    monkeypatch.setattr(provider, 'on_search_run', mock_on_search_run)

    ctx = XbmcContext(path='/search/query/', params={'q': 'kodi youtube'})
    result, options = provider.navigate(ctx)

    assert len(called) == 1
    assert called[0] == 'kodi youtube'
    assert result == ['search_result_item']
    assert options.get('custom_opt') is True


def test_provider_unknown_route_raises_kodion_exception(provider):
    ctx = XbmcContext(path='/nonexistent/unknown/endpoint/')
    with pytest.raises(KodionException) as exc_info:
        provider.navigate(ctx)

    assert 'Mapping for path "/nonexistent/unknown/endpoint/" not found' in str(exc_info.value)

