# Changelog

## 0.1.0 - 2026-09-23

Initial release.

- Core pipeline (`beadify`): photo → bead grid → chart. Aspect-ratio-preserving resize, CIEDE2000 nearest
  bead-color matching against a bundled MARD 291-color palette (or a custom CSV), background detection
  (PNG alpha or border flood fill), `--max-colors` reduction, `--denoise`, `--mirror`, and a rendered chart
  with per-cell color codes, row/column numbers, bold gridlines every 5 cells, and a color-count legend.
- Optional AI-assisted preparation (`beadify-ai`): Claude analyzes a photo, identifies features at risk of
  being lost in the reduction to ~100 beads (small key colors, low-contrast markings, dim lighting,
  cluttered backgrounds), and proposes a small set of deterministic, reviewable edits (exposure, contrast,
  saturation, local contrast, targeted recolor, smoothing, background cutout, crop, outline). Edits are
  applied without any generative image model, shown for review (`comparison.png`, `changes.md`), and only
  charted after explicit confirmation.
- 40 pytest tests covering both the core pipeline and the AI module (against a mocked API client).
