# -*- coding: utf-8 -*-
"""
Pytest configuration and Kodi mock registration.
"""
import os
import sys
import tempfile
import pytest

# 1. Ensure resources/lib is first in sys.path
ADDON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RESOURCES_LIB = os.path.join(ADDON_DIR, 'resources', 'lib')

if RESOURCES_LIB not in sys.path:
    sys.path.insert(0, RESOURCES_LIB)

# 2. Preemptively register mocks in sys.modules BEFORE any addon imports occur
from tests.mocks import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs

sys.modules['xbmc'] = xbmc
sys.modules['xbmcaddon'] = xbmcaddon
sys.modules['xbmcgui'] = xbmcgui
sys.modules['xbmcplugin'] = xbmcplugin
sys.modules['xbmcvfs'] = xbmcvfs


@pytest.fixture(autouse=True)
def reset_kodi_mocks():
    """Reset accumulated state in Kodi mocks before and after each test."""
    xbmc.LOG_RECORDS.clear()
    xbmcplugin.clear_mock_data()
    yield
    xbmc.LOG_RECORDS.clear()
    xbmcplugin.clear_mock_data()


@pytest.fixture
def temp_db_path():
    """Provide a unique temporary database file path and clean up after."""
    fd, path = tempfile.mkstemp(suffix='.sqlite')
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def mock_context():
    """Provide an instance of XbmcContext configured with mocks."""
    from youtube_plugin.kodion.context.xbmc.xbmc_context import XbmcContext
    context = XbmcContext()
    return context

