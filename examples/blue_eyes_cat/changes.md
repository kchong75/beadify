# Proposed changes for cat_flame_point.png

**Subject:** A cream / white 'flame point' cat lying down and looking left, with blue eyes, pink ear and nose, tan markings on the back and a banded tail.

**Summary:** Brightened the photo slightly, made both blue eyes clearly blue, strengthened the tail bands and the tan back patches, and added a dark outline. The cat's shape, pose and overall coloring are unchanged.

## Features to keep

1. **F1 Blue eyes** (ellipse at (0.19, 0.34), radii 0.03 x 0.04) - The two pale blue-gray irises are the most recognizable trait of this cat, but each is only ~3-4 cells wide and blends with the cream fur when the photo is averaged down, so it would become a gray or brown bead.
2. **F2 Far blue eye** (ellipse at (0.07, 0.38), radii 0.01 x 0.02) - The second eye at the edge of the face is even smaller and would vanish completely.
3. **F3 Banded tail** (box (0.80, 0.61) to (0.98, 0.70)) - The tail alternates cream and tan bands. The contrast between bands is low, so they would merge into one beige color.
4. **F4 Tan back markings** (box (0.50, 0.40) to (0.82, 0.62)) - The soft tan patches on the back give the coat its flame-point look; at this size they would flatten into the surrounding cream.

## Edits

1. **E1 exposure** (applied)
   - Why: The photo is a little dim, which pushes the white and cream fur toward gray and brown beads. A mild global brightening lets it reach the light cream and white beads.
   - Settings: gain=1.25
   - Where: whole image
2. **E2 colorize** (applied)
   - Why: Pushes the iris toward a clear blue and lightens it slightly so it matches a blue bead instead of the surrounding cream or the dark pupil.
   - Serves: Blue eyes
   - Settings: target_rgb=[70, 140, 215], strength=0.7, lightness_strength=0.4
   - Where: ellipse at (0.19, 0.34), radii 0.03 x 0.04
3. **E3 colorize** (applied)
   - Why: Same treatment for the second eye so both eyes read as blue.
   - Serves: Far blue eye
   - Settings: target_rgb=[70, 140, 215], strength=0.7, lightness_strength=0.4
   - Where: ellipse at (0.07, 0.38), radii 0.01 x 0.02
4. **E4 local_contrast** (applied)
   - Why: Sharpens the difference between neighbouring tail bands so alternating cream and tan cells survive the downscale.
   - Serves: Banded tail
   - Settings: amount=1.4, radius_frac=0.006
   - Where: box (0.80, 0.61) to (0.98, 0.70)
5. **E5 contrast** (applied)
   - Why: Spreads the light and dark bands of the tail further apart in brightness.
   - Serves: Banded tail
   - Settings: factor=1.4
   - Where: box (0.80, 0.61) to (0.98, 0.70)
6. **E6 local_contrast** (applied)
   - Why: Keeps the soft tan patches on the back distinct from the cream fur around them.
   - Serves: Tan back markings
   - Settings: amount=0.7, radius_frac=0.02
   - Where: box (0.50, 0.40) to (0.82, 0.62)
7. **E7 outline** (applied)
   - Why: A thin dark outline around the silhouette, as in traditional bead patterns. It is added outside the cat so thin parts such as the tail keep all their own beads.
   - Settings: width_frac=0.012, color_rgb=[55, 55, 55]
   - Where: whole image
   - Note: 15 px outline

## What stays the same

Only brightness, contrast, color, texture and outline are adjusted - nothing is drawn, added or removed. The next step (color detection, nearest bead color, chart) is the unchanged beadify pipeline.

