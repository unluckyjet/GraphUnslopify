# Runtime environment evidence

**Current source after 0.8.0.** Install the source checkout and regenerate scripts.
The immutable PyPI 0.8.0 release has the earlier provenance envelope without this
optional context. A version label alone does not identify subsequent source edits;
keep the executed-script fingerprint too.

Generated programs capture an `environment` snapshot in the runtime report and
PNG/SVG/PDF/supported HTML provenance. One snapshot is frozen before the first
static export, while the figure's owned rendering settings are active. Tables
capture their actual generated figure dimensions. Later HTML export reuses that
snapshot after the Matplotlib context closes.

```sh
graphunslopify render figure.json --out-dir figures --api local --json
graphunslopify provenance figures/figure.svg
```

Use the actual output path shown by your render command. `environment` is a nested
schema-version1 object within the existing version1 report/provenance envelope.

## What is recorded

| Field | Meaning |
| --- | --- |
| `python` | Runtime Python version/implementation, optimization level and whether hash randomization is enabled. It does not recover the interpreter's hidden random hash seed. |
| `platform` | OS family and machine architecture; no hostname or working directory. |
| `loaded_core_versions` | Actual imported NumPy, pandas, Matplotlib, Pillow and FreeType versions. Unknown values are null. |
| `installed_optional_versions` | Selected installed graphunslopify, Plotly, SciPy and pypdf distribution versions. This is availability information, not a claim every package was used or that a shadowed optional module matches its distribution metadata. Missing/unreadable metadata stays null. |
| `rendering` | Primary Matplotlib backend, nominal figure inches/dpi, requested export dpi/formats, target manuscript width, requested interactive output, selected active rc parameters and resolved default-font basename/family/SHA256. |
| `execution` | Effective CLI strict/warning policy, or explicit unknown policy for a fresh direct-call report. These are settings; the final `policy` record separately reports acceptance/exit status. |
| `random_constants` | Declared bootstrap seed/draw count and point/pair jitter seeds where present in generated source. This is not a dump of all random-generator states or a certification of statistical assumptions. |
| `unavailable` | Names of context fields whose collection failed, without raw exception text or private paths. Absent optional packages are simply null. |

The backend is the primary Matplotlib configuration; file writers and the eventual
HTML viewer have their own behavior. Requested output settings do not assert that
every export succeeded: consult `outputs` and `skipped_outputs`. Nominal figure
inches are distinct from the actual tight-cropped export widths in inspection
measurements. The default font record does not enumerate every bold, math or glyph
fallback font in the figure.

## Failure and compatibility behavior

If execution fails before any export snapshot, the report says
`capture_stage: "no_export_snapshot"`. Figure dimensions, rc settings and default
font remain null. Loaded versions and declared settings can still help diagnose
the failure. It does not invent a successfully rendered figure.

Imports alone do not collect a snapshot. The normal generated CLI starts a fresh
report/context each run. Advanced callers using `main()` directly must start a new
report lifecycle for independent runs; a fresh direct call has no known CLI policy.
The snapshot detaches mutable rc lists, so later configuration changes cannot
silently rewrite previously captured settings.

Old version1 envelopes and legacy version0 reads remain supported without adding
the reader's current host environment. New environment records are validated
against the packaged [environment schema](environment.schema.json), also embedded
as an offline definition in the runtime-report schema. Malformed context fails
explicitly, including nonfinite numbers that permissive JSON parsers accept. Artifact auditing also checks that embedded environment evidence
matches its runtime report; matching bytes alone does not establish that parity.

## Scope and reproduction

The collector uses a fixed allowlist. It does not dump environment variables,
command arguments, process IDs, timestamps, executable paths, usernames, font
directories, hostnames, installed-package lists or dataset rows. The original spec
and data path remain part of the existing evidence envelope.

This is a useful environment receipt, not a lockfile or a complete machine image.
It omits OS build numbers, BLAS/compiler/driver settings, arbitrary fonts/plugins,
browser and FFmpeg versions, and undeclared external state. Match the code/data
fingerprints, Python/core versions, relevant optional dependencies, font hash and
rendering settings when investigating differences. Identical records alone do not
guarantee identical output on every platform or establish scientific validity.

Static rerender tests still verify identical PNG/SVG/PDF bytes for identical inputs
in one environment. Tests inspect real exports/report parity, tables, repeated CLI
policies/DPI, early failures, missing metadata, detached settings, safe scope,
malformed context and old envelopes without backfill. Four-platform installed-wheel
CI uses `scripts/install-smoke.py --require-environment` to require current-source
report/export parity; omit that flag when checking an older published wheel.

Implementation: `src/codegen/environment.ts`, `runtime.ts`, `index.ts`, `outputs.ts`,
`compose.ts`; reader/audit in `python/graphunslopify/`. Controls:
`python/tests/test_environment.py`, `test_provenance.py`, `test_audit.py`.
