# -*- coding: utf-8 -*-
"""

    Copyright (C) 2016-2025 plugin.video.youtube

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only for more information.
"""

from __future__ import absolute_import, division, unicode_literals

import os
from zlib import crc32

from ... import logging
from ...compatibility import xbmcgui
from ...constants import DATA_PATH
from ...utils.file_system import make_dirs
from ...utils.qr_code import encode, png_bytes, to_png


ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
XBFONT_CENTER_X = 0x00000002
XBFONT_CENTER_Y = 0x00000004

# Kodi does not load textures from special://temp, so use addon data instead
TEXTURE_PATH = '/'.join((DATA_PATH, 'sign_in'))

# Window coordinates are in the default 1280x720 skin resolution
_WIDTH = 1280
_PANEL = (40, 40, 1200, 640)
_MARGIN = 30
_COLUMN_MAX_WIDTH = 360
_IMAGE_MAX_SIZE = 260
_COLUMNS_TOP = 185

_TEXT_COLOUR = '0xFFFFFFFF'
_DIM_TEXT_COLOUR = '0xFFB0B0B0'

# RGBA colours of generated solid textures
_TEXTURES = {
    'panel': b'\x14\x14\x14\xF2',
    'button_focus': b'\xE0\xE0\xE0\xFF',
    'button_no_focus': b'\x40\x40\x40\xFF',
}


class _Window(xbmcgui.WindowDialog):
    def __init__(self, *_args, **_kwargs):
        super(_Window, self).__init__()
        self.aborted = False
        self.cancel_button = None

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.aborted = True
            self.close()

    def onControl(self, control):
        if control == self.cancel_button:
            self.aborted = True
            self.close()


