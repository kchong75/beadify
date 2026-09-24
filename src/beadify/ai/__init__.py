"""AI-assisted photo preparation for beadify.

The core pipeline (color detection, nearest bead color, chart rendering) is not touched by this
package. It adds a step in front of it: an AI reads the photo, decides which features of the
subject must survive the reduction to beads, and proposes a small set of brightness / contrast /
color / outline edits. The edits are applied deterministically and shown to the user for
confirmation before the ordinary pipeline runs on the edited image.
"""

from .analyze import DEFAULT_MODEL, AIError, analyze_image
from .ops import apply_plan
from .plan import OP_CATALOG, Edit, EditPlan, Feature, PlanError, Region

__all__ = [
    "AIError", "DEFAULT_MODEL", "Edit", "EditPlan", "Feature", "OP_CATALOG", "PlanError", "Region",
    "analyze_image", "apply_plan",
]
