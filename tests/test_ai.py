import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from beadify.ai import AIError, EditPlan, PlanError, analyze_image, apply_plan
from beadify.ai.analyze import extract_json
from beadify.ai.cli import main as ai_main
from beadify.ai.ops import region_mask
from beadify.ai.plan import Region, clean_params


def make_photo(size=(200, 160), transparent=True):
    """A cream disc with a small gray 'eye' on a transparent (or gray) background."""
    im = Image.new("RGBA", size, (0, 0, 0, 0) if transparent else (120, 120, 120, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([30, 20, 170, 150], fill=(150, 140, 125, 255))
    d.ellipse([70, 60, 90, 78], fill=(120, 125, 135, 255))
    return im


EYE = {"shape": "ellipse", "cx": 0.4, "cy": 0.43, "rx": 0.07, "ry": 0.07}


def plan_from(edits, **extra):
    return EditPlan.from_dict({"subject": "test", "features": [], "edits": edits, **extra})


# --- plan ---------------------------------------------------------------------------------

def test_clean_params_fills_defaults_and_clamps():
    params, notes = clean_params("exposure", {"gain": 9})
    assert params == {"gain": 2.0} and "clamped" in notes[0]
    assert clean_params("exposure", {})[0] == {"gain": 1.0}


def test_clean_params_rejects_unknown_op_and_bad_values():
    with pytest.raises(PlanError):
        clean_params("teleport", {})
    with pytest.raises(PlanError):
        clean_params("exposure", {"gain": "bright"})
    with pytest.raises(PlanError):
        clean_params("colorize", {"target_rgb": [1, 2]})


def test_region_validation():
    assert Region.from_dict(EYE).shape == "ellipse"
    with pytest.raises(PlanError):
        Region.from_dict({"shape": "circle"})
    with pytest.raises(PlanError):
        Region.from_dict({"shape": "rect", "x0": 0.5, "y0": 0.1, "x1": 0.4, "y1": 0.2})


def test_plan_round_trip():
    plan = plan_from([{"op": "exposure", "params": {"gain": 1.2}, "reason": "dim", "region": EYE}],
                     features=[{"name": "eye", "why": "small", "region": EYE}])
    again = EditPlan.from_json(json.dumps(plan.to_dict()))
    assert again.edits[0].op == "exposure" and again.features[0].name == "eye"


def test_extract_json_tolerates_fences():
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(PlanError):
        extract_json("no json here")


# --- ops ----------------------------------------------------------------------------------

def test_region_mask_is_soft_and_localised():
    m = region_mask(Region.from_dict(EYE), 160, 200)
    assert m[69, 80] > 0.9 and m[0, 0] == 0 and m.max() <= 1.0


def test_exposure_brightens_and_keeps_transparency():
    im = make_photo()
    out, results = apply_plan(im, plan_from([{"op": "exposure", "params": {"gain": 1.4}}]))
    assert results[0]["applied"]
    assert np.asarray(out)[80, 100, :3].sum() > np.asarray(im)[80, 100, :3].sum()
    assert np.asarray(out)[0, 0, 3] == 0


def test_colorize_only_changes_its_region():
    im = make_photo()
    plan = plan_from([{"op": "colorize", "region": EYE,
                       "params": {"target_rgb": [60, 130, 220], "strength": 0.9}}])
    out, _ = apply_plan(im, plan)
    before, after = np.asarray(im).astype(int), np.asarray(out).astype(int)
    assert after[69, 80, 2] - after[69, 80, 0] > before[69, 80, 2] - before[69, 80, 0] + 30  # eye got bluer
    assert (after[110, 140] == before[110, 140]).all()  # body outside the region untouched


def test_outline_adds_ring_and_pads_canvas():
    im = make_photo()
    out, results = apply_plan(im, plan_from([{"op": "outline", "params": {"width_frac": 0.03, "color_rgb": [10, 10, 10]}}]))
    assert results[0]["applied"] and out.width > im.width and out.height > im.height
    arr = np.asarray(out)
    assert (arr[..., 3] > 0).sum() > (np.asarray(im)[..., 3] > 0).sum()  # the ring adds opaque pixels
    ring = (arr[..., :3] == (10, 10, 10)).all(axis=-1) & (arr[..., 3] == 255)
    assert ring.sum() > 100  # the new pixels have the requested outline color
    assert not ring[arr.shape[0] // 2, arr.shape[1] // 2]  # ...and the subject's interior is untouched


def test_outline_skipped_without_transparent_background():
    _, results = apply_plan(make_photo(transparent=False), plan_from([{"op": "outline"}]))
    assert not results[0]["applied"] and "no transparent" in results[0]["note"]


def test_invalid_edits_are_reported_not_fatal():
    out, results = apply_plan(make_photo(), plan_from([{"op": "teleport"}, {"op": "exposure", "params": {"gain": 1.1}}]))
    assert [r["applied"] for r in results] == [False, True]
    assert "unknown operation" in results[0]["note"]


# --- analysis with a fake API client --------------------------------------------------------

class FakeMessages:
    def __init__(self, replies, stop_reason="end_turn"):
        self.replies, self.calls, self.stop_reason = list(replies), [], stop_reason

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.replies.pop(0)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=text)])


