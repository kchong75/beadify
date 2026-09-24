"""Deterministic execution of an :class:`~beadify.ai.plan.EditPlan` on an image."""

import warnings

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree
from skimage import color as skcolor
from skimage.morphology import skeletonize
from skimage.segmentation import random_walker

from .plan import PlanError, Region, clean_params

WORK_SIDE = 480  # resolution of the cut-out segmentation
MAX_SIDE = 2048  # working resolution cap; the bead grid is at most ~100 cells wide anyway


def _to_lab(rgb):
    return skcolor.rgb2lab(rgb.astype(np.float64) / 255.0)


def _to_rgb(lab):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # out-of-gamut values are simply clipped
        rgb = skcolor.lab2rgb(lab)
    return np.rint(np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)


def region_mask(region, height, width):
    """Soft mask (H, W) in [0, 1] for a region; the whole image when ``region`` is None."""
    if region is None:
        return np.ones((height, width), dtype=np.float64)
    c = region.coords
    canvas = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(canvas)
    if region.shape == "polygon":
        draw.polygon([(x * width, y * height) for x, y in c["points"]], fill=255)
        x0, y0, x1, y1 = region.bbox()
        half = min((x1 - x0) * width, (y1 - y0) * height) / 2.0
    elif region.shape == "ellipse":
        box = [(c["cx"] - c["rx"]) * width, (c["cy"] - c["ry"]) * height,
               (c["cx"] + c["rx"]) * width, (c["cy"] + c["ry"]) * height]
        draw.ellipse(box, fill=255)
        half = min(c["rx"] * width, c["ry"] * height)
    else:
        draw.rectangle([c["x0"] * width, c["y0"] * height, c["x1"] * width, c["y1"] * height], fill=255)
        half = min((c["x1"] - c["x0"]) * width, (c["y1"] - c["y0"]) * height) / 2.0
    mask = np.asarray(canvas, dtype=np.float64) / 255.0
    sigma = region.feather * half * 0.5
    return ndimage.gaussian_filter(mask, sigma) if sigma > 0.5 else mask


def _masked_blur(x, weight, sigma):
    """Gaussian blur that ignores pixels where ``weight`` is 0 (transparent background)."""
    num = np.stack([ndimage.gaussian_filter(x[..., i] * weight, sigma) for i in range(x.shape[-1])], -1)
    den = ndimage.gaussian_filter(weight, sigma)[..., None]
    return num / np.maximum(den, 1e-6)


def _op_exposure(lab, p, ctx):
    out = lab.copy()
    out[..., 0] = np.minimum(out[..., 0] * p["gain"], 100.0)
    return out


def _op_contrast(lab, p, ctx):
    sel = ctx["subject"] & (ctx["mask"] > 0.5)
    pivot = float(lab[..., 0][sel].mean()) if sel.any() else float(lab[..., 0].mean())
    out = lab.copy()
    out[..., 0] = np.clip(pivot + p["factor"] * (out[..., 0] - pivot), 0.0, 100.0)
    return out


def _op_saturation(lab, p, ctx):
    out = lab.copy()
    out[..., 1:] *= p["factor"]
    return out


def _op_local_contrast(lab, p, ctx):
    sigma = max(p["radius_frac"] * max(lab.shape[:2]), 1.0)
    detail = lab - _masked_blur(lab, ctx["subject"].astype(np.float64), sigma)
    out = lab + p["amount"] * detail
    out[..., 0] = np.clip(out[..., 0], 0.0, 100.0)
    return out


def _op_colorize(lab, p, ctx):
    target = _to_lab(np.array([[p["target_rgb"]]], dtype=np.uint8))[0, 0]
    out = lab.copy()
    out[..., 1:] += p["strength"] * (target[1:] - out[..., 1:])
    out[..., 0] += p["lightness_strength"] * (target[0] - out[..., 0])
    return out


def _op_smooth(lab, p, ctx):
    size = max(3, int(round(p["radius_frac"] * max(lab.shape[:2]))) * 2 + 1)
    return np.stack([ndimage.median_filter(lab[..., i], size=size) for i in range(3)], -1)


LATE_OPS = ("cutout", "crop", "outline")

_OPS = {
    "exposure": _op_exposure,
    "contrast": _op_contrast,
    "saturation": _op_saturation,
    "local_contrast": _op_local_contrast,
    "colorize": _op_colorize,
    "smooth": _op_smooth,
}


