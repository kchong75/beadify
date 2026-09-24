"""Render a Pattern as a printable, grid-based bead chart image."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .quantize import EMPTY

FONT_DIR = Path(__file__).parent / "fonts"

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
INK = (30, 30, 30)
THIN_LINE = (175, 175, 175)
BAND = (150, 142, 214)  # purple frame carrying the row / column numbers
BAND_TEXT = (35, 30, 80)
MUTED = (95, 95, 95)

BOLD_LINE_EVERY = 5


@lru_cache(maxsize=None)
def _font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), max(int(size), 6))


def _fit_font(draw, text, max_width, max_size, bold=False):
    """Largest font (<= max_size) in which ``text`` is at most ``max_width`` wide."""
    size = int(max_size)
    while size > 6:
        font = _font(size, bold)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 1
    return _font(6, bold)


def _text_color_for(rgb):
    r, g, b = (int(v) for v in rgb)
    return INK if (0.2126 * r + 0.7152 * g + 0.0722 * b) > 140 else WHITE


def _draw_line_rect(draw, x0, y0, x1, y1, color):
    draw.rectangle([x0, y0, x1, y1], fill=color)


def render_pattern(pattern, title=None, preview=None, cell=40):
    """Draw the chart and return it as a PIL image.

    ``preview`` is an optional PIL image of the original photo shown in the header.
    ``cell`` is the size of one bead cell in pixels.
    """
    if cell < 16:
        raise ValueError("cell size must be at least 16 pixels")
    rows, cols = pattern.rows, pattern.cols
    c = cell
    band = max(int(c * 0.75), 16)
    pad = c
    grid_w, grid_h = cols * c, rows * c
    block_w, block_h = grid_w + 2 * band, grid_h + 2 * band
    canvas_w = max(block_w + 2 * pad, 22 * c + 2 * pad)
    thick = max(2, c // 12)

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # ---- header -----------------------------------------------------------------------
    counts = pattern.counts()
    title_font = _font(c * 1.3, bold=True)
    stat_font = _font(c * 0.55)
    thumb_box = int(c * 4.5)
    thumb = None
    if preview is not None:
        thumb = preview.convert("RGB")
        thumb.thumbnail((thumb_box, thumb_box), Image.LANCZOS)
    stats = "Grid: %d × %d    Beads: %d    Colors: %d    Palette: %s (%d colors)" % (
        cols,
        rows,
        pattern.total_beads,
        len(counts),
        pattern.palette.name,
        len(pattern.palette),
    )
    stat_lines = [stats]
    if pattern.mirrored:
        stat_lines.append("Mirrored: this chart is flipped left-to-right")
    text_h = int(c * 1.3) + int(c * 0.35) + len(stat_lines) * int(c * 0.8)
    thumb_h = (thumb.height + int(c * 0.6)) if thumb else 0
    header_h = pad + max(text_h, thumb_h) + int(c * 0.5)

    # ---- legend layout ----------------------------------------------------------------
    sw_w, sw_h = int(c * 1.6), c
    gap_x, gap_y = int(c * 0.4), int(c * 0.4)
    entry_h = sw_h + int(c * 0.7)
    per_row = max(1, (canvas_w - 2 * pad + gap_x) // (sw_w + gap_x))
    legend_rows = max(1, -(-len(counts) // per_row))
    legend_head_h = int(c * 1.1)
    legend_h = legend_head_h + legend_rows * (entry_h + gap_y) + int(c * 0.9)

    canvas_h = header_h + block_h + int(c * 0.8) + legend_h + pad
    im = Image.new("RGB", (canvas_w, canvas_h), WHITE)
    d = ImageDraw.Draw(im)

    # ---- header drawing ---------------------------------------------------------------
    d.text((pad, pad), title or "Bead pattern", font=title_font, fill=INK, anchor="la")
    y = pad + int(c * 1.3) + int(c * 0.35)
    for line in stat_lines:
        d.text((pad, y), line, font=stat_font, fill=MUTED, anchor="la")
        y += int(c * 0.8)
    if thumb is not None:
        tx = canvas_w - pad - thumb.width
        d.rectangle([tx - 1, pad - 1, tx + thumb.width, pad + thumb.height], outline=THIN_LINE)
        im.paste(thumb, (tx, pad))
        d.text(
            (tx + thumb.width // 2, pad + thumb.height + int(c * 0.15)),
            "Original",
            font=_font(c * 0.4),
            fill=MUTED,
            anchor="ma",
        )

    # ---- pattern block ----------------------------------------------------------------
    bx = (canvas_w - block_w) // 2
    by = header_h
    gx, gy = bx + band, by + band  # top-left of the cell grid
    d.rectangle([bx, by, bx + block_w - 1, by + block_h - 1], fill=BAND)
    d.rectangle([gx, gy, gx + grid_w - 1, gy + grid_h - 1], fill=WHITE)

    code_font = _fit_font(
        d, max(pattern.palette.codes, key=len), c * 0.88, c * 0.42, bold=True
    )
    for r in range(rows):
        for col in range(cols):
            i = int(pattern.grid[r, col])
            if i == EMPTY:
                continue
            x0, y0 = gx + col * c, gy + r * c
            rgb = tuple(int(v) for v in pattern.palette.rgb[i])
            d.rectangle([x0, y0, x0 + c - 1, y0 + c - 1], fill=rgb)
            d.text(
                (x0 + c / 2, y0 + c / 2),
                pattern.palette.codes[i],
                font=code_font,
                fill=_text_color_for(rgb),
                anchor="mm",
            )

    # grid lines: thin everywhere, thick after every 5th cell and around the outside
    for k in range(cols + 1):
        x = gx + k * c
        heavy = k % BOLD_LINE_EVERY == 0 or k == cols
        w = thick if heavy else 1
        x0 = x - w // 2
        _draw_line_rect(d, x0, gy, x0 + w - 1, gy + grid_h - 1, BLACK if heavy else THIN_LINE)
    for k in range(rows + 1):
        y = gy + k * c
        heavy = k % BOLD_LINE_EVERY == 0 or k == rows
        w = thick if heavy else 1
        y0 = y - w // 2
        _draw_line_rect(d, gx, y0, gx + grid_w - 1, y0 + w - 1, BLACK if heavy else THIN_LINE)
    # close the corners of the outer frame
    for xx in (gx, gx + grid_w):
        for yy in (gy, gy + grid_h):
            d.rectangle([xx - thick // 2, yy - thick // 2, xx - thick // 2 + thick - 1,
                         yy - thick // 2 + thick - 1], fill=BLACK)

    # row / column numbers on all four sides
    num_font = _fit_font(d, str(max(rows, cols)), c * 0.9, c * 0.42, bold=True)
    for col in range(cols):
        cx = gx + col * c + c / 2
        label = str(col + 1)
        d.text((cx, by + band / 2), label, font=num_font, fill=BAND_TEXT, anchor="mm")
        d.text((cx, gy + grid_h + band / 2), label, font=num_font, fill=BAND_TEXT, anchor="mm")
    for r in range(rows):
        cy = gy + r * c + c / 2
        label = str(r + 1)
        d.text((bx + band / 2, cy), label, font=num_font, fill=BAND_TEXT, anchor="mm")
        d.text((gx + grid_w + band / 2, cy), label, font=num_font, fill=BAND_TEXT, anchor="mm")

    # ---- legend -----------------------------------------------------------------------
    ly = by + block_h + int(c * 0.8)
    d.text((pad, ly), "Colors used", font=_font(c * 0.75, bold=True), fill=INK, anchor="la")
    ly += legend_head_h
    legend_font = _fit_font(d, max(pattern.palette.codes, key=len), sw_w * 0.85, c * 0.5, bold=True)
    count_font = _font(c * 0.5)
    for n, (code, count) in enumerate(counts):
        col, row = n % per_row, n // per_row
        sx = pad + col * (sw_w + gap_x)
        sy = ly + row * (entry_h + gap_y)
        rgb = tuple(int(v) for v in pattern.palette.rgb[pattern.palette.index_of(code)])
        d.rectangle([sx, sy, sx + sw_w - 1, sy + sw_h - 1], fill=rgb, outline=INK)
        d.text((sx + sw_w / 2, sy + sw_h / 2), code, font=legend_font, fill=_text_color_for(rgb), anchor="mm")
        d.text((sx + sw_w / 2, sy + sw_h + int(c * 0.1)), str(count), font=count_font, fill=INK, anchor="ma")
    total_y = ly + legend_rows * (entry_h + gap_y) + int(c * 0.1)
    d.text(
        (pad, total_y),
        "Total: %d beads, %d colors" % (pattern.total_beads, len(counts)),
        font=_font(c * 0.55, bold=True),
        fill=INK,
        anchor="la",
    )
    return im
