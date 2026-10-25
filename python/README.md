# GraphUnslopify

Translate semantic JSON into reviewable Python figures, render local data, and check claims,
readability and accessibility. The package includes the TypeScript translator and a Node runtime;
translation and rendering need no hosted service after installation.

From a source checkout: `python -m pip install ./python`.

```sh
graphunslopify doctor
graphunslopify demo
graphunslopify render graphunslopify-demo/figure.json --strict --json
```

The demo creates public synthetic CSV data and PNG/SVG/PDF figures, a standalone Python program,
and a JSON verification report. Data paths in a JSON spec resolve beside the spec file.
`graphunslopify translate figure.json --output figure.py` emits code without rendering.

```python
from graphunslopify import Figure

Figure.line("results.csv").x("epoch", "Epoch").y("score", "Score").render(strict=True)
```

`Figure.translate()` and `Figure.from_profile()` default to the packaged local translator.
Select a hosted translator explicitly with `api="https://your-service"` or
`GRAPHUNSLOPIFY_API`; use `api="local"` to override that environment setting.
`GRAPHUNSLOPIFY_NODE` can select a specific Node executable.

Use `[interactive]` for supported self-contained Plotly HTML. Strict verification rejects failed
or untested required checks; literal data claims are not statistical significance tests.
Read the repository documentation for the supported combinations and limits.

## What it checks

`text_too_small` and `text_near_minimum` measure every text element at the width the figure will
occupy on the page. Pass `target_width_in` and a 12pt label in a 10-inch figure is correctly
reported as 4.1pt once it is squeezed into a column.

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
always yields the same findings. Reasoning and sources are in [research notes](https://github.com/unluckyjet/JSONTranslator/blob/main/docs/research.md).


Source and versioned documentation: <https://github.com/unluckyjet/JSONTranslator>.
MIT license. The bundled translator includes Zod's MIT license; runtime/dependency licenses ship
with their respective Python distributions.

## Paper audits

`graphunslopify audit paper/ --out-dir audit-output` regenerates all figures in the directory’s
`graphunslopify.json` manifest with strict verification. `--baseline previous/audit.report.json`
adds data, numeric-representation, claim, description and artifact differences. It writes aggregate
JSON/Markdown plus individual programs, figures, logs and reports. See the repository paper-audit
guide for the manifest contract and supported metadata-backed artifact checks.

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
