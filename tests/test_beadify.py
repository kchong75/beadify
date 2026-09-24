import numpy as np
import pytest
from PIL import Image, ImageDraw

from beadify import build_pattern, load_palette, render_pattern
from beadify.cli import main
from beadify.palette import natural_key
from beadify.pattern import Pattern
from beadify.prep import grid_size
from beadify.quantize import EMPTY, map_to_palette


@pytest.fixture(scope="module")
def palette():
    return load_palette()


@pytest.fixture()
def photo(tmp_path):
    """A white-background JPEG-like image with a red disc and a blue square."""
    im = Image.new("RGB", (300, 200), "white")
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 140, 140], fill=(220, 30, 30))
    d.rectangle([180, 60, 260, 140], fill=(30, 60, 220))
    path = tmp_path / "photo.png"
    im.save(path)
    return path


def test_natural_sort_order():
    codes = ["C5", "B20", "B3", "B19", "A10", "A9", "ZG1"]
    assert sorted(codes, key=natural_key) == ["A9", "A10", "B3", "B19", "B20", "C5", "ZG1"]


def test_palette_loads_all_mard_colors(palette):
    assert len(palette) == 291
    for code in ("B3", "B19", "B20", "C2", "C5", "C6", "C7", "H5"):
        assert code in palette.codes


def test_exact_palette_colors_map_to_themselves(palette):
    rgb = palette.rgb[:60].reshape(6, 10, 3)
    idx = map_to_palette(rgb, palette)
    assert (idx.reshape(-1) == np.arange(60)).all()


def test_grid_size_keeps_aspect_ratio():
    assert grid_size((300, 200), size=100)[0] == (100, 67)
    assert grid_size((200, 300), size=100)[0] == (67, 100)
    assert grid_size((300, 200), width=30)[0] == (30, 20)


def test_grid_size_both_dimensions_crops_instead_of_stretching():
    (cols, rows), box = grid_size((300, 200), width=50, height=50)
    assert (cols, rows) == (50, 50)
    assert box == (50, 0, 250, 200)  # centered square crop


def test_background_removed_and_counts_add_up(photo, palette):
    p = build_pattern(photo, size=30, palette=palette)
    assert p.grid.shape == (20, 30)
    assert p.grid[0, 0] == EMPTY  # white corner is background
    assert 0 < p.total_beads < p.grid.size
    assert sum(n for _, n in p.counts()) == p.total_beads
    assert p.counts() == sorted(p.counts(), key=lambda kv: natural_key(kv[0]))


def test_bg_none_keeps_every_cell(photo, palette):
    p = build_pattern(photo, size=30, palette=palette, bg="none")
    assert p.total_beads == p.grid.size


def test_transparent_png_cells_are_empty(tmp_path, palette):
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([25, 25, 75, 75], fill=(200, 40, 40, 255))
    path = tmp_path / "t.png"
    im.save(path)
    p = build_pattern(path, size=20, palette=palette)
    assert p.grid[0, 0] == EMPTY and p.grid[10, 10] != EMPTY
    assert len({p.code_at(r, c) for r in range(6, 14) for c in range(6, 14)}) == 1  # no dark edge bleed


def test_max_colors_is_respected(photo, palette):
    unlimited = build_pattern(photo, size=40, palette=palette, saturation=1.0)
    limited = build_pattern(photo, size=40, palette=palette, max_colors=2)
    assert len(limited.counts()) <= 2
    assert len(limited.counts()) <= len(unlimited.counts())


def test_mirror_flips_grid(photo, palette):
    a = build_pattern(photo, size=30, palette=palette)
    b = build_pattern(photo, size=30, palette=palette, mirror=True)
    assert (b.grid == a.grid[:, ::-1]).all() and b.mirrored


def test_render_draws_bold_line_every_five_cells(palette):
    grid = np.full((10, 12), EMPTY, dtype=np.int32)
    grid[0, 0] = 0
    pattern = Pattern(grid, palette)
    cell = 40
    im = render_pattern(pattern, cell=cell).convert("RGB")
    band = max(int(cell * 0.75), 16)
    block_w = 12 * cell + 2 * band
    bx = (im.width - block_w) // 2
    gx = bx + band
    # find header height by locating the purple band's top edge along the middle of the image
    col = [im.getpixel((bx + 3, y)) for y in range(im.height)]
    by = next(y for y, px in enumerate(col) if px == (150, 142, 214))
    gy = by + band
    y_probe = gy + 2 * cell + cell // 2  # inside an empty row, away from horizontal lines
    dark = lambda x: sum(im.getpixel((x, y_probe))) < 100
    assert dark(gx + 5 * cell) and dark(gx + 10 * cell)  # bold after 5th and 10th column
    assert not dark(gx + 3 * cell) and not dark(gx + 7 * cell)  # ordinary boundaries are thin/light
    assert dark(gx + 12 * cell)  # outer border


def test_cli_end_to_end(photo, tmp_path, capsys):
    out = tmp_path / "out.png"
    assert main([str(photo), "-o", str(out), "--size", "24", "--title", "Test", "--mirror"]) == 0
    assert out.exists() and Image.open(out).width > 500
    text = capsys.readouterr().out
    assert "Grid 24 x 16" in text


def test_cli_missing_input(tmp_path, capsys):
    assert main([str(tmp_path / "nope.jpg")]) == 2
