# Paper project history and shared settings

Current source after **0.8.0** adds a persistent project around an existing
[paper manifest](paper-audits.md). It records independent audits and settings
changes, lists each figure's last result and checks whether declared inputs and
saved exports still match. Install from source for these commands; the published
0.8.0 wheel remains unchanged.

This is the backend milestone for review item10. The packaged project dashboard
is still tracked in [spec67](../pipeline/specs/67-project-management-interface.md).
The [single-figure editor](local-editor.md) remains a separate workflow.

## Start a project

```sh
graphunslopify demo paper
graphunslopify audit-init paper
graphunslopify project-init paper
graphunslopify project-status paper
graphunslopify project-run paper
graphunslopify project-history paper
```

For your existing paper, start with its existing manifest and run `project-init`.
The default owned folder is `paper/graphunslopify-project`; `--folder NAME`
selects a different new child. For a custom folder, pass that folder or its
`project.json` to subsequent commands. Initialization refuses an existing folder.
Move the entire paper to retain relative source/data references and its history.
References outside the paper still require those original external files.

`project-run` audits every manifest entry through the existing strict runner.
Each run retains source definitions, complete reports, generated code, exports
and [before/after evidence](figure-comparison.md) under a new history directory.
Failures are retained too. Original spec files, authored programs and data are
not rewritten by the manager. Raw datasets are hashed rather than copied into
the history. History is ignored by the generated `.gitignore`; keep a deliberate
backup if you need it on another machine.

## Apply shared settings

Shared settings are partial semantic `style` fields, output `size`/`dpi`, and an
optional local `palette_lock` path relative to the paper manifest. They use the
canonical figure schema; arbitrary colours, font sizes and output stems are not
project settings. Supplying a shared object replaces the prior shared object;
`{}` clears the overrides.

Use a current revision from `project-status` when saving settings. This Python
example runs the same operations as the CLI without copying a token by hand:

```python
from graphunslopify.project import project_status, set_project_shared, run_project

state = project_status("paper")
set_project_shared(
    "paper",
    {"style": {"grid": True}, "output": {"size": "double_column", "dpi": 144}},
    expected_revision=state["revision"],
)
current = project_status("paper")
result = run_project("paper", expected_revision=current["revision"])
print(result["status"], result["directory"])
raise SystemExit(result["exit_code"])
```

The CLI equivalent is `project-shared paper --settings shared.json
--expected-revision REVISION`, with the same JSON object in `shared.json`.
Use the actual `revision` string returned by `project-status` for `REVISION`.
`project-run` also accepts `--expected-revision`; stale requests are refused.

For JSON figures, overrides are applied to an effective execution manifest, while
the original definitions remain intact. Authored Python executes unchanged as
trusted local code. Its reported settings must satisfy the shared policy; a
scientific pass can therefore have project exit2 for a style mismatch. Regenerate
or deliberately update that authored program to meet the shared requirements.
Explicit audits can execute any side effects of a selected trusted script;
read-only status/history never import it.

The existing palette helper reserves appearances when it sees new series. That
can update a referenced palette file during rendering. A project run detects
that input change and refuses current acceptance; review the reserved identities
and rerun. With a complete, canonical existing lock the audit leaves its bytes
unchanged. Palette/source bytes are checked before and after, not protected by a
filesystem transaction against unrelated writers.

## Read the results correctly

| Field | Meaning |
| --- | --- |
| `last_status` | Scientific result of that figure in the newest intact completed paper audit. |
| `last_accepted` | That result passed and the paper run also met the project/failure policy. |
| `freshness: unchanged` | Captured declared input hashes still match. |
| `changed` | A definition, declared input or applicable shared setting changed. Run again. |
| `unknown` | A script lacks declared input coverage; no current-input pass is inferred. |
| `unavailable` | Input or saved export evidence is missing, damaged or superseded by incomplete history. |
| `not_run` | No relevant completed audit exists. |
| `history_integrity: partial` | At least one historical event lacks an intact completion receipt. |

The top-level `inputs_match_last_run` requires matching declared inputs, accepted
results and verified exports for every entry. It does not certify independence,
arbitrary script imports, undeclared dependencies or an unchanged execution
environment. Declare a script's data in its manifest entry; even then the check
covers those declarations rather than all possible Python dependencies.

`project-status` exit0 means the query succeeded. Read its status fields to decide
whether an audit is needed. `project-run` returns0 only for project acceptance;
failed, incomplete, mismatched or changed-during-run evidence returns2.
`project-history` returns2 when evidence is incomplete/damaged. Recorded SHA-256
receipts detect changed bytes; they are not signatures or third-party trust.

## Baselines and recovery

The default baseline is the latest intact completed audit, including retained
failed audits. Select an earlier completed event with `--baseline EVENT_ID`, or
explicitly begin an independent run with `--no-baseline`. Additional policy flags
are `--fail-on-warning`, `--fail-on-change` and positive per-figure `--timeout`.
Scientific status and stricter project acceptance remain separate.

A receipt is written only after the event's source/result/aggregate evidence is
saved. Interrupted or damaged events remain visible and cannot silently become
completed passes. Automatic baseline selection refuses newer incomplete/damaged
history. Preserve that evidence and use `--no-baseline` for deliberate recovery;
a later intact run can describe current inputs while history remains partial.

Only one managed operation can run at a time. If `.operation.lock` survives a
crash, check its PID and confirm no owning operation remains before removing
that specific lock. The manager never guesses process liveness or deletes it
automatically. Restore matching missing evidence from a backup when available;
deleting a damaged event erases history rather than repairing it.

The underlying saved `history/EVENT_ID/audit/audit.report.json` also works with
[explicit MLflow logging](experiment-tracking.md).

## Verification

`python/tests/test_project.py` exercises actual audits, strict failure/recovery,
shared export provenance, scripts, input changes (including changed/restored data),
palette reservation, moved papers, damaged exports/history and revision/ownership
refusals. `scripts/check-project-management.py` uses actual installed CLI commands
to create two figures, change shared size/DPI, read real PNG dimensions and
embedded provenance, retain failures, recover, move the paper and detect damaged
exports. `scripts/install-smoke.py --require-project` runs it with external network
connections blocked after installation; all four distribution jobs require it.
These checks measure the backend, not dashboard usability or researcher adoption.
