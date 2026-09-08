# -*- coding: utf-8 -*-
"""
Integration tests for YouTubePlayerClient, DASH MPD manifests, HLS live streams,
ciphers, rate-bypass throttling, and playability error handling.
"""
import json
import os
import re
from unittest.mock import MagicMock, patch
import pytest

from youtube_plugin.youtube.client.player_client import YouTubePlayerClient
from youtube_plugin.youtube.client.subtitles import Subtitles
from youtube_plugin.youtube.youtube_exceptions import YouTubeException


FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'innertube'))


def load_innertube_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def player_client(mock_context):
    client = YouTubePlayerClient(context=mock_context)
    return client


# ============================================================================
# Basic Progressive & Format Tests
# ============================================================================

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


# ============================================================================
# Cluster A: Adaptive MPEG-DASH & Local MPD Manifest Synthesis
# ============================================================================

class TestAdaptiveMpdStreaming:
    """Integration tests for MPEG-DASH adaptive stream matching and MPD manifest generation."""

    def test_adaptive_stream_processing_and_mpd_manifest_generation(self, requests_mock, mock_context):
        payload = load_innertube_fixture('player_response.json')
        requests_mock.post(
            'https://www.youtube.com/youtubei/v1/player',
            json=payload,
        )

        settings = mock_context.get_settings()
        settings.use_isa(True)
        settings.use_mpd_videos(True)

        with patch.object(mock_context, 'inputstream_adaptive_capabilities', return_value=frozenset(['avc1', 'mp4a', 'vp9', 'opus'])):
            client = YouTubePlayerClient(context=mock_context)
            streams, item = client.load_stream_info('dQw4w9WgXcQ', use_mpd=True)

            stream_list = list(streams)
            assert len(stream_list) >= 1

            manifest_stream = stream_list[0]
            assert 'manifest/dash' in manifest_stream['url']
            assert manifest_stream['meta']['id'] == 'dQw4w9WgXcQ'

    def test_adaptive_streams_filtered_by_isa_capabilities(self, mock_context):
        payload = load_innertube_fixture('player_response.json')
        settings = mock_context.get_settings()
        settings.use_isa(True)
        settings.use_mpd_videos(True)

        with patch.object(mock_context, 'inputstream_adaptive_capabilities', return_value=frozenset(['vp9', 'opus'])):
            client = YouTubePlayerClient(context=mock_context)
            responses = {
                'web': {
                    'adaptive_fmts': payload['streamingData']['adaptiveFormats'],
                    'client': {'headers': {}},
                }
            }
            video_data, audio_data = client._process_adaptive_streams(responses)
            assert len(video_data) >= 1
            for group_key in video_data:
                assert 'vp9' in str(group_key) or 'webm' in str(group_key)

    def test_generate_mpd_manifest_creates_valid_xml(self, mock_context):
        settings = mock_context.get_settings()
        settings.use_isa(True)
        settings.use_mpd_videos(True)

        with patch.object(mock_context, 'inputstream_adaptive_capabilities', return_value=frozenset(['avc1', 'mp4a', 'vp9', 'opus'])):
            client = YouTubePlayerClient(context=mock_context)
            client.video_id = 'dQw4w9WgXcQ'
            payload = load_innertube_fixture('player_response.json')
            responses = {
                'web': {
                    'adaptive_fmts': payload['streamingData']['adaptiveFormats'],
                    'client': {'headers': {}},
                }
            }
            video_data, audio_data = client._process_adaptive_streams(responses)
            manifest_url, main_stream = client._generate_mpd_manifest(video_data, audio_data, None)

            assert manifest_url is not None
            assert 'manifest/dash' in manifest_url
            assert main_stream is not None

    def test_process_mpd_manifest_stream(self, player_client):
        stream_list = {}
        responses = {
            'web': {
                'mpd_manifest': 'https://manifest.googlevideo.com/api/manifest/dash/test.mpd',
                'client': {'headers': {'User-Agent': 'TestClient'}},
            }
        }
        player_client._process_mpd(stream_list, responses)
        assert '9998' in stream_list
        assert 'manifest/dash' in stream_list['9998']['url']

    def test_prepare_headers(self):
        cookie_mock = MagicMock()
        cookie_mock.name = 'SID'
        cookie_mock.value = 'mock_cookie_val'
        headers = {'User-Agent': 'Kodi'}
        prepared = YouTubePlayerClient._prepare_headers(headers, cookies=[cookie_mock], new_headers={'X-Extra': '1'})
        assert prepared['Cookie'] == 'SID=mock_cookie_val'
        assert prepared['X-Extra'] == '1'
        assert prepared['User-Agent'] == 'Kodi'


