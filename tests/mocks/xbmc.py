# -*- coding: utf-8 -*-
"""
Mock implementation of Kodi's xbmc C-module.
"""
import json
import os
import tempfile
import time

LOGDEBUG = 0
LOGINFO = 1
LOGNOTICE = 2
LOGWARNING = 3
LOGERROR = 4
LOGSEVERE = 5
LOGFATAL = 6
LOGNONE = 7

PLAYLIST_MUSIC = 0
PLAYLIST_VIDEO = 1
PLAYLIST_PICTURE = 2

ISO_639_1 = 0
ISO_639_2 = 1
ENGLISH_NAME = 2



# Message log accumulator for test assertions
LOG_RECORDS = []


def log(msg, level=LOGINFO):
    LOG_RECORDS.append((level, str(msg)))


def getInfoLabel(info_label):
    labels = {
        'System.BuildVersion': '21.0-ALPHA1 Git:20230501-unknown',
        'System.CurrentWindow': '10025',
        'ListItem.Title': 'Test Title',
        'ListItem.Icon': 'DefaultVideo.png',
    }
    return labels.get(info_label, '')


def getCondVisibility(condition):
    return False


_TEMP_BASE = tempfile.gettempdir()


def translatePath(path):
    if not path:
        return ''
    if path.startswith('special://'):
        rel = path.replace('special://', '').replace('/', os.sep)
        return os.path.join(_TEMP_BASE, 'kodi_test_special', rel)
    return path


def sleep(msec):
    time.sleep(msec / 1000.0)


def executebuiltin(function, wait=False):
    pass


def executeJSONRPC(json_string):
    if 'Application.GetProperties' in json_string:
        return json.dumps({
            'id': 1,
            'jsonrpc': '2.0',
            'result': {
                'name': 'Kodi',
                'version': {
                    'major': 21,
                    'minor': 0,
                    'revision': '20230501-unknown',
                    'tag': 'stable',
                    'tagversion': '',
                }
            }
        })
    return '{"id": 1, "jsonrpc": "2.0", "result": "OK"}'



def getLanguage(format=None, region=False):
    return 'English'



def convertLanguage(language, code_format):
    return language



def getRegion(id_):
    return 'en'


def getCleanInstall():
    return False


class Monitor(object):
    def __init__(self):
        self._abort = False

    def abortRequested(self):
        return self._abort

    def waitForAbort(self, timeout=0):
        if timeout <= 0:
            return self._abort
        # Sleep up to timeout in small increments
        start = time.time()
        while time.time() - start < timeout:
            if self._abort:
                return True
            time.sleep(0.01)
        return self._abort

    def onSettingsChanged(self):
        pass

    def trigger_abort(self):
        self._abort = True


class Player(object):
    def __init__(self):
        self._playing = False
        self._time = 0.0
        self._total_time = 0.0

    def isPlaying(self):
        return self._playing

    def isPlayingVideo(self):
        return self._playing

    def isPlayingAudio(self):
        return False

    def getTime(self):
        return self._time

    def getTotalTime(self):
        return self._total_time

    def pause(self):
        pass

    def stop(self):
        self._playing = False


class PlayList(object):
    def __init__(self, playList):
        self._playlist = playList
        self._items = []

    def getPlayListId(self):
        return self._playlist

    def clear(self):
        self._items.clear()

    def add(self, url, listitem=None, index=-1):
        if index == -1:
            self._items.append((url, listitem))
        else:
            self._items.insert(index, (url, listitem))

    def size(self):
        return len(self._items)

