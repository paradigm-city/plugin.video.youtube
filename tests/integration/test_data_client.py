# -*- coding: utf-8 -*-
"""
Integration tests for YouTubeDataClient using mocked HTTP responses.
"""
import json
import os
import pytest

from youtube_plugin.youtube.client.data_client import YouTubeDataClient


FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'v3_api'))


def load_v3_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def clear_request_cache(mock_context):
    mock_context.get_requests_cache().clear()
    yield
    mock_context.get_requests_cache().clear()


@pytest.fixture
def data_client(mock_context):
    configs = {
        'user': {
            'key': 'AIzaSy_TEST_API_KEY_1234567890',
            'id': 'test-client-id.apps.googleusercontent.com',
            'secret': 'test-client-secret',
        }
    }
    client = YouTubeDataClient(context=mock_context, configs=configs)
    return client


def test_get_videos_metadata_parsing(requests_mock, data_client):
    payload = load_v3_fixture('video_details.json')
    requests_mock.get(
        'https://www.googleapis.com/youtube/v3/videos',
        json=payload,
    )

    result = data_client.get_videos('dQw4w9WgXcQ')
    assert result is not None
    assert 'items' in result
    assert len(result['items']) == 1

    video = result['items'][0]
    assert video['id'] == 'dQw4w9WgXcQ'
    assert video['snippet']['title'] == 'Rick Astley - Never Gonna Give You Up (Official Music Video)'
    assert video['contentDetails']['duration'] == 'PT3M33S'
    assert video['statistics']['viewCount'] == '1500000000'


def test_search_results_with_pagination(requests_mock, data_client):
    payload = load_v3_fixture('search_results.json')
    requests_mock.get(
        'https://www.googleapis.com/youtube/v3/search',
        json=payload,
    )

    result = data_client.search(q='Rick Astley')
    assert result is not None
    assert result.get('nextPageToken') == 'CDIQAA'
    assert len(result.get('items', [])) == 2

    # First item is a video
    item_0 = result['items'][0]
    assert item_0['id']['kind'] == 'youtube#video'
    assert item_0['id']['videoId'] == 'dQw4w9WgXcQ'

    # Second item is a channel
    item_1 = result['items'][1]
    assert item_1['id']['kind'] == 'youtube#channel'
    assert item_1['id']['channelId'] == 'UC_x5XG1OV2P6uZZ5FSM9Ttw'


def test_get_subscriptions_list(requests_mock, data_client):
    payload = load_v3_fixture('subscriptions_list.json')
    requests_mock.get(
        'https://www.googleapis.com/youtube/v3/subscriptions',
        json=payload,
    )

    result = data_client.get_subscription(channel_id='UC_x5XG1OV2P6uZZ5FSM9Ttw')
    assert result is not None
    assert len(result.get('items', [])) == 2

    channels = [item['snippet']['resourceId']['channelId'] for item in result['items']]
    assert 'UC_x5XG1OV2P6uZZ5FSM9Ttw' in channels
    assert 'UCuAXFkgsw1L7xaCfnd5JJOw' in channels


def test_quota_exceeded_error_handling(requests_mock, data_client):
    payload = load_v3_fixture('quota_exceeded.json')
    requests_mock.get(
        'https://www.googleapis.com/youtube/v3/videos',
        status_code=403,
        json=payload,
    )

    result = data_client.get_videos('quota_test_unique_video')
    assert result is not None
    assert 'error' in result
    assert result['error']['errors'][0]['reason'] == 'quotaExceeded'


def test_v3_api_unavailable_without_key(mock_context):
    client = YouTubeDataClient(context=mock_context, configs={'user': {'key': ''}})
    assert client.v3_api_available() is False

    result = client.api_request(method='GET', path='videos')
    assert result is None or result == {}

