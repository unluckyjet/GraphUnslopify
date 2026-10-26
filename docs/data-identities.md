# Data identifiers, filters and measurements

Identifiers name things; numbers measure things. A CSV model called `01` must remain distinct
from `1`, and a numeric model ID must match the string name used in `series_order`, a claim,
an emphasis or a baseline. This contract applies through generated Python preparation,
rendering and exported evidence.

## Names have one shared boundary

After explicit filters and before reshaping/transforms, the generated program adapts declared
identity columns to their textual names. This includes series, facets (both dimensions), paired
units, named repeat units, categorical axes, heatmap/confusion labels and table row keys.
Wide data restores source names before melting and adapts the virtual series names afterwards.
Measurements, continuous coordinates and temporal axes retain their own types.

CSV names retain their spelling, including leading zeros. CSV retains pandas' existing missing
value conventions: a missing identity is not converted into a cohort called `nan`. JSON string
names retain their spelling, and native JSON scalar values retain their values before textual
conversion. For example, integer `1` becomes `"1"`, float `1.0` becomes `"1.0"`, and native
booleans become `"True"`/`"False"`. Parquet and direct prepared DataFrames use the same textual
representation of their supplied scalar values. Existing categorical level metadata is retained.
Data already rounded or merged before it reaches this boundary cannot be reconstructed.

Different typed names that collide as the same text, such as integer `1` and string `"1"` in
one identity column, fail rather than silently merging. Blank and non-scalar identifiers fail too, as do nonfinite Python/NumPy floating-point
identifiers. Required category/series/panel/pair names cannot be missing in retained
rows. Missing repeat-unit IDs stay missing and retain the existing exclusion/count disclosure;
they do not become independent units. Separate names do not prove statistical independence.

A source column with both an identity and a measurement role is explicitly refused with
`unsupported_identity_roles`. For example, `group: "loss"` while y measures `loss` needs two
source columns. This avoids turning a continuous measurement into categorical text. The rule
also covers overlays, secondary axes, repeat metrics and derived event/outcome columns.

## Filters keep their original typed meaning

Filters run against the ordinarily loaded, typed data before identity adaptation. This preserves
existing numeric equality/range/membership and string comparisons. It does not change every
CSV column to text.

For CSV model cells `01` and `1`, pandas' typed view contains two numeric 1s. A raw filter
`model eq 1` retains both, and the plot then correctly shows two distinct named cohorts.
`model eq "01"` matches neither in that typed view, as before. For exact selection that the
typed view cannot express, prepare an explicit inclusion/text filter column or filter the
source data first. Avoid treating an ordering list as an implicit data filter.

The adapter copies direct DataFrames rather than mutating their source. The generated pipeline
retains row correspondence through filtering and temporal sorting, restores names before wide
reshaping, and consumes its private lexical bookkeeping before drawing. Its internal `load`/
`prepare` functions are intended to be used together; arbitrary external reshaping between
them is outside that pipeline contract.

## Ordering and visible evidence

String `series_order` names now match numeric-looking cohorts in plots, table columns, palette
locks, emphasis, comparisons, annotations and direct labels. As before, unlisted observed series
remain present after the requested series. Duplicate series/category orders are refused.

An explicit `category_order` must cover the observed categories. Listed categories absent from
a particular facet are allowed; observed categories omitted from the list are an error. This
prevents an empty bar plot or a waterfall silently dropping contributions. Apply explicit
filters when excluding data is intended. With no explicit order, each kind retains its ordering
policy over the prepared names; nominal text is not automatically a continuous numeric axis.

## One input snapshot

Typed measurements and original names are read from one byte snapshot, so a file changing
between parser calls cannot attach one experiment's names to another experiment's values.
The data fingerprint belongs to that loaded snapshot. Local compressed files retain the hash
of their actual file bytes; an HTTP response decoded by the reader uses the delivered content
bytes. Compressed CSV/JSON parsing and explicit HTTP inputs retain the reader's existing
behavior. Rendering may fetch an explicitly requested URL; translation itself never fetches
the dataset. Normal local rendering requires no service or network connection.

JSON names use a literal object view of the same payload, so date-looking names, large integer
unit IDs and numeric-looking column headers survive inference. This also avoids a version
dependency on pandas' date-conversion flags. The older [pandas JSON parser](https://github.com/pandas-dev/pandas/blob/v2.0.3/pandas/io/json/_json.py)
performs date conversion separately from numeric dtype inference; current compatibility tests
exercise literal names directly instead of assuming `dtype=False` disables every conversion.

## Verification and limits

`python/tests/test_identity_references.py` covers independent actual line/bar/heatmap/table marks,
confusion counts, matched differences, equal-unit weighting, facets, typed file inputs,
wide reshaping, filters/transforms, missing/invalid/colliding names, ordering/refusal controls,
palette/annotation names, compressed and HTTP snapshots, fingerprints, claims and PNG/SVG
descriptions. The corrected initial 34-case contract failed 32 cases at `d308f36`; its already
correct string-filter and missing-repeat-ID cases are retained. The expanded contract has 62 cases.

Fresh-wheel smoke checks real installed line artists for `01`/`1` as well as a strict supported
claim, with external connections blocked after installation. Parquet references require the
existing `[parquet]` extra and run in the Python CI matrix. Refreshed generated baselines and
public Q–Q/scaling images carry current source fingerprints; their existing pixels are unchanged.

This fixes a shared identity boundary. It does not finish the independent scientific reference
matrix for all 21 chart kinds, categorical overlay geometry, final exported-width measurements
or table context checks. Those remain tracked separately in pipeline contract 24.