def fake_client(replies, **kw):
    messages = FakeMessages(replies, **kw)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


GOOD = json.dumps({"subject": "a disc", "features": [{"name": "eye", "why": "tiny", "region": EYE}],
                   "edits": [{"op": "exposure", "params": {"gain": 1.2}, "reason": "dim"}], "summary": "ok"})


def test_analyze_image_sends_both_views_and_parses_plan():
    client, messages = fake_client([GOOD])
    plan = analyze_image(make_photo(), client=client)
    assert plan.subject == "a disc" and plan.edits[0].op == "exposure"
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5" and call["thinking"] == {"type": "adaptive"}
    content = call["messages"][0]["content"]
    assert sum(1 for b in content if b["type"] == "image") == 2  # plain view + coordinate-grid view
    assert "betas" not in call  # fallbacks are opt-in


def test_analyze_image_retries_once_on_unusable_reply():
    client, messages = fake_client(["I think the cat is nice.", GOOD])
    assert analyze_image(make_photo(), client=client).subject == "a disc"
    assert "could not be used" in messages.calls[1]["messages"][0]["content"][-1]["text"]


def test_analyze_image_gives_up_after_two_bad_replies():
    client, _ = fake_client(["nope", "still nope"])
    with pytest.raises(AIError):
        analyze_image(make_photo(), client=client)


def test_analyze_image_reports_refusal():
    client, _ = fake_client([GOOD], stop_reason="refusal")
    with pytest.raises(AIError, match="declined"):
        analyze_image(make_photo(), client=client)


def test_analyze_image_feedback_and_fallbacks():
    client, messages = fake_client([GOOD])
    prev = EditPlan.from_json(GOOD)
    analyze_image(make_photo(), client=client, feedback="leave the eye alone", previous_plan=prev, use_fallbacks=True)
    call = messages.calls[0]
    assert call["betas"] and call["fallbacks"]
    text = call["messages"][0]["content"][-1]["text"]
    assert "leave the eye alone" in text and "previous plan" in text


# --- CLI ----------------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path):
    photo = tmp_path / "disc.png"
    make_photo().save(photo)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"subject": "disc", "features": [{"name": "eye", "why": "tiny", "region": EYE}],
                                "edits": [{"op": "colorize", "region": EYE, "feature": "eye", "reason": "keep it blue",
                                           "params": {"target_rgb": [60, 130, 220], "strength": 0.8}}],
                                "summary": "made the eye blue"}))
    return tmp_path, photo, plan


def test_cli_enhance_writes_reviewable_files(workspace, capsys):
    tmp, photo, plan = workspace
    work = tmp / "work"
    assert ai_main(["enhance", str(photo), "--plan", str(plan), "-w", str(work)]) == 0
    for name in ("plan.json", "enhanced.png", "comparison.png", "changes.md", "meta.json"):
        assert (work / name).is_file()
    assert "keep it blue" in (work / "changes.md").read_text()
    assert "beadify-ai chart" in capsys.readouterr().out
    assert not (work / "pattern.png").exists()  # nothing is charted before confirmation


def test_cli_chart_requires_confirmation(workspace, capsys):
    tmp, photo, plan = workspace
    work = tmp / "work"
    ai_main(["enhance", str(photo), "--plan", str(plan), "-w", str(work)])
    assert ai_main(["chart", "-w", str(work)]) == 3  # no --yes and no terminal: refuses
    assert not (work / "pattern.png").exists()


def test_cli_chart_runs_the_unchanged_core_with_passthrough_options(workspace, capsys):
    tmp, photo, plan = workspace
    work = tmp / "work"
    ai_main(["enhance", str(photo), "--plan", str(plan), "-w", str(work)])
    assert ai_main(["chart", "-w", str(work), "--yes", "--size", "24", "--max-colors", "3"]) == 0
    assert (work / "pattern.png").is_file()
    assert "Grid 24 x" in capsys.readouterr().out


def test_cli_enhance_rejects_unknown_arguments(workspace):
    tmp, photo, plan = workspace
    assert ai_main(["enhance", str(photo), "--plan", str(plan), "--size", "10"]) == 2


def test_cli_missing_input(tmp_path):
    assert ai_main(["enhance", str(tmp_path / "nope.png"), "--plan", str(tmp_path / "p.json")]) == 1


