# -*- coding: utf-8 -*-
"""
Live smoke tests probing YouTube's real Innertube streaming endpoints (opt-in).
"""
import pytest

from youtube_plugin.youtube.client.player_client import YouTubePlayerClient


pytestmark = pytest.mark.live


def test_live_innertube_stream_extraction(mock_context):
    """Verify live Innertube player endpoint returns playable streams for public video."""
    client = YouTubePlayerClient(context=mock_context)
    # Using 'jNQXAC9IVRw' (first YouTube video 'Me at the zoo')
    streams, item = client.load_stream_info('jNQXAC9IVRw')

    assert item is not None
    assert 'Me at the zoo' in item.get('snippet', {}).get('title', '')

    stream_list = list(streams)
    assert len(stream_list) > 0

    first_stream = stream_list[0]
    assert 'url' in first_stream
    assert 'googlevideo.com' in first_stream['url']
    assert first_stream.get('container') in ('mp4', 'webm', 'hls', 'mpd')


def test_live_innertube_music_video_streams(mock_context):
    """Verify live Innertube returns stream data for music video without cipher crash."""
    client = YouTubePlayerClient(context=mock_context)
    # 'dQw4w9WgXcQ' (Rick Astley)
    streams, item = client.load_stream_info('dQw4w9WgXcQ')

    assert item is not None
    assert 'Rick Astley' in item.get('snippet', {}).get('title', '')
    stream_list = list(streams)
    assert len(stream_list) > 0
    assert any('googlevideo.com' in s.get('url', '') for s in stream_list)
