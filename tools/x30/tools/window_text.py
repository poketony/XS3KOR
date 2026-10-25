"""Battle HUD labels from SLPS table0 at 004016b8 (20-byte sprite records).

002ce7b8/002ceff0 consume x/y/w/h/relative-CBP; 0023a660 binds PSMT8,
TBW16. The XTX upload is CT32, DBW8, 384x128. Only label indices change;
CLUTs, font glyphs, portraits and all other bytes stay in their own original.
"""

import hashlib
import io


SOURCES = {
    'window0': '95698e621ac7ab3571acd07cf676e786ff86c0e48937e259939a013b3286d760',
    'window1': '0b96468eac34cc86aedfcc5e46e109b9fd499cfeb5c48a04ba8e83a18000ded4',
    'window2': 'ca2b3fdb5d1995e71c7abb2d2a8a55a73d13b779c316f1122d8fde82b24bd3d1',
}
# Label: (sprite ID, texture rectangle, relative CBP).
LABELS = {
    'enemy_info': (18, (513, 54, 87, 17), 0x3b8),
    'boost': (19, (600, 54, 67, 17), 0x3b8),
    'command': (20, (667, 54, 101, 17), 0x3b8),
    'boost_red': (21, (513, 71, 61, 17), 0x3b8),
    'stock': (22, (574, 71, 67, 17), 0x3b8),
    'player': (27, (398, 128, 92, 10), 0x364),
    'enemy': (28, (398, 138, 92, 10), 0x364),
    'anima': (32, (513, 114, 67, 15), 0x39c),
    'act_large': (42, (322, 175, 59, 15), 0x370),
    'act_small': (101, (644, 176, 44, 15), 0x38c),
}
# Actual upload coordinates for the five 16x16 CSM1 CLUTs.
CLUTS = {0x3b8: (352, 112), 0x364: (208, 96), 0x39c: (304, 112),
         0x370: (224, 96), 0x38c: (272, 112)}


def validate(data, variant):
    if variant not in SOURCES or hashlib.sha256(data).hexdigest() != SOURCES[variant]:
        raise ValueError(f'{variant}.xtx original SHA-256 mismatch')


def offsets(rect):
    x0, y0, width, height = rect
    result = []
    for y in range(y0, y0+height):
        for x in range(x0, x0+width):
            linear = ((y & ~15)*1024 + (x & ~15)*2
                      + ((((y & ~3) >> 1)+(y & 1)) & 7)*2048
                      + ((x+(((y+2) >> 2 & 1)*4)) & 7)*4
                      + ((y >> 1) & 1) + ((x >> 2) & 2))
            cx, cy = linear//4 % 512, linear//2048
            if cx >= 384 or cy >= 128:
                raise ValueError('Window label pixel outside upload')
            result.append(80+(cy*384+cx)*4+linear % 4)
    return result


def palette_offsets(cbp):
    x, y = CLUTS[cbp]
    result = []
    for index in range(256):
        stored = (index & ~24) | ((index & 8) << 1) | ((index & 16) >> 1)
        result.append(80+((y+stored//16)*384+x+stored % 16)*4)
    return result


def palette(data, cbp):
    result = []
    for start in palette_offsets(cbp):
        r, g, b, a = data[start:start+4]
        result.append((r, g, b, min(255, a*255//128)))
    return result


def png_bytes(size, pixels):
    from PIL import Image
    image = Image.new('RGBA', size)
    image.putdata(pixels)
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def extract(data, variant):
    validate(data, variant)
    result = {}
    for name, (_, rect, cbp) in LABELS.items():
        colors = palette(data, cbp)
        result[name] = png_bytes(rect[2:], [colors[data[pos]] for pos in offsets(rect)])
    return result


def rebuild(data, images, variant):
    from PIL import Image
    validate(data, variant)
    if set(images) != set(LABELS):
        raise ValueError('Exactly the ten window label PNGs are required')
    output, details, cache = bytearray(data), [], {}
    for name, (_, rect, cbp) in LABELS.items():
        with Image.open(io.BytesIO(images[name])) as image:
            if image.format != 'PNG' or image.size != rect[2:] or getattr(image, 'n_frames', 1) != 1:
                raise ValueError(f'{name}: expected one {rect[2]} PNG')
            if 'A' not in image.getbands() and 'transparency' not in image.info:
                raise ValueError(f'{name}: preserve the PNG alpha channel')
            pixels = list(image.convert('RGBA').getdata())
        colors = palette(data, cbp)
        changed, quantized, max_error = 0, 0, 0
        for pos, pixel in zip(offsets(rect), pixels):
            old = data[pos]
            # Duplicate palette indices and hidden source pixels must roundtrip.
            if pixel == colors[old]:
                continue
            key = cbp, pixel
            if key not in cache:
                distances = [sum((a-b)**2 for a, b in zip(pixel, color)) for color in colors]
                index = min(range(256), key=distances.__getitem__)
                cache[key] = index, distances[index]
            index, error = cache[key]
            output[pos] = index
            changed += index != old
            quantized += error != 0
            max_error = max(max_error, error)
        details.append({'label': name, 'changed_pixels': changed, 'quantized_pixels': quantized,
                        'max_rgba_squared_error': max_error})
    return bytes(output), details
