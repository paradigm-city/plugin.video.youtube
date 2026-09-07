# -*- coding: utf-8 -*-
"""
Unit tests for Kodi UI context menu assembly and conditional action generation.
"""
import pytest

from youtube_plugin.kodion.constants import PATHS
from youtube_plugin.kodion.items import MediaItem
from youtube_plugin.youtube.helper.utils import update_video_items
from youtube_plugin.youtube.provider import Provider


@pytest.fixture
def provider():
    return Provider()


def _get_context_menu_actions(item):
    """Helper to extract (label, command) tuples from an item's context menu."""
    menu = item.get_context_menu() or []
    return [entry for entry in menu if isinstance(entry, (tuple, list)) and len(entry) >= 2]


def _has_action_param(command, param_substring):
    return param_substring in command


def test_default_video_context_menu_playback_items(provider, mock_context):
    media_item = MediaItem('Sample Video', 'plugin://plugin.video.youtube/play/?video_id=sample123')
    media_item.video_id = 'sample123'
    snippet = {
        'title': 'Sample Video',
        'channelId': 'UC_sample_channel',
        'channelTitle': 'Sample Channel',
    }

    update_video_items(
        provider,
        mock_context,
        {'sample123': [media_item]},
        yt_items_dict={'sample123': {'snippet': snippet}},
    )

    actions = _get_context_menu_actions(media_item)
    commands = [cmd for _, cmd in actions]

    # Verify standard playback options
    assert any(_has_action_param(cmd, 'video_id=') for cmd in commands)
    assert any(_has_action_param(cmd, 'prompt_for_subtitles=True') for cmd in commands)
    assert any(_has_action_param(cmd, 'audio_only=True') for cmd in commands)
    assert any(_has_action_param(cmd, 'ask_for_quality=True') for cmd in commands)
    assert any('Action(Queue)' in cmd for cmd in commands)
    # Channel navigation
    assert any(_has_action_param(cmd, 'route/channel/') for cmd in commands)


def test_live_video_context_menu_timeshift(provider, mock_context):
    media_item = MediaItem('Live Stream', 'plugin://plugin.video.youtube/play/?video_id=live123')
    media_item.video_id = 'live123'
    snippet = {
        'title': 'Live Stream',
        'channelId': 'UC_live',
        'liveBroadcastContent': 'live',
    }
    yt_item = {
        'snippet': snippet,
        'liveStreamingDetails': {
            'actualStartTime': '2026-09-07T00:00:00Z',
        },
    }

    update_video_items(
        provider,
        mock_context,
        {'live123': [media_item]},
        yt_items_dict={'live123': yt_item},
    )

    actions = _get_context_menu_actions(media_item)
    commands = [cmd for _, cmd in actions]
    assert any(_has_action_param(cmd, 'timeshift=True') for cmd in commands)



def test_watch_later_local_when_not_logged_in(provider, mock_context):
    media_item = MediaItem('Local WL Video', 'plugin://plugin.video.youtube/play/?video_id=vid1')
    media_item.video_id = 'vid1'
    snippet = {'title': 'Local WL Video', 'channelId': 'UC_wl'}

    update_video_items(
        provider,
        mock_context,
        {'vid1': [media_item]},
        yt_items_dict={'vid1': {'snippet': snippet}},
    )

    actions = _get_context_menu_actions(media_item)
    commands = [cmd for _, cmd in actions]
    # Local watch later uses kodion/watch_later/add
    assert any('kodion/watch_later/add' in cmd for cmd in commands)


def test_watch_later_omitted_inside_watch_later_folder(provider, mock_context):
    # Set context path to watch later folder
    mock_context._path = PATHS.WATCH_LATER

    media_item = MediaItem('In WL Video', 'plugin://plugin.video.youtube/play/?video_id=vid2')
    media_item.video_id = 'vid2'
    snippet = {'title': 'In WL Video', 'channelId': 'UC_wl'}

    update_video_items(
        provider,
        mock_context,
        {'vid2': [media_item]},
        yt_items_dict={'vid2': {'snippet': snippet}},
    )

    actions = _get_context_menu_actions(media_item)
    commands = [cmd for _, cmd in actions]
    assert not any('watch_later/add' in cmd for cmd in commands)


def test_bookmarks_omitted_inside_bookmarks_folder(provider, mock_context):
    mock_context._path = PATHS.BOOKMARKS

    media_item = MediaItem('Bookmarked Video', 'plugin://plugin.video.youtube/play/?video_id=vid3')
    media_item.video_id = 'vid3'
    snippet = {'title': 'Bookmarked Video', 'channelId': 'UC_bm'}

    update_video_items(
        provider,
        mock_context,
        {'vid3': [media_item]},
        yt_items_dict={'vid3': {'snippet': snippet}},
    )

    actions = _get_context_menu_actions(media_item)
    commands = [cmd for _, cmd in actions]
    assert not any('kodion/bookmarks/add/?item_id=' in cmd and 'video_id' in cmd for cmd in commands)


def test_playlist_item_remove_own_playlist_only(provider, mock_context, monkeypatch):
    # Logged in and viewing own playlist
    client = provider.get_client(mock_context)
    monkeypatch.setattr(client, 'logged_in', True)
    mock_context._path = '/channel/mine/playlist/PL_own_123/'

    media_item = MediaItem('Playlist Video', 'plugin://plugin.video.youtube/play/?video_id=vid4')
    media_item.video_id = 'vid4'
    media_item.playlist_id = 'PL_own_123'
    snippet = {'title': 'Playlist Video', 'channelId': 'mine'}

    update_video_items(
        provider,
        mock_context,
        {'vid4': [media_item]},
        yt_items_dict={'vid4': {'snippet': snippet}},
    )

    actions = _get_context_menu_actions(media_item)
    commands = [cmd for _, cmd in actions]
    assert any('playlist/remove/video' in cmd for cmd in commands)


