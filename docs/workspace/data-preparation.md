# Preview data preparation

Open **Data preparation preview** under the dataset in the figure editor.
Switch off **Live preview** if you want to inspect a draft before its first
render. Choose **Preview data preparation** after changing the columns,
filters or transformations you intend to use.

The preview shows parsed types and missing values, conversions, filter
counts, and exclusion reasons with source record numbers. Record numbers
start at one and refer to parsed records. A wide-to-long reshape can
create several prepared rows from one original record. A baseline can
contribute to a transformation while being excluded from display.

In the paper workspace, save the native JSON definition and preview its
effective data preparation before starting an audit. The preview uses
the current project revision and the figure's effective data binding.

The preview reads local data and runs the same generated preparation
steps used by the figure. It leaves the draft and source data untouched.
Some chart-specific checks and computations happen during rendering.
Inspect the report, adjust the draft if needed, and run the usual
verification when ready.
