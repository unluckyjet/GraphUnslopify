# Paper review panel evidence

Collect three separate evidence views for the figures in an initialized paper.

```sh
graphunslopify project-review-panel ./paper --journal-profile nature-final-graphs
```

- **Readability** shows the saved native measurements or PDF page inspection.
- **Statistical claims** shows recorded check outcomes, uncertainty and evidence
  gaps. Numerical claims for PDF-only figures remain untested.
- **Journal formatting** checks the recorded PNG, SVG, PDF and other figure
  exports against a selected dated profile. It uses the current registered PDF
  only when its hash still matches the inspection. The report records each
  format's results, unavailable evidence and remaining manual checks.

Repeat `--figure` with the keys from `project-review` to select particular
figures. Use `--expected-revision` to bind the collection to a current saved
review. Omit `--journal-profile` when a venue has yet to be selected. The report
will show where a profile is required. Figure execution and any model review
are separate actions.

`graphunslopify.review_panel_providers.PaperReviewRoles` accepts a `DraftProvider`
for each of `readability`, `statistical_claims` and `journal_formatting`. Its
`disclosure()` shows the exact request and consent digest for each role. Review
all three before calling `request(consent=True, consent_sha256=digests)`, where
`digests` maps each role to its approved digest. Only the journal role receives
technical profile measurements. The result keeps unavailable roles and local
deterministic evidence visible and reports reused provider configurations.

For a saved CLI review, provide a JSON file with public settings for all three
roles. Each role accepts `endpoint`, `model` and optional `protocol` (`responses`
or `chat`). Role providers can use different models or share one configuration.

```json
{
  "readability": {"endpoint": "http://127.0.0.1:8000/v1/responses", "model": "local-model"},
  "statistical_claims": {"endpoint": "http://127.0.0.1:8000/v1/responses", "model": "local-model"},
  "journal_formatting": {"endpoint": "http://127.0.0.1:8000/v1/responses", "model": "local-model"}
}
```

```sh
graphunslopify project-review-panel-plan ./paper --providers providers.json \
  --figure training --journal-profile nature-final-graphs --out review-plan.json
graphunslopify project-review-panel-send ./paper --plan review-plan.json \
  --consent --consent-sha256 "$APPROVED_PLAN_DIGEST" --out review-result.json
```

Open the saved plan to inspect the three requests and destinations before
supplying its `consent_sha256`. Pass authorization separately with
`GRAPHUNSLOPIFY_REVIEW_READABILITY_API_KEY`,
`GRAPHUNSLOPIFY_REVIEW_STATISTICAL_CLAIMS_API_KEY` and
`GRAPHUNSLOPIFY_REVIEW_JOURNAL_FORMATTING_API_KEY` as needed. A partial result
is saved and returns exit code 2. Changes to the evidence, profile or plan
require a new disclosure.
