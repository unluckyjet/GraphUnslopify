"""One appearance per series, shared by every figure in a paper.

`series_order` fixes colour assignment inside a single spec. Across figure 1 and
figure 7 there was nothing, so a model could be blue in one and orange in the
next, which quietly undoes the argument that the generator owning presentation
makes figures agree.

The lock file is the missing piece. First figure to mention a series claims an
appearance for it; every figure after that reads the same one. It is plain JSON
and belongs in version control next to the paper.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

# Okabe-Ito minus the yellow, which is unreadable on white.
PALETTE = [
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#8C564B",
    "#000000",
]
LINE_STYLES = ["-", "--", "-.", ":"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
HATCHES = ["", "///", "...", "xxx", "\\\\\\", "+++", "ooo", "**"]


# Private observational hook: allocation uses the same parsed byte snapshot.
LOAD_OBSERVER: ContextVar = ContextVar("graphunslopify_palette_load_observer", default=None)


def load(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"version": 1, "series": {}}
    try:
        content = path.read_bytes()
        lock = json.loads(content.decode("utf8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "series": {}}
    observer = LOAD_OBSERVER.get()
    if observer is not None:
        observer(path, content)
    return lock


def save(path: str | Path, lock: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf8")


def reserve(lock: dict[str, Any], names: list[str]) -> dict[str, dict[str, Any]]:
    """Claim an appearance for each name, keeping any already claimed.

    New series take the lowest index nobody holds, so adding a method to a paper
    does not recolour the ones already in it.
    """
    series = lock.setdefault("series", {})
    taken = {entry["index"] for entry in series.values()}

    for name in names:
        if name in series:
            continue
        index = 0
        while index in taken:
            index += 1
        taken.add(index)
        series[name] = {
            "index": index,
            "colour": PALETTE[index % len(PALETTE)],
            "linestyle": LINE_STYLES[index % len(LINE_STYLES)],
            "marker": MARKERS[index % len(MARKERS)],
            "hatch": HATCHES[index % len(HATCHES)],
        }
    return series


def appearance(path: str | Path, names: list[str]) -> dict[str, dict[str, Any]]:
    """Read the lock, reserve anything new, write it back, return the mapping."""
    lock = load(path)
    series = reserve(lock, names)
    save(path, lock)
    return series
