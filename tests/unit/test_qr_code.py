# -*- coding: utf-8 -*-
"""
Unit tests for the QR Code encoder and PNG writer (kodion.utils.qr_code):
- Matrices match reference fingerprints for versions 1-10, levels L and M
- Version selection, automatic mask selection and size limits
- Function patterns and format information
- PNG output for QR Codes and solid textures
"""
import hashlib
import struct
import zlib

import pytest

from youtube_plugin.kodion.utils import qr_code


def fingerprint(modules):
    rows = '\n'.join(''.join('1' if dark else '0' for dark in row)
                     for row in modules)
    return hashlib.sha1(rows.encode('ascii')).hexdigest()[:16]


def full_capacity_text(version, ecl):
    """Data that exactly fills a version, leaving no room for padding"""
    count_bits = 8 if version < 10 else 16
    length = (qr_code._num_data_codewords(version, ecl) * 8
              - 4 - count_bits) // 8
    return ''.join(chr(48 + (idx * 7) % 75) for idx in range(length))


def read_png(data):
    """Minimal PNG reader for the files written by qr_code.png_bytes"""
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8
    chunks = {}
    while pos < len(data):
        length, = struct.unpack('>I', data[pos:pos + 4])
        chunk_type = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        crc, = struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])
        assert crc == zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        chunks[chunk_type] = chunk_data
        pos += 12 + length
    width, height, depth, colour_type = struct.unpack(
        '>IIBB', chunks[b'IHDR'][:10]
    )
    raw = zlib.decompress(chunks[b'IDAT'])
    channels = {0: 1, 6: 4}[colour_type]
    stride = width * channels + 1
    rows = [raw[idx * stride:(idx + 1) * stride] for idx in range(height)]
    assert all(row[0] == 0 for row in rows), 'rows must be unfiltered'
    assert b'IEND' in chunks
    return width, height, depth, colour_type, [row[1:] for row in rows]


# Fingerprints of encode(full_capacity_text(version, ecl), ecl, mask).
# Generated with this encoder and verified to be identical to the matrices
# produced by the segno QR Code library for the same version, level and mask.
REFERENCE_FINGERPRINTS = (
    (1, 'L', 0, 'b39f7fc979df8fbb'),
    (1, 'L', 3, '759601a7e8afa87d'),
    (1, 'L', 7, 'aa489318ea56df3a'),
    (1, 'M', 0, '455e3fa5db50e602'),
    (1, 'M', 3, '98a8729081900f11'),
    (1, 'M', 7, '60a26ef1bb8671a0'),
    (2, 'L', 0, '5860e730031640c5'),
    (2, 'L', 3, '71e941e0dd5e06bb'),
    (2, 'L', 7, '96c9634e35112dbe'),
    (2, 'M', 0, 'b99dd4459b8b3768'),
    (2, 'M', 3, '37483bf42525f514'),
    (2, 'M', 7, '739406f6d25b9f98'),
    (5, 'L', 0, '3dba96a21c8a04aa'),
    (5, 'L', 3, '36e62633c19c7a1b'),
    (5, 'L', 7, '81b5536b6bb7d852'),
    (5, 'M', 0, '2403afa8000d1706'),
    (5, 'M', 3, 'cd45ca799d433eb0'),
    (5, 'M', 7, '77f9816079d14669'),
    (7, 'L', 0, '6a63413a2cc76074'),
    (7, 'L', 3, 'b2f379d2df7466d3'),
    (7, 'L', 7, '6e794f62e325b80f'),
    (7, 'M', 0, '380cc2db7f61fff5'),
    (7, 'M', 3, '15181f1c638eba9d'),
    (7, 'M', 7, '01969b06b08c7f51'),
    (10, 'L', 0, '65b6d2e2a2d82772'),
    (10, 'L', 3, '6fee284b169182be'),
    (10, 'L', 7, '006976245272b893'),
    (10, 'M', 0, '840a41d1b6420118'),
    (10, 'M', 3, '35e9ea23e38cc90e'),
    (10, 'M', 7, '3eb306519cdc4313'),
)

SIGN_IN_URL = 'https://www.google.com/device?user_code=ABCD-EFGH'


