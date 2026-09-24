"""Ask Claude to look at a photo and propose an :class:`~beadify.ai.plan.EditPlan`."""

import base64
import io
import json

from PIL import Image, ImageDraw

from ..render import _font
from .plan import OP_CATALOG, EditPlan, PlanError

DEFAULT_MODEL = "claude-opus-5"
FALLBACK_MODEL = "claude-opus-4-8"
FALLBACK_BETA = "server-side-fallback-2026-06-01"
VIEW_SIDE = 1400  # long side of the images sent to the model
VIEW_BACKGROUND = (110, 110, 110)  # transparent areas are shown as flat gray


class AIError(RuntimeError):
    """Raised when the AI step cannot produce a usable plan."""


def _catalog_text():
    lines = []
    for name, spec in OP_CATALOG.items():
        params = []
        for key, s in spec["params"].items():
            if s["type"] == "float":
                params.append("%s: number %g..%g (default %g)" % (key, s["min"], s["max"], s["default"]))
            else:
                params.append("%s: [r, g, b] (default %s)" % (key, s["default"]))
        lines.append("- %s: %s\n    params: %s" % (name, spec["doc"], "; ".join(params)))
    return "\n".join(lines)


SYSTEM_PROMPT = """\
You prepare photos for conversion into fuse-bead (Perler / Hama / MARD) patterns.

The conversion is fixed and mechanical: the photo is averaged down to a grid of roughly 100 cells
on its longest side, and every cell is then given the single nearest color from a palette of about
290 flat bead colors. Consequences you must plan for:
- Details smaller than about 3% of the image width are averaged away, and low-contrast patterns
  (fur markings, tail rings, whisker shadows) disappear.
- Small but identity-defining colors (an eye, a nose, a logo color) are blended with their
  surroundings and end up as the wrong color or as gray/brown.
- Photos taken in dim or shaded light turn pale subjects (white or cream fur, paper, skin) into
  mid-gray or brown beads.

Your job: look at the photo, work out what makes THIS subject recognizable, and decide the smallest
set of edits that keeps those features alive through the conversion. You never redraw or add
anything: you only adjust brightness, contrast, color, texture and outline of what is already
there, using the operations below. Do not change the subject's shape, pose, or true colors in a way
that would make it look like a different subject; prefer conservative values. Use at most 10 edits.

Allowed operations:
@@OPS@@

Regions are normalized to the image: x and y run from 0 (left / top) to 1 (right / bottom). A
second copy of the photo is provided with a labeled grid every 0.1 so you can read coordinates off
it. Shapes: {"shape": "ellipse", "cx", "cy", "rx", "ry"}, {"shape": "rect", "x0", "y0", "x1", "y1"} or
{"shape": "polygon", "points": [[x, y], ...]} (clockwise, 20-40 points for a subject outline),
plus an optional "feather" 0..1 (edge softness, default 0.3). Omit "region" to affect the whole image.
Keep regions tight around the feature they target, and make sure each feature's region really
covers it on the grid image.

If the subject is small in the frame or sits on a cluttered, non-transparent background, that alone
ruins the result (the grid gets spent on the surroundings, and a white or beige subject blends into
its background). Then start with a `cutout` whose polygon follows the subject's whole outline
(tails, ears, paws and limbs included), followed by a `crop` around the same polygon, and add the
color edits for the features after that.

Reply with ONE JSON object and nothing else, with this shape:
{
  "subject": "one short sentence describing the subject",
  "features": [
    {"name": "short name", "why": "what identifies the subject here and why it would be lost",
     "region": {...}}
  ],
  "edits": [
    {"op": "<operation>", "params": {...}, "region": {...},
     "feature": "name of the feature this edit serves, if any",
     "reason": "plain-language explanation a non-expert can check"}
  ],
  "summary": "two or three sentences summarizing what you changed and what you deliberately left alone"
}
""".replace("@@OPS@@", _catalog_text())


def _flatten(image, side=VIEW_SIDE):
    im = image.convert("RGBA")
    bg = Image.new("RGBA", im.size, VIEW_BACKGROUND + (255,))
    im = Image.alpha_composite(bg, im).convert("RGB")
    if max(im.size) > side:
        scale = side / float(max(im.size))
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    return im


