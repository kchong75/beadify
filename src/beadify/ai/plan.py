"""Edit-plan data model, validation, and the catalog of allowed edit operations.

An :class:`EditPlan` is what the AI produces after looking at a photo: the subject, the
features that must survive the reduction to beads (and why they are at risk), and a short
list of edits drawn from :data:`OP_CATALOG`. The plan is plain JSON so a person can read,
correct and re-run it.
"""

import json
from dataclasses import dataclass, field


class PlanError(ValueError):
    """Raised when a plan cannot be understood at all."""


def _float(lo, hi, default):
    return {"type": "float", "min": lo, "max": hi, "default": default}


def _rgb(default):
    return {"type": "rgb", "default": list(default)}


# Everything the AI may ask for. The executor never runs anything outside this catalog, and
# every numeric parameter is clamped to the range given here.
OP_CATALOG = {
    "exposure": {
        "doc": "Scale lightness (CIELAB L*) by `gain`. Above 1 brightens dim, shaded subjects so "
               "light fur, paper or skin can reach the light beads instead of gray ones.",
        "params": {"gain": _float(0.5, 2.0, 1.0)},
    },
    "contrast": {
        "doc": "Stretch lightness around the region's mean by `factor` (above 1 = more contrast).",
        "params": {"factor": _float(0.5, 2.0, 1.0)},
    },
    "saturation": {
        "doc": "Multiply color intensity (chroma) by `factor`.",
        "params": {"factor": _float(0.0, 2.5, 1.0)},
    },
    "local_contrast": {
        "doc": "Unsharp mask on lightness and color. Brings back small low-contrast details such as "
               "tail rings, fur markings and whisker shadows. `amount` is the strength, `radius_frac` "
               "the blur radius as a fraction of the longest image side.",
        "params": {"amount": _float(0.0, 2.0, 0.8), "radius_frac": _float(0.002, 0.05, 0.01)},
    },
    "colorize": {
        "doc": "Move the region's hue/chroma toward `target_rgb` by `strength` and, optionally, its "
               "lightness by `lightness_strength`. Use it to make a small but identity-defining color "
               "(an eye, a nose) survive bead matching. Keep the region tight around the feature.",
        "params": {
            "target_rgb": _rgb([128, 128, 128]),
            "strength": _float(0.0, 1.0, 0.5),
            "lightness_strength": _float(0.0, 1.0, 0.0),
        },
    },
    "smooth": {
        "doc": "Median filter that unifies noisy fur or texture into flat shades (bead cells are flat).",
        "params": {"radius_frac": _float(0.001, 0.03, 0.004)},
    },
    "cutout": {
        "doc": "Remove a cluttered or non-transparent background. `region` (required, use a polygon) is a "
               "rough outline of the whole subject; it may be off by about 3 percent of the image because the "
               "edge is refined from the image colors inside a band of `band_frac` around it. Everything "
               "outside becomes empty (no bead). Applied after the color edits.",
        "params": {"band_frac": _float(0.01, 0.08, 0.03)},
    },
    "crop": {
        "doc": "Crop the image to the bounding box of `region` (required) plus `margin_frac` on each side. "
               "Use it when the subject is small in the frame so the bead grid is spent on the subject, "
               "not on empty surroundings. Coordinates of all other regions still refer to the original "
               "image. Applied after `cutout`.",
        "params": {"margin_frac": _float(0.0, 0.2, 0.03)},
    },
    "outline": {
        "doc": "Add a dark outline around the subject's silhouette. Needs a transparent background "
               "(a cut-out image, or after `cutout`); it is always applied last and ignores any region.",
        "params": {"width_frac": _float(0.002, 0.05, 0.01), "color_rgb": _rgb([50, 50, 50])},
    },
}

MAX_EDITS = 12


