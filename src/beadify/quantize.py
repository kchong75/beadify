"""Map image colors onto a bead palette (CIEDE2000) and tidy up the result."""

import numpy as np
from skimage import color as skcolor

from .palette import rgb_to_lab

EMPTY = -1  # index used for cells that hold no bead

_CHUNK = 1500


def delta_e_matrix(lab, palette_lab):
    """CIEDE2000 distance between every row of ``lab`` (U, 3) and every palette color -> (U, N)."""
    out = np.empty((len(lab), len(palette_lab)), dtype=np.float64)
    for start in range(0, len(lab), _CHUNK):
        chunk = lab[start : start + _CHUNK]
        out[start : start + _CHUNK] = skcolor.deltaE_ciede2000(
            chunk[:, None, :], palette_lab[None, :, :]
        )
    return out


class Matcher:
    """Nearest-palette-color lookup over the unique colors of an RGB grid."""

    def __init__(self, rgb, palette):
        rows, cols = rgb.shape[:2]
        flat = rgb.reshape(-1, 3)
        self.unique, self.inverse = np.unique(flat, axis=0, return_inverse=True)
        self.inverse = self.inverse.reshape(-1)
        self.shape = (rows, cols)
        self.dist = delta_e_matrix(rgb_to_lab(self.unique), palette.lab)  # (U, N)

    def assign(self, allowed=None):
        """Index of the nearest palette color for every cell, restricted to ``allowed`` if given."""
        if allowed is None:
            best = self.dist.argmin(axis=1)
        else:
            allowed = np.asarray(sorted(allowed))
            best = allowed[self.dist[:, allowed].argmin(axis=1)]
        return best[self.inverse].reshape(self.shape)


def map_to_palette(rgb, palette, empty_mask=None, max_colors=None):
    """Map an (H, W, 3) uint8 grid to palette indices; masked cells get ``EMPTY``.

    With ``max_colors`` the palette usage is reduced greedily: colors are removed
    one at a time, always the one whose removal increases the total perceptual
    error the least, with its cells re-assigned to the next-nearest kept color.
    """
    if max_colors is not None and max_colors < 1:
        raise ValueError("max_colors must be >= 1")
    matcher = Matcher(rgb, palette)
    idx = matcher.assign()
    if empty_mask is None:
        empty_mask = np.zeros(idx.shape, dtype=bool)
    if empty_mask.all():
        return np.full(idx.shape, EMPTY, dtype=np.int32)

    if max_colors is not None:
        idx = _reduce_colors(matcher, empty_mask, max_colors)
    idx = idx.astype(np.int32)
    idx[empty_mask] = EMPTY
    return idx


def _reduce_colors(matcher, empty_mask, max_colors):
    # Weight each unique source color by how many *bead* cells use it.
    weights = np.bincount(
        matcher.inverse[~empty_mask.reshape(-1)], minlength=len(matcher.unique)
    ).astype(np.float64)
    allowed = set(np.unique(matcher.dist[weights > 0].argmin(axis=1)).tolist())
    while len(allowed) > max_colors:
        cols = np.asarray(sorted(allowed))
        sub = matcher.dist[:, cols]  # (U, K)
        order = np.argsort(sub, axis=1)
        rows = np.arange(len(sub))
        best_pos, second_pos = order[:, 0], order[:, 1]
        penalty = weights * (sub[rows, second_pos] - sub[rows, best_pos])
        cost = np.bincount(best_pos, weights=penalty, minlength=len(cols))
        allowed.remove(int(cols[int(cost.argmin())]))
    return matcher.assign(allowed)


def denoise(idx, passes=1):
    """Replace isolated cells (no same-code neighbor among the 8 around them).

    An isolated cell takes the most common code among its non-empty neighbors,
    provided at least three such neighbors exist.
    """
    idx = idx.copy()
    rows, cols = idx.shape
    for _ in range(passes):
        src = idx.copy()
        for r in range(rows):
            for c in range(cols):
                cur = src[r, c]
                if cur == EMPTY:
                    continue
                nb = src[max(r - 1, 0) : r + 2, max(c - 1, 0) : c + 2].ravel()
                nb = nb[nb != EMPTY]
                nb = np.delete(nb, np.where(nb == cur)[0][:1])  # drop the cell itself
                if len(nb) < 3 or (nb == cur).any():
                    continue
                vals, counts = np.unique(nb, return_counts=True)
                idx[r, c] = vals[counts.argmax()]
    return idx
