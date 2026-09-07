# -*- coding: utf-8 -*-
"""
Integration tests for YouTubeDataClient using mocked HTTP responses:
- Core metadata, search, and quota error handling
- Playlist and playlist item CRUD operations
- Channel identification, handle resolution, and sections
- Subscriptions listing and mutations
- Feeds, discovery, video categories, and live events
- Video ratings and watch history reporting
- Comments and localization endpoints
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
    """Unauthenticated client with valid API key."""
    configs = {
        'user': {
            'key': 'AIzaSy_TEST_API_KEY_1234567890',
            'id': 'test-client-id.apps.googleusercontent.com',
            'secret': 'test-client-secret',
        }
    }
    client = YouTubeDataClient(context=mock_context, configs=configs)
    return client


@pytest.fixture
def logged_in_client(mock_context, requests_mock):
    """Authenticated client with OAuth2 access tokens."""
    configs = {
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
    requests_mock.get(
        'https://www.googleapis.com/youtube/v3/channels',
        json={'items': [{'id': 'UC_MINE_CHANNEL_ID'}]},
    )
    client = YouTubeDataClient(context=mock_context, configs=configs)
    client.set_access_token({'user': 'mock_user_token', 'tv': 'mock_tv_token'})
    return client


# ============================================================================
# Core Queries & Error Resilience
# ============================================================================

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


# ============================================================================
# Playlist Management & Mutations (Cluster A)
# ============================================================================

class TestPlaylistsManagement:
    """Integration tests for playlist queries, creation, and video management."""

    def test_get_playlists_by_id(self, requests_mock, data_client):
        payload = load_v3_fixture('playlists.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/playlists',
            json=payload,
        )

        result = data_client.get_playlists('PL_TEST_PLAYLIST_1')
        assert result is not None
        assert len(result.get('items', [])) == 2
        assert result['items'][0]['id'] == 'PL_TEST_PLAYLIST_1'
        assert 'id=PL_TEST_PLAYLIST_1' in requests_mock.last_request.url

    def test_get_playlists_of_channel_mine(self, requests_mock, logged_in_client):
        payload = load_v3_fixture('playlists.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/playlists',
            json=payload,
        )

        result = logged_in_client.get_playlists_of_channel('mine')
        assert result is not None
        assert requests_mock.last_request.qs['mine'] == ['true']

    def test_get_playlist_items(self, requests_mock, data_client):
        payload = load_v3_fixture('playlist_items.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            json=payload,
        )

        result = data_client.get_playlist_items('PL_TEST_PLAYLIST_1')
        assert result is not None
        assert len(result.get('items', [])) == 2
        assert result['items'][0]['snippet']['resourceId']['videoId'] == 'dQw4w9WgXcQ'
        assert 'playlistId=PL_TEST_PLAYLIST_1' in requests_mock.last_request.url

    def test_get_playlist_item_id_of_video_id_found(self, requests_mock, data_client):
        payload = load_v3_fixture('playlist_items.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            json=payload,
        )

        item_id = data_client.get_playlist_item_id_of_video_id('PL_TEST', 'dQw4w9WgXcQ')
        assert item_id == 'PLI_ITEM_ID_1'

    def test_get_playlist_item_id_of_video_id_not_found(self, requests_mock, data_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            json={'items': []},
        )

        item_id = data_client.get_playlist_item_id_of_video_id('PL_TEST', 'nonexistent_vid')
        assert item_id is None

    def test_create_playlist(self, requests_mock, logged_in_client):
        created_payload = {
            'id': 'PL_NEW_1',
            'snippet': {'title': 'New Test Playlist'},
            'status': {'privacyStatus': 'private'},
        }
        requests_mock.post(
            'https://www.googleapis.com/youtube/v3/playlists',
            json=created_payload,
        )

        result = logged_in_client.create_playlist('New Test Playlist', privacy_status='private')
        assert result['id'] == 'PL_NEW_1'
        body = requests_mock.last_request.json()
        assert body['snippet']['title'] == 'New Test Playlist'
        assert body['status']['privacyStatus'] == 'private'

    def test_rename_playlist(self, requests_mock, logged_in_client):
        renamed_payload = {
            'id': 'PL_EXISTING_1',
            'snippet': {'title': 'Updated Title'},
        }
        requests_mock.put(
            'https://www.googleapis.com/youtube/v3/playlists',
            json=renamed_payload,
        )

        result = logged_in_client.rename_playlist('PL_EXISTING_1', 'Updated Title')
        assert result['id'] == 'PL_EXISTING_1'
        body = requests_mock.last_request.json()
        assert body['id'] == 'PL_EXISTING_1'
        assert body['snippet']['title'] == 'Updated Title'

    def test_remove_playlist(self, requests_mock, logged_in_client):
        requests_mock.delete(
            'https://www.googleapis.com/youtube/v3/playlists',
            status_code=204,
        )

        logged_in_client.remove_playlist('PL_DELETE_1')
        assert 'id=PL_DELETE_1' in requests_mock.last_request.url
        assert requests_mock.last_request.qs['mine'] == ['true']

    def test_add_video_to_playlist(self, requests_mock, logged_in_client):
        created_item = {'id': 'PLI_NEW_ITEM_1'}
        requests_mock.post(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            json=created_item,
        )

        result = logged_in_client.add_video_to_playlist('PL_CUSTOM_1', 'dQw4w9WgXcQ')
        assert result['id'] == 'PLI_NEW_ITEM_1'
        body = requests_mock.last_request.json()
        assert body['snippet']['playlistId'] == 'PL_CUSTOM_1'
        assert body['snippet']['resourceId']['videoId'] == 'dQw4w9WgXcQ'

    def test_remove_video_from_playlist(self, requests_mock, logged_in_client):
        requests_mock.delete(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            status_code=204,
        )

        logged_in_client.remove_video_from_playlist('PL_CUSTOM_1', 'PLI_TO_DELETE', 'dQw4w9WgXcQ')
        assert 'id=PLI_TO_DELETE' in requests_mock.last_request.url


# ============================================================================
# Channel Resolution & Sections (Cluster B)
# ============================================================================

class TestChannelsAndSections:
    """Integration tests for channel identification, handle resolution, and channel sections."""

    def test_get_channels_by_id(self, requests_mock, data_client):
        payload = load_v3_fixture('channel_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/channels',
            json=payload,
        )

        result = data_client.get_channels('UC_x5XG1OV2P6uZZ5FSM9Ttw')
        assert result is not None
        assert len(result['items']) == 1
        channel = result['items'][0]
        assert channel['snippet']['title'] == 'Google Developers'
        assert channel['statistics']['subscriberCount'] == '2300000'

    def test_get_channels_mine(self, requests_mock, logged_in_client):
        payload = load_v3_fixture('channel_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/channels',
            json=payload,
        )

        result = logged_in_client.get_channels('mine')
        assert result is not None
        assert requests_mock.last_request.qs['mine'] == ['true']

    def test_get_channel_by_identifier_handle(self, requests_mock, data_client):
        payload = load_v3_fixture('channel_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/channels',
            json=payload,
        )

        channel_id = data_client.get_channel_by_identifier('@googledevelopers')
        assert channel_id == 'UC_x5XG1OV2P6uZZ5FSM9Ttw'
        assert requests_mock.last_request.qs['forhandle'] == ['@googledevelopers']

    def test_get_channel_by_identifier_mine(self, requests_mock, logged_in_client):
        payload = load_v3_fixture('channel_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/channels',
            json=payload,
        )

        channel_id = logged_in_client.get_channel_by_identifier('mine')
        assert channel_id == 'UC_x5XG1OV2P6uZZ5FSM9Ttw'
        assert requests_mock.last_request.qs['mine'] == ['true']

    def test_get_channel_sections(self, requests_mock, data_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/channelSections',
            json={'items': [{'id': 'section_1'}]},
        )

        result = data_client.get_channel_sections('UC_x5XG1OV2P6uZZ5FSM9Ttw')
        assert result is not None
        assert len(result.get('items', [])) == 1
        assert 'channelId=UC_x5XG1OV2P6uZZ5FSM9Ttw' in requests_mock.last_request.url

    def test_get_channel_videos(self, requests_mock, data_client):
        payload = load_v3_fixture('search_results.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/search',
            json=payload,
        )

        result = data_client.get_channel_videos('UC_x5XG1OV2P6uZZ5FSM9Ttw')
        assert result is not None
        assert 'channelId=UC_x5XG1OV2P6uZZ5FSM9Ttw' in requests_mock.last_request.url
        assert requests_mock.last_request.qs['type'] == ['video']


# ============================================================================
# Subscriptions Management (Cluster C)
# ============================================================================

class TestSubscriptionActions:
    """Integration tests for subscriptions query, subscription, and unsubscription."""

    def test_get_my_subscriptions(self, requests_mock, logged_in_client):
    def test_get_subscriptions_mine(self, requests_mock, logged_in_client):
        payload = load_v3_fixture('subscriptions_list.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/subscriptions',
            json=payload,
        )

        result = logged_in_client.get_my_subscriptions()
        result = logged_in_client.get_subscription('mine')
        assert result is not None
        assert len(result.get('items', [])) == 2
        assert requests_mock.last_request.qs['mine'] == ['true']

    def test_get_subscriptions_channel(self, requests_mock, data_client):
        payload = load_v3_fixture('subscriptions_list.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/subscriptions',
            json=payload,
        )

        result = data_client.get_subscription('UC_SOME_CHANNEL')
        assert result is not None
        assert 'channelId=UC_SOME_CHANNEL' in requests_mock.last_request.url

    def test_subscribe(self, requests_mock, logged_in_client):
        created_sub = {'id': 'sub_new_123'}
        requests_mock.post(
            'https://www.googleapis.com/youtube/v3/subscriptions',
            json=created_sub,
        )

        result = logged_in_client.subscribe('UC_TARGET_CHANNEL')
        assert result['id'] == 'sub_new_123'
        body = requests_mock.last_request.json()
        assert body['snippet']['resourceId']['channelId'] == 'UC_TARGET_CHANNEL'

    def test_unsubscribe(self, requests_mock, logged_in_client):
        requests_mock.delete(
            'https://www.googleapis.com/youtube/v3/subscriptions',
            status_code=204,
        )

        logged_in_client.unsubscribe('sub_id_to_delete')
        assert 'id=sub_id_to_delete' in requests_mock.last_request.url


# ============================================================================
# Feeds, Discovery & Categories (Cluster D)
# ============================================================================

class TestFeedsAndDiscovery:
    """Integration tests for trending, related videos, video categories, and live events."""

    def test_get_trending_videos(self, requests_mock, data_client):
        payload = load_v3_fixture('video_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/videos',
            json=payload,
        )

        result = data_client.get_trending_videos()
        assert result is not None
        assert requests_mock.last_request.qs['chart'] == ['mostpopular']

    def test_get_related_videos(self, requests_mock, data_client):
        mock_response = {
            'contents': {
                'singleColumnWatchNextResults': {
                    'results': {
                        'results': {
                            'contents': [
                                {
                                    'itemSectionRenderer': {
                                        'contents': [
                                            {'compactVideoRenderer': {'videoId': 'related_1'}}
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                }
            }
        }
        requests_mock.post(
            'https://www.youtube.com/youtubei/v1/next',
            json=mock_response,
        )

        result = data_client.get_related_videos('dQw4w9WgXcQ')
        assert result is not None
        assert 'relatedToVideoId=dQw4w9WgXcQ' in requests_mock.last_request.url
        assert requests_mock.last_request.json()['videoId'] == 'dQw4w9WgXcQ'

    def test_get_video_categories(self, requests_mock, data_client):
        payload = load_v3_fixture('video_categories.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/videoCategories',
            json=payload,
        )

        result = data_client.get_video_categories()
        assert result is not None
        assert len(result.get('items', [])) == 3
        assert result['items'][0]['snippet']['title'] == 'Film & Animation'

    def test_get_video_category_by_id(self, requests_mock, data_client):
        payload = load_v3_fixture('video_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/videos',
            json=payload,
        )

        result = data_client.get_video_category('10')
        assert result is not None
        assert requests_mock.last_request.qs['videocategoryid'] == ['10']

    def test_get_guide_categories(self, requests_mock, data_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/guideCategories',
            json={'items': [{'id': 'GC_TEST_1'}]},
        )

        result = data_client.get_guide_categories()
        assert result is not None
        assert len(result.get('items', [])) == 1

    def test_get_live_events(self, requests_mock, data_client):
        payload = load_v3_fixture('search_results.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/search',
            json=payload,
        )

        result = data_client.get_live_events(event_type='live')
        assert result is not None
        assert requests_mock.last_request.qs['eventtype'] == ['live']


# ============================================================================
# Ratings & Watch History (Cluster E)
# ============================================================================

class TestRatingsAndHistory:
    """Integration tests for video ratings, disliked videos, and playback progress."""

    def test_get_video_rating(self, requests_mock, logged_in_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/videos/getRating',
            json={'items': [{'id': 'dQw4w9WgXcQ', 'rating': 'like'}]},
        )

        result = logged_in_client.get_video_rating('dQw4w9WgXcQ')
        assert result is not None
        assert result['items'][0]['rating'] == 'like'

    def test_rate_video(self, requests_mock, logged_in_client):
        requests_mock.post(
            'https://www.googleapis.com/youtube/v3/videos/rate',
            status_code=204,
        )

        logged_in_client.rate_video('dQw4w9WgXcQ', rating='like')
        assert 'id=dQw4w9WgXcQ' in requests_mock.last_request.url
        assert requests_mock.last_request.qs['rating'] == ['like']

    def test_get_disliked_videos(self, requests_mock, logged_in_client):
        payload = load_v3_fixture('video_details.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/videos',
            json=payload,
        )

        result = logged_in_client.get_disliked_videos()
        assert result is not None
        assert requests_mock.last_request.qs['myrating'] == ['dislike']

    def test_update_watch_history(self, requests_mock, logged_in_client):
        playback_stats_url = 'https://www.youtube.com/api/stats/playback'
        requests_mock.get(
            playback_stats_url,
            json={},
            status_code=200,
        )

        logged_in_client.update_watch_history(
            video_id='dQw4w9WgXcQ',
            url=playback_stats_url,
            status=(120.5, 0.0, 120.5, 'playing'),
        )

        last_qs = requests_mock.last_request.qs
        assert last_qs['cmt'] == ['120.500']
        assert last_qs['state'] == ['playing']


# ============================================================================
# Comments & Localization (Cluster F & G)
# ============================================================================

class TestCommentsAndLocalization:
    """Integration tests for comment threads, replies, languages, and regions."""

    def test_get_parent_comments(self, requests_mock, data_client):
        payload = load_v3_fixture('comments.json')
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/commentThreads',
            json=payload,
        )

        result = data_client.get_parent_comments('dQw4w9WgXcQ')
        assert result is not None
        assert len(result.get('items', [])) == 1
        comment = result['items'][0]['snippet']['topLevelComment']['snippet']
        assert comment['textDisplay'] == 'Classic masterpiece!'
        assert comment['likeCount'] == 4200

    def test_get_child_comments(self, requests_mock, data_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/comments',
            json={'items': [{'id': 'reply_comment_1'}]},
        )

        result = data_client.get_child_comments('Ugz_TEST_COMMENT_THREAD_1')
        assert result is not None
        assert requests_mock.last_request.qs['parentid'] == ['ugz_test_comment_thread_1']

    def test_get_supported_languages(self, requests_mock, data_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/i18nLanguages',
            json={'items': [{'id': 'en', 'snippet': {'name': 'English'}}]},
        )

        result = data_client.get_supported_languages()
        assert result is not None
        assert result['items'][0]['id'] == 'en'

    def test_get_supported_regions(self, requests_mock, data_client):
        requests_mock.get(
            'https://www.googleapis.com/youtube/v3/i18nRegions',
            json={'items': [{'id': 'US', 'snippet': {'name': 'United States'}}]},
        )

        result = data_client.get_supported_regions()
        assert result is not None
        assert result['items'][0]['id'] == 'US'
