"""Canonical figure helpers, bound to a distinct generated-program namespace.

Helpers deliberately read the caller's scientific constants and report state.
Use bind(); directly importing and calling these templates is unsupported.
The emitter's inline form is generated from these same plain Python bodies.
"""

from __future__ import annotations

import copy as _runtime_copy
import hashlib as _runtime_hashlib
import json as _runtime_json
from pathlib import Path as _RuntimePath
from types import FunctionType as _FunctionType
from typing import Any

# Templates receive actual globals through bind(); these values prevent accidental
# reliance on the template module as a scientific execution context.
_UNBOUND_PROGRAM_GLOBAL = object()
ALT_TEXT: Any = _UNBOUND_PROGRAM_GLOBAL
CLAIMS: Any = _UNBOUND_PROGRAM_GLOBAL
CURRENT_PANEL: Any = _UNBOUND_PROGRAM_GLOBAL
DATA_HASH: Any = _UNBOUND_PROGRAM_GLOBAL
DATA_PATH: Any = _UNBOUND_PROGRAM_GLOBAL
DIAGNOSTIC_ADVICE: Any = _UNBOUND_PROGRAM_GLOBAL
DPI: Any = _UNBOUND_PROGRAM_GLOBAL
ENCODING_SENTENCE: Any = _UNBOUND_PROGRAM_GLOBAL
FIGURE_TITLE: Any = _UNBOUND_PROGRAM_GLOBAL
FORMATS: Any = _UNBOUND_PROGRAM_GLOBAL
GROUP: Any = _UNBOUND_PROGRAM_GLOBAL
IDENTITY_CONFLICTS: Any = _UNBOUND_PROGRAM_GLOBAL
IDENTITY_FIELDS: Any = _UNBOUND_PROGRAM_GLOBAL
PANEL_ORIGINAL_NAMES: Any = _UNBOUND_PROGRAM_GLOBAL
PANEL_SOURCE_KEYS: Any = _UNBOUND_PROGRAM_GLOBAL
Path: Any = _UNBOUND_PROGRAM_GLOBAL
REQUIRED_IDENTITY_FIELDS: Any = _UNBOUND_PROGRAM_GLOBAL
ROW_COUNTS: Any = _UNBOUND_PROGRAM_GLOBAL
RUN_REPORT: Any = _UNBOUND_PROGRAM_GLOBAL
RUNTIME_OPTIONAL_PACKAGES: Any = _UNBOUND_PROGRAM_GLOBAL
SPEC_HASH: Any = _UNBOUND_PROGRAM_GLOBAL
SPEC_JSON: Any = _UNBOUND_PROGRAM_GLOBAL
STATIC_FINDINGS: Any = _UNBOUND_PROGRAM_GLOBAL
STEM: Any = _UNBOUND_PROGRAM_GLOBAL
TARGET_WIDTH_IN: Any = _UNBOUND_PROGRAM_GLOBAL
TOOL: Any = _UNBOUND_PROGRAM_GLOBAL
UNKNOWN_DIAGNOSTIC: Any = _UNBOUND_PROGRAM_GLOBAL
X_FIELD: Any = _UNBOUND_PROGRAM_GLOBAL
Y_FIELD: Any = _UNBOUND_PROGRAM_GLOBAL
argparse: Any = _UNBOUND_PROGRAM_GLOBAL
contextlib: Any = _UNBOUND_PROGRAM_GLOBAL
describe_figure: Any = _UNBOUND_PROGRAM_GLOBAL
escape: Any = _UNBOUND_PROGRAM_GLOBAL
finish_report: Any = _UNBOUND_PROGRAM_GLOBAL
hashlib: Any = _UNBOUND_PROGRAM_GLOBAL
io: Any = _UNBOUND_PROGRAM_GLOBAL
json: Any = _UNBOUND_PROGRAM_GLOBAL
main: Any = _UNBOUND_PROGRAM_GLOBAL
matplotlib: Any = _UNBOUND_PROGRAM_GLOBAL
np: Any = _UNBOUND_PROGRAM_GLOBAL
pd: Any = _UNBOUND_PROGRAM_GLOBAL
pretty: Any = _UNBOUND_PROGRAM_GLOBAL
re: Any = _UNBOUND_PROGRAM_GLOBAL
series_names: Any = _UNBOUND_PROGRAM_GLOBAL
sys: Any = _UNBOUND_PROGRAM_GLOBAL

RUNTIME_ABI = 1
__all__ = ["bind", "runtime_info"]

# Scientific helper/inspection/provenance sources, independent of unrelated UI
# and SDK changes. No expected hashes are embedded here (including this file).
SOURCE_COMPONENTS = (
    "figure_runtime.py",
    "inspect.py",
    "diagnostics.py",
    "diagnostics.json",
    "export_size.py",
    "data_view.py",
    "colour.py",
    "cell_colour.py",
    "provenance.py",
    "schemas/environment.schema.json",
    "schemas/runtime-identity.schema.json",
)

