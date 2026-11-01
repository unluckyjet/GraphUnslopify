# Regenerate changed paper figures

Current source adds **Regenerate changed figures** beside **Audit paper** in the
[paper workspace](project-management.md). Install the source package; this is
newer than the immutable PyPI 0.8.0 release.

Use it after saving a definition, updating a dataset or applying shared settings.
It executes changed figures and can reuse intact accepted native results whose
inputs and rendering context still match. **Audit paper** always executes every
figure. Both paths retain strict failures and the selected comparison policy.

```sh
graphunslopify project-run paper/ --selective
```

The saved summary reports **executed**, **reused** and **not run** separately from
scientific passed/failed/incomplete counts. A reused figure identifies its original
execution and the more recent run from which evidence was copied. Its original
runtime report, source identity and export bytes are preserved. Copying that
evidence is not a new execution or an independent reproduction.

| Situation | Behavior |
| --- | --- |
| Unchanged accepted JSON figure | Reuse requires matching inputs, canonical generated program, producer, strict policy and observed environment, plus intact source/report/export evidence. |
| Definition, data, palette or shared settings changed | Regenerate affected native figures. |
| Authored Python, including a script with declared data | Execute it again; other imports and inputs cannot be inferred from one declared dataset. |
| Missing or changed saved program, report or export | Execute the affected figure again. Keep the old history and its unavailable evidence visible. |
| Newest native run failed/incomplete, history is damaged, or older evidence lacks reuse guards | Execute afresh; never search backward for a more favorable pass. |
| Moved project or changed producer/environment/policy | Execute afresh. |
| External video encoder, external TeX or unsupported relative plotting configuration | Execute afresh; no reusable context is claimed. GIFs use the guarded Pillow path. |
| Source-free PDF | Keep separate visual evidence; native regeneration does not verify its original observations or numerical claims. |

An unavailable comparison baseline can still reject paper acceptance after fresh
figures pass. Review the previous run and comparison. To audit current inputs
without relying on that old comparison, explicitly choose **No baseline**, or:

```sh
graphunslopify project-run paper/ --selective --no-baseline
```

A preceding failed native run forces fresh execution. This choice retains the
failed history and the current strict scientific checks; it does not repair or
authenticate old evidence.

## What is checked

The owned runner compares full current input hashes and recomputes canonical
program bytes for the destination. It verifies saved programs, input definitions,
runtime reports, logs and exports before copying an explicit inventory into a
new run. It checks original execution ancestry and rechecks reused source/history
and rendering context before committing the result. Current input/producer guards
and the ordinary audit policies still run.

A fresh interpreter observes its Python executable/prefix, installed package
versions, plotting config/rc settings and discovered font bytes. Missing or changed
context prevents reuse. Version comparison does not authenticate every external
dependency binary. These cooperative local checks are not filesystem CAS, a
sandbox for trusted authored programs or author authentication. A report records
what its execution tested; it cannot establish the appropriateness of an experiment.

Global baseline/change policies are evaluated again even when individual native
results are reused. Warning rejection remains strict. Per-figure timeouts apply
to new figure executions; bounded environment probes are separate setup work.

## Functional verification

The actual source and minimum-Python checks cover all 30 frozen runtime cases:
29 accepted cases spanning all 21 kinds, including GIF, reuse identical reports
and export bytes; the original strict negative executes again and stays rejected.
The original corpus data/specs/statuses/formats and numerical reference protocols
are unchanged. This is functional conformance, not a speed or human productivity
study.

```sh
python scripts/check-project-reuse.py --out-dir /tmp/new-paper-reuse-check
PYTHON=python npm run project-reuse-check
```

The browser driver uses real spec/data edits, strict executions, original-history
checks, mixed PDF/program inputs, keyboard/mobile interaction and held genuine
responses. Its authored fixture deliberately pauses to expose concurrency races;
its duration is not performance evidence. Fresh installed checks and exact CI are
required for delivery alongside the seven repository gates.


Generated native programs are saved as exact canonical UTF-8 bytes on every
platform. Host text newline conversion must not change the program whose hash
is compared for reuse. Earlier Windows history with different source bytes
requires a real rerun; the tool does not normalize saved programs or rewrite
old reports to make them appear equivalent.