# ============================================================================
# Cluster B: Live Stream HLS Playlist Extraction
# ============================================================================

class TestLiveHlsStreaming:
    """Integration tests for live streams via HLS m3u8 playlist parsing."""

    def test_live_stream_hls_manifest_parsing(self, requests_mock, player_client):
        live_payload = load_innertube_fixture('player_response_live.json')
        requests_mock.post(
            'https://www.youtube.com/youtubei/v1/player',
            json=live_payload,
        )

        hls_playlist_content = (
            '#EXTM3U\n'
            '#EXT-X-VERSION:3\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720,FRAME-RATE=30.000,CODECS="avc1.4d401f,mp4a.40.2"\n'
            'https://rr1---sn-test.googlevideo.com/videoplayback/itag/95/live_stream_720.m3u8\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=640x360,FRAME-RATE=30.000,CODECS="avc1.42001e,mp4a.40.2"\n'
            'https://rr1---sn-test.googlevideo.com/videoplayback/itag/93/live_stream_360.m3u8\n'
        )
        requests_mock.get(
            'https://manifest.googlevideo.com/api/manifest/hls_variant/test_live.m3u8',
            text=hls_playlist_content,
        )

        streams, item = player_client.load_stream_info('LIVE_VID_123')
        assert item is not None
        assert item['snippet']['title'] == 'NASA Live Stream'

        stream_list = list(streams)
        assert len(stream_list) >= 1
        live_stream = stream_list[0]
        assert live_stream.get('live') is True
        assert 'Live' in live_stream.get('title', '')


# ============================================================================
# Cluster C: Signature Cipher & Rate-Bypass Throttling
# ============================================================================

class TestSignatureCipherAndThrottling:
    """Tests for decrypting obfuscated signatures, calculating nsig, and cpn nonces."""

    def test_signature_cipher_decryption(self, mock_context):
        client = YouTubePlayerClient(context=mock_context)
        client.video_id = 'CIPHER_VID_456'

        mock_cipher = MagicMock()
        mock_cipher.get_signature.return_value = 'DECIPHERED_SIG_VALID'
        client._cipher = mock_cipher

        stream_map = {
            'itag': 18,
            'signatureCipher': 's=ENCRYPTED_SIG_ABC123&sp=signature&url=https%3A%2F%2Frr1.googlevideo.com%2Fvideoplayback%3Fitag%3D18',
        }

        url = client._process_signature_cipher(stream_map)
        assert url is not None
        assert '&signature=DECIPHERED_SIG_VALID' in url
        mock_cipher.get_signature.assert_called_once_with('ENCRYPTED_SIG_ABC123')

    def test_throttling_n_parameter_recalculation(self, player_client):
        mock_calc = MagicMock()
        mock_calc.calculate_n.return_value = 'NEW_THROTTLED_TOKEN'
        player_client._calculate_n = mock_calc

        test_url = 'https://rr1.googlevideo.com/videoplayback?itag=18&n=ORIGINAL_TOKEN&other=1'
        processed_url = player_client._process_url_params(test_url)

        assert processed_url is not None
        assert 'n=NEW_THROTTLED_TOKEN' in processed_url
        assert 'ratebypass=yes' in processed_url
        mock_calc.calculate_n.assert_called_once_with('ORIGINAL_TOKEN')

    def test_generate_cpn(self, player_client):
        cpn1 = player_client._generate_cpn()
        cpn2 = player_client._generate_cpn()

        assert len(cpn1) == 16
        assert len(cpn2) == 16
        assert re.match(r'^[a-zA-Z0-9_-]{16}$', cpn1)
        assert cpn1 != cpn2

    def test_process_url_params_without_url(self, player_client):
        assert player_client._process_url_params(None) is None
        assert player_client._process_url_params('') == ''

    def test_signature_cipher_exception_handling(self, mock_context):
        client = YouTubePlayerClient(context=mock_context)
        client.video_id = 'CIPHER_ERR_VID'
        mock_cipher = MagicMock()
        mock_cipher.get_signature.side_effect = Exception('Decryption failed')
        client._cipher = mock_cipher

        stream_map = {
            'itag': 18,
            'signatureCipher': 's=BAD_SIG&sp=sig&url=https%3A%2F%2Fvideo',
        }
        assert client._process_signature_cipher(stream_map) is None
        assert client._cipher is False

    def test_signature_cipher_missing_keys(self, mock_context):
        client = YouTubePlayerClient(context=mock_context)
        assert client._process_signature_cipher({'signatureCipher': 'sp=sig'}) is None

    def test_throttling_disabled_returns_none(self, player_client):
        player_client._calculate_n = False
        assert player_client._process_url_params('https://video?n=TOKEN') is None