FUNCTION_NAMES = (
    "_aligned",
    "_interval_overlap",
    "alt_text",
    "capture_environment",
    "check_claim",
    "data_fingerprint",
    "diagnostic_text",
    "disclose_legend_aliases",
    "disclose_panel_aliases",
    "edit_target",
    "facet_key",
    "finding",
    "heading_dollars",
    "layer_artist",
    "legend_alias",
    "legend_alias_path",
    "legend_handle_key",
    "literal_heading_lines",
    "mark_panel_text",
    "metadata_for",
    "metric_label",
    "metric_label_path",
    "new_report",
    "normalize_identities",
    "overlap_phrase",
    "panel_label_value",
    "record_output",
    "run_cli",
    "script_fingerprint",
    "series_artist",
    "significance_result",
    "skip_output",
    "source_legend_handles",
    "validate_legend_aliases",
    "validate_panel_aliases",
    "verify_claims",
    "wrap_heading",
)


def _aligned(frame, subject, reference):
    """Require complete, finite x coverage for the named series."""
    if GROUP is None or Y_FIELD not in frame:
        return None
    columns = [subject] if reference is None else [subject, reference]
    selected = frame[frame[GROUP].isin(columns)]
    if (
        selected.empty
        or selected[X_FIELD].isna().any()
        or selected.duplicated([X_FIELD, GROUP]).any()
    ):
        return None
    pivot = selected.pivot_table(
        index=X_FIELD, columns=GROUP, values=Y_FIELD, aggfunc="mean", dropna=False, observed=True
    )
    if any(column not in pivot.columns for column in columns):
        return None
    pair = pivot[columns].sort_index()
    if not len(pair) or not np.isfinite(pair.to_numpy(dtype=float)).all():
        return None
    return pair


def _interval_overlap(frame, subject, reference):
    """How many shared x values have overlapping intervals, or None.

    None when there is nothing to measure: no reference, no grouping, or no
    uncertainty in the spec, in which case _low was never written.
    """
    if reference is None or GROUP is None or "_low" not in frame:
        return None
    lows = frame.pivot_table(
        index=X_FIELD, columns=GROUP, values="_low", aggfunc="mean", observed=True
    )
    highs = frame.pivot_table(
        index=X_FIELD, columns=GROUP, values="_high", aggfunc="mean", observed=True
    )
    for column in (subject, reference):
        if column not in lows.columns or column not in highs.columns:
            return None
    shared = lows.index.intersection(highs.index).sort_values()
    bounds = [
        lows.loc[shared, subject].to_numpy(dtype=float),
        highs.loc[shared, subject].to_numpy(dtype=float),
        lows.loc[shared, reference].to_numpy(dtype=float),
        highs.loc[shared, reference].to_numpy(dtype=float),
    ]
    usable = np.all([np.isfinite(edge) for edge in bounds], axis=0)
    if not usable.any():
        return None
    mine_low, mine_high, their_low, their_high = (edge[usable] for edge in bounds)
    touching = (mine_low <= their_high) & (their_low <= mine_high)
    return int(np.sum(touching)), int(usable.sum())


def alt_text(frame):
    detail = describe_figure(frame)
    body = ENCODING_SENTENCE + (f" {detail}" if detail else "")
    for claim in CLAIMS:
        if claim.get("_verdict") is not True:
            continue
        wording = claim["wording"].replace("{reference}", str(claim.get("reference")))
        sentence = f"{claim['subject']} {wording}"
        # A claim the spread does not separate is not quoted bare. The bands
        # are what persuade a reader to trust the verdict, so a reader who
        # cannot see them is owed the same caveat.
        overlap = overlap_phrase(claim.get("_overlap"))
        if overlap is not None:
            sentence += f", though {overlap}"
        body += " " + sentence[:1].upper() + sentence[1:] + "."
    return body


