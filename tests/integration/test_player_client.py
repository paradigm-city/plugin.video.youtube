# -*- coding: utf-8 -*-
"""
Integration tests for YouTubePlayerClient and stream/caption extraction using mocked responses.
"""
import json
import os
import pytest

from youtube_plugin.youtube.client.player_client import YouTubePlayerClient
from youtube_plugin.youtube.client.subtitles import Subtitles


FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'innertube'))


def load_innertube_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def player_client(mock_context):
    client = YouTubePlayerClient(context=mock_context)
    return client


def test_player_load_stream_info_progressive(requests_mock, player_client):
    payload = load_innertube_fixture('player_response.json')
    requests_mock.post(
        'https://www.youtube.com/youtubei/v1/player',
        json=payload,
    )

    streams, item = player_client.load_stream_info('dQw4w9WgXcQ')
    assert item is not None
    assert item['snippet']['title'] == 'Rick Astley - Never Gonna Give You Up'

    stream_list = list(streams)
    assert len(stream_list) >= 1

    stream = stream_list[0]
    assert stream['container'] == 'mp4'
    assert stream['video']['height'] == 360
    assert stream['video']['codec'] == 'h.264'
    assert stream['audio']['codec'] == 'aac'
    assert 'googlevideo.com/videoplayback' in stream['url']


def test_get_stream_format_definitions(player_client):
    # Test progressive format (itag 18 - 360p)
    fmt18 = player_client._get_stream_format('18')
    assert fmt18 is not None
    assert fmt18['container'] == 'mp4'
    assert fmt18['video']['height'] == 360
    assert fmt18['video']['codec'] == 'h.264'
    assert fmt18['audio']['codec'] == 'aac'

    # Test adaptive video format (itag 137 - 1080p)
    fmt137 = player_client._get_stream_format('137', title='1080p')
    assert fmt137 is not None
    assert fmt137['video']['height'] == 1080
    assert fmt137['video']['codec'] == 'h.264'


    # Test adaptive audio format (itag 140 - 128k AAC)
    fmt140 = player_client._get_stream_format('140', title='Audio')
    assert fmt140 is not None
    assert fmt140['audio']['codec'] == 'aac'
    assert fmt140['audio']['bitrate'] == 128


def test_subtitles_caption_tracks_extraction(mock_context):
    payload = load_innertube_fixture('player_response.json')
    captions = payload['captions']

    subs = Subtitles(mock_context, video_id='dQw4w9WgXcQ')
    subs.load(captions, headers={})

    assert len(subs.caption_tracks) == 2
    lang_codes = [track['languageCode'] for track in subs.caption_tracks]
    assert 'en' in lang_codes
    assert 'de' in lang_codes
