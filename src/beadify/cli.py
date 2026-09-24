"""Command-line interface: ``beadify photo.jpg -o pattern.png``."""

import argparse
import sys
from pathlib import Path

from . import __version__, prep
from .palette import load_palette
from .pattern import build_pattern
from .render import render_pattern


def _positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def build_parser():
    p = argparse.ArgumentParser(
        prog="beadify",
        description="Turn a photo into a fuse-bead (Perler / Hama / MARD) pattern chart.",
    )
    p.add_argument("image", help="input image (JPEG, PNG, ...); PNG transparency is treated as empty cells")
    p.add_argument("-o", "--output", help="output image path (default: <input name>_pattern.png)")
    p.add_argument("--version", action="version", version="beadify " + __version__)

    g = p.add_argument_group("grid size")
    g.add_argument("--size", type=_positive_int, default=100,
                   help="length of the longest side in beads, aspect ratio kept (default: 100)")
    g.add_argument("--width", type=_positive_int, help="grid width in beads (height follows the aspect ratio)")
    g.add_argument("--height", type=_positive_int, help="grid height in beads (width follows the aspect ratio)")
    g.add_argument("--resample", choices=["lanczos", "box"], default="lanczos",
                   help="downscale filter (default: lanczos)")
    p.epilog = "Giving both --width and --height center-crops the photo to that aspect ratio (no stretching)."

    g = p.add_argument_group("colors")
    g.add_argument("--palette", help="custom palette CSV with columns code,r,g,b (default: bundled MARD 291 colors)")
    g.add_argument("--max-colors", type=_positive_int, help="limit the number of different colors used")
    g.add_argument("--saturation", type=float, default=1.0, help="saturation factor applied before matching (default: 1.0)")
    g.add_argument("--contrast", type=float, default=1.0, help="contrast factor applied before matching (default: 1.0)")
    g.add_argument("--denoise", action="store_true", help="replace isolated single beads by their surrounding color")

    g = p.add_argument_group("background")
    g.add_argument("--bg", choices=["auto", "none"], default="auto",
                   help="auto: use PNG transparency, else remove a uniform border-connected background; "
                        "none: keep everything (default: auto)")
    g.add_argument("--bg-color", help="background color to remove, e.g. '#FFFFFF' (default: estimated from the border)")
    g.add_argument("--bg-tolerance", type=float, default=12.0,
                   help="max CIEDE2000 distance from the background color (default: 12)")

    g = p.add_argument_group("output")
    g.add_argument("--title", help="chart title (default: input file name)")
    g.add_argument("--mirror", action="store_true", help="flip the chart left-to-right (for pieces ironed from the back)")
    g.add_argument("--cell-size", type=_positive_int, default=40, help="cell size in pixels (default: 40)")
    g.add_argument("--no-preview", action="store_true", help="do not show the original photo in the header")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    src = Path(args.image)
    if not src.is_file():
        print("error: input image not found: %s" % src, file=sys.stderr)
        return 2
    out = Path(args.output) if args.output else Path.cwd() / (src.stem + "_pattern.png")

    try:
        palette = load_palette(args.palette)
        bg_color = prep.parse_hex_color(args.bg_color) if args.bg_color else None
        pattern = build_pattern(
            src,
            size=args.size,
            width=args.width,
            height=args.height,
            palette=palette,
            max_colors=args.max_colors,
            bg=args.bg,
            bg_color=bg_color,
            bg_tolerance=args.bg_tolerance,
            saturation=args.saturation,
            contrast=args.contrast,
            denoise=args.denoise,
            resample=args.resample,
            mirror=args.mirror,
        )
        preview = None if args.no_preview else prep.flatten_on_white(prep.load_image(src))
        chart = render_pattern(pattern, title=args.title or src.stem, preview=preview, cell=args.cell_size)
    except (ValueError, KeyError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    chart.save(out)

    print("Saved %s (%d x %d px)" % (out, chart.width, chart.height))
    print("Grid %d x %d, %d beads, %d colors" % (pattern.cols, pattern.rows, pattern.total_beads, len(pattern.counts())))
    for code, count in pattern.counts():
        print("  %-4s %d" % (code, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