def capture_environment(fig=None):
    if RUN_REPORT.get("environment") is not None:
        return RUN_REPORT["environment"]
    import importlib.metadata as package_metadata
    import platform

    unavailable = []

    def installed(name):
        try:
            return package_metadata.version(name)
        except package_metadata.PackageNotFoundError:
            return None
        except Exception:  # noqa: BLE001 -- unreadable distribution metadata stays unavailable
            unavailable.append(name + ".version")
            return None

    def text(value):
        return str(value) if value else None

    core = {
        name: text(getattr(module, "__version__", None))
        for name, module in (
            ("numpy", np),
            ("pandas", pd),
            ("matplotlib", matplotlib),
            ("Pillow", sys.modules.get("PIL")),
        )
    }
    core["freetype"] = text(
        getattr(getattr(matplotlib, "ft2font", None), "__freetype_version__", None)
    )
    rc = None
    font = None
    if fig is not None:
        keys = (
            "font.family",
            "font.size",
            "font.style",
            "font.weight",
            "font.variant",
            "font.stretch",
            "mathtext.fontset",
            "text.usetex",
            "text.parse_math",
            "svg.fonttype",
            "pdf.fonttype",
            "ps.fonttype",
            "savefig.transparent",
            "savefig.facecolor",
            "figure.facecolor",
            "axes.facecolor",
            "path.simplify",
            "path.simplify_threshold",
            "agg.path.chunksize",
            "svg.hashsalt",
        )
        rc = {key: matplotlib.rcParams.get(key) for key in keys}
        try:
            from matplotlib import font_manager

            path = Path(font_manager.findfont(font_manager.FontProperties()))
            font = {
                "family": font_manager.get_font(str(path)).family_name,
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        except Exception:  # noqa: BLE001 -- any failed actual font capture stays unavailable
            unavailable.append("default_font")
    snapshot = {
        "schema_version": 1,
        "capture_stage": "before_export" if fig is not None else "no_export_snapshot",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "optimize": sys.flags.optimize,
            "hash_randomization": bool(sys.flags.hash_randomization),
        },
        "platform": {"system": text(platform.system()), "machine": text(platform.machine())},
        "loaded_core_versions": core,
        "installed_optional_versions": {
            name: installed(name) for name in RUNTIME_OPTIONAL_PACKAGES
        },
        "rendering": {
            "backend": str(matplotlib.get_backend()),
            "figure_inches": list(map(float, fig.get_size_inches())) if fig is not None else None,
            "figure_dpi": float(fig.dpi) if fig is not None else None,
            "export_dpi": DPI,
            "target_width_in": TARGET_WIDTH_IN,
            "requested_formats": list(FORMATS),
            "requested_interactive": RUN_REPORT["spec"]["output"]["interactive"],
            "rc_parameters": rc,
            "default_font": font,
        },
        "execution": dict(
            RUN_REPORT.get(
                "_execution_policy",
                {"strict": None, "fail_on_warning": None, "source": "direct_call"},
            )
        ),
        "random_constants": {
            key: globals()[key]
            for key in ("BOOTSTRAP_SEED", "BOOTSTRAP_DRAWS", "POINT_JITTER_SEED", "PAIR_SEED")
            if key in globals()
        },
        "unavailable": unavailable,
    }
    # Detach mutable rc lists and normalize the stored snapshot to JSON types.
    snapshot = json.loads(json.dumps(snapshot, allow_nan=False))
    RUN_REPORT["environment"] = snapshot
    return snapshot


