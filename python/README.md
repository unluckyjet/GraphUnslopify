# GraphUnslopify

Translate semantic JSON into reviewable Python figures, render local data, and check claims,
readability and accessibility. The package includes the TypeScript translator and a Node runtime;
translation and rendering need no hosted service after installation.

In a Python 3.10+ virtual environment:

```sh
python -m pip install graphunslopify==0.8.0
```

For a complete first-figure walkthrough, read the [five-minute guide](https://github.com/unluckyjet/GraphUnslopify/blob/main/docs/getting-started.md).

From a source checkout, `python -m pip install ./python` remains supported.

```sh
graphunslopify doctor
graphunslopify demo
graphunslopify render graphunslopify-demo/figure.json --strict --json
```

The demo creates public synthetic CSV data and PNG/SVG/PDF figures, a reviewable Python program,
and a JSON verification report. Data paths in a JSON spec resolve beside the spec file.
`graphunslopify translate figure.json --output figure.py` emits code without rendering.

Current development source uses a compact entry program bound to the exact scientific runtime
that generated it. For a portable source archive, use `graphunslopify bundle figure.json --output
figure.zip` or `Figure(...).bundle("figure.zip")`, then follow `REPRODUCE.md` in the ZIP.
The archive includes runtime source and licenses; third-party scientific libraries stay external.
This source feature does not change the published0.8.0 release. See [runtime and bundle details](../docs/figure-runtime.md).

`graphunslopify preview --open` launches the packaged offline browser editor. Choose data, edit a
spec or recipe, review live strict previews and apply an offered fix. Download figures, Python,
spec and report together; input data enters the ZIP only when explicitly selected.
See [the local editor workflow](../docs/local-editor.md), including VS Code's integrated terminal.

```python
from graphunslopify import Figure

Figure.line("results.csv").x("epoch", "Epoch").y("score", "Score").render(strict=True)
```

`Figure.translate()` and `Figure.from_profile()` default to the packaged local translator.
Select a hosted translator explicitly with `api="https://your-service"` or
`GRAPHUNSLOPIFY_API`; use `api="local"` to override that environment setting.
`GRAPHUNSLOPIFY_NODE` can select a specific Node executable.

Current development source enables strict verification by default in `Figure.render()` and
execution commands. Explicit `strict=False` / `--no-strict` opts out while retaining failed or
incomplete report verdicts; warning rejection always implies strict mode. The pinned0.8.0 wheel uses these defaults. Older 0.7.0 installs require `strict=True` / `--strict`.

Use `[interactive]` for supported self-contained Plotly HTML. Strict verification rejects failed
or untested required checks; literal data claims are not statistical significance tests.
Read the repository documentation for the supported combinations and limits.

## Trace how observations reach the prepared data

Enable local reader, filter and preparation tracing on a render.

```sh
graphunslopify render figure.json --trace-observations --json
```

The SDK equivalent is `figure.render(trace_observations=True)`. The report's
`observation_selection` names the evidence file and two roots. `node_id` is
the reader and filter selection. `preparation_node_id` is present after
successful preparation. The SDK returns the file as `observation_path`. Load it with
`ObservationLedger.from_json(path.read_bytes())` from
`graphunslopify.observation_provenance` and call `explain(root_node_id)`.

The graph follows parsed records through filters, wide reshaping, numeric
conversion, cumulative totals, normalization, and baseline comparisons. It
keeps duplicate records distinct and records why a record was filtered out,
missing, unmatched, or hidden after a baseline comparison. Ordinals start at
zero and refer to parsed records, including quoted CSV records spanning multiple
lines. The graph records derived values locally. This evidence covers
preparation before statistical summaries and per-mark rendering.

## What it checks

`text_too_small` and `text_near_minimum` measure every text element at the width the figure will
occupy on the page. Generated programs measure their written PNG/SVG/PDF widths, including
tight cropping and padding, before calculating manuscript scaling. For your own figure, pass
`target_width_in` and `export_paths=["figure.pdf"]` after saving; without paths the API uses the
nominal canvas. Reports retain the measured widths and scale. See
[the measurement contract and limits](../docs/export-legibility.md).

`tick_labels_collide` compares neighbouring tick label bounding boxes. `legend_covers_data` counts
plotted points falling inside the legend box. `overplotting` measures marker ink against plotting
area.

`series_indistinguishable` measures CIEDE2000 between every pair of legend colours as composited
over white, then repeats it under simulated protanopia, deuteranopia and tritanopia.
`greyscale_collision` catches pairs that survive colour but merge in a black and white print, and
stays quiet when a second channel such as line style or marker already separates them.

`truncated_bar_axis` is an error, because a bar's length encodes its value. `axis_exaggeration`
warns when a line axis is zoomed so far that a rounding error fills the frame.

Every check is geometric or colorimetric. Nothing asks a model for an opinion, so the same figure
always yields the same findings. Reasoning and sources are in [research notes](https://github.com/unluckyjet/GraphUnslopify/blob/v0.8.0/docs/research.md).


[Source](https://github.com/unluckyjet/GraphUnslopify) · [Versioned 0.8.0 documentation](https://github.com/unluckyjet/GraphUnslopify/tree/v0.8.0/docs) · [Release assets](https://github.com/unluckyjet/GraphUnslopify/releases/tag/v0.8.0).
MIT license. The bundled translator includes Zod's MIT license; runtime/dependency licenses ship
with their respective Python distributions.

## Paper audits

`graphunslopify audit paper/ --out-dir audit-output` regenerates all figures in the directory’s
`graphunslopify.json` manifest with strict verification. `--baseline previous/audit.report.json`
adds data, numeric-representation, claim, description and artifact differences. It writes aggregate
JSON/Markdown plus individual programs, figures, logs and reports. See the repository paper-audit
guide for the manifest contract and supported metadata-backed artifact checks.

Current source after0.8.0 adds `project-init`, `project-status`, `project-run`,
`project-shared` and `project-history` around the same manifest. They retain
complete audit/settings history, check declared input/export freshness and apply
shared semantic settings to JSON figures. Authored scripts retain their own
source and must meet the requested shared policy. See [project management](../docs/project-management.md);
`graphunslopify project-preview paper/ --open` provides the packaged local paper
workspace for definition/binding edits, shared settings, real audits and history.

Current source also offers `project-run --selective` and **Regenerate changed figures**.
They reuse intact accepted native results when inputs and rendering context match,
record original execution ancestry and disclose executed/reused counts. Authored
programs still execute; missing or failed evidence prevents reuse. See
[selective regeneration](../docs/selective-paper-regeneration.md).
Use **Download review packet** or `project-export` for saved figures, whole-paper
checks and an offline report, without copying original datasets or re-executing
science. See [review packet export](../docs/paper-review-export.md).

## Notebook example

Install the notebook extra for JupyterLab and kernel execution. Run
`graphunslopify notebook --output quickstart.ipynb`, then `jupyter lab quickstart.ipynb`, or add
`--execute` to run it through the current Python environment. All 21 figure kinds have named
Python constructors and a shared Kind typing Literal. See the repository notebook guide.

## Local MCP server

Install the agent extra, then run `graphunslopify mcp-config` (or `--client codex`) to print a
configuration for the current environment. The host launches `graphunslopify mcp` over stdio.
Seven read-only compiler tools share the canonical emitter; data profiling/rendering remain local
CLI operations. See the repository agent guide for setup, error semantics and protocol tests.

## Reviewed three-figure proposals in current source

The [figure autopilot](../docs/workspace/figure-autopilot.md) accepts a dataset
and research question, exposes mappings/exclusions/assumptions for review, then
generates three actual strict native drafts. In `graphunslopify preview`, open
**Start from a research question** to compare all three, explicitly apply a
passed draft and undo while preserving the complete comparison ancestry.
Failed drafts remain visible and downloadable. Import `propose_figures` and
`generate_drafts` from `graphunslopify.autopilot`,or use `autopilot-propose` to save
a bound review and `autopilot-generate` to replay it after acknowledgement.
These current-source features are newer than PyPI0.8.0.

## Reviewer questions in current source

The [figure reviewer](../docs/workspace/figure-review-agent.md) combines selected
paper figures' saved checks with separately labelled,unverified model advice.
Use `review-agent-plan` to inspect the exact provider request,then explicitly
consent with `review-agent-run`. Python callers use `FigureReviewPlan` from
`graphunslopify.review_agent`. Failed/stale/missing checks remain explicit and no
figure settings are changed. Provider workers have a90s execution deadline;
Python callers can discard pending results with a `threading.Event` passed as
`cancelled=`. Stopping the local worker cannot unsend an HTTP request.
The paper workspace and single-figure editor expose session HTTP APIs for disclosure, explicit
consent, status, cancellation and freshness-checked JSON downloads. Browser
reviewer controls remain in development. Editor review binds actual completed
native renders; its request download is an ephemeral disclosure, not a replayable
paper CLI request. Input, program, report and export changes invalidate advice.

## Import Python figures in current source

[Import supported Matplotlib/Seaborn scripts](../docs/workspace/source-imports.md)
with `graphunslopify import-source original.py --out-dir new-import`, or use the
local editor's reviewed import/apply/undo flow. User source is never run. Original
bytes and located unsupported findings are preserved; CSV references need explicit
mapping. Default CLI rendering is strict. This is newer than PyPI 0.8.0.

## Experiment tracking in current source

Current source [imports CSV, TensorBoard, MLflow and W&B histories](../docs/workspace/experiment-histories.md)
with run selection, reviewed comparisons, strict rendering and undo. Tracker SDKs
use the optional `experiments` extra. Endpoint/key access is explicit and local
MLflow sources are queried through owned copies; see the tested scope in the guide.

Source after0.8.0 adds `python -m pip install "./python[tracking]"` and
`graphunslopify track-mlflow` for saved audit/workflow reports. Choose an explicit
MLflow store and experiment/run; rejected science stays rejected and existing
training runs keep their lifecycle. See [the complete guide](../docs/experiment-tracking.md).
The immutable public0.8.0 package does not include this extra/command.

Current source also provides [command search and keyboard shortcuts](../docs/workspace/commands.md) in both local workspaces, with existing review, draft and export checks.

Current source supports [reviewed presentation edits across selected figures](../docs/workspace/selected-presentation.md), with per-figure overrides, explicit PDF/program exclusions, selective checks and undo.
