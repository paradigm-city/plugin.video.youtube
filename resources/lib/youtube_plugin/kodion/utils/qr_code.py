# -*- coding: utf-8 -*-
"""

    Copyright (C) 2016-2025 plugin.video.youtube

    SPDX-License-Identifier: GPL-2.0-only
    See LICENSES/GPL-2.0-only for more information.

    Minimal QR Code (ISO/IEC 18004) encoder, byte mode only, versions 1-10,
    with a PNG writer, used to display sign-in URLs on screen.
"""

from __future__ import absolute_import, division, unicode_literals

import struct
import zlib


# Error correction level: (format bits, ecc codewords per block by version,
#                          number of ecc blocks by version)
_ECC_LEVELS = {
    'L': (1,
          (None, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18),
          (None, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4)),
    'M': (0,
          (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26),
          (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)),
}
_MIN_VERSION = 1
_MAX_VERSION = 10

_MASKS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


def _num_raw_data_modules(version):
    result = (16 * version + 128) * version + 64
    if version >= 2:
        num_align = version // 7 + 2
        result -= (25 * num_align - 10) * num_align - 55
        if version >= 7:
            result -= 36
    return result


def _num_data_codewords(version, ecl):
    _, ecc_len, num_blocks = _ECC_LEVELS[ecl]
    return (_num_raw_data_modules(version) // 8
            - ecc_len[version] * num_blocks[version])


def _alignment_positions(version, size):
    if version == 1:
        return []
    num_align = version // 7 + 2
    step = (version * 8 + num_align * 3 + 5) // (num_align * 4 - 4) * 2
    result = [size - 7 - idx * step for idx in range(num_align - 1)]
    result.append(6)
    return result[::-1]