def check_claim(frame, claim):
    """Return (holds, detail). None means the claim could not be tested."""
    subject, reference = claim["subject"], claim.get("reference")
    tolerance = claim.get("tolerance") or 0.0
    pair = _aligned(frame, subject, reference)
    if pair is None:
        return (
            None,
            "named series are missing, have incomplete x coverage, duplicate x values, or non-finite measurements",
        )

    mine = pair[subject].to_numpy(dtype=float)
    theirs = pair[reference].to_numpy(dtype=float) if reference else None
    kind = claim["kind"]
    if (
        kind
        in ("gap_widens", "gap_narrows", "monotone_increasing", "monotone_decreasing", "converges")
        and len(mine) < 2
    ):
        return None, "at least two x values are required for a trend claim"

    if kind == "beats_everywhere":
        losses = int(np.sum(mine <= theirs))
        return losses == 0, f"{losses} of {len(mine)} x values are not above {reference}"

    if kind == "beats_on_average":
        gap = float(mine.mean() - theirs.mean())
        return gap > 0, f"mean difference is {gap:+.4g}"

    if kind == "beats_at_end":
        gap = float(mine[-1] - theirs[-1])
        return gap > 0, f"difference at the largest x is {gap:+.4g}"

    if kind in ("gap_widens", "gap_narrows"):
        gap = mine - theirs
        half = max(len(gap) // 2, 1)
        early, late = float(gap[:half].mean()), float(gap[half:].mean())
        change = late - early
        widening = kind == "gap_widens"
        holds = change > 0 if widening else change < 0
        return holds, f"gap moves from {early:+.4g} to {late:+.4g}, a change of {change:+.4g}"

    if kind in ("monotone_increasing", "monotone_decreasing"):
        steps = np.diff(mine)
        rising = kind == "monotone_increasing"
        breaks = int(np.sum(steps < -tolerance if rising else steps > tolerance))
        return breaks == 0, f"{breaks} of {len(steps)} steps go the wrong way"

    if kind == "converges":
        tail = max(len(mine) // 5, 1)
        spread = float(np.abs(mine - theirs)[-tail:].max())
        return spread <= tolerance, f"largest gap over the final fifth is {spread:.4g}"

    if kind == "no_worse_than":
        deficit = float(np.max(theirs - mine))
        return deficit <= tolerance, f"largest shortfall against {reference} is {deficit:.4g}"

    if kind == "within_tolerance":
        spread = float(np.max(np.abs(mine - theirs)))
        return spread <= tolerance, f"largest absolute difference is {spread:.4g}"

    return None, f"no test implemented for {kind}"


def data_fingerprint():
    # A figure built from a file that has since changed is worse than no
    # figure, because it looks current.
    try:
        with open(DATA_PATH, "rb") as handle:
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()[:16]
    except OSError:
        return "unreadable"


def diagnostic_text(code, message, severity="warning"):
    advice = DIAGNOSTIC_ADVICE.get(code, UNKNOWN_DIAGNOSTIC)
    return (
        f"{severity.upper()} [{code}] {message}\n"
        f"  Why it matters: {advice['consequence']}\n"
        f"  Recommended correction: {advice['correction']}"
    )


def disclose_legend_aliases(description):
    labels = RUN_REPORT["spec"]["legend"].get("labels", [])
    if not labels:
        return description
    mappings = [f"{item['text']} means source series {item['series']}" for item in labels]
    return description + " Display names: " + "; ".join(mappings) + "."


def disclose_panel_aliases(description):
    spec = RUN_REPORT["spec"]
    mappings = [
        f"{item['text']} means source metric {item['field']}"
        for item in spec.get("repeat", {}).get("labels", [])
    ]
    facet = spec.get("facet", {})
    for item in facet.get("labels", []):
        source = f"{facet['by']}={item['value']}"
        if "row" in item:
            source += f", {facet['rows']}={item['row']}"
        mappings.append(f"{item['text']} means source panel {source}")
    return (
        description
        if not mappings
        else description + " Panel display names: " + "; ".join(mappings) + "."
    )


def edit_target(artist, path, role, source=None, value=None):
    artist._graphunslopify_text_target = {
        "path": path,
        "role": role,
        "source": source,
        "editable": path is not None,
    }
    if value is not None:
        artist._graphunslopify_text_target["value"] = value
    return artist


def facet_key(item):
    return tuple((field, item[field]) for field in ("value", "row") if field in item)


def finding(severity, code, message):
    item = {
        "severity": severity,
        "code": code,
        "message": message,
        **DIAGNOSTIC_ADVICE.get(code, UNKNOWN_DIAGNOSTIC),
    }
    if item not in RUN_REPORT["findings"]:
        RUN_REPORT["findings"].append(item)


def heading_dollars(text):
    return text.count("$") - text.count(r"\$")


def layer_artist(artist, index):
    layer = RUN_REPORT["spec"]["layers"][index]
    if layer.get("label"):
        target = {
            "path": ["layers", index, "label"],
            "role": "layer_label",
            "source": {"layer": index, "mark": layer["mark"]},
        }
        for item in artist if isinstance(artist, list) else [artist]:
            item._graphunslopify_legend_text_target = target
    return artist


def legend_alias(source):
    key = str(source)
    return next(
        (
            item["text"]
            for item in RUN_REPORT["spec"]["legend"].get("labels", [])
            if item["series"] == key
        ),
        key,
    )


def legend_alias_path(source):
    labels = RUN_REPORT["spec"]["legend"].get("labels", [])
    index = next(
        (index for index, item in enumerate(labels) if item["series"] == str(source)), len(labels)
    )
    return ["legend", "labels", index, "text"]


def legend_handle_key(handle, label):
    identity = getattr(handle, "_graphunslopify_legend_identity", None)
    target = getattr(handle, "_graphunslopify_legend_text_target", None)
    if identity is not None:
        return ("series", identity["series"])
    if target is not None:
        return ("layer", target["source"]["layer"])
    return ("external", label)


def literal_heading_lines(lines, original):
    # An originally literal paragraph must not acquire a MathText line.
    index = 0
    while index < len(lines):
        count = heading_dollars(lines[index])
        if count == 0 or count % 2:
            index += 1
            continue
        line = lines[index]
        cuts = [
            match
            for match in re.finditer(r"\s+", line)
            if heading_dollars(line[: match.start()]) % 2
        ]
        if cuts:
            cut = cuts[-1]
            lines[index : index + 1] = [line[: cut.start()], line[cut.end() :]]
            index += 2
            continue
        # A dollar pair inside one word cannot be split without changing it.
        # Keep it with an odd-dollar neighbor; ordinary inspection still owns
        # acceptance if the resulting complete wording cannot fit the column.
        odd = [i for i, text in enumerate(lines) if heading_dollars(text) % 2]
        if not odd:
            return [original]
        neighbor = min(odd, key=lambda i: abs(i - index))
        low, high = sorted((index, neighbor))
        lines[low : high + 1] = [" ".join(lines[low : high + 1])]
        index = low + 1
    return lines


def mark_panel_text(artist, index):
    spec = RUN_REPORT["spec"]
    if "repeat" in spec:
        field = spec["repeat"]["fields"][index]
        return edit_target(
            artist, metric_label_path(field), "metric_label", field, metric_label(field)
        )
    if "facet" in spec:
        labels = spec["facet"].get("labels", [])
        source = PANEL_SOURCE_KEYS[index]
        slot = next(
            (i for i, item in enumerate(labels) if facet_key(item) == facet_key(source)),
            len(labels),
        )
        return edit_target(
            artist,
            ["facet", "labels", slot, "text"],
            "panel_title",
            source,
            panel_label_value(index, PANEL_ORIGINAL_NAMES[index]),
        )
    return artist


def metadata_for(fmt):
    # Embedding the spec means a reviewer can recover what produced the figure.
    stamp = f"{TOOL} spec:{SPEC_HASH} data:{DATA_HASH}"
    provenance = json.dumps(
        {
            "schema_version": 1,
            "tool": TOOL,
            "spec_hash": SPEC_HASH,
            "data_sha256_prefix": DATA_HASH,
            "script_sha256": script_fingerprint(),
            "spec": json.loads(SPEC_JSON),
            "alt_text": ALT_TEXT,
            "environment": capture_environment(),
            **({"runtime": globals()["RUNTIME_BINDING"]} if "RUNTIME_BINDING" in globals() else {}),
        },
        ensure_ascii=False,
    )
    if fmt == "png":
        return {
            "Software": stamp,
            "Description": SPEC_JSON,
            "Comment": ALT_TEXT,
            "GraphUnslopify": provenance,
        }
    if fmt == "svg":
        return {
            "Creator": stamp,
            "Description": ALT_TEXT,
            "Title": FIGURE_TITLE or Path(STEM).name,
            "Identifier": SPEC_HASH,
            "Source": provenance,
            "Date": None,
        }
    return {
        "Creator": stamp,
        "Subject": SPEC_JSON,
        "Keywords": provenance,
        "Title": FIGURE_TITLE or Path(STEM).name,
        "CreationDate": None,
        "ModDate": None,
    }


def metric_label(source):
    labels = RUN_REPORT["spec"].get("repeat", {}).get("labels", [])
    return next((item["text"] for item in labels if item["field"] == str(source)), pretty(source))


def metric_label_path(source):
    labels = RUN_REPORT["spec"].get("repeat", {}).get("labels", [])
    index = next((i for i, item in enumerate(labels) if item["field"] == str(source)), len(labels))
    return ["repeat", "labels", index, "text"]


def new_report():
    return {
        "schema_version": 1,
        "tool": TOOL,
        "spec_hash": SPEC_HASH,
        "spec": json.loads(SPEC_JSON),
        "status": "incomplete",
        "ok": False,
        "data": {},
        "environment": None,
        "findings": [dict(f) for f in STATIC_FINDINGS],
        "inspection": {"available": None, "checked": False},
        "panels": [],
        "claims": [],
        "significance": [],
        "annotations": [],
        "outputs": [],
        "skipped_outputs": [],
        "untested": [],
        "alt_text": "",
    }


def normalize_identities(frame, *, final=True):
    if IDENTITY_CONFLICTS:
        raise ValueError(
            "Columns cannot serve both identifier and measurement roles: "
            + ", ".join(IDENTITY_CONFLICTS)
        )
    for key in ("series_order", "category_order"):
        order = RUN_REPORT["spec"].get(key)
        if order is not None and len(order) != len(set(order)):
            raise ValueError(key + " must contain unique identifiers")
    source = frame.copy()
    lexical = source.attrs.pop("_graphunslopify_identity_rows", {})
    for field in IDENTITY_FIELDS:
        if field not in source:
            if final and field in REQUIRED_IDENTITY_FIELDS:
                raise ValueError(f"Required identifier column {field} is missing")
            continue
        values = source[field].tolist()
        if field in lexical:
            values = [lexical[field][int(index)] for index in source.index]
        seen = {}

        def as_identifier(value, field=field, seen=seen):
            if not pd.api.types.is_scalar(value):
                raise ValueError(f"Identifier {field} must contain scalar values")
            if pd.isna(value):
                return None
            if isinstance(value, (float, np.floating)) and not np.isfinite(value):
                raise ValueError(f"Numeric identifier {field} must be finite")
            text = str(value)
            if not text.strip():
                raise ValueError(f"Identifier {field} must be nonempty")
            if text in seen and seen[text] != value:
                raise ValueError(
                    f"Distinct identifiers in {field} collide as textual name {text!r}"
                )
            seen[text] = value
            return text

        normalized = [as_identifier(value) for value in values]
        dtype = source[field].dtype
        if isinstance(dtype, pd.CategoricalDtype):
            categories = [as_identifier(value) for value in dtype.categories]
            source[field] = pd.Categorical(normalized, categories=categories, ordered=dtype.ordered)
        else:
            source[field] = pd.Series(normalized, index=source.index, dtype=object)
        if field in REQUIRED_IDENTITY_FIELDS and source[field].isna().any():
            raise ValueError(f"Required identifier {field} is missing for retained observations")
    return source


def overlap_phrase(measured):
    # Counts, not a p-value. Non-overlapping intervals imply a difference;
    # overlapping ones do not imply its absence, and Cumming's mapping from
    # overlap to significance is conditioned on n. Report what was measured.
    if measured is None or measured[0] == 0:
        return None
    return f"the intervals overlap at {measured[0]} of {measured[1]} x values"


def panel_label_value(index, original):
    labels = RUN_REPORT["spec"].get("facet", {}).get("labels", [])
    if not labels:
        return str(original)
    key = facet_key(PANEL_SOURCE_KEYS[index])
    return next((item["text"] for item in labels if facet_key(item) == key), str(original))


def record_output(path):
    path = Path(path)
    if path.suffix.lower() == ".svg":
        text = path.read_text(encoding="utf8")
        title_id, description_id = f"title-{SPEC_HASH}", f"description-{SPEC_HASH}"
        if f'<desc id="{description_id}">' not in text:
            end = text.index(">", text.index("<svg "))
            attributes = (
                f' role="img" aria-labelledby="{title_id}" aria-describedby="{description_id}"'
            )
            text = text[:end] + attributes + text[end:]
            text = text.replace("<title>", f'<title id="{title_id}">', 1)
            description = f'<desc id="{description_id}">{escape(ALT_TEXT)}</desc>'
            text = text.replace("</title>", "</title>\n " + description, 1)
            # Normalize path formatting, preserving meaningful metadata whitespace.
            text = re.sub(
                r'(<path\b[^>]*\bd=")([^"]*)(")',
                lambda m: m[1] + "\n".join(line.rstrip() for line in m[2].split("\n")) + m[3],
                text,
            )
            path.write_text(text, encoding="utf8")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    RUN_REPORT["outputs"].append(
        {
            "path": str(path),
            "format": path.suffix[1:],
            "sha256": digest.hexdigest(),
            "bytes": path.stat().st_size,
        }
    )


def run_cli(argv=None):
    global RUN_REPORT, DATA_HASH, ALT_TEXT, SAMPLE_SIZE_TEXT, Y_FIELD  # noqa: PLW0603 -- reset the bound program context
    parser = argparse.ArgumentParser(
        description="Render this figure and write its verification evidence"
    )
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="reject failed or incomplete verification (default)",
    )
    policy.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="explicit legacy opt-out; keep failed/incomplete reports without verification exit 2",
    )
    parser.add_argument(
        "--fail-on-warning", action="store_true", help="strict mode, also rejecting warnings"
    )
    parser.add_argument(
        "--report", default=f"{STEM}.report.json", metavar="FILE", help="JSON report destination"
    )
    parser.add_argument(
        "--json", action="store_true", help="print only JSON on stdout; rendering logs go to stderr"
    )
    args = parser.parse_args(argv)
    if args.report == "-":
        parser.error("use --json for JSON stdout; --report expects a file path")
    RUN_REPORT = new_report()
    RUN_REPORT["_execution_policy"] = {
        "strict": args.strict or args.fail_on_warning,
        "fail_on_warning": args.fail_on_warning,
        "source": "cli",
    }
    DATA_HASH, ALT_TEXT, SAMPLE_SIZE_TEXT = "unknown", "", ""
    Y_FIELD = RUN_REPORT["spec"]["y"]["field"]
    ROW_COUNTS.clear()
    globals().get("MISSING_INTERVALS", {}).clear()
    logs = io.StringIO()
    runtime_failure = False
    try:
        with contextlib.redirect_stdout(logs):
            main()
    except (Exception, SystemExit) as problem:  # noqa: BLE001 -- CLI records all runtime failures
        runtime_failure = True
        finding("error", "runtime_error", str(problem) or type(problem).__name__)
    report = finish_report()
    rejected = ((args.strict or args.fail_on_warning) and not report["ok"]) or (
        args.fail_on_warning and any(f["severity"] == "warning" for f in report["findings"])
    )
    report["exit_code"] = 1 if runtime_failure else 2 if rejected else 0
    report["policy"] = {
        "strict": args.strict or args.fail_on_warning,
        "fail_on_warning": args.fail_on_warning,
        "passed": report["exit_code"] == 0,
    }
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    path = Path(args.report)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf8")
    except OSError as problem:
        print(f"could not write report {path}: {problem}", file=sys.stderr)
        return 1
    if logs.getvalue():
        print(logs.getvalue(), end="", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(encoded, end="")
    else:
        print(f"verification: {report['status']}; wrote {path}")
        for item in report["findings"]:
            print(
                diagnostic_text(item["code"], item["message"], item["severity"]),
                file=sys.stderr if item["code"] == "runtime_error" else sys.stdout,
            )
        for reason in report["untested"]:
            print(diagnostic_text("check_untested", reason))
        for claim in report["claims"]:
            if claim["verdict"] in {"fails", "untested"}:
                print(
                    diagnostic_text(
                        "claim_failed" if claim["verdict"] == "fails" else "check_untested",
                        claim.get("detail", claim["kind"]),
                        "error" if claim["verdict"] == "fails" else "warning",
                    )
                )
    return report["exit_code"]


def script_fingerprint():
    try:
        with open(__file__, "rb") as handle:
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()
    except (NameError, OSError):
        return None


def series_artist(artist, source, suffix="", legend=True):
    if source is not None:
        for target in artist if isinstance(artist, list) else [artist]:
            target._graphunslopify_legend_identity = {
                "series": str(source),
                "suffix": suffix,
                "legend": legend,
            }
    return artist


def significance_result(left, right, **details):
    item = {"panel": CURRENT_PANEL, "pair": [str(left), str(right)], **details}
    # Insets and broken axes redraw the same logical comparison.
    RUN_REPORT["significance"] = [
        old
        for old in RUN_REPORT["significance"]
        if (old["panel"], old["pair"]) != (item["panel"], item["pair"])
    ]
    RUN_REPORT["significance"].append(item)


def skip_output(kind, reason):
    RUN_REPORT["skipped_outputs"].append({"format": kind, "reason": reason})
    finding("warning", "output_skipped", f"{kind}: {reason}")


def source_legend_handles(axes):
    ordinary, labels = axes.get_legend_handles_labels()
    public = {id(handle): label for handle, label in zip(ordinary, labels, strict=False)}
    handles, names, seen = [], [], set()
    for handle in [*axes.get_children(), *axes.containers]:
        identity = getattr(handle, "_graphunslopify_legend_identity", None)
        include = (
            identity.get("legend", True)
            if identity is not None
            else (
                id(handle) in public
                or getattr(handle, "_graphunslopify_legend_text_target", None) is not None
            )
        )
        if include and id(handle) not in seen:
            handles.append(handle)
            names.append(public.get(id(handle), handle.get_label()))
            seen.add(id(handle))
    return handles, names


def validate_legend_aliases(frame):
    labels = RUN_REPORT["spec"]["legend"].get("labels", [])
    if not labels:
        return
    if GROUP is None or GROUP not in frame:
        raise ValueError("Legend display names require a source grouping column")
    names = [str(name) for name in series_names(frame)]
    if len(set(names)) != len(names):
        raise ValueError("Source series IDs have ambiguous string representations")
    requested = [item["series"] for item in labels]
    if len(set(requested)) != len(requested):
        raise ValueError("Each source series may have only one legend display name")
    unknown = sorted(set(requested) - set(names))
    if unknown:
        raise ValueError(f"Legend display names refer to unknown source series: {unknown}")
    if any(not item["text"].strip() for item in labels):
        raise ValueError("Legend display names must contain visible text")
    displayed = [legend_alias(name).strip() for name in names]
    if len(set(displayed)) != len(displayed):
        raise ValueError("Legend display names must uniquely identify source series")


def validate_panel_aliases(frame, blocks):
    spec = RUN_REPORT["spec"]
    repeat = spec.get("repeat", {})
    labels = repeat.get("labels", [])
    if labels:
        fields = repeat["fields"]
        requested = [item["field"] for item in labels]
        if len(set(fields)) != len(fields) or len(set(requested)) != len(requested):
            raise ValueError("Repeated metric labels require unique source fields and overrides")
        if any(field not in fields or field not in frame for field in requested):
            raise ValueError("Metric display names refer to unknown prepared source fields")
        shown = [metric_label(field).strip() for field in fields]
        if any(not item["text"].strip() for item in labels) or len(set(shown)) != len(shown):
            raise ValueError(
                "Metric display names must visibly and uniquely identify source fields"
            )
    facet = spec.get("facet", {})
    labels = facet.get("labels", [])
    if labels:
        keys = [facet_key(item) for item in PANEL_SOURCE_KEYS]
        requested = [facet_key(item) for item in labels]
        if len(set(keys)) != len(keys) or len(set(requested)) != len(requested):
            raise ValueError(
                "Facet display names require unambiguous source values and unique overrides"
            )
        if any(("row" in item) != ("rows" in facet) for item in labels):
            raise ValueError(
                "Facet display names must include row values exactly for two-dimensional facets"
            )
        if any(key not in keys for key in requested):
            raise ValueError("Facet display names refer to unknown prepared source panels")
        shown = [panel_label_value(i, name).strip() for i, (name, _) in enumerate(blocks)]
        if any(not item["text"].strip() for item in labels) or len(set(shown)) != len(shown):
            raise ValueError("Facet display names must visibly and uniquely identify source panels")


def verify_claims(frame):
    """Test every claim. Returns True when none of them failed."""
    if not CLAIMS:
        return True
    print("claims:")
    ok = True
    for claim in CLAIMS:
        holds, detail = check_claim(frame, claim)
        wording = claim["wording"].replace("{reference}", str(claim.get("reference")))
        sentence = f"{claim['subject']} {wording}"
        if holds is None:
            print(f"  UNTESTED  {sentence} ({detail})")
            continue
        if holds:
            print(f"  HOLDS     {sentence} ({detail})")
            overlap = overlap_phrase(
                _interval_overlap(frame, claim["subject"], claim.get("reference"))
            )
            if overlap is not None:
                print(f"            but {overlap}, so the spread does not separate them")
        else:
            ok = False
            print(f"  FAILS     {sentence} ({detail})")
            print("            the figure does not support this. Do not write it in the caption.")
    return ok


def wrap_heading(original, artist, renderer, width):
    from matplotlib.text import Text

    probe = Text(
        fontproperties=artist.get_fontproperties(),
        usetex=artist.get_usetex(),
        parse_math=artist.get_parse_math(),
    )
    probe.set_figure(artist.get_figure())
    parse_math, use_tex = artist.get_parse_math(), artist.get_usetex()
    lines = []
    for paragraph in original.split("\n"):
        dollars = heading_dollars(paragraph)
        mathematical = (parse_math or use_tex) and dollars > 0 and dollars % 2 == 0
        probe.set_parse_math(parse_math and mathematical)
        paragraph_lines = []
        tokens, token = [], ""
        math_mode, depth, escaped, space = False, 0, False, False
        for position, char in enumerate(paragraph):
            separable = char.isspace() and not math_mode and depth == 0 and not escaped
            if token and separable != space:
                tokens.append(token)
                token = ""
            token += char
            space = separable
            dollar_boundary = (
                not escaped if use_tex else position == 0 or paragraph[position - 1] != "\\"
            )
            if char == "$" and mathematical and dollar_boundary:
                math_mode = not math_mode
            elif not escaped:
                if char == "{" and (math_mode or use_tex):
                    depth += 1
                elif char == "}" and depth:
                    depth -= 1
            escaped = char == "\\" and not escaped
        if token:
            tokens.append(token)
        line, separator = "", ""
        for token in tokens:
            if token.isspace():
                separator += token
                continue
            candidate = line + separator + token
            probe.set_text(
                candidate.replace(r"\$", "$")
                if parse_math and not mathematical and not use_tex
                else candidate
            )
            if line and probe.get_window_extent(renderer).width > width:
                paragraph_lines.append(line)
                line = token
            else:
                line = candidate
            separator = ""
        paragraph_lines.append(line + separator)
        if parse_math and not mathematical and not use_tex and dollars > 1:
            paragraph_lines = literal_heading_lines(paragraph_lines, paragraph)
        lines.extend(paragraph_lines)
    return "\n".join(lines)


_TEMPLATES = {name: globals()[name] for name in FUNCTION_NAMES}
_SOURCE_SHA256 = _runtime_hashlib.sha256(_RuntimePath(__file__).read_bytes()).hexdigest()


def runtime_info() -> dict[str, Any]:
    """Identify actual helper bytes/capabilities, independently of package version."""
    return {"abi": RUNTIME_ABI, "source_sha256": _SOURCE_SHA256, "functions": list(FUNCTION_NAMES)}


def bind(
    namespace: dict[str, Any],
    *,
    abi: int,
    source_sha256: str,
    required: list[str] | tuple[str, ...],
    components: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Install canonical function code with isolated per-program globals/defaults.

    Validation/cloning precedes mutation. Shared templates retain no program
    namespace, data or reports. Actual module source drift is also refused.
    """
    actual = runtime_info()
    advice = None
    guidance = (
        "Install the exact GraphUnslopify runtime that generated this figure; "
        "an archival bundle must include its matching runtime."
    )
    if type(abi) is not int or abi != RUNTIME_ABI or source_sha256 != _SOURCE_SHA256:
        raise RuntimeError(f"Figure runtime ABI/source mismatch. {guidance}")
    if _runtime_hashlib.sha256(_RuntimePath(__file__).read_bytes()).hexdigest() != _SOURCE_SHA256:
        raise RuntimeError(f"Figure runtime source changed after import. {guidance}")
    if components is not None:
        if not isinstance(components, dict) or set(components) != set(SOURCE_COMPONENTS):
            raise RuntimeError(f"Figure runtime component capabilities mismatch. {guidance}")
        try:
            actual_components = {
                name: _runtime_hashlib.sha256(
                    _RuntimePath(__file__).parent.joinpath(name).read_bytes()
                ).hexdigest()
                for name in SOURCE_COMPONENTS
            }
        except OSError as problem:
            raise RuntimeError(f"Figure runtime component is unavailable. {guidance}") from problem
        if actual_components != components:
            raise RuntimeError(f"Figure runtime component source mismatch. {guidance}")
        actual["components"] = actual_components
        advice = _runtime_json.loads(
            _RuntimePath(__file__).with_name("diagnostics.json").read_text(encoding="utf8")
        )
    if not isinstance(namespace, dict):
        raise TypeError("Figure runtime requires the generated program's own globals dictionary")
    if (
        not isinstance(required, (list, tuple))
        or not required
        or not all(isinstance(name, str) for name in required)
        or len(set(required)) != len(required)
        or any(name not in _TEMPLATES for name in required)
    ):
        raise RuntimeError(f"Figure runtime capabilities mismatch. {guidance}")
    bindings = {}
    for name in required:
        template = _TEMPLATES[name]
        if template.__closure__ is not None:
            raise RuntimeError(f"Figure runtime template {name} unexpectedly captures state")
        function = _FunctionType(
            template.__code__, namespace, name, _runtime_copy.deepcopy(template.__defaults__)
        )
        function.__kwdefaults__ = _runtime_copy.deepcopy(template.__kwdefaults__)
        function.__annotations__ = dict(template.__annotations__)
        function.__dict__.update(_runtime_copy.deepcopy(template.__dict__))
        bindings[name] = function
    if advice is not None:
        bindings["DIAGNOSTIC_ADVICE"] = _runtime_copy.deepcopy(advice["advice"])
        bindings["UNKNOWN_DIAGNOSTIC"] = _runtime_copy.deepcopy(advice["unknown"])
    namespace.update(bindings)
    return actual