# ============================================================================
# Cluster D: Error Handling & Playability Status
# ============================================================================

class TestErrorHandlingAndPlayability:
    """Tests for unplayable videos, geo-blocking, age-gates, and error hooks."""

    def test_unplayable_video_raises_youtube_exception(self, requests_mock, player_client):
        payload = load_innertube_fixture('player_response_unplayable.json')
        requests_mock.post(
            'https://www.youtube.com/youtubei/v1/player',
            json=payload,
        )

        with pytest.raises(YouTubeException) as exc_info:
            player_client.load_stream_info('UNPLAYABLE_VID_1')

        assert 'The uploader has not made this video available in your country' in str(exc_info.value)

    def test_live_stream_offline_raises_youtube_exception(self, requests_mock, player_client):
        payload = {
            'playabilityStatus': {
                'status': 'LIVE_STREAM_OFFLINE',
                'reason': 'Live stream will begin in 2 hours',
            },
            'videoDetails': {
                'videoId': 'OFFLINE_LIVE_VID',
                'title': 'Scheduled Stream',
            },
        }
        requests_mock.post(
            'https://www.youtube.com/youtubei/v1/player',
            json=payload,
        )

        with pytest.raises(YouTubeException) as exc_info:
            player_client.load_stream_info('OFFLINE_LIVE_VID')

        assert 'Live stream will begin in 2 hours' in str(exc_info.value)

    def test_player_error_hook_structured_error(self):
        exc_mock = MagicMock()
        exc_mock.json_data = {
            'error': {
                'message': 'API rate limit exceeded',
                'errors': [{'reason': 'rateLimitExceeded'}],
            }
        }
        exc_mock.pass_data = True
        exc_mock.raise_exc = True

        title, info, details, data, exception = YouTubePlayerClient._player_error_hook(exc=exc_mock)
        assert details['error_reason'] == 'rateLimitExceeded'
        assert details['error_message'] == 'API rate limit exceeded'
        assert data is not None
        assert exception == YouTubeException

    def test_player_error_hook_unstructured_error(self):
        exc_mock = MagicMock()
        exc_mock.json_data = None
        exc_mock.pass_data = False
        exc_mock.raise_exc = False

        title, info, details, data, exception = YouTubePlayerClient._player_error_hook(exc=exc_mock)
        assert details is None
        assert data is None
        assert exception is None

    def test_get_error_details_parsing(self, player_client):
        status_with_runs = {
            'errorScreen': {
                'playerErrorMessageRenderer': {
                    'reason': {
                        'runs': [{'text': 'First part. '}, {'text': 'Second part.'}],
                    }
                }
            }
        }
        assert player_client._get_error_details(status_with_runs) == 'First part. Second part.'

        status_with_simple_text = {
            'errorScreen': {
                'playerErrorMessageRenderer': {
                    'reason': {
                        'simpleText': 'Single text message',
                    }
                }
            }
        }
        assert player_client._get_error_details(status_with_simple_text) == {'simpleText': 'Single text message'}

        assert player_client._get_error_details(None) is None


# ============================================================================
# Cluster E: Audio-Only & Stream Filtering
# ============================================================================

