# -*- coding: utf-8 -*-
"""
Unit tests for the sign-in QR Code dialog (XbmcQRCodeDialog):
- Textures are written to addon data, as Kodi does not load them from temp
- One QR Code per entry, or a single QR Code with the entries listed
- Controls stay within the panel and do not overlap
- Status and footer updates, Back/Cancel handling and cleanup on close
"""
import os

import pytest
import xbmcgui
import xbmcvfs

from youtube_plugin.kodion.constants import DATA_PATH, TEMP_PATH
from youtube_plugin.kodion.ui.xbmc import xbmc_qr_code_dialog
from youtube_plugin.kodion.ui.xbmc.xbmc_qr_code_dialog import XbmcQRCodeDialog


def make_entries(count):
    return [{
        'title': 'Client %d' % idx,
        'qr': 'https://www.google.com/device?user_code=ABCD-000%d' % idx,
        'lines': ('google.com/device', '[B]ABCD-000%d[/B]' % idx),
    } for idx in range(count)]


def controls_of(dialog, control_type):
    return [control for control in dialog._window.controls
            if type(control) is control_type]


def qr_images(dialog):
    # The panel background is the only image wider than the QR Codes
    return [image for image in controls_of(dialog, xbmcgui.ControlImage)
            if image.width < 600]


def overlapping(controls):
    boxes = [(c.x, c.y, c.x + c.width, c.y + c.height) for c in controls]
    return [(a, b) for idx, a in enumerate(boxes) for b in boxes[idx + 1:]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]]


@pytest.fixture
def dialog_factory():
    dialogs = []

    def factory(entries, **kwargs):
        dialog = XbmcQRCodeDialog('Sign In', 'Message', entries,
                                  cancel_label='Cancel', **kwargs)
        dialogs.append(dialog)
        dialog.show()
        return dialog

    yield factory
    for dialog in dialogs:
        dialog.close()


class TestTextures:
    def test_written_to_addon_data(self, dialog_factory):
        dialog = dialog_factory(make_entries(2))
        texture_dir = xbmcvfs.translatePath(
            xbmc_qr_code_dialog.TEXTURE_PATH + '/'
        )
        assert texture_dir.startswith(xbmcvfs.translatePath(DATA_PATH))
        assert not texture_dir.startswith(xbmcvfs.translatePath(TEMP_PATH))

        for image in controls_of(dialog, xbmcgui.ControlImage):
            assert os.path.dirname(image.filename) == texture_dir.rstrip('\\/')
            with open(image.filename, 'rb') as texture:
                assert texture.read(8) == b'\x89PNG\r\n\x1a\n'

    def test_named_by_content(self, dialog_factory):
        entries = make_entries(2)
        first = qr_images(dialog_factory(entries))
        second = qr_images(dialog_factory(entries[:1]))
        assert first[0].filename == second[0].filename
        assert first[0].filename != first[1].filename

    def test_removed_on_close(self, dialog_factory):
        dialog = dialog_factory(make_entries(3))
        files = [image.filename
                 for image in controls_of(dialog, xbmcgui.ControlImage)]
        files.extend((dialog._window.cancel_button.focusTexture,
                      dialog._window.cancel_button.noFocusTexture))
        assert all(os.path.exists(path) for path in files)
        dialog.close()
        assert not any(os.path.exists(path) for path in files)


class TestLayout:
    @pytest.mark.parametrize('count', (1, 2, 3, 4))
    def test_qr_code_per_entry(self, dialog_factory, count):
        dialog = dialog_factory(make_entries(count))
        assert len(qr_images(dialog)) == count
        labels = [label.getLabel()
                  for label in controls_of(dialog, xbmcgui.ControlLabel)]
        for entry in make_entries(count):
            assert '[B]%s[/B]' % entry['title'] in labels
            assert all(line in labels for line in entry['lines'])

    @pytest.mark.parametrize('count', (1, 2, 3, 4))
    def test_single_qr_code(self, dialog_factory, count):
        dialog = dialog_factory(make_entries(count),
                                qr='http://192.168.1.2:50152/youtube/sign_in',
                                qr_lines=('192.168.1.2:50152',))
        assert len(qr_images(dialog)) == 1
        labels = [label.getLabel()
                  for label in controls_of(dialog, xbmcgui.ControlLabel)]
        assert '192.168.1.2:50152' in labels
        assert 'google.com/device    [B]ABCD-0000[/B]' in labels

    @pytest.mark.parametrize('single_qr', (False, True))
    @pytest.mark.parametrize('count', (1, 2, 3, 4))
    def test_controls_fit_and_do_not_overlap(self, dialog_factory,
                                             count, single_qr):
        kwargs = {'qr': 'http://192.168.1.2:50152/'} if single_qr else {}
        dialog = dialog_factory(make_entries(count), **kwargs)
        controls = dialog._window.controls
        panel = controls[0]
        for control in controls:
            assert panel.x <= control.x
            assert control.x + control.width <= panel.x + panel.width
            assert panel.y <= control.y
            assert control.y + control.height <= panel.y + panel.height
        assert overlapping(controls[1:]) == []


class TestInteraction:
    def test_status_and_footer(self, dialog_factory):
        dialog = dialog_factory(make_entries(2))
        dialog.set_status(1, 'Approved')
        dialog.set_status(5, 'ignored')
        dialog.set_footer('Expires in 9:59')
        assert dialog._status_labels[1].getLabel() == 'Approved'
        assert dialog._status_labels[0].getLabel() == ''
        assert dialog._footer_label.getLabel() == 'Expires in 9:59'

    def test_shown_with_cancel_focused(self, dialog_factory):
        dialog = dialog_factory(make_entries(1))
        window = dialog._window
        assert window.shown
        assert window.getFocus() is window.cancel_button
        assert window.cancel_button.getLabel() == 'Cancel'
        assert dialog.is_aborted() is False

    @pytest.mark.parametrize('action_id', (10, 92))
    def test_back_aborts(self, dialog_factory, action_id):
        dialog = dialog_factory(make_entries(1))
        window = dialog._window
        window.onAction(xbmcgui.Action(action_id))
        assert window.closed
        assert dialog.is_aborted() is True

    def test_other_actions_ignored(self, dialog_factory):
        dialog = dialog_factory(make_entries(1))
        dialog._window.onAction(xbmcgui.Action(7))  # Select
        assert dialog.is_aborted() is False

    def test_cancel_button_aborts(self, dialog_factory):
        dialog = dialog_factory(make_entries(1))
        window = dialog._window
        window.onControl(window.cancel_button)
        assert window.closed
        assert dialog.is_aborted() is True

    def test_context_manager(self):
        with XbmcQRCodeDialog('Sign In', 'Message', make_entries(1)) as dialog:
            window = dialog._window
            assert window.shown
        assert window.closed
        assert dialog.is_aborted() is True
