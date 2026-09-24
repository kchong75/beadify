"""Human-facing outputs of the AI step: a before/after image and a written change list."""

from PIL import Image, ImageDraw

from ..render import _font
from .analyze import VIEW_BACKGROUND

FEATURE_COLOR = (255, 60, 60)
EDIT_COLOR = (40, 150, 255)


def _flatten(im, height):
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, VIEW_BACKGROUND + (255,))
    im = Image.alpha_composite(bg, im).convert("RGB")
    scale = height / float(im.height)
    return im.resize((max(1, round(im.width * scale)), height), Image.LANCZOS)


def _draw_region(draw, region, size, color, label, font, pad=0, label_below=False):
    """Outline ``region`` (grown by ``pad`` px) and tag it with ``label``."""
    c, (w, h) = region.coords, size
    if region.shape == "polygon":
        pts = [(x * w, y * h) for x, y in c["points"]]
        draw.line(pts + [pts[0]], fill=color, width=3)
        x0, y0, x1, y1 = region.bbox()
        box = [x0 * w - pad, y0 * h - pad, x1 * w + pad, y1 * h + pad]
    elif region.shape == "ellipse":
        box = [(c["cx"] - c["rx"]) * w - pad, (c["cy"] - c["ry"]) * h - pad,
               (c["cx"] + c["rx"]) * w + pad, (c["cy"] + c["ry"]) * h + pad]
        draw.ellipse(box, outline=color, width=3)
    else:
        box = [c["x0"] * w - pad, c["y0"] * h - pad, c["x1"] * w + pad, c["y1"] * h + pad]
        draw.rectangle(box, outline=color, width=3)
    anchor, y = ("lt", box[3]) if label_below else ("lb", box[1])
    tag = draw.textbbox((box[0], y), label, font=font, anchor=anchor)
    draw.rectangle([tag[0] - 2, tag[1] - 2, tag[2] + 2, tag[3] + 2], fill=color)
    draw.text((box[0], y), label, font=font, fill=(255, 255, 255), anchor=anchor)


def build_comparison(original, enhanced, plan, panel_height=720):
    """Side-by-side image: original with the plan's regions marked (F = feature, E = edit) | enhanced."""
    left = _flatten(original, panel_height)
    right = _flatten(enhanced, panel_height)
    draw = ImageDraw.Draw(left)
    font = _font(max(14, panel_height // 40), bold=True)
    for i, feature in enumerate(plan.features, start=1):
        if feature.region:
            _draw_region(draw, feature.region, left.size, FEATURE_COLOR, "F%d" % i, font, pad=7, label_below=True)
    for i, edit in enumerate(plan.edits, start=1):
        if edit.region:
            _draw_region(draw, edit.region, left.size, EDIT_COLOR, "E%d" % i, font)

    gap, head = 24, int(panel_height * 0.07)
    width = max(left.width, right.width, 460)  # both panels and their titles must fit
    canvas = Image.new("RGB", (2 * width + 3 * gap, panel_height + head + 2 * gap), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    title = _font(max(14, head * 0.42), bold=True)
    d.text((gap, gap + head / 2), "Original (red F = keep, blue E = edited)", font=title, fill=(30, 30, 30), anchor="lm")
    d.text((2 * gap + width, gap + head / 2), "Enhanced (what becomes beads)", font=title, fill=(30, 30, 30), anchor="lm")
    canvas.paste(left, (gap + (width - left.width) // 2, gap + head))
    canvas.paste(right, (2 * gap + width + (width - right.width) // 2, gap + head))
    return canvas


def _describe_params(params):
    return ", ".join("%s=%s" % (k, v) for k, v in params.items())


def changes_markdown(plan, results, source_name, model=None):
    """A plain-language, reviewable list of what was found and what was changed."""
    out = ["# Proposed changes for %s\n" % source_name]
    if plan.subject:
        out.append("**Subject:** %s\n" % plan.subject)
    if plan.summary:
        out.append("**Summary:** %s\n" % plan.summary)
    if plan.features:
        out.append("## Features to keep\n")
        for i, f in enumerate(plan.features, start=1):
            where = " (%s)" % f.region.describe() if f.region else ""
            out.append("%d. **F%d %s**%s - %s" % (i, i, f.name, where, f.why or "identifies the subject"))
        out.append("")
    out.append("## Edits\n")
    if not results:
        out.append("No edits were proposed; the photo would be converted as it is.\n")
    for r in results:
        status = "applied" if r["applied"] else "NOT applied"
        head = "%d. **E%d %s** (%s)" % (r["index"], r["index"], r["op"], status)
        out.append(head)
        if r["reason"]:
            out.append("   - Why: %s" % r["reason"])
        if r["feature"]:
            out.append("   - Serves: %s" % r["feature"])
        if r["params"]:
            out.append("   - Settings: %s" % _describe_params(r["params"]))
        out.append("   - Where: %s" % (r["region"].describe() if r["region"] else "whole image"))
        if r["note"]:
            out.append("   - Note: %s" % r["note"])
    out.append("")
    out.append("## What stays the same\n")
    out.append("Only brightness, contrast, color, texture and outline are adjusted - nothing is drawn, "
               "added or removed. The next step (color detection, nearest bead color, chart) is the "
               "unchanged beadify pipeline.\n")
    if model:
        out.append("_Plan produced by %s._" % model)
    return "\n".join(out) + "\n"
