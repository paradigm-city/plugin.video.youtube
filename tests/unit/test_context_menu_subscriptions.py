# -*- coding: utf-8 -*-
"""
Unit tests for channel related video context menu entries:
- Subscribe / unsubscribe based on the cached subscription status
- Bookmark / remove bookmark based on bookmarked channels
- Single subscription status lookup per listing, only when logged in
"""
import pytest

from youtube_plugin.kodion.constants import PATHS
from youtube_plugin.kodion.items import MediaItem
from youtube_plugin.youtube.helper.utils import update_video_items
from youtube_plugin.youtube.provider import Provider


SUBSCRIBE = 'subscriptions/add'
UNSUBSCRIBE = 'subscriptions/remove'
BOOKMARK_ADD = 'bookmarks/add'
BOOKMARK_REMOVE = 'bookmarks/remove'


@pytest.fixture
def provider():
    return Provider()


@pytest.fixture(autouse=True)
def empty_bookmarks(mock_context):
    bookmarks = mock_context.get_bookmarks_list()
    bookmarks.clear()
    yield bookmarks
    bookmarks.clear()


class LookupLog(list):
    """Records status lookups and holds the set of subscribed channels."""
    subscribed = None


@pytest.fixture
def status_lookups(provider, mock_context, monkeypatch):
    """Log the client in and replace the subscription status lookup."""
    client = provider.get_client(mock_context)
    monkeypatch.setattr(client, 'logged_in', True)
    lookups = LookupLog()
    subscribed = set()

    def _get_subscription_status(channel_ids):
        lookups.append(set(channel_ids))
        return {channel_id: channel_id in subscribed for channel_id in channel_ids}

    monkeypatch.setattr(client, 'get_subscription_status', _get_subscription_status)
    lookups.subscribed = subscribed
    return lookups


def _build(provider, context, videos):
    """Run update_video_items for {video_id: channel_id} and return the items."""
    items = {}
    yt_items = {}
    for video_id, channel_id in videos.items():
        item = MediaItem(video_id, 'plugin://plugin.video.youtube/play/?video_id=' + video_id)
        item.video_id = video_id
        items[video_id] = [item]
        yt_items[video_id] = {
            'snippet': {
                'title': video_id,
                'channelId': channel_id,
                'channelTitle': 'Channel ' + channel_id,
            },
        }
    update_video_items(provider, context, items, yt_items_dict=yt_items)
    return {video_id: item_list[0] for video_id, item_list in items.items()}


def _commands(item):
    return [
        entry[1]
        for entry in item.get_context_menu() or ()
        if isinstance(entry, (tuple, list)) and len(entry) >= 2
    ]


def _has(item, fragment):
    return any(fragment in command for command in _commands(item))


def test_logged_in_shows_unsubscribe_only_for_subscribed_channels(provider, mock_context,
                                                                  status_lookups):
    status_lookups.subscribed.add('UC_SUBBED')

    items = _build(provider, mock_context, {'vid_a': 'UC_SUBBED', 'vid_b': 'UC_OTHER'})

    assert _has(items['vid_a'], UNSUBSCRIBE)
    assert not _has(items['vid_a'], SUBSCRIBE)
    assert _has(items['vid_b'], SUBSCRIBE)
    assert not _has(items['vid_b'], UNSUBSCRIBE)


def test_subscription_status_is_looked_up_once_per_listing(provider, mock_context,
                                                           status_lookups):
    _build(provider, mock_context, {
        'vid_a': 'UC_ONE',
        'vid_b': 'UC_ONE',
        'vid_c': 'UC_TWO',
    })

    assert status_lookups == [{'UC_ONE', 'UC_TWO'}]


def test_unsubscribe_targets_channel_id(provider, mock_context, status_lookups):
    status_lookups.subscribed.add('UC_SUBBED')

    items = _build(provider, mock_context, {'vid_a': 'UC_SUBBED'})

    unsubscribe = [cmd for cmd in _commands(items['vid_a']) if UNSUBSCRIBE in cmd]
    assert len(unsubscribe) == 1
    assert 'channel_id=' in unsubscribe[0]


def test_my_subscriptions_feed_defaults_to_unsubscribe(provider, mock_context, monkeypatch):
    # Without a status lookup result, videos in the subscriptions feed fall
    # back to being treated as subscribed.
    client = provider.get_client(mock_context)
    monkeypatch.setattr(client, 'logged_in', True)
    monkeypatch.setattr(client, 'get_subscription_status', lambda channel_ids: {})
    mock_context._path = PATHS.MY_SUBSCRIPTIONS + '/'

    items = _build(provider, mock_context, {'vid_a': 'UC_FEED'})

    assert _has(items['vid_a'], UNSUBSCRIBE)
    assert not _has(items['vid_a'], SUBSCRIBE)


def test_not_logged_in_has_no_subscription_entries_or_lookup(provider, mock_context, monkeypatch):
    client = provider.get_client(mock_context)
    monkeypatch.setattr(client, 'logged_in', False)

    def _fail(_channel_ids):
        raise AssertionError('status lookup must not run when logged out')

    monkeypatch.setattr(client, 'get_subscription_status', _fail)

    items = _build(provider, mock_context, {'vid_a': 'UC_ANY'})

    assert not _has(items['vid_a'], SUBSCRIBE)
    assert not _has(items['vid_a'], UNSUBSCRIBE)


def test_bookmarked_channel_offers_remove_bookmark(provider, mock_context, status_lookups,
                                                   empty_bookmarks):
    # Channel bookmarks are stored as 'None' until updated with channel details
    empty_bookmarks.add_item('UC_BOOKMARKED', 'None')

    items = _build(provider, mock_context, {'vid_a': 'UC_BOOKMARKED', 'vid_b': 'UC_OTHER'})

    assert _has(items['vid_a'], BOOKMARK_REMOVE)
    assert not _has(items['vid_a'], BOOKMARK_ADD)
    assert _has(items['vid_b'], BOOKMARK_ADD)
    assert not _has(items['vid_b'], BOOKMARK_REMOVE)
