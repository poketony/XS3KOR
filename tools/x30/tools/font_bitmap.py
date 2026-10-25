"""Pack the existing 20x24, four-plane X30 font sheets without losing the tail."""

import io


CHANNELS = ('red', 'green', 'blue', 'alpha')
GLYPH_WIDTH = 20
GLYPH_HEIGHT = 24
GRID = 32
GLYPHS = GRID * GRID
SIZE = (GLYPH_WIDTH * GRID, GLYPH_HEIGHT * GRID)
PIXEL_BYTES = GLYPHS * GLYPH_WIDTH * GLYPH_HEIGHT
TAIL_BYTES = 3072
FILE_BYTES = PIXEL_BYTES + TAIL_BYTES
QUANTIZE = bytes((value + 42) // 85 for value in range(256))


def validate_original(original):
    if len(original) != FILE_BYTES:
        raise ValueError(f'Expected a complete {FILE_BYTES}-byte font, got {len(original)}')


def read_png(data):
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or image.size != SIZE:
            raise ValueError(f'Expected a {SIZE[0]}x{SIZE[1]} PNG sheet; got {image.format} {image.size}')
        if image.mode not in ('L', 'RGB', 'RGBA', 'P'):
            raise ValueError(f'Unsupported PNG mode: {image.mode}')
        if getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Animated font sheets are not supported')
        image.load()
        # These are independent glyph planes, not an RGBA composite image.
        if image.convert('RGBA').getchannel('A').getextrema() != (255, 255):
            raise ValueError('Font sheets must be opaque; PNG transparency is not a glyph plane')
        return image.convert('L').tobytes()


def pack(original, channels):
    validate_original(original)
    if set(channels) != set(CHANNELS):
        raise ValueError('Expected exactly red, green, blue and alpha sheets')
    result = bytearray(PIXEL_BYTES)
    for plane, name in enumerate(CHANNELS):
        pixels = channels[name]
        if not isinstance(pixels, bytes) or len(pixels) != PIXEL_BYTES:
            raise ValueError(f'{name}: expected {PIXEL_BYTES} grayscale bytes')
        quantized = pixels.translate(QUANTIZE)
        for glyph in range(GLYPHS):
            x = (glyph % GRID) * GLYPH_WIDTH
            y = (glyph // GRID) * GLYPH_HEIGHT
            for row in range(GLYPH_HEIGHT):
                source = (y + row) * SIZE[0] + x
                target = (glyph * GLYPH_HEIGHT + row) * GLYPH_WIDTH
                for column, value in enumerate(quantized[source:source + GLYPH_WIDTH]):
                    result[target + column] |= value << (plane * 2)
    return bytes(result) + original[PIXEL_BYTES:]


def unpack(original):
    validate_original(original)
    channels = {}
    for plane, name in enumerate(CHANNELS):
        pixels = bytearray(PIXEL_BYTES)
        levels = bytes(((value >> (plane * 2)) & 3) * 85 for value in range(256))
        data = original[:PIXEL_BYTES].translate(levels)
        for glyph in range(GLYPHS):
            x = (glyph % GRID) * GLYPH_WIDTH
            y = (glyph // GRID) * GLYPH_HEIGHT
            for row in range(GLYPH_HEIGHT):
                source = (glyph * GLYPH_HEIGHT + row) * GLYPH_WIDTH
                target = (y + row) * SIZE[0] + x
                pixels[target:target + GLYPH_WIDTH] = data[source:source + GLYPH_WIDTH]
        channels[name] = bytes(pixels)
    return channels


def rebuild(original, pngs):
    if set(pngs) != set(CHANNELS):
        raise ValueError('Expected exactly red, green, blue and alpha PNGs')
    return pack(original, {name: read_png(pngs[name]) for name in CHANNELS})
