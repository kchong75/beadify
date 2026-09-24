"""``beadify-ai``: AI-assisted preparation of a photo, then the regular beadify pipeline.

    beadify-ai enhance photo.png -w work/      # AI reads the photo, proposes and applies edits
    beadify-ai grid photo.png                  # photo with a 0-1 coordinate grid (to write a plan by hand)
    (review work/comparison.png and work/changes.md)
    beadify-ai chart -w work/ --yes -o out.png # unchanged beadify pipeline on work/enhanced.png
    beadify-ai run photo.png -o out.png        # both steps with an interactive confirmation

Options that ``beadify-ai chart`` / ``run`` do not know (``--size``, ``--max-colors``, ...) are
passed straight through to the regular ``beadify`` command.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .. import prep
from ..cli import main as core_main
from .analyze import DEFAULT_MODEL, AIError, _flatten, _grid_overlay, analyze_image
from .ops import apply_plan
from .plan import EditPlan, PlanError
from .report import build_comparison, changes_markdown


def _add_enhance_args(p):
    p.add_argument("image", help="input photo (a transparent PNG cut-out works best for outlines)")
    p.add_argument("-w", "--workdir", help="folder for plan.json, enhanced.png, comparison.png, changes.md "
                                           "(default: <image name>_ai)")
    p.add_argument("--plan", help="use this plan.json instead of asking the AI (e.g. one you edited by hand)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Claude model for the analysis (default: %(default)s)")
    p.add_argument("--fallbacks", action="store_true",
                   help="ask the API to retry on a fallback model if the primary one declines the request")
    p.add_argument("--feedback", help="what to change about the previous plan in the work folder; re-runs the AI "
                                      "with your comments")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="beadify-ai",
        description="AI-assisted photo preparation for bead patterns. The AI only proposes edits; you "
                    "confirm them before the normal beadify pipeline runs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    e = sub.add_parser("enhance", help="AI analysis + edited photo + comparison + change list (no chart yet)")
    _add_enhance_args(e)

    g = sub.add_parser("grid", help="save the photo with a 0-1 coordinate grid (for writing a plan by hand)")
    g.add_argument("image")
    g.add_argument("-o", "--output", help="output path (default: <image name>_grid.png)")

    c = sub.add_parser("chart", help="build the bead chart from a confirmed work folder")
    c.add_argument("-w", "--workdir", required=True, help="folder created by `beadify-ai enhance`")
    c.add_argument("-o", "--output", help="chart path (default: <workdir>/pattern.png)")
    c.add_argument("--yes", action="store_true", help="the changes have been reviewed and confirmed")

    r = sub.add_parser("run", help="enhance, ask for confirmation, then build the chart")
    _add_enhance_args(r)
    r.add_argument("-o", "--output", help="chart path (default: <workdir>/pattern.png)")
    r.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    return parser


def _confirm(question, yes):
    if yes:
        return True
    if not sys.stdin.isatty():
        print("Not confirmed (no interactive terminal). Review the changes, then re-run with --yes.")
        return False
    return input("%s [y/N] " % question).strip().lower() in ("y", "yes")


def enhance(args):
    """Steps 1-2: analysis and edit. Returns the work folder path."""
    src = Path(args.image)
    if not src.is_file():
        raise AIError("input image not found: %s" % src)
    workdir = Path(args.workdir) if args.workdir else Path.cwd() / (src.stem + "_ai")
    workdir.mkdir(parents=True, exist_ok=True)
    image = prep.load_image(src)

    model = None
    if args.plan:
        plan = EditPlan.from_json(Path(args.plan).read_text(encoding="utf-8"))
    else:
        previous = None
        prev_path = workdir / "plan.json"
        if args.feedback and prev_path.is_file():
            previous = EditPlan.from_json(prev_path.read_text(encoding="utf-8"))
        print("Asking %s to analyze %s ..." % (args.model, src.name))
        plan = analyze_image(image, model=args.model, use_fallbacks=args.fallbacks,
                             feedback=args.feedback, previous_plan=previous)
        model = args.model

    enhanced, results = apply_plan(image, plan)
    (workdir / "plan.json").write_text(json.dumps(plan.to_dict(), indent=2) + "\n", encoding="utf-8")
    enhanced.save(workdir / "enhanced.png")
    build_comparison(image, enhanced, plan).save(workdir / "comparison.png")
    (workdir / "changes.md").write_text(changes_markdown(plan, results, src.name, model), encoding="utf-8")
    (workdir / "meta.json").write_text(
        json.dumps({"source": str(src.resolve()), "created": datetime.now().isoformat(timespec="seconds"),
                    "model": model or "plan file"}, indent=2) + "\n", encoding="utf-8")

    print()
    print(changes_markdown(plan, results, src.name, model))
    print("Written to %s/: comparison.png, changes.md, plan.json, enhanced.png" % workdir)
    return workdir


def chart(workdir, output, yes, extra):
    """Step 3: the unchanged beadify pipeline on the confirmed, enhanced photo."""
    workdir = Path(workdir)
    enhanced = workdir / "enhanced.png"
    if not enhanced.is_file():
        print("error: %s not found; run `beadify-ai enhance` first" % enhanced, file=sys.stderr)
        return 2
    if not _confirm("Generate the bead chart from %s?" % enhanced, yes):
        return 3
    meta_path = workdir / "meta.json"
    title = Path(json.loads(meta_path.read_text())["source"]).stem if meta_path.is_file() else workdir.name
    out = output or str(workdir / "pattern.png")
    core_args = [str(enhanced), "-o", out] + list(extra)
    if "--title" not in core_args:
        core_args += ["--title", title]
    return core_main(core_args)


def main(argv=None):
    args, extra = build_parser().parse_known_args(argv)
    if args.command in ("enhance", "grid") and extra:
        print("error: unrecognized arguments: %s" % " ".join(extra), file=sys.stderr)
        return 2
    try:
        if args.command == "grid":
            src = Path(args.image)
            if not src.is_file():
                raise AIError("input image not found: %s" % src)
            out = Path(args.output) if args.output else Path.cwd() / (src.stem + "_grid.png")
            _grid_overlay(_flatten(prep.load_image(src))).save(out)
            print("Saved %s (grid lines every 0.1; x runs left to right, y top to bottom)" % out)
            return 0
        if args.command == "chart":
            return chart(args.workdir, args.output, args.yes, extra)
        workdir = enhance(args)
        if args.command == "enhance":
            print("\nNext: review comparison.png and changes.md, then run:\n  beadify-ai chart -w %s --yes "
                  "[beadify options]" % workdir)
            return 0
        if not _confirm("Proceed with these changes and build the chart?", args.yes):
            return 3
        return chart(workdir, args.output, True, extra)
    except (AIError, PlanError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