def _grid_overlay(im):
    """Copy of ``im`` with thin lines and labels every 0.1 in normalized coordinates."""
    out = im.copy()
    draw = ImageDraw.Draw(out)
    font = _font(max(10, im.width // 60))
    for i in range(1, 10):
        t = i / 10.0
        x, y = round(t * im.width), round(t * im.height)
        draw.line([(x, 0), (x, im.height)], fill=(255, 235, 0), width=1)
        draw.line([(0, y), (im.width, y)], fill=(255, 235, 0), width=1)
        for pos, anchor in (((x + 2, 2), "la"), ((x + 2, im.height - 2), "ld")):
            draw.text(pos, "%.1f" % t, font=font, fill=(255, 235, 0), anchor=anchor)
        draw.text((2, y + 1), "%.1f" % t, font=font, fill=(255, 235, 0), anchor="la")
    return out


def _png_b64(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def extract_json(text):
    """Pull the first JSON object out of a model reply (tolerates code fences and chatter)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise PlanError("the reply contains no JSON object")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise PlanError("the reply is not valid JSON: %s" % exc)


def _user_content(image, feedback, previous_plan, correction):
    view = _flatten(image)
    content = [
        {"type": "text", "text": "Photo to analyze (transparent areas, if any, are shown as flat gray):"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _png_b64(view)}},
        {"type": "text", "text": "The same photo with a coordinate grid (labels are normalized 0-1):"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": _png_b64(_grid_overlay(view))}},
    ]
    text = "Analyze the subject and return the JSON edit plan."
    if previous_plan is not None:
        text += "\n\nThe previous plan was:\n%s" % json.dumps(previous_plan.to_dict(), indent=2)
    if feedback:
        text += "\n\nThe user reviewed it and asked for these changes; follow them:\n%s" % feedback
    if correction:
        text += "\n\nYour previous reply could not be used (%s). Reply with the JSON object only." % correction
    content.append({"type": "text", "text": text})
    return content


def _translate_api_error(exc):
    """Turn Anthropic SDK exceptions into an AIError with an actionable message (most specific first)."""
    try:
        import anthropic
    except ImportError:
        return None
    if isinstance(exc, anthropic.AuthenticationError):
        return AIError("Authentication failed. Set ANTHROPIC_API_KEY or run `ant auth login`.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AIError("The API key lacks permission for this request: %s" % exc)
    if isinstance(exc, anthropic.NotFoundError):
        return AIError("Model or endpoint not found (check --model): %s" % exc)
    if isinstance(exc, anthropic.RateLimitError):
        return AIError("Rate limited by the API; wait a moment and try again.")
    if isinstance(exc, anthropic.APIStatusError):
        return AIError("API error (%s): %s" % (exc.status_code, exc.message))
    if isinstance(exc, anthropic.APIConnectionError):
        return AIError("Could not reach the API; check the network connection.")
    return None


def _make_client():
    try:
        import anthropic
    except ImportError:
        raise AIError("The 'anthropic' package is required for AI analysis: pip install anthropic "
                      "(or pass a ready-made plan with --plan).")
    return anthropic.Anthropic()  # credentials come from the environment / `ant auth login`


def analyze_image(image, client=None, model=DEFAULT_MODEL, use_fallbacks=False, feedback=None,
                  previous_plan=None, max_tokens=16000):
    """Return an :class:`EditPlan` for a PIL image.

    ``client`` is an ``anthropic.Anthropic`` instance (created from the environment when omitted).
    ``feedback`` and ``previous_plan`` let a reviewer steer a second pass. With ``use_fallbacks`` the
    request also asks the API to retry on a fallback model if the primary one declines it.
    """
    client = client or _make_client()
    correction = None
    for attempt in range(2):
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": _user_content(image, feedback, previous_plan, correction)}],
        }
        try:
            if use_fallbacks:
                response = client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks=[{"model": FALLBACK_MODEL}], **kwargs
                )
            else:
                response = client.messages.create(**kwargs)
        except Exception as exc:  # map SDK errors; anything else is a genuine bug
            friendly = _translate_api_error(exc)
            if friendly is not None:
                raise friendly
            raise
        if response.stop_reason == "refusal":
            raise AIError("The model declined to analyze this image (stop reason: refusal).")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return EditPlan.from_dict(extract_json(text))
        except PlanError as exc:
            correction = str(exc)
    raise AIError("The model did not return a usable plan twice in a row: %s" % correction)
