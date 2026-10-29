# Contributing to GraphUnslopify

Contributions that improve scientific correctness, understandable diagnostics,
reproducible evidence and research workflows are welcome. Start with the
[public roadmap](ROADMAP.md) and the [current review list](pipeline/review-roadmap-2026-10-28.md).
The focused implementation queue is in [pipeline/](pipeline/README.md).

## Report a problem or propose a change

Use the [issue forms](https://github.com/unluckyjet/GraphUnslopify/issues/new/choose).
Give the installed version or exact source commit, Python/Node versions, operating
system, a minimal specification and a small synthetic dataset. Include the exact
command, expected behavior, actual report/exit code and any relevant export.
`graphunslopify doctor` prints package/translator identity. Remove private paths,
credentials and unpublished research data before attaching evidence.

For a numerical or scientific error, explain the intended units, experimental
units, exclusions and assumptions. Supply a hand calculation or a separately
implemented reference when possible. A successful render is not evidence that a
scientific claim is correct. A new chart request should explain the research task
and how the proposed encoding communicates its quantities.

Report potential security vulnerabilities through the [security policy](SECURITY.md).
Public issues are for ordinary bugs, scientific results and feature requests.

## Set up a checkout

Use Python3.10 or newer and Node22.6 or newer; CI tests the supported platforms in
[checks.yml](.github/workflows/checks.yml). From the repository root:

```sh
python -m venv .venv
# Activate .venv/bin/activate (macOS/Linux) or .venv\Scripts\Activate.ps1 (PowerShell).
python -m pip install --upgrade pip
npm ci
python -m pip install -e "./python[dev,interactive,statistics,pdf,notebook,tracking,parquet]"
```

The extras above exercise the optional contexts in the full suite. A small
rendering change can start with `./python[dev,interactive,statistics]`; record any
unavailable optional context or skipped test. Manuscript compilation also needs
a LaTeX installation with Latin Modern fonts; the render CI job records its Linux
packages.

## Make a focused change

- Keep semantic intent in the canonical TypeScript schema/checker/emitter.
  Python adapters should use the same translator rather than inventing a second one.
- For TypeScript or embedded cell-colour changes, run `npm run build:translator`
  and commit the refreshed packaged translator, schemas and diagnostic catalog.
- For a new owned finding code, add reviewed problem/consequence/correction
  guidance as described in [diagnostics](docs/diagnostics.md). A proposed repair
  must preserve meaning; unavailable evidence must remain untested.
- For scientific behavior, check real calculations and drawn artists against
  independently computed answers. Add a regression for a real failure mode;
  distinguish execution errors, unsupported checks and false scientific claims.
- Preserve authors' source data. Keep exclusions, numerical assumptions and
  limitations visible. Source additions after0.8.0 must not be attributed to the
  immutable0.8.0 package or its versioned release evidence.
- Keep commits focused and descriptions useful. Follow [CLAUDE.md](CLAUDE.md),
  including its no-assistant-attribution rule.

## Verify and open a pull request

Set `PYTHON` to the environment's interpreter so every command uses the same
scientific stack: `export PYTHON=python` on macOS/Linux, or
`$env:PYTHON = "python"` in PowerShell. Run all seven required gates:

```sh
npm run typecheck
npm test
npm run test:python
npm run baseline -- --check
npm run render-check
npm run recipe-check
npm run compose-check
```

Run `npm run gallery-check` for layout/gallery changes and inspect the actual
figures. To intentionally regenerate baselines, use `PYTHON=python npm run baseline`
on macOS/Linux, or set `$env:PYTHON` before `npm run baseline` in PowerShell.
Review code, pixel and provenance differences. Do not regenerate evidence just
to erase an unexplained failure.

Open a [pull request](https://github.com/unluckyjet/GraphUnslopify/compare) with the
problem, resulting behavior and verification results, including skips and scope
limits. Link a relevant issue if one exists. Check CI for the exact pushed commit;
local success alone is insufficient. A failing check needs diagnosis before merge.
Use a new source release for new distribution behavior; follow the
[release process](docs/versioning.md) rather than replacing published artifacts.
