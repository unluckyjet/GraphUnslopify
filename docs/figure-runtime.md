# Versioned scientific runtime and standalone bundles

Current development source emits a readable Python entry with explicit data, design,
calculations and strict verification. Common report, inspection and provenance helpers
come from one canonical Python implementation. This source feature is newer than the
published0.8.0 package; no new release is implied.

The program declares its required helper names, integer ABI, actual helper SHA256 and
actual scientific component source hashes. It validates the loaded files before binding
functions to that program's own globals. Different figures retain separate data, reports
and diagnostic advice. A matching package version alone is insufficient: an older source
installation is refused with installation/bundle guidance. Regenerate after intentional
runtime changes, or retain the matching original source distribution.

Reports record the actual binding under `script.runtime`. PNG/SVG/PDF/HTML provenance
also includes it. The [runtime identity schema](runtime-identity.schema.json) describes
its shape. Environment evidence keeps its existing schema. Reading embedded evidence
validates structure and source-hash consistency; it does not authenticate an author or
execute/recheck the original data.

## Archive and reproduce

```sh
graphunslopify bundle path/to/figure.json --output figure.zip
# Extract figure.zip, then in its directory:
python -m pip install -r _graphunslopify/requirements.txt
python reproduce.py --json
```

The SDK offers `Figure(spec).bundle("figure.zip")`. The local editor's existing ZIP
button uses the same bundle builder. SDK paths resolve from the caller's directory;
CLI data/palette paths resolve beside the spec. Bundling archives source without
rendering or asserting that checks passed. The generated program keeps strict policy.

The archive contains the actual readable package runtime/resources, MIT and Zod
licenses, program, effective specification, input fingerprints, a per-file manifest,
requirements and observed exporter versions. The launcher inserts its dedicated runtime
folder before executing the program; it works outside the checkout with no installed
GraphUnslopify package and no Node executable. Third-party scientific libraries remain
external. FFmpeg for MP4 and custom system fonts must be supplied when applicable.
Observed versions document the exporter; different environments may produce different pixels.

`REPRODUCE.md` names the actual launcher, normally `reproduce.py` or `_reproduce.py`
when preserving an author's script called `reproduce.py`. Launch it in a fresh Python
process. It validates immutable source/runtime and original input hashes before running.
Archived output/report hashes are retained for inspection; actual reproduction replaces
these reference outputs and writes its own current report. Repeated reproduction remains
usable. Hashes provide integrity checks, not authorship authentication.

The CLI/SDK include source data by default; `--no-data` / `include_data=False` omits its
bytes while retaining its expected hash. The editor still excludes data unless the user
selects its existing consent checkbox. A workbook contains all its worksheets. Supply the
exact original input at the manifest's relative path before reproducing an omitted-data
archive; altered input is refused. Palette locks used by the figure remain included.

## Evidence and limits

The frozen30-case/all21-kind protocol predates runtime edits. Conformance compares
actual accepted inline programs, canonical functions in their original contexts and
current default entries, including original strict negatives, report mathematics,
visible PNG pixels and SVG/PDF drawings. The [frozen runtime comparison](../benchmarks/runtime/README.md)
now records complete entry/runtime/package/bundle footprint and native/direct startup
and execution costs. Its900 formal executions retain870 original passes/30 strict
failures with unchanged drawings and mathematical reports. Latency outcomes are mixed;
complete source size grows while entry size shrinks. Human productivity and researcher
adoption are not measured. Required delivery checks and exact-commit CI remain separate
from benchmark conformance.
