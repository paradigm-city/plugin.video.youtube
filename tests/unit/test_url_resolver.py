# -*- coding: utf-8 -*-
"""
Unit tests for YouTube URL resolving logic.
"""
from urllib.parse import parse_qsl, urlsplit

import pytest

from youtube_plugin.youtube.helper.url_resolver import (
    CommonResolver,
    UrlResolver,
    YouTubeResolver,
)


class MockResponse(object):
    def __init__(self, url, status_code=200, text=''):
        self.url = url
        self.status_code = status_code
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def yt_resolver(mock_context):
    return YouTubeResolver(context=mock_context)


@pytest.fixture
def common_resolver(mock_context):
    return CommonResolver(context=mock_context)


# =========================================================================
# YouTubeResolver.supports_url
# =========================================================================

@pytest.mark.parametrize('url,expected_method', [
    ('https://www.youtube.com/@mkbhd', 'GET'),
    ('https://youtube.com/c/PewDiePie', 'GET'),
    ('https://m.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw', 'GET'),
    ('https://www.youtube.com/clip/Ugkx_test_clip_123', 'GET'),
    ('https://www.youtube.com/user/TEDtalksDirector', 'GET'),
    ('https://www.youtube.com/shorts/dQw4w9WgXcQ', 'HEAD'),
    ('https://www.youtube.com/live/dQw4w9WgXcQ', 'HEAD'),
    ('https://www.youtube.com/embed/dQw4w9WgXcQ', 'HEAD'),
    ('https://www.youtube.com/redirect?q=https://example.com', 'HEAD'),
    ('https://www.youtube.com/supported_browsers?next_url=test', 'HEAD'),
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'HEAD'),
    ('https://music.youtube.com/watch?v=dQw4w9WgXcQ', 'GET'),
    ('https://www.youtube.com/LinusTechTips', 'GET'),
])
def test_youtube_resolver_supports_valid_urls(yt_resolver, url, expected_method):
    components = urlsplit(url)
    assert yt_resolver.supports_url(url, components) == expected_method


@pytest.mark.parametrize('url', [
    'https://vimeo.com/12345678',
    'https://dailymotion.com/video/x123',
    'https://google.com/search?q=test',
    'https://example.com/video.mp4',
])
def test_youtube_resolver_rejects_non_youtube_urls(yt_resolver, url):
    components = urlsplit(url)
    assert yt_resolver.supports_url(url, components) is False


# =========================================================================
# YouTubeResolver.resolve (Redirect & Query Rewriting)
# =========================================================================

def test_resolve_redirect_query_parameter(yt_resolver, monkeypatch):
    target = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    redirect_url = f'https://www.youtube.com/redirect?q={target}&event=channel_description'
    components = urlsplit(redirect_url)
    monkeypatch.setattr(yt_resolver, 'request', lambda *args, **kwargs: MockResponse(target, 200))
    resolved = yt_resolver.resolve(redirect_url, components, method='HEAD')
    assert resolved == target



def test_resolve_supported_browsers_wrapper(yt_resolver):
    wrapper_url = (
        'https://www.youtube.com/supported_browsers'
        '?next_url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ'
        '&feature=youtu.be'
    )
    components = urlsplit(wrapper_url)
    resolved = yt_resolver.resolve(wrapper_url, components, method='HEAD')
    resolved_comp = urlsplit(resolved)
    params = dict(parse_qsl(resolved_comp.query))

    assert resolved_comp.scheme == 'https'
    assert resolved_comp.netloc == 'www.youtube.com'
    assert resolved_comp.path == '/watch'
    assert params.get('v') == 'dQw4w9WgXcQ'
    assert params.get('feature') == 'youtu.be'


def test_resolve_clip_url_parsing(yt_resolver, monkeypatch):
    mock_html = (
        '<html>'
        '<meta property="og:video:url" content="https://www.youtube.com/watch?v=sample123">'
        '<div>"clipConfig":{"test": 1}</div>'
        '<div>"startTimeMs":"15000"</div>'
        '<div>"endTimeMs":"45000"</div>'
        '</html>'
    )
    clip_url = 'https://www.youtube.com/clip/Ugkx_sample_clip'

    monkeypatch.setattr(
        yt_resolver,
        'request',
        lambda *args, **kwargs: MockResponse(clip_url, 200, mock_html)
    )

    components = urlsplit(clip_url)
    resolved = yt_resolver.resolve(clip_url, components, method='GET')
    resolved_comp = urlsplit(resolved)
    params = dict(parse_qsl(resolved_comp.query))

    assert params.get('v') == 'sample123'
    assert params.get('clip') == 'True'
    assert params.get('start') == '15.0'
    assert params.get('end') == '45.0'


def test_resolve_channel_metadata_og_url(yt_resolver, monkeypatch):
    mock_html = (
        '<html>'
        '<meta property="og:url" content="https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw">'
        '</html>'
    )
    handle_url = 'https://www.youtube.com/@Google'

    monkeypatch.setattr(
        yt_resolver,
        'request',
        lambda *args, **kwargs: MockResponse(handle_url, 200, mock_html)
    )

    components = urlsplit(handle_url)
    resolved = yt_resolver.resolve(handle_url, components, method='GET')
    assert resolved == 'https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw'


# =========================================================================
# CommonResolver
# =========================================================================

def test_common_resolver_rejects_youtube(common_resolver):
    url = 'https://www.youtube.com/watch?v=123'
    assert common_resolver.supports_url(url, urlsplit(url)) is False


def test_common_resolver_supports_external_urls(common_resolver):
    url = 'https://bit.ly/3xyz123'
    assert common_resolver.supports_url(url, urlsplit(url)) == 'HEAD'


def test_common_resolver_follows_redirects(common_resolver, monkeypatch):
    source_url = 'https://bit.ly/3xyz123'
    destination_url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

    monkeypatch.setattr(
        common_resolver,
        'request',
        lambda *args, **kwargs: MockResponse(destination_url, 200)
    )

    resolved = common_resolver.resolve(source_url, urlsplit(source_url))
    assert resolved == destination_url
