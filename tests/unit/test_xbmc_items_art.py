"""
Unit tests for landscape artwork assignment and fallbacks in Kodi list items.
"""
import pytest
from youtube_plugin.kodion.items import (
    BaseItem,
    DirectoryItem,
    ImageItem,
    VideoItem,
    directory_listitem,
    image_listitem,
    media_listitem,
    playback_item,
)
from youtube_plugin.youtube.helper.utils import (
    update_channel_info,
    update_video_items,
)
from youtube_plugin.youtube.provider import Provider


@pytest.fixture
def provider():
    return Provider()


def test_base_item_landscape_defaults_and_custom():
    item = BaseItem('Test Item', 'plugin://test/uri', image='https://example.com/thumb.jpg')
    # Default fallback to image
    assert item.get_landscape() == 'https://example.com/thumb.jpg'

    # Custom landscape
    item.set_landscape('https://example.com/landscape.jpg')
    assert item.get_landscape() == 'https://example.com/landscape.jpg'

    # Initialized directly with landscape
    item_with_landscape = BaseItem(
        'Test Item 2',
        'plugin://test/uri2',
        image='https://example.com/thumb2.jpg',
        landscape='https://example.com/landscape2.jpg',
    )
    assert item_with_landscape.get_landscape() == 'https://example.com/landscape2.jpg'


def test_media_listitem_art_landscape(mock_context):
    video_item = VideoItem(
        'Sample Video',
        'plugin://plugin.video.youtube/play/?video_id=sample123',
        image='https://example.com/video_thumb.jpg',
    )

    _, list_item, _ = media_listitem(mock_context, video_item)
    assert list_item.getArt('landscape') == 'https://example.com/video_thumb.jpg'
    assert list_item.getArt('thumb') == 'https://example.com/video_thumb.jpg'

    # Set custom landscape and verify it takes precedence
    video_item.set_landscape('https://example.com/video_landscape_16_9.jpg')
    _, list_item2, _ = media_listitem(mock_context, video_item)
    assert list_item2.getArt('landscape') == 'https://example.com/video_landscape_16_9.jpg'
    assert list_item2.getArt('thumb') == 'https://example.com/video_thumb.jpg'


def test_directory_listitem_art_landscape(mock_context):
    dir_item = DirectoryItem(
        'Sample Channel / Playlist',
        'plugin://plugin.video.youtube/channel/UC123/',
        image='https://example.com/channel_avatar.jpg',
    )

    _, list_item, _ = directory_listitem(mock_context, dir_item)
    assert list_item.getArt('landscape') == 'https://example.com/channel_avatar.jpg'
    assert list_item.getArt('thumb') == 'https://example.com/channel_avatar.jpg'
    assert list_item.getArt('poster') == 'https://example.com/channel_avatar.jpg'

    # If landscape (e.g. Channel banner) is set, verify landscape differs from poster
    dir_item.set_landscape('https://example.com/channel_banner.jpg')
    _, list_item2, _ = directory_listitem(mock_context, dir_item)
    assert list_item2.getArt('landscape') == 'https://example.com/channel_banner.jpg'
    assert list_item2.getArt('thumb') == 'https://example.com/channel_avatar.jpg'
    assert list_item2.getArt('poster') == 'https://example.com/channel_avatar.jpg'


def test_playback_item_art_landscape(mock_context):
    video_item = VideoItem(
        'Playback Video',
        'plugin://plugin.video.youtube/play/?video_id=play123',
        image='https://example.com/playback_thumb.jpg',
    )
    list_item = playback_item(mock_context, video_item)
    assert list_item.getArt('landscape') == 'https://example.com/playback_thumb.jpg'
    assert list_item.getArt('thumb') == 'https://example.com/playback_thumb.jpg'


def test_image_listitem_art_landscape(mock_context):
    image_item = ImageItem(
        'Sample Image',
        'https://example.com/image.png',
        image='https://example.com/thumb.png',
    )
    _, list_item, _ = image_listitem(mock_context, image_item)
    assert list_item.getArt('landscape') == 'https://example.com/thumb.png'


def test_update_channel_info_sets_landscape_for_directory_item(provider, mock_context):
    channel_dir_item = DirectoryItem(
        'Channel Name',
        'plugin://plugin.video.youtube/channel/UC_channel_1/',
        image='https://example.com/channel_icon.jpg',
    )
    channel_dir_item.channel_id = 'UC_channel_1'

    channel_data = {
        'UC_channel_1': {
            'name': 'Channel Name',
            'image': 'https://example.com/channel_icon.jpg',
            'fanart': 'https://example.com/channel_banner_wide.jpg',
        }
    }

    update_channel_info(
        provider,
        mock_context,
        channel_items_dict={'UC_channel_1': [channel_dir_item]},
        data=channel_data,
    )

    assert channel_dir_item.get_landscape() == 'https://example.com/channel_banner_wide.jpg'
    _, list_item, _ = directory_listitem(mock_context, channel_dir_item)
    assert list_item.getArt('landscape') == 'https://example.com/channel_banner_wide.jpg'


def test_update_video_items_landscape_thumbnail(provider, mock_context):
    video_item = VideoItem('Video 1', 'plugin://plugin.video.youtube/play/?video_id=vid1')
    video_item.video_id = 'vid1'
    snippet = {
        'title': 'Video 1',
        'thumbnails': {
            'medium': {'url': 'https://example.com/mqdefault.jpg', 'width': 320, 'height': 180},
            'high': {'url': 'https://example.com/hqdefault.jpg', 'width': 480, 'height': 360},
        },
    }

    mock_context.set_params(fanart_type='3')  # FANART_THUMBNAIL
    update_video_items(
        provider,
        mock_context,
        {'vid1': [video_item]},
        yt_items_dict={'vid1': {'snippet': snippet}},
    )

    assert video_item.get_landscape() is not None
    _, list_item, _ = media_listitem(mock_context, video_item)
    assert list_item.getArt('landscape') is not None
    assert list_item.getArt('landscape') == video_item.get_landscape()

