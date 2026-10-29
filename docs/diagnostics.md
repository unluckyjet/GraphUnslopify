# Understand and correct a finding

Current source after 0.8.0 explains each owned compiler, runtime and inspection
finding with its original problem, scientific consequence and recommended
correction. These explanations require a source installation; the published
0.8.0 wheel is unchanged.

For example, `log_domain_hidden` means finite zero/negative observations cannot
appear on the selected logarithmic axis. The visible evidence can therefore
differ from the dataset supporting the conclusion. Review those observations and
use a scientifically justified linear scale, or document a justified selection;
silently deleting the observations is not a repair.

```sh
graphunslopify explain log_domain_hidden
graphunslopify explain uncertainty_unavailable --json
graphunslopify render figure.json --json
```

The explanation command reads the installed catalog without starting Node or
opening data. Unrecognized codes return exit2 and explicitly unclassified advice.
They never acquire an invented scientific correction.

## Where explanations appear

- Compiler findings and schema issues include `consequence` and `correction`.
  Schema issues retain their field path and actual validation message.
- Generated programs embed the catalog, so runtime explanations remain available
  when the optional Python inspection package cannot be imported.
- Human generated-script/CLI output names the problem, why it matters and the
  recommended correction. Failed and untested claims also receive bounded guidance.
- Python inspection findings expose `.consequence`/`.correction`, and `str(report)`
  shows them. The original three-field dataclass representation remains compatible.
- Both local browser workspaces show guidance using literal DOM text. Saved
  findings without the new fields use the current catalog for display; their saved
  evidence is not rewritten. Unrecognized historical codes stay explicitly limited.
- Pre-execution schema/static rejection raises `SpecError` with `.diagnostics`.
  Its `.report` remains reserved for an actual execution report. CLI JSON retains
  those structured diagnostics instead of requiring text scraping.

Runtime report schema1 accepts the new optional string fields and old three-field
findings. Stable codes, contextual messages, severities, strict exit policy and
proposed `fix` patches retain their meanings. Guidance can require scientific
judgment; it does not silently change data, comparators, thresholds or hypotheses.
The pre-existing console-only repeated-x and unavailable-palette warnings also
include guidance. They remain log messages; adding explanations does not turn
them into new structured findings or change `--fail-on-warning` policy.

## Maintaining advice

`src/diagnostics.ts` is the reviewed catalog. Related codes can share a specific
explanation when their mechanism and correction match. `npm run build:translator`
embeds it in the translator and emits `python/graphunslopify/diagnostics.json`;
CI rejects generated-resource drift. Add reviewed advice when adding an owned code.
Coverage checks inspect actual compiler/runtime and Python inspection call sites.

`test/diagnostics.test.ts` and `python/tests/test_diagnostics.py` exercise source
coverage, invalid-spec paths, actual log-domain failure/recovery without changing
observations, final-artist text repair, and bounded unknown codes.
`scripts/check-diagnostics.py` repeats real installed-package and package-free
checks; `scripts/install-smoke.py --require-diagnostics` runs it after blocking
external network access. Browser checks verify displayed guidance and strict
failure/recovery in both workspaces.