def _gf_multiply(x, y):
    z = 0
    for idx in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> idx) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for idx in range(degree):
            result[idx] = _gf_multiply(result[idx], root)
            if idx + 1 < degree:
                result[idx] ^= result[idx + 1]
        root = _gf_multiply(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for idx, coef in enumerate(divisor):
            result[idx] ^= _gf_multiply(coef, factor)
    return result


def _encode_data(data, version, ecl):
    bits = []

    def append_bits(value, length):
        bits.extend((value >> idx) & 1 for idx in range(length - 1, -1, -1))

    # Byte mode indicator and character count
    append_bits(0b0100, 4)
    append_bits(len(data), 8 if version < 10 else 16)
    for byte in data:
        append_bits(byte, 8)

    capacity = _num_data_codewords(version, ecl) * 8
    append_bits(0, min(4, capacity - len(bits)))
    append_bits(0, -len(bits) % 8)
    pad_byte = 0xEC
    while len(bits) < capacity:
        append_bits(pad_byte, 8)
        pad_byte ^= 0xEC ^ 0x11

    codewords = [0] * (len(bits) // 8)
    for idx, bit in enumerate(bits):
        codewords[idx >> 3] |= bit << (7 - (idx & 7))

    # Split into blocks, append error correction codewords and interleave
    _, ecc_len, num_blocks = _ECC_LEVELS[ecl]
    block_ecc_len = ecc_len[version]
    num_blocks = num_blocks[version]
    raw_codewords = _num_raw_data_modules(version) // 8
    num_short_blocks = num_blocks - raw_codewords % num_blocks
    short_block_len = raw_codewords // num_blocks
    divisor = _rs_divisor(block_ecc_len)

    blocks = []
    offset = 0
    for block_idx in range(num_blocks):
        length = short_block_len - block_ecc_len + (
            0 if block_idx < num_short_blocks else 1
        )
        block = codewords[offset:offset + length]
        offset += length
        ecc = _rs_remainder(block, divisor)
        if block_idx < num_short_blocks:
            block.append(0)
        blocks.append(block + ecc)

    result = []
    for idx in range(len(blocks[0])):
        for block_idx, block in enumerate(blocks):
            if (idx != short_block_len - block_ecc_len
                    or block_idx >= num_short_blocks):
                result.append(block[idx])
    return result


class _Matrix(object):
    def __init__(self, version):
        self.version = version
        self.size = size = version * 4 + 17
        self.modules = [[False] * size for _ in range(size)]
        self.function = [[False] * size for _ in range(size)]

    def set_function(self, x, y, dark):
        self.modules[y][x] = dark
        self.function[y][x] = True

    def draw_function_patterns(self):
        size = self.size
        for idx in range(size):
            self.set_function(6, idx, idx % 2 == 0)
            self.set_function(idx, 6, idx % 2 == 0)

        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x = cx + dx
                    y = cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        dist = max(abs(dx), abs(dy))
                        self.set_function(x, y, dist not in (2, 4))

        positions = _alignment_positions(self.version, size)
        last = len(positions) - 1
        for i, cx in enumerate(positions):
            for j, cy in enumerate(positions):
                if ((i == 0 and j == 0)
                        or (i == 0 and j == last)
                        or (i == last and j == 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set_function(cx + dx, cy + dy,
                                          max(abs(dx), abs(dy)) != 1)

        # Reserve format bit areas, real values are drawn after masking
        self.draw_format_bits(0, 0)

        if self.version >= 7:
            remainder = self.version
            for _ in range(12):
                remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25)
            bits = self.version << 12 | remainder
            for idx in range(18):
                dark = (bits >> idx) & 1 == 1
                a = size - 11 + idx % 3
                b = idx // 3
                self.set_function(a, b, dark)
                self.set_function(b, a, dark)

    def draw_format_bits(self, ecl_bits, mask):
        data = ecl_bits << 3 | mask
        remainder = data
        for _ in range(10):
            remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
        bits = (data << 10 | remainder) ^ 0x5412

        def bit(idx):
            return (bits >> idx) & 1 == 1

        size = self.size
        for idx in range(6):
            self.set_function(8, idx, bit(idx))
        self.set_function(8, 7, bit(6))
        self.set_function(8, 8, bit(7))
        self.set_function(7, 8, bit(8))
        for idx in range(9, 15):
            self.set_function(14 - idx, 8, bit(idx))
        for idx in range(8):
            self.set_function(size - 1 - idx, 8, bit(idx))
        for idx in range(8, 15):
            self.set_function(8, size - 15 + idx, bit(idx))
        self.set_function(8, size - 8, True)

    def draw_codewords(self, codewords):
        size = self.size
        num_bits = len(codewords) * 8
        idx = 0
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vert in range(size):
                y = size - 1 - vert if upward else vert
                for offset in range(2):
                    x = right - offset
                    if self.function[y][x] or idx >= num_bits:
                        continue
                    self.modules[y][x] = (
                        (codewords[idx >> 3] >> (7 - (idx & 7))) & 1 == 1
                    )
                    idx += 1
            right -= 2

    def apply_mask(self, mask):
        mask_func = _MASKS[mask]
        modules = self.modules
        function = self.function
        for y in range(self.size):
            for x in range(self.size):
                if not function[y][x] and mask_func(x, y):
                    modules[y][x] = not modules[y][x]

    def penalty_score(self):
        size = self.size
        modules = self.modules
        columns = [[modules[y][x] for y in range(size)] for x in range(size)]
        score = 0

        finder_like = ('10111010000', '00001011101')
        for line in modules + columns:
            run_colour = None
            run_length = 0
            for dark in line:
                if dark == run_colour:
                    run_length += 1
                    if run_length == 5:
                        score += 3
                    elif run_length > 5:
                        score += 1
                else:
                    run_colour = dark
                    run_length = 1
            text = ''.join('1' if dark else '0' for dark in line)
            text = ''.join(('0000', text, '0000'))
            for pattern in finder_like:
                start = text.find(pattern)
                while start != -1:
                    score += 40
                    start = text.find(pattern, start + 1)

        for y in range(size - 1):
            for x in range(size - 1):
                dark = modules[y][x]
                if (dark == modules[y][x + 1]
                        == modules[y + 1][x] == modules[y + 1][x + 1]):
                    score += 3

        dark_count = sum(sum(row) for row in modules)
        total = size * size
        score += (abs(dark_count * 20 - total * 10) + total - 1) // total * 10
        return score


def encode(text, ecl='M', mask=None):
    """
    Encode text as a QR Code.
    Returns a square list of rows, each a list of bools where True is dark.
    """
    if ecl not in _ECC_LEVELS:
        raise ValueError('Unsupported error correction level: %r' % ecl)
    data = bytearray(text.encode('utf-8'))

    for version in range(_MIN_VERSION, _MAX_VERSION + 1):
        count_bits = 8 if version < 10 else 16
        if 4 + count_bits + len(data) * 8 <= (
                _num_data_codewords(version, ecl) * 8):
            break
    else:
        raise ValueError('Data too long for QR Code: %d bytes' % len(data))

    codewords = _encode_data(data, version, ecl)
    ecl_bits = _ECC_LEVELS[ecl][0]

    matrix = _Matrix(version)
    matrix.draw_function_patterns()
    matrix.draw_codewords(codewords)

    if mask is None:
        best_score = None
        for candidate in range(len(_MASKS)):
            matrix.apply_mask(candidate)
            matrix.draw_format_bits(ecl_bits, candidate)
            score = matrix.penalty_score()
            if best_score is None or score < best_score:
                best_score = score
                mask = candidate
            # Masking is an XOR, so applying it again undoes it
            matrix.apply_mask(candidate)

    matrix.apply_mask(mask)
    matrix.draw_format_bits(ecl_bits, mask)
    return matrix.modules


def png_bytes(width, height, rows, colour_type=0):
    """
    Build a PNG file from unfiltered 8-bit rows of pixel data.
    colour_type 0 is greyscale (1 byte per pixel), 6 is RGBA (4 bytes).
    Returns the PNG file contents as bytes.
    """
    def chunk(chunk_type, chunk_data):
        return b''.join((
            struct.pack('>I', len(chunk_data)),
            chunk_type,
            chunk_data,
            struct.pack('>I',
                        zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF),
        ))

    return b''.join((
        b'\x89PNG\r\n\x1a\n',
        chunk(b'IHDR', struct.pack('>IIBBBBB',
                                   width, height, 8, colour_type, 0, 0, 0)),
        chunk(b'IDAT', zlib.compress(
            b''.join(b''.join((b'\x00', row)) for row in rows), 9
        )),
        chunk(b'IEND', b''),
    ))


def to_png(modules, scale=8, border=4):
    """
    Render a QR Code module matrix as an 8-bit greyscale PNG.
    Returns the PNG file contents as bytes.
    """
    pixels = (len(modules) + 2 * border) * scale
    light_border = b'\xFF' * (border * scale)

    rows = []
    blank_row = b'\xFF' * pixels
    rows.extend([blank_row] * (border * scale))
    for line in modules:
        row = b''.join(
            (b'\x00' if dark else b'\xFF') * scale
            for dark in line
        )
        row = b''.join((light_border, row, light_border))
        rows.extend([row] * scale)
    rows.extend([blank_row] * (border * scale))

    return png_bytes(pixels, pixels, rows)
