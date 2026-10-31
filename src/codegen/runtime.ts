import { RUNTIME_HELPERS } from "./runtime-source.ts";
import type { FigureSpec } from "../schema.ts";
import { verify } from "../verify.ts";
import { pyStr } from "./py.ts";
import { DIAGNOSTIC_ADVICE, UNKNOWN_DIAGNOSTIC } from "../diagnostics.ts";

/** Runtime evidence lives in each generated program, including offline copies. */
export function emitRuntime(spec: FigureSpec, out: string[]): void {
  const derivedFrame = spec.kind === "kaplan_meier" ? "survival_claim_frame"
    : spec.kind === "calibration" ? "calibration_claim_frame"
      : spec.kind === "qq" ? "qq_claim_frame" : undefined;
  const summary = derivedFrame ? `${derivedFrame}(frame) if CLAIMS and not frame.empty else frame`
    : 'summarise(frame) if not frame.empty and "aggregation" in RUN_REPORT["spec"] and RUN_REPORT["spec"]["kind"] != "heatmap" else frame';

  out.push("", `STATIC_FINDINGS = json.loads(${pyStr(JSON.stringify(verify(spec)))})`);
  out.push(`DIAGNOSTIC_ADVICE = json.loads(${pyStr(JSON.stringify(DIAGNOSTIC_ADVICE))})`,
    `UNKNOWN_DIAGNOSTIC = json.loads(${pyStr(JSON.stringify(UNKNOWN_DIAGNOSTIC))})`);
  out.push(...`

${RUNTIME_HELPERS.edit_target}


${RUNTIME_HELPERS.series_artist}


${RUNTIME_HELPERS.layer_artist}


${RUNTIME_HELPERS.legend_handle_key}


${RUNTIME_HELPERS.source_legend_handles}


${RUNTIME_HELPERS.legend_alias}


${RUNTIME_HELPERS.legend_alias_path}


${RUNTIME_HELPERS.validate_legend_aliases}


${RUNTIME_HELPERS.disclose_legend_aliases}


PANEL_SOURCE_KEYS = []
PANEL_ORIGINAL_NAMES = []


${RUNTIME_HELPERS.metric_label}


${RUNTIME_HELPERS.metric_label_path}


${RUNTIME_HELPERS.facet_key}


${RUNTIME_HELPERS.panel_label_value}


${RUNTIME_HELPERS.mark_panel_text}


${RUNTIME_HELPERS.validate_panel_aliases}


${RUNTIME_HELPERS.disclose_panel_aliases}


${RUNTIME_HELPERS.new_report}


RUN_REPORT = new_report()
CURRENT_PANEL = 0


${RUNTIME_HELPERS.finding}


${RUNTIME_HELPERS.diagnostic_text}


${RUNTIME_HELPERS.record_output}


${RUNTIME_HELPERS.skip_output}


${RUNTIME_HELPERS.significance_result}


def describe_panels(blocks):
    global Y_FIELD, SAMPLE_SIZE_TEXT
    original_y, original_n = Y_FIELD, SAMPLE_SIZE_TEXT
    descriptions = []
    try:
        for index, (name, frame) in enumerate(blocks):
            if "REPEAT_FIELDS" in globals():
                Y_FIELD = name
            if frame.empty:
                reason = f"panel {name} has no data"
                finding("warning", "empty_panel", reason)
                RUN_REPORT["untested"].append(reason)
            summary = ${summary}
            label = str(name) if name is not None else None
            panel = {"index": index, "name": label, "metric": Y_FIELD}
            RUN_REPORT["panels"].append(panel)
            verify_claims(summary)
            for claim in CLAIMS:
                verdict, detail = check_claim(summary, claim)
                measured = _interval_overlap(summary, claim["subject"], claim.get("reference"))
                claim["_verdict"], claim["_overlap"] = verdict, measured
                record = {k: v for k, v in claim.items() if not k.startswith("_")}
                record.update({"panel": index, "metric": Y_FIELD, "detail": detail,
                               "verdict": "untested" if verdict is None else "holds" if verdict else "fails",
                               "interval_overlap": measured})
                RUN_REPORT["claims"].append(record)
            # Keep the original single-panel description byte-for-byte where possible.
            SAMPLE_SIZE_TEXT = original_n if len(blocks) == 1 else ""
            body = "No data." if frame.empty else alt_text(${derivedFrame ? "frame" : "summary"})
            if len(blocks) > 1:
                body = body.removeprefix(ENCODING_SENTENCE).strip()
                body = f"Panel {label if label is not None else index + 1}: {body}"
            descriptions.append(body)
    finally:
        Y_FIELD, SAMPLE_SIZE_TEXT = original_y, original_n
    if len(blocks) == 1:
        description = descriptions[0]
    else:
        counts = f" {original_n}." if original_n else ""
        description = ENCODING_SENTENCE + counts + " " + " ".join(descriptions)
${spec.filter?.length ? `    selection = ROW_COUNTS.get("filtering", {})
    if selection.get("removed_rows", 0):
        description += f" Selected {selection['retained_rows']} of {selection['source_rows']} source rows; {selection['removed_rows']} excluded by declared filters."
` : ""}    if AUTHOR_CONTEXT:
        description += f" {AUTHOR_CONTEXT}"
    return description


def finish_report():
    capture_environment()
    RUN_REPORT.pop("_execution_policy", None)
    RUN_REPORT["script"] = {"sha256": script_fingerprint()}
    RUN_REPORT["data"] = {"path": DATA_PATH, "sha256_prefix": DATA_HASH, "counts": dict(ROW_COUNTS)}
    RUN_REPORT["alt_text"] = ALT_TEXT
    for field, counts in ROW_COUNTS.get("measurements", {}).items():
        if counts["nonfinite"]:
            finding("warning", "nonfinite_measurements", f"{counts['nonfinite']} non-finite measurements in {field}")
    if ROW_COUNTS.get("missing_plot_keys", 0):
        finding("warning", "missing_plot_keys", f"{ROW_COUNTS['missing_plot_keys']} rows lack plotting keys")
    if ROW_COUNTS.get("finite") == 0:
        RUN_REPORT["untested"].append("no finite measurements in the requested value field")
    if ROW_COUNTS.get("prepared", 0) and ROW_COUNTS.get("missing_plot_keys") == ROW_COUNTS["prepared"]:
        RUN_REPORT["untested"].append("no assignable plotting keys")
    if ROW_COUNTS.get("unlisted_series"):
        finding("warning", "unlisted_series_retained", "Unlisted series were retained: " + ", ".join(ROW_COUNTS["unlisted_series"]))
    sizes = ROW_COUNTS.get("sample_sizes", [])
    if sizes and min(sizes) != max(sizes):
        finding("warning", "unequal_sample_sizes", "Sample sizes differ between plotted points")
    if ROW_COUNTS.get("missing_unit_ids", 0):
        finding("warning", "missing_unit_ids", f"{ROW_COUNTS['missing_unit_ids']} rows lack a declared unit ID")
    if RUN_REPORT["spec"].get("uncertainty") and sizes and min(sizes) < 2:
        RUN_REPORT["untested"].append("uncertainty: fewer than two observations at one or more points")
        finding("warning", "uncertainty_unavailable", RUN_REPORT["untested"][-1])
${spec.annotate?.length ? "    finalize_annotations()\n" : ""}    failed = (any(f["severity"] == "error" for f in RUN_REPORT["findings"])
              or any(c["verdict"] == "fails" for c in RUN_REPORT["claims"]))
    incomplete = (not RUN_REPORT["inspection"]["checked"] or bool(RUN_REPORT["untested"])
                  or bool(RUN_REPORT["skipped_outputs"])
                  or any(c["verdict"] == "untested" for c in RUN_REPORT["claims"])
                  or any(c["status"] == "untested" for c in RUN_REPORT["significance"]))
    RUN_REPORT["status"] = "failed" if failed else "incomplete" if incomplete else "passed"
    RUN_REPORT["ok"] = RUN_REPORT["status"] == "passed"
    return RUN_REPORT


${RUNTIME_HELPERS.run_cli}

`.trimEnd().split("\n"));
}
