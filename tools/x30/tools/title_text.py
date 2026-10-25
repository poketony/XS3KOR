"""Five title-menu labels, constrained by SLPS 00a811a0's UV/TEX0 writes.

PSMT8/TBW16, upload CT32/DBW8. TEX0 CBP-TBP=0x308: CLUT at CT32
(0,112). Text UVs cover x=0..120, rows 0,1,2,4,5 of 18 pixels; highlighted
backgrounds at y=112 and y=129 are deliberately outside the edit regions.
"""

import hashlib
import io


SOURCE_SHA256 = '2ed9c9118369c20509d849e0c81208b26427ea3ffd2e31a2ee98dfa96bdb7d72'
LABELS = ('new_game', 'continue', 'data', 'disc1', 'disc2')
ROWS = (0, 1, 2, 4, 5)
WIDTH, HEIGHT = 120, 18


def validate(data):
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('titleobj.xtx original SHA-256 mismatch')


def offsets(row):
    result = []
    for y in range(row*HEIGHT, (row+1)*HEIGHT):
        for x in range(WIDTH):
            linear = ((y & ~15)*1024 + (x & ~15)*2
                      + ((((y & ~3) >> 1)+(y & 1)) & 7)*2048
                      + ((x+(((y+2) >> 2 & 1)*4)) & 7)*4
                      + ((y >> 1) & 1) + ((x >> 2) & 2))
            cx, cy = linear//4 % 512, linear//2048
            if cx >= 72 or cy >= 128:
                raise ValueError('Title label pixel outside upload')
            result.append(80+(cy*72+cx)*4+linear % 4)
    return result


def palette(data):
    result = []
    for index in range(256):
        stored = (index & ~24) | ((index & 8) << 1) | ((index & 16) >> 1)
        start = 80+((112+stored//16)*72+stored % 16)*4
        r, g, b, a = data[start:start+4]
        result.append((r, g, b, min(255, a*255//128)))
    return result


def png_bytes(pixels):
    from PIL import Image
    image = Image.new('RGBA', (WIDTH, HEIGHT))
    image.putdata(pixels)
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def extract(data):
    validate(data)
    colors = palette(data)
    return {name: png_bytes([colors[data[offset]] for offset in offsets(row)])
            for row, name in zip(ROWS, LABELS)}


def rebuild(data, images):
    from PIL import Image
    validate(data)
    if set(images) != set(LABELS):
        raise ValueError('Exactly the five title label PNGs are required')
    colors = palette(data)
    output = bytearray(data)
    cache, details = {}, []
    for row, name in zip(ROWS, LABELS):
        with Image.open(io.BytesIO(images[name])) as image:
            if image.format != 'PNG' or image.size != (WIDTH, HEIGHT) or getattr(image, 'n_frames', 1) != 1:
                raise ValueError(f'{name}: expected one {WIDTH}x{HEIGHT} PNG')
            if 'A' not in image.getbands() and 'transparency' not in image.info:
                raise ValueError(f'{name}: preserve the PNG alpha channel')
            pixels = list(image.convert('RGBA').getdata())
        changed, quantized, max_error = 0, 0, 0
        for offset, pixel in zip(offsets(row), pixels):
            old = data[offset]
            # Keep duplicate-color indices and hidden source data unchanged.
            if pixel == colors[old]:
                continue
            if pixel not in cache:
                distances = [sum((a-b)**2 for a, b in zip(pixel, color)) for color in colors]
                index = min(range(256), key=distances.__getitem__)
                cache[pixel] = index, distances[index]
            index, error = cache[pixel]
            output[offset] = index
            changed += index != old
            quantized += error != 0
            max_error = max(max_error, error)
        details.append({'label': name, 'changed_pixels': changed, 'quantized_pixels': quantized,
                        'max_rgba_squared_error': max_error})
    return bytes(output), details