class XbmcQRCodeDialog(object):
    """
    Non-modal window showing up to four entries, each with a title, lines of
    text and an updatable status line.

    Without a single qr, entries are shown side by side, each with its own
    QR code. With a single qr, that QR code is shown on the left and the
    entries are listed next to it.

    entries: sequence of dicts with keys
        title: str
        qr: str, data to encode as a QR code
        lines: sequence of str, shown below the title
    qr: str, optional data to encode as a single QR code for all entries
    qr_lines: sequence of str, shown below the single QR code
    """
    log = logging.getLogger(__name__)

    def __init__(self,
                 heading,
                 message,
                 entries,
                 cancel_label='',
                 qr=None,
                 qr_lines=()):
        self._heading = heading
        self._message = message
        self._entries = tuple(entries)
        self._cancel_label = cancel_label
        self._qr = qr
        self._qr_lines = tuple(qr_lines)
        self._window = None
        self._status_labels = []
        self._footer_label = None
        self._files = []

    def __enter__(self):
        self.show()
        return self

    def __exit__(self, exc_type=None, exc_val=None, exc_tb=None):
        self.close()

    def _write_texture(self, name, data):
        base_path = make_dirs(TEXTURE_PATH)
        if not base_path:
            return ''
        path = os.path.join(base_path, name)
        try:
            with open(path, 'wb') as texture_file:
                texture_file.write(data)
        except (IOError, OSError):
            self.log.exception(('Unable to write texture', 'Path: %r'), path)
            return ''
        self._files.append(path)
        return path

    def _qr_texture(self, data):
        return self._write_texture(
            'sign_in_qr_%08x.png' % (crc32(data.encode('utf-8')) & 0xFFFFFFFF),
            to_png(encode(data)),
        )

    def _solid_texture(self, name):
        return self._write_texture(
            'sign_in_%s.png' % name,
            png_bytes(1, 1, (_TEXTURES[name],), colour_type=6),
        )

    def show(self):
        window = _Window()
        controls = []

        panel_x, panel_y, panel_width, panel_height = _PANEL
        inner_x = panel_x + _MARGIN
        inner_width = panel_width - 2 * _MARGIN

        controls.append(xbmcgui.ControlImage(
            panel_x, panel_y, panel_width, panel_height,
            self._solid_texture('panel'),
        ))
        controls.append(xbmcgui.ControlLabel(
            inner_x, panel_y + 20, inner_width, 40,
            self._heading,
            textColor=_TEXT_COLOUR,
            alignment=XBFONT_CENTER_X,
        ))
        message_box = xbmcgui.ControlTextBox(
            inner_x, panel_y + 65, inner_width, 75,
            textColor=_DIM_TEXT_COLOUR,
        )
        controls.append(message_box)

        if self._qr:
            self._add_list(controls, inner_x, inner_width)
        else:
            self._add_columns(controls, inner_width)

        button_width = 180
        button_height = 45
        button_y = panel_y + panel_height - _MARGIN - button_height
        self._footer_label = xbmcgui.ControlLabel(
            inner_x, button_y, inner_width - button_width - _MARGIN,
            button_height,
            '',
            textColor=_DIM_TEXT_COLOUR,
            alignment=XBFONT_CENTER_Y,
        )
        controls.append(self._footer_label)
        cancel_button = xbmcgui.ControlButton(
            inner_x + inner_width - button_width, button_y,
            button_width, button_height,
            self._cancel_label,
            focusTexture=self._solid_texture('button_focus'),
            noFocusTexture=self._solid_texture('button_no_focus'),
            alignment=XBFONT_CENTER_X | XBFONT_CENTER_Y,
            textColor=_TEXT_COLOUR,
            focusedColor='0xFF000000',
        )
        controls.append(cancel_button)

        window.addControls(controls)
        message_box.setText(self._message)
        window.cancel_button = cancel_button
        window.setFocus(cancel_button)
        window.show()
        self._window = window

    def _add_list(self, controls, inner_x, inner_width):
        """Single QR code on the left, entries listed on the right"""
        image_size = _IMAGE_MAX_SIZE + 40
        x = inner_x
        y = _COLUMNS_TOP + 5
        controls.append(xbmcgui.ControlImage(
            x, y, image_size, image_size,
            self._qr_texture(self._qr),
        ))
        y += image_size + 5
        for line in self._qr_lines:
            controls.append(xbmcgui.ControlLabel(
                x - 10, y, image_size + 20, 30,
                line,
                textColor=_DIM_TEXT_COLOUR,
                alignment=XBFONT_CENTER_X,
            ))
            y += 30

        x = inner_x + image_size + 2 * _MARGIN
        width = inner_x + inner_width - x
        y = _COLUMNS_TOP
        row_height = min(135, 420 // (len(self._entries) or 1))
        for entry in self._entries:
            controls.append(xbmcgui.ControlLabel(
                x, y, width, 30,
                '[B]%s[/B]' % entry['title'],
                textColor=_TEXT_COLOUR,
            ))
            y += 30
            controls.append(xbmcgui.ControlLabel(
                x, y, width, 30,
                '    '.join(entry.get('lines', ())),
                textColor=_TEXT_COLOUR,
            ))
            y += 30
            status_label = xbmcgui.ControlLabel(
                x, y, width, 30,
                '',
                textColor=_DIM_TEXT_COLOUR,
            )
            controls.append(status_label)
            self._status_labels.append(status_label)
            y += row_height - 60

    def _add_columns(self, controls, inner_width):
        """Entries side by side, each with its own QR code"""
        num_entries = len(self._entries) or 1
        column_width = min(_COLUMN_MAX_WIDTH, inner_width // num_entries)
        image_size = min(_IMAGE_MAX_SIZE, column_width - 30)
        column_x = (_WIDTH - column_width * num_entries) // 2

        for entry_idx, entry in enumerate(self._entries):
            x = column_x + entry_idx * column_width
            y = _COLUMNS_TOP

            controls.append(xbmcgui.ControlLabel(
                x, y, column_width, 30,
                '[B]%s[/B]' % entry['title'],
                textColor=_TEXT_COLOUR,
                alignment=XBFONT_CENTER_X,
            ))
            y += 35

            controls.append(xbmcgui.ControlImage(
                x + (column_width - image_size) // 2, y,
                image_size, image_size,
                self._qr_texture(entry['qr']),
            ))
            y += image_size + 10

            for line in entry.get('lines', ()):
                controls.append(xbmcgui.ControlLabel(
                    x, y, column_width, 30,
                    line,
                    textColor=_TEXT_COLOUR,
                    alignment=XBFONT_CENTER_X,
                ))
                y += 30

            status_label = xbmcgui.ControlLabel(
                x, y, column_width, 30,
                '',
                textColor=_DIM_TEXT_COLOUR,
                alignment=XBFONT_CENTER_X,
            )
            controls.append(status_label)
            self._status_labels.append(status_label)

    def close(self):
        window = self._window
        if window:
            self._window = None
            window.close()
        self._status_labels = []
        self._footer_label = None
        for path in self._files:
            try:
                os.remove(path)
            except (IOError, OSError):
                pass
        self._files = []

    def is_aborted(self):
        return self._window is None or self._window.aborted

    def set_status(self, entry_idx, text):
        try:
            self._status_labels[entry_idx].setLabel(text)
        except IndexError:
            pass

    def set_footer(self, text):
        if self._footer_label:
            self._footer_label.setLabel(text)
