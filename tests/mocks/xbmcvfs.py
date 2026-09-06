# -*- coding: utf-8 -*-
"""
Mock implementation of Kodi's xbmcvfs C-module.
"""
import os
import shutil
import tempfile

_TEMP_VFS_BASE = os.path.join(tempfile.gettempdir(), 'kodi_test_vfs')
os.makedirs(_TEMP_VFS_BASE, exist_ok=True)


def translatePath(path):
    if not path:
        return ''
    if path.startswith('special://'):
        rel = path.replace('special://', '').replace('/', os.sep)
        resolved = os.path.join(_TEMP_VFS_BASE, rel)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        return resolved
    return path


def exists(path):
    resolved = translatePath(path)
    return os.path.exists(resolved)


def mkdir(path):
    resolved = translatePath(path)
    try:
        os.mkdir(resolved)
        return True
    except OSError:
        return False


def mkdirs(path):
    resolved = translatePath(path)
    try:
        os.makedirs(resolved, exist_ok=True)
        return True
    except OSError:
        return False


def delete(path):
    resolved = translatePath(path)
    try:
        if os.path.isfile(resolved):
            os.remove(resolved)
            return True
        elif os.path.isdir(resolved):
            shutil.rmtree(resolved)
            return True
        return False
    except OSError:
        return False


def listdir(path):
    resolved = translatePath(path)
    if not os.path.exists(resolved) or not os.path.isdir(resolved):
        return [], []
    dirs = []
    files = []
    for entry in os.listdir(resolved):
        full = os.path.join(resolved, entry)
        if os.path.isdir(full):
            dirs.append(entry)
        else:
            files.append(entry)
    return dirs, files


class File(object):
    def __init__(self, filepath, mode='r'):
        self._filepath = translatePath(filepath)
        self._mode = mode
        self._file = open(self._filepath, self._mode)

    def read(self, bytes_num=-1):
        return self._file.read(bytes_num)

    def write(self, data):
        return self._file.write(data)

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()

    def size(self):
        return os.path.getsize(self._filepath) if os.path.exists(self._filepath) else 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