@dataclass
class Region:
    """A normalized (0-1, origin top-left) ellipse, rectangle or polygon with a soft edge."""

    shape: str
    coords: dict
    feather: float = 0.3

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise PlanError("region must be an object")
        shape = data.get("shape")
        keys = {"ellipse": ("cx", "cy", "rx", "ry"), "rect": ("x0", "y0", "x1", "y1")}
        if shape == "polygon":
            try:
                points = [[min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0)] for x, y in data["points"]]
            except (KeyError, TypeError, ValueError):
                raise PlanError("polygon region needs 'points': [[x, y], ...]")
            if len(points) < 3:
                raise PlanError("a polygon needs at least 3 points")
            return cls("polygon", {"points": points}, min(max(float(data.get("feather", 0.3)), 0.0), 1.0))
        if shape not in keys:
            raise PlanError("region.shape must be 'ellipse', 'rect' or 'polygon', got %r" % (shape,))
        try:
            coords = {k: min(max(float(data[k]), 0.0), 1.0) for k in keys[shape]}
        except (KeyError, TypeError, ValueError):
            raise PlanError("region %r needs numeric %s" % (shape, ", ".join(keys[shape])))
        if shape == "ellipse" and (coords["rx"] <= 0 or coords["ry"] <= 0):
            raise PlanError("ellipse radii must be > 0")
        if shape == "rect" and (coords["x1"] <= coords["x0"] or coords["y1"] <= coords["y0"]):
            raise PlanError("rect must have x1 > x0 and y1 > y0")
        feather = min(max(float(data.get("feather", 0.3)), 0.0), 1.0)
        return cls(shape, coords, feather)

    def bbox(self):
        """Bounding box ``(x0, y0, x1, y1)`` in normalized coordinates."""
        c = self.coords
        if self.shape == "ellipse":
            return (max(c["cx"] - c["rx"], 0.0), max(c["cy"] - c["ry"], 0.0),
                    min(c["cx"] + c["rx"], 1.0), min(c["cy"] + c["ry"], 1.0))
        if self.shape == "rect":
            return (c["x0"], c["y0"], c["x1"], c["y1"])
        xs, ys = [p[0] for p in c["points"]], [p[1] for p in c["points"]]
        return (min(xs), min(ys), max(xs), max(ys))

    def to_dict(self):
        out = {"shape": self.shape}
        if self.shape == "polygon":
            out["points"] = [[round(x, 4), round(y, 4)] for x, y in self.coords["points"]]
        else:
            out.update({k: round(v, 4) for k, v in self.coords.items()})
        out["feather"] = round(self.feather, 3)
        return out

    def describe(self):
        c = self.coords
        if self.shape == "polygon":
            x0, y0, x1, y1 = self.bbox()
            return "polygon with %d points spanning (%.2f, %.2f) to (%.2f, %.2f)" % (len(c["points"]), x0, y0, x1, y1)
        if self.shape == "ellipse":
            return "ellipse at (%.2f, %.2f), radii %.2f x %.2f" % (c["cx"], c["cy"], c["rx"], c["ry"])
        return "box (%.2f, %.2f) to (%.2f, %.2f)" % (c["x0"], c["y0"], c["x1"], c["y1"])


@dataclass
class Feature:
    """Something about the subject that must survive the reduction to beads."""

    name: str
    why: str = ""
    region: "Region" = None

    def to_dict(self):
        out = {"name": self.name, "why": self.why}
        if self.region:
            out["region"] = self.region.to_dict()
        return out


@dataclass
class Edit:
    """One operation from :data:`OP_CATALOG`, optionally limited to a region."""

    op: str
    params: dict = field(default_factory=dict)
    region: "Region" = None
    reason: str = ""
    feature: str = ""

    def to_dict(self):
        out = {"op": self.op, "params": self.params, "reason": self.reason}
        if self.feature:
            out["feature"] = self.feature
        if self.region:
            out["region"] = self.region.to_dict()
        return out


@dataclass
class EditPlan:
    subject: str = ""
    summary: str = ""
    features: list = field(default_factory=list)
    edits: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise PlanError("the plan must be a JSON object")
        features, edits = [], []
        for item in data.get("features") or []:
            if not isinstance(item, dict) or not item.get("name"):
                raise PlanError("every feature needs a 'name'")
            region = Region.from_dict(item["region"]) if item.get("region") else None
            features.append(Feature(str(item["name"]), str(item.get("why", "")), region))
        raw_edits = data.get("edits") or []
        if not isinstance(raw_edits, list):
            raise PlanError("'edits' must be a list")
        for item in raw_edits[:MAX_EDITS]:
            if not isinstance(item, dict) or not item.get("op"):
                raise PlanError("every edit needs an 'op'")
            region = Region.from_dict(item["region"]) if item.get("region") else None
            params = item.get("params") or {}
            if not isinstance(params, dict):
                raise PlanError("edit.params must be an object")
            edits.append(
                Edit(str(item["op"]), params, region, str(item.get("reason", "")), str(item.get("feature", "")))
            )
        return cls(str(data.get("subject", "")), str(data.get("summary", "")), features, edits)

    @classmethod
    def from_json(cls, text):
        try:
            return cls.from_dict(json.loads(text))
        except json.JSONDecodeError as exc:
            raise PlanError("plan is not valid JSON: %s" % exc)

    def to_dict(self):
        return {
            "subject": self.subject,
            "summary": self.summary,
            "features": [f.to_dict() for f in self.features],
            "edits": [e.to_dict() for e in self.edits],
        }


def clean_params(op, params):
    """Fill defaults and clamp values for ``op``. Returns ``(params, notes)``.

    Raises :class:`PlanError` for an unknown operation.
    """
    if op not in OP_CATALOG:
        raise PlanError("unknown operation %r (allowed: %s)" % (op, ", ".join(sorted(OP_CATALOG))))
    spec = OP_CATALOG[op]["params"]
    out, notes = {}, []
    for key, s in spec.items():
        value = params.get(key, s["default"])
        if s["type"] == "float":
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise PlanError("%s.%s must be a number" % (op, key))
            clamped = min(max(value, s["min"]), s["max"])
            if clamped != value:
                notes.append("%s clamped from %g to %g" % (key, value, clamped))
            out[key] = clamped
        else:
            try:
                rgb = [int(min(max(int(v), 0), 255)) for v in value]
                if len(rgb) != 3:
                    raise ValueError
            except (TypeError, ValueError):
                raise PlanError("%s.%s must be [r, g, b]" % (op, key))
            out[key] = rgb
    extra = sorted(set(params) - set(spec))
    if extra:
        notes.append("ignored unknown parameters: %s" % ", ".join(extra))
    return out, notes
