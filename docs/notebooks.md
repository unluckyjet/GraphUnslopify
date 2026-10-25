# Notebooks and the Python builder

Install the package in the Python environment used by your notebook kernel. From a checkout:

```sh
python -m pip install "./python[notebook]"
graphunslopify notebook --output quickstart.ipynb
jupyter lab quickstart.ipynb
```

The notebook extra supplies JupyterLab, an IPython kernel and execution tooling. In an existing
Jupyter or VS Code notebook environment, installing the base package in the selected kernel is
also sufficient for the figure-building API. No separate notebook extension is required.

The example is packaged with the wheel; it does not depend on a cloned `examples/` directory.
The copy command refuses to overwrite an existing file. To execute it without opening a browser:

```sh
graphunslopify notebook --output executed.ipynb --execute
```

Execution uses the current Python executable, without editing installed user kernel specs.
A failed cell is retained in the notebook and produces a nonzero command result. The shipped
example contains public synthetic data only and explicitly selects `api="local"`, so a configured
HTTP API cannot accidentally make it depend on a hosted translator.

## What the example demonstrates

It creates 48 synthetic observations, builds two mean curves with bootstrap intervals over four
named seeds per epoch/model, renders PNG/SVG/PDF, and displays the PNG in the notebook. It checks
actual sample counts and a literal `beats_everywhere` claim, then reads the computed description
and interval-overlap caveat. A deliberately reversed claim must raise `SpecError` and preserve
its failed runtime report. The notebook's expected rejection is handled; it is not a failed cell.

A portable JSON spec and Python program are saved beside the synthetic CSV. The code prints the
temporary example directory so it can be copied and rerun. To work on real data, choose explicit
persistent input/output paths instead. Numeric relationships, independent observation units,
units/labels and manuscript context remain the author's responsibility. A held numeric claim is
not statistical significance or equivalence.

## All supported kinds in Python

`Figure.of(kind, path)` and named constructors support all 21 canonical compiler kinds:

```text
line scatter bar box violin ecdf raincloud ridgeline forest paired_difference
slope dumbbell calibration qq kaplan_meier scaling_fit confusion_matrix
waterfall sparkline_grid heatmap table
```

`Kind` is exported as a typing Literal for these names. Kind-specific options use `.set(...)`;
the compiler's recipes remain the source for valid field combinations. The adapter is tested
against every canonical recipe rather than maintaining another renderer.

```python
from graphunslopify import Figure, SpecError

figure = (Figure.line("results.csv")
    .x("epoch", "Epoch")
    .y("score", "Score")
    .by("model", order=["base", "ours"])
    .average_over("seed")
    .set(legend={"position": "outside_bottom"}))

try:
    result = figure.render(cwd="figures", strict=True, api="local")
except SpecError as problem:
    report = problem.report  # Available when runtime checks executed.
    raise
```

CSV is the default input; named constructors infer regular JSON tables and Parquet from `.json`
and `.parquet` suffixes. Parquet needs its optional reader extra. Other explicit formats can be
set through `data` in the spec. JSON Lines profiling does not imply JSON Lines rendering support.
See [installation](installation.md) for local/HTTP selection and path behavior.

The notebook runs in CI through a real kernel on minimum Python 3.10 and Python 3.12; checks
require an image output, exact sample counts and the controlled false-claim rejection. The
committed source notebook has cleared outputs; execution artifacts are generated per run.
Notebook execution uses [NBClient](https://nbclient.readthedocs.io/en/latest/client.html).
