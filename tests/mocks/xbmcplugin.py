# -*- coding: utf-8 -*-
"""
Mock implementation of Kodi's xbmcplugin C-module.
"""

SORT_METHOD_NONE = 0
SORT_METHOD_LABEL = 1
SORT_METHOD_LABEL_IGNORE_THE = 2
SORT_METHOD_DATE = 3
SORT_METHOD_SIZE = 4
SORT_METHOD_FILE = 5
SORT_METHOD_DRIVE_TYPE = 6
SORT_METHOD_TRACKNUM = 7
SORT_METHOD_DURATION = 8
SORT_METHOD_TITLE = 9
SORT_METHOD_TITLE_IGNORE_THE = 10
SORT_METHOD_ARTIST = 11
SORT_METHOD_ARTIST_IGNORE_THE = 12
SORT_METHOD_ALBUM = 13
SORT_METHOD_ALBUM_IGNORE_THE = 14
SORT_METHOD_GENRE = 15
SORT_METHOD_VIDEO_YEAR = 16
SORT_METHOD_VIDEO_RATING = 17
SORT_METHOD_PROGRAM_COUNT = 18
SORT_METHOD_PLAYLIST_ORDER = 19
SORT_METHOD_EPISODE = 20
SORT_METHOD_VIDEO_TITLE = 21
SORT_METHOD_SORT_TITLE = 22
SORT_METHOD_PRODUCTIONCODE = 23
SORT_METHOD_SONG_RATING = 24
SORT_METHOD_MPAA_RATING = 25
SORT_METHOD_VIDEO_RUNTIME = 26
SORT_METHOD_STUDIO = 27
SORT_METHOD_STUDIO_IGNORE_THE = 28
SORT_METHOD_FULLPATH = 29
SORT_METHOD_LABEL_IGNORE_FOLDERS = 30
SORT_METHOD_LASTPLAYED = 31
SORT_METHOD_PLAYCOUNT = 32
SORT_METHOD_LISTENERS = 33
SORT_METHOD_UNSORTED = 34
SORT_METHOD_CHANNEL = 35
SORT_METHOD_CHANNEL_NUMBER = 36
SORT_METHOD_BITRATE = 37
SORT_METHOD_DATEADDED = 38

# Test inspection storage
DIRECTORY_ITEMS = []
RESOLVED_URL = []
CONTENT_TYPE = {}


def addDirectoryItem(handle, url, listitem, isFolder=False, totalItems=0):
    DIRECTORY_ITEMS.append({
        'handle': handle,
        'url': url,
        'listitem': listitem,
        'isFolder': isFolder,
        'totalItems': totalItems,
    })
    return True


def addDirectoryItems(handle, items, totalItems=0):
    for item in items:
        # items can be (url, listitem, isFolder)
        if len(item) == 3:
            url, listitem, isFolder = item
        else:
            url, listitem = item
            isFolder = False
        DIRECTORY_ITEMS.append({
            'handle': handle,
            'url': url,
            'listitem': listitem,
            'isFolder': isFolder,
            'totalItems': totalItems,
        })
    return True


def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    return True


def setResolvedUrl(handle, succeeded, listitem):
    RESOLVED_URL.append({
        'handle': handle,
        'succeeded': succeeded,
        'listitem': listitem,
    })


def setContent(handle, content):
    CONTENT_TYPE[handle] = content


def setPluginCategory(handle, category):
    pass


def addSortMethod(handle, sortMethod, label2=""):
    pass


def setProperty(handle, key, value):
    pass


def clear_mock_data():
    DIRECTORY_ITEMS.clear()
    RESOLVED_URL.clear()
    CONTENT_TYPE.clear()