def _thin_part_seeds(rough, fraction=0.65):
    """Subject seeds that survive in thin parts (a leg, a tail tip) of a rough outline.

    Shrinking the outline by the band width leaves nothing inside a part that is narrower than
    the band. Along the outline's medial axis, a disc of ``fraction`` of the local half-width always
    fits inside such a part, so its seeds scale with the part instead of vanishing.
    """
    dist = ndimage.distance_transform_edt(rough)
    seeds = np.zeros(rough.shape, dtype=bool)
    height, width = rough.shape
    for y, x in np.argwhere(skeletonize(rough)):
        r = fraction * dist[y, x]
        if r < 1.0:
            seeds[y, x] = True
            continue
        y0, y1, x0, x1 = max(int(y - r), 0), min(int(y + r) + 1, height), max(int(x - r), 0), min(int(x + r) + 1, width)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        seeds[y0:y1, x0:x1] |= (yy - y) ** 2 + (xx - x) ** 2 <= r * r
    return seeds & rough


def _segment(rgba, region, params):
    """Segment one subject out of ``region``'s rough outline. Returns (alpha_mask or None, note).

    The rough ``region`` becomes a trimap: well inside is subject, well outside is background, and
    the band between (``band_frac`` of the longest side) is decided by a random walker on the colors.
    ``alpha_mask`` is a float (H, W) array in [0, 1], sized to ``rgba``; ``None`` means skipped.
    """
    h, w = rgba.shape[:2]
    scale = min(1.0, WORK_SIDE / float(max(h, w)))
    sh, sw = max(8, int(round(h * scale))), max(8, int(round(w * scale)))
    small = np.asarray(Image.fromarray(rgba[..., :3]).resize((sw, sh), Image.LANCZOS))
    hard = Region(region.shape, region.coords, 0.0)
    rough = region_mask(hard, sh, sw) > 0.5
    band = max(2, int(round(params["band_frac"] * max(sh, sw))))
    fg = ndimage.binary_erosion(rough, iterations=band)
    fg |= _thin_part_seeds(rough)
    bg = ~ndimage.binary_dilation(rough, iterations=band)
    if fg.sum() < 20 or bg.sum() < 20:
        return None, "skipped: the outline is too small or fills the whole image"
    markers = np.zeros((sh, sw), dtype=np.int32)
    markers[bg], markers[fg] = 1, 2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # probabilities a hair outside [0, 1] are harmless here
        prob = random_walker(_to_lab(small) / 100.0, markers, beta=200, mode="cg_j", channel_axis=-1,
                             return_full_prob=True)[1]
    keep = prob > 0.5
    # Edge gradients alone leave a fringe where the subject and the background have similar colors, so
    # inside the uncertain band also require a pixel to be closer to the subject's colors than to the
    # background's (nearest neighbours among the seed pixels).
    lab_small = _to_lab(small)
    band_px = ~fg & ~bg
    if band_px.any():
        rng = np.random.RandomState(0)

        def sample(mask, n=4000):
            pts = lab_small[mask]
            return pts[rng.choice(len(pts), min(n, len(pts)), replace=False)]

        d_fg = cKDTree(sample(fg)).query(lab_small[band_px], k=5)[0].mean(axis=1)
        d_bg = cKDTree(sample(bg)).query(lab_small[band_px], k=5)[0].mean(axis=1)
        keep[band_px] &= d_fg < d_bg
    keep = ndimage.binary_opening(keep, iterations=1)
    labels, count = ndimage.label(keep)
    if count == 0:
        return None, "skipped: no subject found inside the outline"
    sizes = ndimage.sum(keep, labels, range(1, count + 1))
    keep = ndimage.binary_fill_holes(labels == (1 + int(np.argmax(sizes))))
    trimmed = ndimage.binary_erosion(keep, iterations=1)  # drop the one-pixel fringe of background color
    keep = trimmed if trimmed.sum() > 0.5 * keep.sum() else keep  # ...unless the subject is very thin
    soft = ndimage.gaussian_filter(keep.astype(np.float32), 1.0)
    alpha = np.asarray(Image.fromarray(soft, "F").resize((w, h), Image.BILINEAR))
    alpha = np.clip((alpha - 0.5) * 4.0 + 0.5, 0.0, 1.0)
    return alpha, "kept %.0f%% of the image as this subject" % (100.0 * (alpha > 0.5).mean())


