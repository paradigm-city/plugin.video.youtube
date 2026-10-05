# -*- coding: utf-8 -*-
"""
Integration tests for the sign-in page served by the addon HTTP server:
- Only available while sign-in is in progress, and only with its token
- Lists each code with a link to its Google sign-in page
- Status endpoint reflects approvals shared by the sign-in dialog
- Final state expires, content is escaped and not cached
"""
import json
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

import pytest
import xbmcgui

from youtube_plugin.kodion.constants import ADDON_ID, PATHS, SIGN_IN_CODES
from youtube_plugin.kodion.network import http_server


PROPERTY = '-'.join((ADDON_ID, SIGN_IN_CODES))
TOKEN = '0123456789abcdef'


def share(entries, sign_in_token=TOKEN, **extra):
    data = dict(token=sign_in_token, entries=entries, **extra)
    xbmcgui.Window(10000).setProperty(PROPERTY, json.dumps(data))
    return data


def entry(idx, status='pending', title=None):
    return {
        'title': title or 'Client %d' % idx,
        'code': 'ABCD-000%d' % idx,
        'url': 'https://www.google.com/device?user_code=ABCD-000%d' % idx,
        'status': status,
    }


class PageParser(HTMLParser):
    def __init__(self):
        super(PageParser, self).__init__()
        self.links = []
        self.codes = []
        self.entry_classes = []
        self.script = ''
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.links.append(attrs.get('href'))
        elif tag == 'input':
            self.codes.append(attrs.get('value'))
        elif tag == 'div' and 'entry' in attrs.get('class', '').split():
            self.entry_classes.append(attrs['class'])
        elif tag == 'script':
            self._in_script = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.script += data


@pytest.fixture(scope='module')
def server():
    # Shared by all tests, as stopping a server takes up to half a second.
    # Shared sign-in data is reset between tests by the reset_kodi_mocks fixture
    from youtube_plugin.kodion.context.xbmc.xbmc_context import XbmcContext

    httpd = http_server.get_http_server('127.0.0.1', 0, XbmcContext())
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    base_url = 'http://127.0.0.1:%d' % httpd.socket.getsockname()[1]

    def fetch(path, query=None):
        url = base_url + path
        if query is not None:
            url += '?' + query
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return (response.status,
                        dict(response.headers),
                        response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), ''

    yield fetch
    httpd.shutdown()
    httpd.server_close()


def page_path(sign_in_token=TOKEN):
    return 't=' + sign_in_token


class TestAvailability:
    @pytest.mark.parametrize('path', (PATHS.SIGN_IN, PATHS.SIGN_IN_STATUS))
    def test_not_found_without_sign_in(self, server, path):
        assert server(path, page_path())[0] == 404

    @pytest.mark.parametrize('path', (PATHS.SIGN_IN, PATHS.SIGN_IN_STATUS))
    @pytest.mark.parametrize('query', (None, '', 't=', 't=wrong',
                                       't=' + TOKEN[:-1]))
    def test_not_found_without_matching_token(self, server, path, query):
        share([entry(0)])
        assert server(path, query)[0] == 404

    def test_not_found_with_invalid_data(self, server):
        xbmcgui.Window(10000).setProperty(PROPERTY, 'not json')
        assert server(PATHS.SIGN_IN, page_path())[0] == 404

    def test_final_state_expires(self, server):
        share([entry(0, 'approved')], expires=time.time() + 30)
        assert server(PATHS.SIGN_IN_STATUS, page_path())[0] == 200
        share([entry(0, 'approved')], expires=time.time() - 1)
        assert server(PATHS.SIGN_IN_STATUS, page_path())[0] == 404


class TestPage:
    def test_lists_codes_and_links(self, server):
        share([entry(0), entry(1, 'approved'), entry(2)])
        status, headers, html = server(PATHS.SIGN_IN, page_path())
        assert status == 200
        assert headers['Content-Type'] == 'text/html; charset=utf-8'
        assert headers['Cache-Control'] == 'no-store'

        page = PageParser()
        page.feed(html)
        assert page.codes == ['ABCD-0000', 'ABCD-0001', 'ABCD-0002']
        assert page.links == [
            'https://www.google.com/device?user_code=ABCD-000%d' % idx
            for idx in range(3)
        ]
        assert page.entry_classes == ['entry pending', 'entry approved',
                                      'entry pending']

    def test_status_url_in_script(self, server):
        share([entry(0)])
        page = PageParser()
        page.feed(server(PATHS.SIGN_IN, page_path())[2])
        assert '"%s?t=%s"' % (PATHS.SIGN_IN_STATUS, TOKEN) in page.script
        assert '</' not in page.script

    def test_content_is_escaped(self, server):
        share([entry(0, title='<script>alert("x")</script> & Co')])
        html = server(PATHS.SIGN_IN, page_path())[2]
        assert '<script>alert' not in html
        assert '&lt;script&gt;alert("x")&lt;/script&gt; &amp; Co' in html


class TestStatus:
    def test_reflects_shared_statuses(self, server):
        entries = [entry(0), entry(1), entry(2)]
        share(entries)
        status, headers, body = server(PATHS.SIGN_IN_STATUS, page_path())
        assert status == 200
        assert headers['Content-Type'] == 'application/json; charset=utf-8'
        assert headers['Cache-Control'] == 'no-store'
        assert json.loads(body) == ['pending', 'pending', 'pending']

        entries[1]['status'] = 'approved'
        entries[2]['status'] = 'failed'
        share(entries)
        body = server(PATHS.SIGN_IN_STATUS, page_path())[2]
        assert json.loads(body) == ['pending', 'approved', 'failed']

    def test_new_sign_in_replaces_old_token(self, server):
        share([entry(0)])
        share([entry(0)], sign_in_token='fedcba9876543210')
        assert server(PATHS.SIGN_IN_STATUS, page_path())[0] == 404
        assert server(PATHS.SIGN_IN_STATUS,
                      page_path('fedcba9876543210'))[0] == 200