class TestAudioOnlyAndStreamFiltering:
    """Tests for audio-only streams, resolution filters, and unknown format handling."""

    def test_audio_only_stream_filtering(self, requests_mock, player_client):
        payload = load_innertube_fixture('player_response.json')
        requests_mock.post(
            'https://www.youtube.com/youtubei/v1/player',
            json=payload,
        )

        streams, item = player_client.load_stream_info('dQw4w9WgXcQ', audio_only=True)
        assert player_client._audio_only is True
        assert item is not None

    def test_audio_only_formatting(self, player_client):
        player_client._audio_only = True
        fmt = player_client._get_stream_format(
            '18',
            info={'video': {'label': '360p'}, 'audio': {'codec': 'aac', 'bitrate': 96000}},
            title='360p',
        )
        assert 'video' not in fmt
        assert fmt['audio']['codec'] == 'aac'

    def test_stream_format_max_height_filter(self, player_client):
        fmt = player_client._get_stream_format('137', title='1080p', max_height=720)
        assert fmt is False

        fmt_allowed = player_client._get_stream_format('137', title='1080p', max_height=1080)
        assert fmt_allowed is not False
        assert fmt_allowed['video']['height'] == 1080

    def test_stream_format_unknown_or_discontinued(self, player_client):
        assert player_client._get_stream_format('invalid_itag_999999') is None


# ============================================================================
# Cluster F: HTML & Config Extraction
# ============================================================================

class TestHtmlAndConfigExtraction:
    """Tests for player API key extraction from HTML and player configs."""

    def test_get_player_key_found(self, player_client):
        html = '<html><head><script>var config = {"INNERTUBE_API_KEY":"AIzaSyMockKey_12345abcdef"};</script></head></html>'
        key = player_client._get_player_key(html)
        assert key == 'AIzaSyMockKey_12345abcdef'

    def test_get_player_key_not_found(self, player_client):
        html = '<html><body>No key here</body></html>'
        assert player_client._get_player_key(html) is None
        assert player_client._get_player_key('') is None

    def test_get_player_client_static(self):
        config = {'INNERTUBE_CONTEXT': {'client': {'clientName': 'TVHTML5', 'clientVersion': '7.20230405'}}}
        client_dict = YouTubePlayerClient._get_player_client(config)
        assert client_dict['clientName'] == 'TVHTML5'

    def test_get_player_config(self, requests_mock, player_client):
        player_client.video_id = 'dQw4w9WgXcQ'
        mock_html = '<html><script>ytcfg.set({"PLAYER_JS_URL": "/s/player/abcdef/base.js"});</script></html>'
        requests_mock.get('https://www.youtube.com/watch?v=dQw4w9WgXcQ', text=mock_html)

        cfg = player_client._get_player_config()
        assert cfg is not None
        assert cfg['PLAYER_JS_URL'] == '/s/player/abcdef/base.js'

        requests_mock.get('https://www.youtube.com/embed/dQw4w9WgXcQ', text=mock_html)
        cfg_embed = player_client._get_player_config(embed=True)
        assert cfg_embed is not None

    def test_get_player_js(self, requests_mock, player_client):
        player_client.video_id = 'dQw4w9WgXcQ'
        mock_html = '<html><script>ytcfg.set({"PLAYER_JS_URL": "/s/player/abcdef/base.js"});</script></html>'
        requests_mock.get('https://www.youtube.com/watch?v=dQw4w9WgXcQ', text=mock_html)
        requests_mock.get('https://www.youtube.com/s/player/abcdef/base.js', text='var signature=function(){};')

        js_content = player_client._get_player_js()
        assert 'var signature' in js_content

    def test_get_player_config_no_match(self, requests_mock, player_client):
        player_client.video_id = 'dQw4w9WgXcQ'
        requests_mock.get('https://www.youtube.com/watch?v=dQw4w9WgXcQ', text='<html>no cfg here</html>')
        assert player_client._get_player_config() is None

    def test_get_player_js_context_config_fallback(self, requests_mock, player_client):
        player_client.video_id = 'dQw4w9WgXcQ'
        mock_html = '<html><script>ytcfg.set({"WEB_PLAYER_CONTEXT_CONFIGS": {"web": {"jsUrl": "/s/player/fallback/base.js"}}});</script></html>'
        requests_mock.get('https://www.youtube.com/watch?v=dQw4w9WgXcQ', text=mock_html)
        requests_mock.get('https://www.youtube.com/s/player/fallback/base.js', text='var testFallback=1;')

        # Clear cache item if any
        player_client._context.get_data_cache().set_item('player_js_url', {'url': ''})
        js_content = player_client._get_player_js()
        assert 'var testFallback' in js_content
