"""
Unit tests for 16:9 landscape artwork selection, independent of the
thumbnail size and fanart settings.
"""
import pytest
from youtube_plugin.kodion.items import (
    DirectoryItem,
    VideoItem,
    directory_listitem,
    media_listitem,
)
from youtube_plugin.kodion.items.xbmc.xbmc_items import get_art
from youtube_plugin.youtube.helper.utils import (
    LANDSCAPE_THUMB_SIZE,
    THUMB_TYPES,
    THUMB_URL,
    add_thumb_timestamp,
    get_landscape_thumbnail,
    get_thumbnail,
    update_channel_info,
    update_playlist_items,
    update_video_items,
)
from youtube_plugin.youtube.provider import Provider

MQ = 'https://i.ytimg.com/vi/x/mqdefault.jpg'
HQ = 'https://i.ytimg.com/vi/x/hqdefault.jpg'
SD = 'https://i.ytimg.com/vi/x/sddefault.jpg'
MAXRES = 'https://i.ytimg.com/vi/x/maxresdefault.jpg'

THUMBS_NO_MAXRES = {
    'default': {'url': 'https://i.ytimg.com/vi/x/default.jpg',
                'width': 120, 'height': 90},
    'medium': {'url': MQ, 'width': 320, 'height': 180},
    'high': {'url': HQ, 'width': 480, 'height': 360},
    'standard': {'url': SD, 'width': 640, 'height': 480},
}
THUMBS_MAXRES = dict(
    THUMBS_NO_MAXRES,
    maxres={'url': MAXRES, 'width': 1280, 'height': 720},
)


@pytest.fixture
def provider():
    return Provider()


def test_landscape_thumb_prefers_16_9_over_larger_4_3():
    assert get_thumbnail(LANDSCAPE_THUMB_SIZE, THUMBS_NO_MAXRES) == MQ


def test_landscape_thumb_prefers_largest_16_9():
    assert get_thumbnail(LANDSCAPE_THUMB_SIZE, THUMBS_MAXRES) == MAXRES


def test_landscape_thumb_falls_back_to_other_ratio():
    thumbs = {'high': THUMBS_NO_MAXRES['high']}
    assert get_thumbnail(LANDSCAPE_THUMB_SIZE, thumbs) == HQ


def test_add_thumb_timestamp():
    assert add_thumb_timestamp('', '1') == ''
    assert add_thumb_timestamp('https://a/b_live.jpg', '1') == (
        'https://a/b_live.jpg?ct=1'
    )
    assert add_thumb_timestamp('https://a/b.jpg?x=y', '1') == (
        'https://a/b.jpg?x=y&ct=1'
    )
    assert add_thumb_timestamp('https://a/b.jpg', '1') == 'https://a/b.jpg'


@pytest.mark.parametrize('fanart_type', [0, 2, 3])
def test_update_video_items_landscape_any_fanart_setting(provider,
                                                          mock_context,
                                                          fanart_type):
    video_item = VideoItem('Video 1',
                           'plugin://plugin.video.youtube/play/?video_id=vid1')
    video_item.video_id = 'vid1'
    snippet = {'title': 'Video 1', 'thumbnails': dict(THUMBS_NO_MAXRES)}

    mock_context.set_params(fanart_type=fanart_type)
    update_video_items(
        provider,
        mock_context,
        {'vid1': [video_item]},
        yt_items_dict={'vid1': {'snippet': snippet}},
    )

    assert video_item.get_landscape(default=False) == MQ
    _, list_item, _ = media_listitem(mock_context, video_item)
    assert list_item.getArt('landscape') == MQ


@pytest.mark.parametrize('fanart_type', [0, 2, 3])
def test_update_playlist_items_landscape_any_fanart_setting(provider,
                                                            mock_context,
                                                            fanart_type):
    playlist_item = DirectoryItem(
        'Playlist 1',
        'plugin://plugin.video.youtube/playlist/pl1/',
        playlist_id='pl1',
    )
    data = {
        'pl1': {
            'id': 'pl1',
            'snippet': {
                'title': 'Playlist 1',
                'channelId': 'UC1',
                'thumbnails': dict(THUMBS_MAXRES),
            },
            'contentDetails': {'itemCount': 1},
        },
    }

    mock_context.set_params(fanart_type=fanart_type)
    update_playlist_items(
        provider,
        mock_context,
        {'pl1': [playlist_item]},
        data=data,
    )

    assert playlist_item.get_landscape(default=False) == MAXRES


