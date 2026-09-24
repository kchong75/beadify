"""High-level pipeline: photo -> bead pattern data."""

from collections import Counter
from dataclasses import dataclass

import numpy as np

from . import prep, quantize
from .palette import Palette, load_palette, natural_key
from .quantize import EMPTY


@dataclass
class Pattern:
    """A bead pattern: a grid of palette indices (``EMPTY`` = no bead)."""

    grid: np.ndarray  # (rows, cols) int32
    palette: Palette
    mirrored: bool = False

    @property
    def rows(self):
        return self.grid.shape[0]

    @property
    def cols(self):
        return self.grid.shape[1]

    def code_at(self, r, c):
        i = int(self.grid[r, c])
        return None if i == EMPTY else self.palette.codes[i]

    def counts(self):
        """Return ``[(code, count), ...]`` sorted by natural code order (B3, B19, B20, C2, ...)."""
        used = self.grid[self.grid != EMPTY]
        tally = Counter(self.palette.codes[i] for i in used.tolist())
        return sorted(tally.items(), key=lambda kv: natural_key(kv[0]))

    @property
    def total_beads(self):
        return int((self.grid != EMPTY).sum())

    def mirror(self):
        """Return a left-right flipped copy (as the piece looks after ironing and flipping it over)."""
        return Pattern(self.grid[:, ::-1].copy(), self.palette, mirrored=not self.mirrored)


def build_pattern(
    image_path,
    size=100,
    width=None,
    height=None,
    palette=None,
    max_colors=None,
    bg="auto",
    bg_color=None,
    bg_tolerance=12.0,
    saturation=1.0,
    contrast=1.0,
    denoise=False,
    resample="lanczos",
    mirror=False,
):
    """Convert an image file into a :class:`Pattern`.

    See the CLI (``beadify --help``) for the meaning of each option.
    """
    palette = palette if palette is not None else load_palette()
    im = prep.load_image(image_path)
    (cols, rows), box = prep.grid_size(im.size, size=size, width=width, height=height)
    rgb, alpha = prep.resize_rgba(im, cols, rows, box=box, resample=resample)
    empty = prep.detect_background(rgb, alpha, mode=bg, bg_color=bg_color, tolerance=bg_tolerance)
    rgb = prep.enhance(rgb, saturation=saturation, contrast=contrast)
    grid = quantize.map_to_palette(rgb, palette, empty_mask=empty, max_colors=max_colors)
    if denoise:
        grid = quantize.denoise(grid)
    pattern = Pattern(grid, palette)
    return pattern.mirror() if mirror else pattern
