"""Bead palette loading and color-space helpers."""

import csv
import re
from pathlib import Path

import numpy as np
from skimage import color as skcolor

DEFAULT_PALETTE_PATH = Path(__file__).parent / "palettes" / "mard.csv"


def natural_key(code):
    """Sort key so that B3 < B19 < B20 and A9 < A10 (not plain string order)."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", code)]


def rgb_to_lab(rgb):
    """Convert an (..., 3) uint8 / float RGB array (0-255) to CIELAB."""
    arr = np.asarray(rgb, dtype=np.float64) / 255.0
    return skcolor.rgb2lab(arr.reshape(-1, 1, 3)).reshape(arr.shape)


class Palette:
    """An ordered set of bead colors: codes, RGB values and precomputed Lab values."""

    def __init__(self, codes, rgb, name="custom"):
        if len(codes) != len(rgb):
            raise ValueError("codes and rgb must have the same length")
        if len(set(codes)) != len(codes):
            raise ValueError("palette contains duplicate color codes")
        self.name = name
        self.codes = list(codes)
        self.rgb = np.asarray(rgb, dtype=np.uint8).reshape(-1, 3)
        self.lab = rgb_to_lab(self.rgb)
        self._index = {c: i for i, c in enumerate(self.codes)}

    def __len__(self):
        return len(self.codes)

    def index_of(self, code):
        return self._index[code]

    def subset(self, codes):
        """Return a new palette restricted to the given color codes."""
        missing = [c for c in codes if c not in self._index]
        if missing:
            raise KeyError("unknown color codes: " + ", ".join(missing))
        idx = [self._index[c] for c in codes]
        return Palette([self.codes[i] for i in idx], self.rgb[idx], name=self.name)


def load_palette(path=None):
    """Load a palette from a CSV with columns ``code,r,g,b`` (extra columns ignored).

    With no path the bundled MARD 291-color palette is used.
    """
    path = Path(path) if path else DEFAULT_PALETTE_PATH
    codes, rgb = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        needed = {"code", "r", "g", "b"}
        if not needed.issubset(fields):
            raise ValueError(
                "palette CSV must have a header with columns: code,r,g,b (found: %s)"
                % ", ".join(fields)
            )
        for row in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row["code"]:
                continue
            codes.append(row["code"])
            rgb.append([int(row["r"]), int(row["g"]), int(row["b"])])
    if not codes:
        raise ValueError("palette CSV %s contains no colors" % path)
    return Palette(codes, rgb, name=path.stem.upper() if path == DEFAULT_PALETTE_PATH else path.stem)
