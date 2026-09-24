# Proposed changes for cat_calico.jpg

**Subject:** A white calico / tabby-and-white cat lying on its back on a beige carpet, seen from above with the head at the bottom, gray tabby patches on the back, an orange patch near the shoulder, a gray ringed tail on the left and white paws.

**Summary:** Cut the cat out of the carpet and cropped to it so it fills the bead grid, and strengthened the face details, the tail rings and the orange patch. No outline is added. Colors, pose and proportions of the cat are unchanged.

## Features to keep

1. **F1 Face: eyes, nose, ears** (box (0.52, 0.56) to (0.61, 0.62)) - The pale green-yellow eyes with dark pupils, the pink nose and the pink-gray ears make the face recognizable, but they cover only a few cells each and would blend into the white fur.
2. **F2 Ringed gray tail** (box (0.07, 0.20) to (0.31, 0.31)) - The dark and light gray rings on the tail are low in contrast and would merge into a single gray.
3. **F3 Orange patch** (box (0.40, 0.17) to (0.56, 0.30)) - The orange-tan patch near the shoulder and on the raised leg is what makes the cat a calico; against a beige carpet it would turn beige.
4. **F4 White body** (polygon with 51 points spanning (0.07, 0.15) to (0.78, 0.66)) - White fur on a beige carpet blends into the background, so the cat's shape is lost unless the carpet is removed.

## Edits

1. **E1 cutout** (applied)
   - Why: The photo is a cat on a cluttered carpet (with a rug, a shoe and a toy in the corners). The cat is outlined roughly and the edge is refined from the image colors; everything outside becomes empty instead of being beaded.
   - Serves: White body
   - Settings: band_frac=0.018
   - Where: polygon with 51 points spanning (0.07, 0.15) to (0.78, 0.66)
   - Note: kept 12% of the image as subject
2. **E2 crop** (applied)
   - Why: The cat fills only about a third of the frame, so the photo is cropped to the cat. That way the bead grid is spent on the cat instead of on empty carpet.
   - Serves: White body
   - Settings: margin_frac=0.02
   - Where: polygon with 51 points spanning (0.07, 0.15) to (0.78, 0.66)
   - Note: cropped to 535 x 700 px
3. **E3 local_contrast** (applied)
   - Why: Keeps the dark pupils, the pink nose and the ear edges distinct from the white fur after the downscale.
   - Serves: Face: eyes, nose, ears
   - Settings: amount=1.0, radius_frac=0.006
   - Where: box (0.52, 0.56) to (0.61, 0.62)
4. **E4 saturation** (applied)
   - Why: Strengthens the pale green-yellow of the eyes and the pink of the nose so they do not turn white or gray.
   - Serves: Face: eyes, nose, ears
   - Settings: factor=1.5
   - Where: box (0.52, 0.56) to (0.61, 0.62)
5. **E5 local_contrast** (applied)
   - Why: Sharpens the difference between neighboring rings on the tail.
   - Serves: Ringed gray tail
   - Settings: amount=1.2, radius_frac=0.006
   - Where: box (0.07, 0.20) to (0.31, 0.31)
6. **E6 contrast** (applied)
   - Why: Pushes the dark and light rings further apart in brightness.
   - Serves: Ringed gray tail
   - Settings: factor=1.4
   - Where: box (0.07, 0.20) to (0.31, 0.31)
7. **E7 saturation** (applied)
   - Why: Keeps the orange patches orange instead of letting them fade to beige.
   - Serves: Orange patch
   - Settings: factor=1.4
   - Where: box (0.40, 0.17) to (0.56, 0.30)

## What stays the same

Only brightness, contrast, color, texture and outline are adjusted - nothing is drawn, added or removed. The next step (color detection, nearest bead color, chart) is the unchanged beadify pipeline.

