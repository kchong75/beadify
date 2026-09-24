"""Image loading, resizing and background detection."""

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from scipy import ndimage
from skimage import color as skcolor

from .palette import rgb_to_lab

RESAMPLERS = {"lanczos": Image.LANCZOS, "box": Image.BOX}


def parse_hex_color(text):
    """Parse '#RRGGBB' / 'RRGGBB' into an (r, g, b) tuple."""
    t = text.strip().lstrip("#")
    if len(t) != 6:
        raise ValueError("expected a color like #RRGGBB, got %r" % text)
    return tuple(int(t[i : i + 2], 16) for i in (0, 2, 4))


def load_image(path):
    """Open an image, apply its EXIF orientation and return it as RGBA."""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im.convert("RGBA")


def flatten_on_white(im):
    """Composite an RGBA image onto a white background and return it as RGB."""
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def grid_size(src_size, size=100, width=None, height=None):
    """Decide the bead grid (cols, rows) and the source crop box.

    * ``width`` and ``height`` both given: the source is center-cropped to that
      aspect ratio, so the picture is never stretched.
    * only one of them given: the other follows the source aspect ratio.
    * neither: the longest side is ``size`` and the aspect ratio is kept.

    Returns ``((cols, rows), crop_box)``; ``crop_box`` is None when no crop is needed.
    """
    sw, sh = src_size
    for name, v in (("size", size), ("width", width), ("height", height)):
        if v is not None and v < 1:
            raise ValueError("%s must be >= 1" % name)
    if width and height:
        target = width / height
        if sw / sh > target:  # source too wide -> crop left/right
            cw = int(round(sh * target))
            x0 = (sw - cw) // 2
            box = (x0, 0, x0 + cw, sh)
        else:  # source too tall -> crop top/bottom
            ch = int(round(sw / target))
            y0 = (sh - ch) // 2
            box = (0, y0, sw, y0 + ch)
        return (width, height), box
    if width:
        return (width, max(1, int(round(width * sh / sw)))), None
    if height:
        return (max(1, int(round(height * sw / sh))), height), None
    if sw >= sh:
        return (size, max(1, int(round(size * sh / sw)))), None
    return (max(1, int(round(size * sw / sh))), size), None


def resize_rgba(im, cols, rows, box=None, resample="lanczos"):
    """Downscale an RGBA image to (cols, rows) without color bleeding from transparent pixels.

    Returns ``(rgb, alpha)``: rgb is a uint8 (rows, cols, 3) array and alpha a
    float (rows, cols) array in [0, 1].
    """
    method = RESAMPLERS[resample]
    if box is not None:
        im = im.crop(box)
    arr = np.asarray(im, dtype=np.float32)
    alpha = arr[..., 3] / 255.0
    if alpha.min() >= 0.999:  # fully opaque: let Pillow do the work directly
        rgb = np.asarray(im.convert("RGB").resize((cols, rows), method))
        return rgb, np.ones((rows, cols), dtype=np.float32)

    # Premultiply so fully transparent pixels (often black) do not darken the edges.
    chans = [arr[..., i] * alpha for i in range(3)] + [alpha]
    small = [
        np.asarray(Image.fromarray(c.astype(np.float32), mode="F").resize((cols, rows), method))
        for c in chans
    ]
    a = np.clip(small[3], 0.0, 1.0)
    safe = np.maximum(a, 1e-6)
    rgb = np.stack([np.clip(small[i] / safe, 0, 255) for i in range(3)], axis=-1)
    return np.rint(rgb).astype(np.uint8), a


def enhance(rgb, saturation=1.0, contrast=1.0):
    """Optionally boost saturation / contrast of the small RGB grid before matching."""
    if saturation == 1.0 and contrast == 1.0:
        return rgb
    im = Image.fromarray(rgb, "RGB")
    if saturation != 1.0:
        im = ImageEnhance.Color(im).enhance(saturation)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    return np.asarray(im)


def border_pixels(arr):
    """Return the pixels along the outer edge of an (H, W, C) array as (N, C)."""
    return np.concatenate([arr[0], arr[-1], arr[1:-1, 0], arr[1:-1, -1]], axis=0)


def detect_background(rgb, alpha, mode="auto", bg_color=None, tolerance=12.0):
    """Return a boolean (rows, cols) mask that is True for cells that should stay empty.

    Modes:
      * ``none``  - never remove anything (transparent cells are still empty).
      * ``auto``  - use transparency when present; otherwise flood-fill from the
        image border over cells close to the dominant border color, provided the
        border is reasonably uniform.
    An explicit ``bg_color`` overrides the border color estimate.
    """
    empty = alpha < 0.5
    if mode == "none":
        return empty
    if mode != "auto":
        raise ValueError("bg mode must be 'auto' or 'none'")
    if empty.any():  # real transparency: trust it
        return empty

    lab = rgb_to_lab(rgb)
    if bg_color is not None:
        ref = rgb_to_lab(np.array(bg_color, dtype=np.uint8))
    else:
        ref = np.median(border_pixels(lab), axis=0)
        border_de = skcolor.deltaE_ciede2000(border_pixels(lab), ref[None, :])
        if np.mean(border_de < tolerance) < 0.6:  # border not uniform: no clear background
            return empty
    de = skcolor.deltaE_ciede2000(lab, ref[None, None, :])
    candidate = de < tolerance
    labels, _ = ndimage.label(candidate)  # 4-connectivity by default
    touching = np.unique(border_pixels(labels))
    touching = touching[touching != 0]
    bg = np.isin(labels, touching)
    return bg | empty
