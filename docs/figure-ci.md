# Figure CI for a research repository

Use the composite action to regenerate results-linked figures, check their claims/readability,
and attach reviewable images, source programs, logs and machine reports to a GitHub workflow.
The caller needs Python; the action installs it and the packaged local translator/runtime.
No hosted translator, npm setup or package-registry publication is required.

Create `.github/workflows/figures.yml` in your paper repository:

```yaml
name: Figures
on: [push, pull_request]
permissions:
  contents: read
jobs:
  figures:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
      - uses: unluckyjet/GraphUnslopify/.github/actions/figure-ci@main
        with:
          manifest: paper/graphunslopify.json
          artifact-name: paper-figures
```

The action currently lives on main; pin a reviewed commit for reproducible use until the tagged
release is available. GitHub loads the action's own bundled compiler/package, while the manifest
and data resolve in the caller's checkout. The same setup is exercised by this repository's
[consumer integration workflow](../.github/workflows/figure-ci-example.yml): the tool is checked
out separately, a passing paper runs, then a reversed claim must fail while still uploading evidence.

Use a [paper manifest](paper-audits.md) to connect specs/generated scripts and local result files.
Pushes and pull requests rerun all listed figures; narrow the workflow's path filters to your own
spec/data/script paths if appropriate. Numeric claim checks are literal predicates and do not
establish statistical equivalence or experimental independence.

## Baselines and failure policy

Audit execution is always strict. Failed claims, required untested checks, missing inspection,
missing outputs or invalid provenance make the action fail. Warnings remain visible; select
`fail-on-warning: 'true'` to reject them. To compare with a saved audit report:

```yaml
      - uses: unluckyjet/GraphUnslopify/.github/actions/figure-ci@main
        id: figures
        with:
          manifest: paper
          baseline: figure-baseline/audit.report.json
          fail-on-change: 'true'
          fail-on-warning: 'true'
```

Place that baseline file in the caller's checkout (or download a previous workflow artifact before
this step). Its JSON alone is sufficient; original baseline images need not be present to compare
stored hashes. Changed inputs, claims, descriptions, files and PNG pixels appear separately in the
report. `fail-on-change` rejects all recorded changes, including metadata/file-byte changes, and
requires a baseline. Use the artifact review to decide whether a change is intended before saving
a new baseline. The action never approves changes, commits files or comments on a pull request.

## Inputs and outputs

| Input | Default | Meaning |
| --- | --- | --- |
| manifest | graphunslopify.json | Manifest file or directory in the caller workspace |
| output-directory | .graphunslopify-audit | Local full audit evidence |
| baseline | empty | Previous aggregate JSON report |
| fail-on-warning | false | Reject warnings |
| fail-on-change | false | Reject changes against a required baseline |
| timeout | 120 | Seconds per generated program |
| python-version | 3.12 | Python version, minimum 3.10 |
| extras | interactive,parquet,statistics | Optional readers/backends/tests; empty for core |
| artifact-name | figure-audit | Choose a unique name for each use in a job |
| retention-days | 14 | GitHub artifact retention |

The supported integration is GitHub.com with GitHub-hosted Linux runners. Python/package clean
installs are separately tested on Linux/macOS/Windows; those do not substitute for action-level
integration tests. MP4 export requires FFmpeg on the runner.

Outputs: `status`, `exit-code`, `changed`, `report-file` (absolute staged JSON path) and
`artifact-url` (GitHub download link). `report-file` is empty when an invalid manifest/setup prevents
a complete audit. Such failures still produce `command.report.json` and a summary when the audit
step starts. Honor step failure/exit code; a check status can pass while an optional change policy
rejects it.

The action appends a job summary and uploads artifacts even after a failed audit. Its upload stage
contains only the current run's owned evidence and canonical command/report/summary files. It does
not upload the caller's entire output directory, unrelated pre-existing files or source data files.
Previous local runs survive. Artifact contents include generated/selected source and report metadata.

Composite-action behavior follows [GitHub's action packaging documentation](https://docs.github.com/en/actions/tutorials/create-actions/create-a-composite-action).
