"""Locate the golden eval set.

Single source of truth for four callers that used to each glob ~/out/eval
independently — a path that exists on the author's machine and in no clone, so
`eval.py`, `build_demo.py`, `qu_eval.py` and `rerank_eval.py` all hard-failed on a
fresh checkout (two of them with a bare IndexError on an empty glob).

Resolution order, first hit wins:
  1. $GOLDEN_SET                              — explicit override
  2. an explicit path argument                — e.g. sys.argv[1]
  3. <repo>/data/eval/golden_set.json         — SHIPPED; makes a clean clone work
  4. ~/out/eval/golden_set.draft.v*.json      — legacy personal location
"""
import glob
import os

# repo root: <repo>/src/hybrid_search/evalset.py -> up three
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHIPPED = os.path.join(REPO, "data", "eval", "golden_set.json")
LEGACY_DIR = os.path.expanduser("~/out/eval")
LEGACY_GLOB = os.path.join(LEGACY_DIR, "golden_set.draft.v*.json")


def resolve(explicit=None):
    """Absolute path to the golden set, or FileNotFoundError naming every place tried."""
    env = os.environ.get("GOLDEN_SET")
    if env:
        return env
    if explicit:
        return explicit
    if os.path.exists(SHIPPED):
        return SHIPPED
    cands = sorted(glob.glob(LEGACY_GLOB))
    if cands:
        return cands[-1]
    raise FileNotFoundError(
        "No golden eval set found. Looked for:\n"
        f"  $GOLDEN_SET (unset)\n"
        f"  {SHIPPED}\n"
        f"  {LEGACY_GLOB}\n"
        "It ships with the repo at data/eval/golden_set.json — restore it, or point "
        "$GOLDEN_SET at your own set."
    )


def template_path():
    """Optional personal-memory gold template that eval.py merges when present."""
    for p in (os.path.join(REPO, "data", "eval", "gold_core.template.json"),
              os.path.join(LEGACY_DIR, "gold_core.template.json")):
        if os.path.exists(p):
            return p
    return None
