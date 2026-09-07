# -*- coding: utf-8 -*-
"""
Mock implementation of Kodi's xbmcaddon C-module.
"""
import os
import tempfile

_PROFILE_DIR = os.path.join(tempfile.gettempdir(), 'kodi_test_profile')
os.makedirs(_PROFILE_DIR, exist_ok=True)


class Addon(object):
    def __init__(self, id_='plugin.video.youtube'):
        self._id = id_
        self._settings = {
            'youtube.api.enable': 'true',
            'youtube.api.key': '',
            'youtube.api.id': '',
            'youtube.api.secret': '',
            'youtube.folder.video.quality': '0',
            'youtube.general.debug.level': '0',
            'youtube.general.items.per.page': '50',
            'kodion.search.history.size': '20',
            'kodion.cache.size': '50',
            'kodion.network.connect_timeout': '9',
            'kodion.network.read_timeout': '27',
        }
        self._strings = {
            14076: 'Add to favourites',
            30000: 'YouTube',
            30500: 'General',
        }

    def getSetting(self, setting_id):
        return self._settings.get(setting_id, '')

    def setSetting(self, setting_id, value):
        self._settings[setting_id] = str(value)
        return True

    def getSettingBool(self, setting_id):
        if setting_id not in self._settings or self._settings[setting_id] == '':
            raise ValueError(f'Setting {setting_id} is not set')
        val = str(self._settings[setting_id]).lower()
        return val in ('true', '1', 'yes')

    def setSettingBool(self, setting_id, value):
        self._settings[setting_id] = 'true' if value else 'false'
        return True

    def getSettingInt(self, setting_id):
        if setting_id not in self._settings or self._settings[setting_id] == '':
            raise ValueError(f'Setting {setting_id} is not set')
        return int(self._settings[setting_id])

    def setSettingInt(self, setting_id, value):
        self._settings[setting_id] = str(int(value))
        return True

    def getSettingNumber(self, setting_id):
        if setting_id not in self._settings or self._settings[setting_id] == '':
            raise ValueError(f'Setting {setting_id} is not set')
        return float(self._settings[setting_id])

    def setSettingNumber(self, setting_id, value):

        self._settings[setting_id] = str(float(value))
        return True

    def getSettingString(self, setting_id):
        return self._settings.get(setting_id, '')

    def setSettingString(self, setting_id, value):
        self._settings[setting_id] = str(value)
        return True

    def getLocalizedString(self, string_id):
        return self._strings.get(int(string_id), str(string_id))

    def getAddonInfo(self, info_id):
        infos = {
            'id': self._id,
            'name': 'YouTube',
            'version': '7.4.4',
            'path': os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')),
            'profile': _PROFILE_DIR,
            'icon': 'resources/media/icon.png',
            'fanart': 'resources/media/fanart.jpg',
            'author': 'anxdpanic, bromix',
        }
        return infos.get(info_id, '')

    def getSettings(self):
        return Settings(self)

    def openSettings(self):
        pass


class Settings(object):
    def __init__(self, addon):
        self._addon = addon

    def getBool(self, setting_id):
        return self._addon.getSettingBool(setting_id)

    def setBool(self, setting_id, value):
        return self._addon.setSettingBool(setting_id, value)

    def getInt(self, setting_id):
        return self._addon.getSettingInt(setting_id)

    def setInt(self, setting_id, value):
        return self._addon.setSettingInt(setting_id, value)

    def getString(self, setting_id):
        return self._addon.getSettingString(setting_id)

    def setString(self, setting_id, value):
        return self._addon.setSettingString(setting_id, value)

    def getStringList(self, setting_id):
        val = self._addon.getSettingString(setting_id)
        return val.split('|') if val else []

    def setStringList(self, setting_id, value):
        return self._addon.setSettingString(setting_id, '|'.join(value))

