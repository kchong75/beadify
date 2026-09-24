# blue_eyes_cat

Demonstrates what the AI-assisted step is actually for: this cat's blue eyes are only a few beads wide,
and their real pixel color is a pale, low-saturation gray-blue — not vivid enough to win against the
surrounding cream fur when matched to the nearest bead color.

| File | AI-enhanced? | Colors | Blue-eye beads |
|---|---|---|---|
| `baseline_pattern_unlimited_colors.png` | no | 56 | 0 |
| `baseline_pattern_20colors.png` | no | 20 | 0 |
| `ai_pattern_unlimited_colors.png` | yes | 86 | 31, across 12 different blues (`C16`, `C29`, `P14`, ...) |
| `ai_pattern_20colors.png` | yes | 20 | 25 (`C16`, a deep blue) |

`baseline_*` is the photo run straight through `beadify` with no AI step. At **every** color budget, from
20 colors up to unlimited, zero beads come out blue - the eyes disappear into the surrounding gray/beige
fur codes (`H3`, `M7`, `M9`, ...). This isn't a color-count problem; the AI step's `colorize` edit is what
lets the eyes survive at all.

`eye_comparison.jpg` is a face crop of the two 20-color charts side by side (baseline left, AI-enhanced
right) - see the top-level README for the full picture.

Regenerate this example:

```bash
beadify-ai enhance ../../tests/fixtures/cat_flame_point.png --plan plan.json -w .
beadify tests/fixtures/cat_flame_point.png -o baseline_pattern_unlimited_colors.png
beadify tests/fixtures/cat_flame_point.png -o baseline_pattern_20colors.png --max-colors 20 --denoise
beadify-ai chart -w . --yes -o ai_pattern_unlimited_colors.png
beadify-ai chart -w . --yes -o ai_pattern_20colors.png --max-colors 20 --denoise
```
