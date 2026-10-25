"""Pixel-only editing of the three observed PSE direct-RGBA TM2 logos.

SLPS 00248ad0 reads file+0x10+picture_header_size; the original headers,
dimensions, transfer configuration and allocation size must stay unchanged.
This is not a general-purpose TM2 encoder.
"""

import hashlib
import io
import struct

from PIL import Image


ASSETS = {
    'logo_ep1': ((136, 90), '3c8d85dd075946d611f9075d0c46b3d69e9692616e76b358c7cc0c1feae24b85'),
    'logo_ep2': ((136, 90), 'c46b0cb30c74a7f07565f035c6533c6e76643a488ea9a59fb3b8bad5be470c0c'),
    'logo_pp': ((128, 90), 'b590e2b7425c7864312c5da51e82f12944a78547b3c216b9ac883f45c89265d1'),
}


def validate(data, name):
    dimensions, expected = ASSETS[name]
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'{name}: original TM2 SHA-256 mismatch')
    if data[:16] != b'TIM2\x04\x00\x01\x00'+bytes(8):
        raise ValueError(f'{name}: unexpected TM2 file header')
    total, clut, size, header, colors, fmt, mip, clut_type, kind, w, h = struct.unpack_from('<3I2H4B2H', data, 16)
    if (total != len(data)-16 or (w, h) != dimensions or size != w*h*4
            or len(data) != 64+size or (clut, header, colors, fmt, mip, clut_type, kind) != (0, 48, 0, 0, 1, 0, 3)
            or max(data[67::4]) > 128):
        raise ValueError(f'{name}: unsupported TM2 picture layout')


def extract(data, name):
    validate(data, name)
    pixels = bytearray(data[64:])
    pixels[3::4] = bytes(alpha*255//128 for alpha in pixels[3::4])
    image = Image.frombytes('RGBA', ASSETS[name][0], bytes(pixels))
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def rebuild(data, png, name):
    validate(data, name)
    with Image.open(io.BytesIO(png)) as image:
        if image.format != 'PNG' or image.size != ASSETS[name][0] or getattr(image, 'n_frames', 1) != 1:
            raise ValueError(f'{name}: expected one {ASSETS[name][0]} PNG')
        if 'A' not in image.getbands() and 'transparency' not in image.info:
            raise ValueError(f'{name}: preserve the PNG alpha channel')
        pixels = bytearray(image.convert('RGBA').tobytes())
    pixels[3::4] = bytes((alpha*128+127)//255 for alpha in pixels[3::4])
    return data[:64]+bytes(pixels)
