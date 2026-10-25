"""Fixed-size location-label pixels in ESD and ESDs embedded in map ESP.

Only the selected 256x32, 4-bit image and its dedicated palette change.
Chunk headers, animation commands, other textures and padding remain intact.
"""

from dataclasses import dataclass
import io
import struct


@dataclass(frozen=True)
class Chunk:
    offset: int
    size: int
    kind: int
    index: int
    width: int
    height: int
    format: int
    name: str


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    if end-start < 64 or struct.unpack_from('<I', data, start)[0] != end-start:
        raise ValueError('ESD/ESP container length mismatch')
    offset = start+64
    result = []
    while offset < end and any(data[offset:min(end, offset+64)]):
        if end-offset < 64:
            raise ValueError('Truncated effect header')
        size, _, kind, index, width, height, fmt = struct.unpack_from('<IIHHHHI', data, offset)
        if size < 64 or size % 64 or offset+size > end:
            raise ValueError(f'Invalid effect chunk at {offset:#x}')
        name = data[offset+20:offset+64].split(b'\0', 1)[0].decode('ascii')
        result.append(Chunk(offset, size, kind, index, width, height, fmt, name))
        offset += size
    if any(data[offset:end]):
        raise ValueError('Nonzero effect container tail')
    return result


def locations(data, names, start=0, end=None):
    rows = chunks(data, start, end)
    result = []
    for row in rows:
        if row.kind == 10:
            result.extend(locations(data, names, row.offset+64, row.offset+row.size))
        elif row.kind == 4 and row.name in names:
            if (row.index, row.width, row.height, row.format, row.size) != (3, 256, 32, 4, 4160):
                raise ValueError(f'Unsupported location image: {row.name}')
            pals = [p for p in rows if p.kind == 3 and p.index == row.index+1]
            if len(pals) != 1:
                raise ValueError('Location image must have one matching palette')
            pal = pals[0]
            if (pal.width, pal.height, pal.format, pal.size) != (8, 2, 4, 128):
                raise ValueError('Unsupported location palette')
            if pal.name != row.name[:-4]+'.clt':
                raise ValueError('Location image/palette name mismatch')
            result.append((row, pal))
    return result


def palette(data, pal):
    start = pal.offset+64
    return [tuple(data[start+i*4:start+i*4+3])+(min(255, data[start+i*4+3]*255//128),)
            for i in range(16)]


def pixels(data, image, pal):
    colors = palette(data, pal)
    raw = data[image.offset+64:image.offset+image.size]
    return [colors[value >> shift & 15] for value in raw for shift in (0, 4)]


def extract(data, image, pal):
    from PIL import Image
    result = Image.new('RGBA', (image.width, image.height))
    result.putdata(pixels(data, image, pal))
    stream = io.BytesIO()
    result.save(stream, format='PNG')
    return stream.getvalue()


def adaptive_palette(values):
    from PIL import Image
    visible = [pixel for pixel in values if pixel[3]]
    transparent = len(visible) != len(values)
    limit = 15 if transparent else 16
    reduced = visible
    if len(set(visible)) > limit:
        # Keep transparent pixels out of the quantizer so visible edges survive.
        strip = Image.new('RGBA', (len(visible), 1))
        strip.putdata(visible)
        reduced = list(strip.quantize(colors=limit, method=Image.Quantize.FASTOCTREE,
                                      dither=Image.Dither.NONE).convert('RGBA').getdata())
    reduced = [pixel[:3]+((pixel[3]*128+127)//255,) for pixel in reduced]
    colors = ([(0, 0, 0, 0)] if transparent else []) + sorted(set(reduced))
    raw = bytes(channel for color in colors for channel in color).ljust(64, b'\0')
    visible_iter = iter(color[:3]+(color[3]*255//128,) for color in reduced)
    mapped = [next(visible_iter) if pixel[3] else (0, 0, 0, 0) for pixel in values]
    return raw, mapped


def alpha_mask_palette(colors):
    """Return the ink RGB and alpha levels for a modulation-mask palette."""
    visible = [color for color in colors if color[3]]
    if not visible or len({color[:3] for color in visible}) != 1:
        return None
    alphas = sorted({0, *(color[3] for color in visible)})
    if len(alphas) < 3:
        return None
    return visible[0][:3], alphas


def preview_coverage(values):
    """Convert grayscale RGBA to black coverage, including gray shadows."""
    if any(r != g or r != b for r, g, b, a in values if a):
        raise ValueError('Alpha-mask preview must be monochrome, not a color image')
    # Equivalent appearance over white: RGB*a + 255*(1-a) = 255*(1-coverage).
    # Black retains its alpha; gray becomes translucent black, not empty space.
    return [(a*(255-r)+127)//255 for r, _, _, a in values]


def alpha_mask_values(values, colors):
    """Fit the complete text/shadow mask to the original CLUT's alpha levels."""
    mask = alpha_mask_palette(colors)
    if mask is None:
        return None
    ink, alphas = mask
    visible = [pixel for pixel in values if pixel[3]]
    rgbs = {pixel[:3] for pixel in visible}
    if rgbs.issubset({ink}):
        coverage = [pixel[3] for pixel in values]
    else:
        coverage = preview_coverage(values)
    mapped = []
    errors = []
    for amount in coverage:
        alpha = min(alphas, key=lambda value: abs(value-amount)) if amount else 0
        mapped.append(ink+(alpha,) if alpha else (0, 0, 0, 0))
        errors.append((amount-alpha)**2)
    return mapped, errors


def rebuild(data, image, pal, png):
    from PIL import Image
    with Image.open(io.BytesIO(png)) as editor:
        if editor.format != 'PNG' or editor.size != (256, 32) or getattr(editor, 'n_frames', 1) != 1:
            raise ValueError('Location image must be one 256x32 PNG')
        if 'A' not in editor.getbands() and 'transparency' not in editor.info:
            raise ValueError('Keep the location PNG alpha channel')
        values = list(editor.convert('RGBA').getdata())
    # Invisible RGB is not a color to fit, nor a visible quantization error.
    values = [pixel if pixel[3] else (0, 0, 0, 0) for pixel in values]
    original = [color if color[3] else (0, 0, 0, 0) for color in palette(data, pal)]
    colors, mapped = original, values
    mask_errors = None
    result = bytearray(data)
    if not set(values).issubset(original):
        mask = alpha_mask_values(values, original)
        if mask is not None:
            mapped, mask_errors = mask
        else:
            raw, mapped = adaptive_palette(values)
            result[pal.offset+64:pal.offset+pal.size] = raw
            colors = palette(result, pal)
    indices = {}
    for index, color in enumerate(colors):
        indices.setdefault(color, index)
    changed = quantized = max_error = 0
    for i, (pixel, target) in enumerate(zip(values, mapped)):
        offset, shift = image.offset+64+i//2, (i % 2)*4
        old = data[offset] >> shift & 15
        # Preserve duplicate indices when the existing entry still matches.
        index = old if target == colors[old] else indices[target]
        result[offset] = (result[offset] & ~(15 << shift)) | index << shift
        error = (mask_errors[i] if mask_errors is not None else
                 sum((a-b)**2 for a, b in zip(pixel, target)))
        changed += original[old] != target
        quantized += error != 0
        max_error = max(max_error, error)
    return bytes(result), dict(changed_pixels=changed, quantized_pixels=quantized,
                              max_rgba_squared_error=max_error,
                              palette_changed=result[pal.offset+64:pal.offset+pal.size]
                              != data[pal.offset+64:pal.offset+pal.size],
                              palette_mode='alpha_mask' if mask_errors is not None else 'rgba')