def test_cli_grid_writes_overlay(workspace):
    tmp, photo, _ = workspace
    out = tmp / "grid.png"
    assert ai_main(["grid", str(photo), "-o", str(out)]) == 0
    assert Image.open(out).size == make_photo().size


# --- polygon regions, cutout, crop ------------------------------------------------------------

def noisy_scene(size=(240, 200)):
    """Textured beige 'carpet' with a bright ellipse 'cat' in the middle (opaque photo)."""
    rng = np.random.RandomState(0)
    base = np.array([150, 130, 105], dtype=float)
    arr = np.clip(base + rng.normal(0, 18, size=(size[1], size[0], 3)), 0, 255).astype(np.uint8)
    im = Image.fromarray(arr, "RGB").convert("RGBA")
    ImageDraw.Draw(im).ellipse([80, 60, 180, 140], fill=(240, 240, 235, 255))
    return im


def ellipse_polygon(cx, cy, rx, ry, n=24):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return [[float(cx + rx * np.cos(a)), float(cy + ry * np.sin(a))] for a in t]


def test_polygon_region_round_trip_and_mask():
    region = Region.from_dict({"shape": "polygon", "points": [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]]})
    assert region.bbox() == (0.2, 0.2, 0.8, 0.8)
    assert Region.from_dict(region.to_dict()).coords == region.coords
    mask = region_mask(region, 100, 100)
    assert mask[35, 50] > 0.9 and mask[90, 10] == 0
    with pytest.raises(PlanError):
        Region.from_dict({"shape": "polygon", "points": [[0, 0], [1, 1]]})


def test_cutout_removes_textured_background():
    im = noisy_scene()
    # a rough, slightly oversized outline of the ellipse (centre 130,100 px; radii 50,40 px)
    rough = ellipse_polygon(130 / 240, 100 / 200, 62 / 240, 52 / 200)
    plan = plan_from([{"op": "cutout", "params": {"band_frac": 0.06},
                       "region": {"shape": "polygon", "points": rough}}])
    out, results = apply_plan(im, plan)
    assert results[0]["applied"], results[0]["note"]
    alpha = np.asarray(out)[..., 3]
    assert alpha[100, 130] == 255 and alpha[5, 5] == 0 and alpha[190, 230] == 0
    true_area = np.pi * 50 * 40
    assert abs((alpha > 127).sum() - true_area) / true_area < 0.2  # cut-out follows the real edge


def test_crop_uses_region_bbox_with_margin_and_runs_after_color_edits():
    im = make_photo((200, 160), transparent=False)
    box = {"shape": "rect", "x0": 0.25, "y0": 0.25, "x1": 0.75, "y1": 0.75}
    plan = plan_from([{"op": "crop", "params": {"margin_frac": 0.0}, "region": box},
                      {"op": "colorize", "region": EYE, "params": {"target_rgb": [60, 130, 220], "strength": 0.9}}])
    out, results = apply_plan(im, plan)
    assert out.size == (100, 80) and all(r["applied"] for r in results)
    # the colorize region is in *original* coordinates even though it was listed after the crop
    eye = np.asarray(out)[int(0.43 * 160) - 40, int(0.4 * 200) - 50]
    assert eye[2] > eye[0] + 30


def test_cutout_and_crop_need_a_region():
    _, results = apply_plan(make_photo(), plan_from([{"op": "cutout"}, {"op": "crop"}]))
    assert [r["applied"] for r in results] == [False, False]
    assert all("needs a region" in r["note"] for r in results)


def test_cutout_keeps_thin_parts_narrower_than_the_band():
    """A limb only slightly wider than the trimap band used to lose all its subject seeds."""
    size = (240, 200)
    rng = np.random.RandomState(1)
    arr = np.clip(np.array([150, 130, 105]) + rng.normal(0, 18, (size[1], size[0], 3)), 0, 255).astype(np.uint8)
    im = Image.fromarray(arr, "RGB").convert("RGBA")
    ImageDraw.Draw(im).rectangle([40, 90, 200, 108], fill=(235, 235, 230, 255))  # 19 px tall bar
    x0, x1, y0, y1 = 32 / 240, 208 / 240, 82 / 200, 116 / 200  # loose outline: ~8 px margin
    plan = plan_from([{"op": "cutout", "params": {"band_frac": 0.06},
                       "region": {"shape": "polygon", "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}}])
    out, results = apply_plan(im, plan)
    assert results[0]["applied"], results[0]["note"]
    alpha = np.asarray(out)[..., 3]
    bar = alpha[90:109, 40:201] > 127
    assert bar.mean() > 0.85  # the bar itself survives (the old behaviour kept only a sliver)
    assert (alpha[:70] > 127).sum() == 0 and (alpha[130:] > 127).sum() == 0
