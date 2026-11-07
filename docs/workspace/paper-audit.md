# Paper audit report

Run a strict native audit of the paper and open `index.html` in the exported
ZIP. The first section lists recorded errors, evidence gaps, and warnings in
that order. Each entry links to its figure and has a pointer into `review.json`.
The ZIP retains saved exports, execution receipts, checks, and a hash manifest.

```sh
graphunslopify project-audit ./paper --output review.zip
```

The command writes a new native run in the paper's history. Existing registered
PDF inspections contribute visual evidence. PDF numerical claims stay untested.
Use `--saved-evidence` to review the current saved collection without running
figures. The command retains a report for failed and incomplete audits and
returns exit status `2` for those outcomes.

## Include reviewed model suggestions

Run `review-agent-plan` for the current saved paper and inspect the exact
provider, request, and consent digest in the resulting document. For a paper
that needs multiple requests, select disjoint groups with `--figure`. Together
the requests must include every current figure, including registered PDF rows.

```sh
graphunslopify review-agent-plan ./paper --endpoint "$REVIEW_ENDPOINT" \
  --model "$REVIEW_MODEL" --out plan.json
graphunslopify project-audit ./paper --saved-evidence --review-plan plan.json \
  --consent-sha256 "$REVIEWED_DIGEST" --consent --output review-with-suggestions.zip
```

Repeat `--review-plan` and `--consent-sha256` in matching order for several
requests. The command checks every plan against current evidence before any
transmission. A provider failure is recorded alongside the deterministic
report. Valid replies appear under **Unverified model suggestions** with
their evidence references. The recorded audit verdicts stay separate.
