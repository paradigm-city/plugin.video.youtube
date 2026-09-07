# -*- coding: utf-8 -*-
"""
Mock implementation of Kodi's xbmcgui C-module.
"""


class MockVideoInfoTag(object):
    def __init__(self):
        self._data = {}

    def setTitle(self, title):
        self._data['title'] = title

    def setPlot(self, plot):
        self._data['plot'] = plot

    def setDuration(self, duration):
        self._data['duration'] = duration

    def setPlaycount(self, count):
        self._data['playcount'] = count

    def getTitle(self):
        return self._data.get('title', '')

    def getPlot(self):
        return self._data.get('plot', '')

    def getDuration(self):
        return self._data.get('duration', 0)


class ListItem(object):
    def __init__(self, label="", label2="", path="", offscreen=False):
        self._label = label
        self._label2 = label2
        self._path = path
        self._offscreen = offscreen
        self._art = {}
        self._properties = {}
        self._info = {}
        self._context_menu_items = []
        self._stream_info = {}
        self._video_info_tag = MockVideoInfoTag()

    def setLabel(self, label):
        self._label = label

    def getLabel(self):
        return self._label

    def setLabel2(self, label2):
        self._label2 = label2

    def getLabel2(self):
        return self._label2

    def setPath(self, path):
        self._path = path

    def getPath(self):
        return self._path

    def setArt(self, art):
        if isinstance(art, dict):
            self._art.update(art)

    def getArt(self, key=None):
        if key:
            return self._art.get(key, '')
        return self._art

    def setProperty(self, key, value):
        self._properties[str(key)] = str(value)

    def getProperty(self, key):
        return self._properties.get(str(key), '')

    def setInfo(self, type_, infoLabels):
        if type_ not in self._info:
            self._info[type_] = {}
        if isinstance(infoLabels, dict):
            self._info[type_].update(infoLabels)

    def getVideoInfoTag(self):
        return self._video_info_tag

    def addContextMenuItems(self, items, replaceItems=False):
        if replaceItems:
            self._context_menu_items = list(items)
        else:
            self._context_menu_items.extend(items)

    def getContextMenuItems(self):
        return list(self._context_menu_items)

    def setContentLookup(self, enable):
        pass

    def setSubtitles(self, subtitle_files):
        self._properties['subtitles'] = str(subtitle_files)

    def addStreamInfo(self, stream_type, info_dict):
        if stream_type not in self._stream_info:
            self._stream_info[stream_type] = []
        self._stream_info[stream_type].append(info_dict)

    def setCast(self, actors):
        self._properties['cast'] = str(actors)


class Dialog(object):
    def notification(self, heading, message, icon="", time=3000, sound=True):
        pass

    def ok(self, heading, message):
        return True

    def yesno(self, heading, message, nolabel="", yeslabel="", autoclose=0):
        return True

    def select(self, heading, list_, autoclose=0, preselect=-1, useDetails=False):
        return 0 if list_ else -1

    def contextmenu(self, list_):
        return 0 if list_ else -1

    def textviewer(self, heading, text, usemono=False):
        pass

    def numeric(self, type_, heading, default=""):
        return default

    def input(self, heading, default="", type_=0, option=0, autoclose=0):
        return default


class DialogProgress(object):
    def create(self, heading, message=""):
        pass

    def update(self, percent, message=""):
        pass

    def close(self):
        pass

    def iscanceled(self):
        return False


class DialogProgressBG(object):
    def create(self, heading, message=""):
        pass

    def update(self, percent, heading="", message=""):
        pass

    def close(self):
        pass

    def isFinished(self):
        return False


class Window(object):
    def __init__(self, existing_window_id=0):
        self._window_id = existing_window_id
        self._properties = {}

    def setProperty(self, key, value):
        self._properties[str(key)] = str(value)

    def getProperty(self, key):
        return self._properties.get(str(key), '')

    def clearProperty(self, key):
        self._properties.pop(str(key), None)

