import type { FigureSpec } from "../schema.ts";
import { verify } from "../verify.ts";
import { pyStr } from "./py.ts";

/** Runtime evidence lives in each generated program, including offline copies. */
export function emitRuntime(spec: FigureSpec, out: string[]): void {
  const derivedFrame = spec.kind === "kaplan_meier" ? "survival_claim_frame"
    : spec.kind === "calibration" ? "calibration_claim_frame"
      : spec.kind === "qq" ? "qq_claim_frame" : undefined;
  const summary = derivedFrame ? `${derivedFrame}(frame) if CLAIMS and not frame.empty else frame`
    : 'summarise(frame) if not frame.empty and "aggregation" in RUN_REPORT["spec"] and RUN_REPORT["spec"]["kind"] != "heatmap" else frame';

  out.push("", `STATIC_FINDINGS = json.loads(${pyStr(JSON.stringify(verify(spec)))})`);
  out.push(...`

def new_report():
    return {
        "schema_version": 1, "tool": TOOL, "spec_hash": SPEC_HASH,
        "spec": json.loads(SPEC_JSON), "status": "incomplete", "ok": False,
        "data": {}, "environment": None, "findings": [dict(f) for f in STATIC_FINDINGS],
        "inspection": {"available": None, "checked": False},
        "panels": [], "claims": [], "significance": [], "annotations": [], "outputs": [],
        "skipped_outputs": [], "untested": [], "alt_text": "",
    }


RUN_REPORT = new_report()
CURRENT_PANEL = 0


def finding(severity, code, message):
    item = {"severity": severity, "code": code, "message": message}
    if item not in RUN_REPORT["findings"]:
        RUN_REPORT["findings"].append(item)


def record_output(path):
    path = Path(path)
    if path.suffix.lower() == ".svg":
        text = path.read_text(encoding="utf8")
        title_id, description_id = f"title-{SPEC_HASH}", f"description-{SPEC_HASH}"
        if f'<desc id="{description_id}">' not in text:
            end = text.index(">", text.index("<svg "))
            attributes = f' role="img" aria-labelledby="{title_id}" aria-describedby="{description_id}"'
            text = text[:end] + attributes + text[end:]
            text = text.replace("<title>", f'<title id="{title_id}">', 1)
            description = f'<desc id="{description_id}">{escape(ALT_TEXT)}</desc>'
            text = text.replace("</title>", "</title>\\n " + description, 1)
            # Normalize path formatting, preserving meaningful metadata whitespace.
            text = re.sub(r'(<path\\b[^>]*\\bd=")([^"]*)(")',
                          lambda m: m[1] + "\\n".join(line.rstrip() for line in m[2].split("\\n")) + m[3], text)
            path.write_text(text, encoding="utf8")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    RUN_REPORT["outputs"].append({"path": str(path), "format": path.suffix[1:],
                                  "sha256": digest.hexdigest(), "bytes": path.stat().st_size})


def skip_output(kind, reason):
    RUN_REPORT["skipped_outputs"].append({"format": kind, "reason": reason})
    finding("warning", "output_skipped", f"{kind}: {reason}")


def significance_result(left, right, **details):
    item = {"panel": CURRENT_PANEL, "pair": [str(left), str(right)], **details}
    # Insets and broken axes redraw the same logical comparison.
    RUN_REPORT["significance"] = [old for old in RUN_REPORT["significance"]
        if (old["panel"], old["pair"]) != (item["panel"], item["pair"])]
    RUN_REPORT["significance"].append(item)


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


def run_cli(argv=None):
    global RUN_REPORT, DATA_HASH, ALT_TEXT, SAMPLE_SIZE_TEXT, Y_FIELD
    parser = argparse.ArgumentParser(description="Render this figure and write its verification evidence")
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument("--strict", action="store_true", default=True, help="reject failed or incomplete verification (default)")
    policy.add_argument("--no-strict", dest="strict", action="store_false", help="explicit legacy opt-out; keep failed/incomplete reports without verification exit 2")
    parser.add_argument("--fail-on-warning", action="store_true", help="strict mode, also rejecting warnings")
    parser.add_argument("--report", default=f"{STEM}.report.json", metavar="FILE", help="JSON report destination")
    parser.add_argument("--json", action="store_true", help="print only JSON on stdout; rendering logs go to stderr")
    args = parser.parse_args(argv)
    if args.report == "-":
        parser.error("use --json for JSON stdout; --report expects a file path")
    RUN_REPORT = new_report()
    RUN_REPORT["_execution_policy"] = {"strict": args.strict or args.fail_on_warning, "fail_on_warning": args.fail_on_warning, "source": "cli"}
    DATA_HASH, ALT_TEXT, SAMPLE_SIZE_TEXT = "unknown", "", ""
    Y_FIELD = RUN_REPORT["spec"]["y"]["field"]
    ROW_COUNTS.clear()
    globals().get("MISSING_INTERVALS", {}).clear()
    logs = io.StringIO()
    runtime_failure = False
    try:
        with contextlib.redirect_stdout(logs):
            main()
    except (Exception, SystemExit) as problem:
        runtime_failure = True
        finding("error", "runtime_error", str(problem) or type(problem).__name__)
    report = finish_report()
    rejected = ((args.strict or args.fail_on_warning) and not report["ok"]
                or args.fail_on_warning and any(f["severity"] == "warning" for f in report["findings"]))
    report["exit_code"] = 1 if runtime_failure else 2 if rejected else 0
    report["policy"] = {"strict": args.strict or args.fail_on_warning, "fail_on_warning": args.fail_on_warning,
                        "passed": report["exit_code"] == 0}
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\\n"
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
            if item["code"] == "runtime_error":
                print(item["message"], file=sys.stderr)
    return report["exit_code"]

`.trimEnd().split("\n"));
}
