---
name: perler-beads
description: Convert a photo or image into a fuse-bead (Perler / Hama / MARD) pattern chart - a grid with a color code in every cell, bold lines every 5 cells, row/column numbers, and a color legend with bead counts. Use when the user asks for a bead pattern, perler/Hama/MARD/pixel-bead chart, or to pixelate a picture into beads.
---

# Perler bead pattern generator

This skill drives the `beadify` package in this repository (project root is two levels above this file's
directory: `.claude/skills/perler-beads/` -> repo root).

## Steps

1. Make sure the package is available. Either it is installed (`beadify --version`), or run from the repo
   root with `PYTHONPATH=src python3 -m beadify`. To install: `pip install -e .` from the repo root.
2. Confirm the input image path. Ask the user only for what matters and is not already stated:
   target size (default: longest side 100 beads), max number of colors, whether to mirror the chart.
3. Run the CLI:

   ```bash
   beadify INPUT_IMAGE -o OUTPUT.png [--size 100] [--width W --height H] [--max-colors N] \
       [--denoise] [--mirror] [--bg auto|none] [--bg-color '#RRGGBB'] [--title "Title"]
   ```

4. Show the resulting PNG to the user and report the grid size, total beads and color list printed by the CLI.
5. Iterate on request. Typical fixes:
   - background not removed / too much removed -> `--bg-color '#RRGGBB'`, `--bg-tolerance`, or `--bg none`
   - too many colors or speckles -> `--max-colors N`, `--denoise`
   - washed-out result -> `--saturation 1.2`, `--contrast 1.1`
   - chart too big to work with -> smaller `--size`, or exact `--width/--height` (both center-crop)

## AI-assisted preparation (when a photo loses its key features)

Use this when the plain conversion loses what makes the subject recognizable (small colored eyes, faint
markings or stripes, a pale subject photographed in dim light), or when the user asks for it. The core
`beadify` pipeline is never modified: the edited photo is just fed into it. **Always let the user review
the edits before charting.**

1. Analyze. With an Anthropic API key: `beadify-ai enhance PHOTO -w WORKDIR`. Without one, do the analysis
   yourself: run `beadify-ai grid PHOTO -o grid.png`, look at the photo and the grid image, decide which
   features must survive (and why they would be lost at ~100 cells with a flat bead palette), and write
   `plan.json` (schema and operations: `beadify.ai.plan.OP_CATALOG`; regions are normalized 0-1 ellipses or
   rectangles or polygons read off the grid). For an opaque photo where the subject is small or the
   background is cluttered, start with `cutout` (polygon around the whole subject, tails and limbs included; use a
   fine grid zoom to place the points) and `crop`. Then run `beadify-ai enhance PHOTO -w WORKDIR --plan plan.json`.
2. Show the user `WORKDIR/comparison.png` and summarize `WORKDIR/changes.md`: which features were found,
   what was changed and why, and that only brightness/contrast/color/outline were touched.
3. Ask the user to confirm. If they want changes, either re-run with `--feedback "..."` (API) or edit
   `plan.json` and re-run with `--plan`.
4. Only after confirmation: `beadify-ai chart -w WORKDIR --yes -o OUT.png [beadify options]`. Options such as
   `--size` and `--max-colors` are passed through to `beadify` unchanged.

## Notes

- Default palette is the bundled MARD 291 colors; pass `--palette file.csv` (columns `code,r,g,b`) for
  another brand or for the user's own inventory.
- Colors are matched with CIEDE2000 in CIELAB space. RGB values are screen approximations; remind the
  user to verify colors against a physical color card before buying beads.
- PNG transparency is treated as empty cells (no bead).