def _crop(rgba, region, params):
    h, w = rgba.shape[:2]
    x0, y0, x1, y1 = region.bbox()
    m = params["margin_frac"]
    box = (max(int(round((x0 - m) * w)), 0), max(int(round((y0 - m) * h)), 0),
           min(int(round((x1 + m) * w)), w), min(int(round((y1 + m) * h)), h))
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return rgba, "skipped: the crop box is too small"
    return rgba[box[1] : box[3], box[0] : box[2]].copy(), "cropped to %d x %d px" % (box[2] - box[0], box[3] - box[1])


def _apply_outline(rgba, params):
    """Add a dark ring around the opaque subject. Returns (image, note)."""
    alpha = rgba[..., 3]
    subject = alpha >= 128
    if (~subject).mean() < 0.02:
        return rgba, "skipped: the image has no transparent background to outline"
    width = max(1, int(round(params["width_frac"] * max(rgba.shape[:2]))))
    rgba = np.pad(rgba, ((width, width), (width, width), (0, 0)))  # room so the ring is never cut off
    subject = np.pad(subject, width)
    dist = ndimage.distance_transform_edt(~subject)
    ring = (dist > 0) & (dist <= width)
    rgba[ring] = list(params["color_rgb"]) + [255]
    return rgba, "%d px outline" % width


def apply_plan(image, plan, max_side=MAX_SIDE):
    """Apply ``plan`` to a PIL image.

    Returns ``(enhanced_rgba, results)``; ``results`` has one dict per edit with keys
    ``index, op, applied, params, region, reason, feature, note``. Edits that are invalid are
    skipped and reported rather than aborting the run.
    """
    im = image.convert("RGBA")
    if max(im.size) > max_side:
        scale = max_side / float(max(im.size))
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    arr = np.asarray(im).copy()
    height, width = arr.shape[:2]
    subject = arr[..., 3] >= 128
    lab = _to_lab(arr[..., :3])

    results, late_edits = [], []
    for index, edit in enumerate(plan.edits, start=1):
        entry = {"index": index, "op": edit.op, "applied": False, "params": {}, "region": edit.region,
                 "reason": edit.reason, "feature": edit.feature, "note": ""}
        results.append(entry)
        try:
            params, notes = clean_params(edit.op, edit.params)
        except PlanError as exc:
            entry["note"] = "skipped: %s" % exc
            continue
        entry["params"] = params
        if edit.op in LATE_OPS:
            late_edits.append((edit, entry))  # applied after the color edits, in a fixed order
            continue
        mask = region_mask(edit.region, height, width)
        new = _OPS[edit.op](lab, params, {"subject": subject, "mask": mask})
        lab = lab * (1.0 - mask[..., None]) + new * mask[..., None]
        entry["applied"] = True
        entry["note"] = "; ".join(notes)

    arr[..., :3] = _to_rgb(lab)

    # cutout: one photo can hold several separate subjects (e.g. two pets). Each cutout edit
    # segments its own region independently against the pre-cutout image, and the kept areas are
    # unioned - a second cutout must never be able to erase what an earlier one already kept.
    cutout_edits = [(edit, entry) for edit, entry in late_edits if edit.op == "cutout"]
    if cutout_edits:
        union = np.zeros(arr.shape[:2], dtype=np.float64)
        for edit, entry in cutout_edits:
            if edit.region is None:
                entry["note"] = "skipped: this operation needs a region"
                continue
            mask, note = _segment(arr, edit.region, entry["params"])
            entry["applied"] = mask is not None
            entry["note"] = note
            if mask is not None:
                union = np.maximum(union, mask)
        if any(entry["applied"] for _, entry in cutout_edits):
            arr[..., 3] = np.rint(arr[..., 3] * union).astype(np.uint8)

    for op in ("crop", "outline"):
        for edit, entry in late_edits:
            if edit.op != op:
                continue
            if op == "outline":
                arr, note = _apply_outline(arr, entry["params"])
            elif edit.region is None:
                note = "skipped: this operation needs a region"
            else:
                arr, note = _crop(arr, edit.region, entry["params"])
            entry["applied"] = not note.startswith("skipped")
            entry["note"] = note
    return Image.fromarray(arr, "RGBA"), results
