# Operational comparison controller

The original [protocol README](../../benchmarks/workspace/README.md) is frozen historical protocol-stage documentation. Context-aware producers and independent evaluation are now implemented; the complete controller and seal qualifier are undergoing preparation. No formal results or speed advantage are claimed.

## Complete operational controller

`run-workspace-study.py` preallocates every registered session/cell before worker
dispatch. It executes each once, retains unstarted cells and actual exceptions,
and writes `progress.json`, final `study.json`, original context documents and
original producer evidence to a new output directory. Existing evidence is never
overwritten. Task acceptance is separate from measurement-integrity completion;
a complete run can contain task failures and cannot imply scientific superiority.

Preparation uses the actual same context-aware paths and remains the default:

```sh
python scripts/run-workspace-study.py --track single --out /new/output/single
python scripts/run-workspace-study.py --track paper --out /new/output/paper
python scripts/run-workspace-study.py --track reliability --out /new/output/reliability
python scripts/run-workspace-study.py --track local --profiles-file local-profiles.json --out /new/output/local
python scripts/run-workspace-study.py --track gui --profiles-file gui-profiles.json --out /new/output/gui
```

The profile file maps **every** registered profile to an explicit interpreter and
installed/source selection. Local keys are `checkout-current3.12`,
`checkout-minimum3.10`, `fresh-wheel3.12` and
`standalone-bundle-no-installed-graphunslopify3.12`; GUI keys are `source-current`
and `fresh-wheel`. Each value has exactly `python` (executable path) and `installed`
(boolean). Only the fresh-wheel profiles use `true`. Actual interpreter/package
and genuine standalone absence checks enforce these identities.

The native workflow runs one registered 16-cell plan per actual platform. Pushes
use preparation. Its explicit `study_mode`/`seal_json` dispatch inputs also support
formal mode once qualified; JSON enters through an environment value rather than
shell source. Every job uploads its original evidence even on failure.

`create-workspace-seal.py --ci-acceptance acceptance.json --parity-manifest
preparation.json --out /new/output/seal.json` refuses incomplete qualification.
The parity manifest maps each of the six track names to a list of actual
`study.json` paths: one each for `single`, `paper`, `reliability`, `local`, `gui`,
and all four actual native CI artifacts for `native_ci`. Keep their complete
original directories: qualification verifies every retained file hash, the fixed
plans, execution receipts, actual envelopes, source/package closure and repeated
PNG identities. Native preparation must bind the accepted implementation's real
CI run. This is trusted evidence custody, without authentication against a
malicious evidence owner.

Only a successfully qualified seal can be supplied with `--mode formal --seal
seal.json`. Its source must be the exact full Git revision with all fourteen
accepted checks. Final source/SDK closure guards detect changes during execution.
Invalid seal loading retains planned cells as unstarted. Do not run other work on
the measurement host during formal clocks. Full preparation and an actual seal
have **not yet been completed**; these commands document the implementation and
its prerequisites, not successful formal studies.

The original protocol and its 37 frozen assets remain byte-identical. Full methods and preregistered analysis remain in that protocol; this implementation guide does not amend task order, scientific gates or planned denominators.