def test_update_channel_info_uses_banner_but_not_for_playlists(provider,
                                                              mock_context):
    channel_item = DirectoryItem(
        'Channel',
        'plugin://plugin.video.youtube/channel/UC1/',
        image='https://example.com/avatar.jpg',
        channel_id='UC1',
    )
    playlist_item = DirectoryItem(
        'Playlist',
        'plugin://plugin.video.youtube/channel/UC1/playlist/pl1/',
        image=HQ,
        landscape=MQ,
        channel_id='UC1',
        playlist_id='pl1',
    )
    data = {
        'UC1': {
            'name': 'Channel',
            'image': 'https://example.com/avatar.jpg',
            # FANART_THUMBNAIL: banner is not used as fanart
            'fanart': None,
            'landscape': 'https://example.com/banner.jpg',
        },
    }

    mock_context.set_params(fanart_type=3)
    update_channel_info(
        provider,
        mock_context,
        channel_items_dict={'UC1': [channel_item, playlist_item]},
        data=data,
    )

    assert channel_item.get_landscape() == 'https://example.com/banner.jpg'
    assert playlist_item.get_landscape() == MQ
    _, list_item, _ = directory_listitem(mock_context, channel_item)
    assert list_item.getArt('landscape') == 'https://example.com/banner.jpg'
    assert list_item.getArt('poster') == 'https://example.com/avatar.jpg'


def test_get_art_fallback_order():
    item = VideoItem('Video', 'plugin://test/', image=HQ)
    # no landscape and no fanart: thumbnail image
    assert get_art(item, show_fanart=2)['landscape'] == HQ

    # real fanart is preferred over the thumbnail image...
    item.set_fanart(SD)
    assert get_art(item, show_fanart=2)['landscape'] == SD
    # ...but only if fanart is enabled
    art = get_art(item, show_fanart=0)
    assert art['landscape'] == HQ
    assert 'fanart' not in art

    # explicit landscape art is always preferred
    item.set_landscape(MQ)
    assert get_art(item, show_fanart=2)['landscape'] == MQ
    assert get_art(item, show_fanart=0)['landscape'] == MQ


QHD = 'https://i.ytimg.com/vi/x/qhddefault.jpg'


def test_landscape_thumb_ignores_unknown_phantom_types():
    # the Data API returns qhd (2560x1440) thumbnails that resolve to a 404
    thumbs = dict(
        THUMBS_MAXRES,
        qhd={'url': QHD, 'width': 2560, 'height': 1440},
        xyz={'url': 'https://i.ytimg.com/vi/x/xyzdefault.jpg',
             'width': 3840, 'height': 2160},
    )
    assert get_landscape_thumbnail(thumbs) == MAXRES
    assert get_thumbnail({'size': 0, 'ratio': 0}, thumbs) == MAXRES


def test_landscape_thumb_filters_phantom_urls_in_list():
    thumbs = [
        {'url': QHD, 'width': 2560, 'height': 1440},
        {'url': MQ, 'width': 320, 'height': 180},
    ]
    assert get_landscape_thumbnail(thumbs) == MQ


def test_landscape_thumb_prefers_verified_over_unverified_16_9():
    # e.g. old videos where hq720 does not exist
    thumbs = dict(
        THUMBS_NO_MAXRES,
        **{'720': {'url': 'https://i.ytimg.com/vi/x/hq720.jpg',
                   'size': 1280 * 720,
                   'ratio': 1280 / 720,
                   'unverified': True}}
    )
    assert get_landscape_thumbnail(thumbs) == MQ


def test_landscape_thumb_unverified_only_uses_mqdefault():
    # player meta data only contains generated, unverified thumbnails
    thumbs = {
        thumb_type: {
            'url': THUMB_URL.format('x', thumb['name'], ''),
            'size': thumb['size'],
            'ratio': thumb['ratio'],
            'unverified': True,
        }
        for thumb_type, thumb in THUMB_TYPES.items()
    }
    assert get_landscape_thumbnail(thumbs) == MQ
