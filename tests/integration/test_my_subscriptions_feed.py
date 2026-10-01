# -*- coding: utf-8 -*-
"""
Integration tests for the My Subscriptions feed built from YouTube RSS feeds
in YouTubeDataClient.get_my_subscriptions() using mocked HTTP responses:
- Feed parsing and newest first ordering
- RSS endpoint returning 404 (e.g. YouTube feed outages)
- Fallback to previously cached feed items when a refresh fails
- Rate limited feed requests
"""
import re
import types

import pytest

from youtube_plugin.kodion.sql_store.feed_history import FeedHistory
from youtube_plugin.youtube.client.data_client import YouTubeDataClient


CHANNELS_URL = 'https://www.googleapis.com/youtube/v3/channels'
SUBSCRIPTIONS_URL = 'https://www.googleapis.com/youtube/v3/subscriptions'
FEEDS_URL = re.compile(r'https://www\.youtube\.com/feeds/videos\.xml\?playlist_id=.*')

CHANNEL_ID = 'UC_FEED_CHANNEL'
FEED_ID = 'UULF_FEED_CHANNEL'

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

ATOM_ENTRY = """
 <entry>
  <yt:videoId>{video_id}</yt:videoId>
  <yt:channelId>{channel_id}</yt:channelId>
  <title>{title}</title>
  <published>{published}</published>
  <media:group>
   <media:description>Description of {title}</media:description>
   <media:community>
    <media:starRating count="12" average="5.00" min="1" max="5"/>
    <media:statistics views="345"/>
   </media:community>
  </media:group>
 </entry>"""

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
 <yt:playlistId>{feed_id}</yt:playlistId>
 <yt:channelId>{channel_id}</yt:channelId>
 <title>Videos</title>
 <author>
  <name>Feed Channel</name>
 </author>{entries}
</feed>"""


def atom_feed(*videos):
    entries = ''.join(
        ATOM_ENTRY.format(
            video_id=video_id,
            channel_id=CHANNEL_ID,
            title='Video ' + video_id,
            published=published,
        )
        for video_id, published in videos
    )
    return ATOM_FEED.format(feed_id=FEED_ID, channel_id=CHANNEL_ID, entries=entries)


def feed_requests(requests_mock):
    return [
        request
        for request in requests_mock.request_history
        if '/feeds/videos.xml' in request.url
    ]


def video_ids(response):
    return [item['id'] for item in response['items']]


@pytest.fixture(autouse=True)
def clean_caches(mock_context):
    caches = (
        mock_context.get_requests_cache(),
        mock_context.get_data_cache(),
        mock_context.get_feed_history(),
        mock_context.get_function_cache(),
    )
    FeedHistory._memory_store.clear()
    for cache in caches:
        cache.clear()
    yield
    FeedHistory._memory_store.clear()
    for cache in caches:
        cache.clear()


@pytest.fixture
def subscriptions_only(mock_context):
    """Build the feed from subscriptions only, without saved playlists or
    bookmarks, which use additional endpoints."""
    settings = mock_context.get_settings()
    settings.subscriptions_sources = types.MethodType(
        lambda _self, *_args, **_kwargs: (True, False, False, False),
        settings,
    )
    return settings


@pytest.fixture
def client(mock_context, requests_mock, subscriptions_only):
    requests_mock.get(CHANNELS_URL, json={'items': [{'id': 'UC_MINE_CHANNEL_ID'}]})
    requests_mock.get(SUBSCRIPTIONS_URL, json={
        'items': [{
            'snippet': {
                'title': 'Feed Channel',
                'resourceId': {'channelId': CHANNEL_ID},
            },
            'contentDetails': {'totalItemCount': 3, 'newItemCount': 0},
        }],
    })
    data_client = YouTubeDataClient(context=mock_context, configs=CONFIGS)
    data_client.set_access_token({'user': 'mock_user_token', 'tv': 'mock_tv_token'})
    return data_client


def test_feed_videos_are_returned_newest_first(requests_mock, client):
    requests_mock.get(FEEDS_URL, text=atom_feed(
        ('vid_old', '2026-09-01T10:00:00+00:00'),
        ('vid_new', '2026-09-30T10:00:00+00:00'),
        ('vid_mid', '2026-09-15T10:00:00+00:00'),
    ))

    response = client.get_my_subscriptions(page_token=1)

    assert video_ids(response) == ['vid_new', 'vid_mid', 'vid_old']
    assert response['pageInfo']['totalResults'] == 3
    snippet = response['items'][0]['snippet']
    assert snippet['title'] == 'Video vid_new'
    assert snippet['channelTitle'] == 'Feed Channel'
    assert snippet['videoOwnerChannelId'] == CHANNEL_ID
    requests = feed_requests(requests_mock)
    assert len(requests) == 1
    assert requests[0].url.endswith('playlist_id=' + FEED_ID)


@pytest.mark.parametrize('feed_type, prefix', [
    ('videos', 'UULF'),
    ('shorts', 'UUSH'),
    ('live', 'UULV'),
])
def test_feed_type_selects_uploads_playlist(requests_mock, client, feed_type, prefix):
    requests_mock.get(FEEDS_URL, text=atom_feed(
        ('vid_one', '2026-09-30T10:00:00+00:00'),
    ))

    client.get_my_subscriptions(page_token=1, feed_type=feed_type)

    requests = feed_requests(requests_mock)
    assert len(requests) == 1
    assert requests[0].url.endswith('playlist_id=' + CHANNEL_ID.replace('UC', prefix, 1))


def test_feed_404_without_cached_items_returns_none(requests_mock, client):
    # Mirrors the YouTube RSS outage: every feed request returns 404 and the
    # listing has nothing to show.
    requests_mock.get(FEEDS_URL, status_code=404, text='<html>Error 404 (Not Found)!!1</html>')

    assert client.get_my_subscriptions(page_token=1) is None
    assert len(feed_requests(requests_mock)) == 1


def test_cached_items_are_kept_when_refresh_returns_404(requests_mock, client):
    requests_mock.get(FEEDS_URL, [
        {'text': atom_feed(
            ('vid_a', '2026-09-29T10:00:00+00:00'),
            ('vid_b', '2026-09-30T10:00:00+00:00'),
        )},
        {'status_code': 404, 'text': '<html>Error 404 (Not Found)!!1</html>'},
    ])

    first = client.get_my_subscriptions(page_token=1)
    second = client.get_my_subscriptions(page_token=1, refresh=True)

    assert video_ids(first) == ['vid_b', 'vid_a']
    assert len(feed_requests(requests_mock)) == 2
    assert second is not None
    assert video_ids(second) == ['vid_b', 'vid_a']


def test_rate_limited_feed_returns_none(requests_mock, client):
    requests_mock.get(FEEDS_URL, status_code=429, text='Too Many Requests')

    assert client.get_my_subscriptions(page_token=1) is None