class TestEncode:
    @pytest.mark.parametrize('version,ecl,mask,expected',
                             REFERENCE_FINGERPRINTS)
    def test_matches_reference(self, version, ecl, mask, expected):
        modules = qr_code.encode(full_capacity_text(version, ecl), ecl, mask)
        assert len(modules) == version * 4 + 17
        assert fingerprint(modules) == expected

    def test_sign_in_url(self):
        modules = qr_code.encode(SIGN_IN_URL)
        assert len(modules) == 33  # version 4
        assert fingerprint(modules) == 'c0901dc3b073552b'

    @pytest.mark.parametrize('version', range(1, 10))
    def test_smallest_version_is_chosen(self, version):
        text = full_capacity_text(version, 'M')
        assert len(qr_code.encode(text)) == version * 4 + 17
        # One more byte no longer fits, so the next version is used
        assert len(qr_code.encode(text + 'x')) == version * 4 + 21

    def test_too_long(self):
        with pytest.raises(ValueError):
            qr_code.encode(full_capacity_text(10, 'M') + 'x')

    def test_unsupported_error_correction_level(self):
        with pytest.raises(ValueError):
            qr_code.encode('text', 'H')

    def test_automatic_mask_is_lowest_penalty(self):
        text = SIGN_IN_URL
        scores = []
        for mask in range(8):
            matrix = qr_code._Matrix(4)
            matrix.modules = qr_code.encode(text, 'M', mask)
            scores.append(matrix.penalty_score())
        auto = qr_code.encode(text)
        assert auto == qr_code.encode(text, 'M', scores.index(min(scores)))

    def test_finder_and_timing_patterns(self):
        modules = qr_code.encode(SIGN_IN_URL)
        size = len(modules)
        finder = [
            [max(abs(x - 3), abs(y - 3)) not in (2, 4) for x in range(7)]
            for y in range(7)
        ]
        for left, top in ((0, 0), (size - 7, 0), (0, size - 7)):
            assert [row[left:left + 7]
                    for row in modules[top:top + 7]] == finder
        for idx in range(8, size - 8):
            assert modules[6][idx] == (idx % 2 == 0)
            assert modules[idx][6] == (idx % 2 == 0)
        # Always dark module
        assert modules[size - 8][8] is True

    @pytest.mark.parametrize('ecl,ecl_bits', (('L', 1), ('M', 0)))
    @pytest.mark.parametrize('mask', range(8))
    def test_format_information(self, ecl, ecl_bits, mask):
        modules = qr_code.encode('format', ecl, mask)
        size = len(modules)
        # First copy, read around the top left finder pattern
        positions = ([(8, idx) for idx in range(6)]
                     + [(8, 7), (8, 8), (7, 8)]
                     + [(14 - idx, 8) for idx in range(9, 15)])
        bits = sum(modules[y][x] << idx
                   for idx, (x, y) in enumerate(positions))
        # Second copy, split between the other two finder patterns
        positions = ([(size - 1 - idx, 8) for idx in range(8)]
                     + [(8, size - 15 + idx) for idx in range(8, 15)])
        bits_copy = sum(modules[y][x] << idx
                        for idx, (x, y) in enumerate(positions))
        assert bits == bits_copy
        assert (bits ^ 0x5412) >> 10 == ecl_bits << 3 | mask


class TestPng:
    def test_qr_code_png(self):
        modules = qr_code.encode(SIGN_IN_URL)
        scale, border = 4, 4
        data = qr_code.to_png(modules, scale=scale, border=border)
        width, height, depth, colour_type, rows = read_png(data)

        size = (len(modules) + 2 * border) * scale
        assert (width, height, depth, colour_type) == (size, size, 8, 0)
        # Quiet zone is light
        assert set(rows[0]) == {0xFF}
        assert rows[border * scale][0] == 0xFF
        # Every module is drawn as a scale x scale block
        for y, line in enumerate(modules):
            for x, dark in enumerate(line):
                pixel = rows[(y + border) * scale][(x + border) * scale]
                assert pixel == (0x00 if dark else 0xFF)

    def test_solid_rgba_png(self):
        data = qr_code.png_bytes(1, 1, (b'\x14\x14\x14\xF2',), colour_type=6)
        width, height, depth, colour_type, rows = read_png(data)
        assert (width, height, depth, colour_type) == (1, 1, 8, 6)
        assert rows == [b'\x14\x14\x14\xF2']
