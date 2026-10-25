# Runtime reports and strict checks

Every generated program writes `<stem>.report.json`, including when rendering
fails. The report contains a versioned specification and its hash, data-file
hash prefix, executed-source hash and row/sample accounting, static and rendered findings, per-panel
claim verdicts, corrected significance results, omitted checks/outputs, alt
text, and hashes of files actually written. It contains no raw data rows.

```sh
python figure.py --strict --report reports/figure.json
# The installed CLI forwards the same policy:
graphunslopify check figure.py --strict --json
```

`--json` prints one JSON document on stdout and sends rendering logs to stderr.
`--report FILE` changes the destination; parent directories are created. Paths
are relative to the rendering working directory (`--cwd` in the Python CLI).

| Report status | Meaning |
| --- | --- |
| `passed` | Implemented required checks completed without an error or failed claim |
| `failed` | A static/inspection error, failed claim, or rendering error occurred |
| `incomplete` | Inspection was unavailable, a claim/test/interval was untestable, or a requested output was skipped |

`ok` is true only for `passed`. Warnings are recorded separately. These are
outcomes of the listed checks; they are not a scientific certification.

| Execution policy | Exit code |
| --- | --- |
| Default | 0 after a successful render, even if a check failed; legacy behavior |
| `--strict` | 2 for failed **or incomplete** checks |
| `--fail-on-warning` | Strict mode, also returning 2 for any warning |
| Runtime or report-write error | 1 |

The report's `exit_code` and `policy.passed` record the selected execution policy.
For example, a warning can leave the check status `passed` while an explicitly
selected warning policy rejects the run. CI should use the process exit code.
A failure to write the report is itself a nonzero exit; no report can be promised
at an unwritable destination. Missing core imports or a syntax error before the
program starts are likewise process errors rather than completed reports.

Claims use the same mean/median and declared units as the displayed panel.
Every facet and repeated metric is checked independently. Missing series,
incomplete x coverage, ambiguous raw duplicates, and one-point trend claims
are `untested`, rather than being proved after dropping inconvenient points.
Claim predicates describe numeric relationships. A non-significant p value
or overlapping interval never establishes equivalence.

```python
result = figure.render(strict=True)   # raises SpecError on a rejected run
report = result["report"]
# A runtime SpecError also exposes its report as exception.report.
```

The file contract is [runtime-report.schema.json](runtime-report.schema.json).
The generator owns this implementation; the CLI and builder execute it rather
than duplicating the statistical or inspection logic.
