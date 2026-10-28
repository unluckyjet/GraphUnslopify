# Install and run locally

New here? Start with the [five-minute first-figure tour](getting-started.md), including
virtual-environment setup, a complete example and a failed-check/recovery exercise.

Python 3.10+ is required. In a virtual environment, install the versioned package without cloning the repository or installing npm:

```sh
python -m pip install graphunslopify==0.8.0
graphunslopify doctor
graphunslopify demo
```

The demo writes public synthetic results, a JSON spec, PNG/SVG/PDF figures, the generated Python
program and a strict verification report to `graphunslopify-demo/`. It refuses to replace different
existing demo inputs. `doctor` checks that the packaged translator and Python package version agree.
The [0.8.0 release](https://github.com/unluckyjet/GraphUnslopify/releases/tag/v0.8.0) supplies
a wheel, source distribution and `SHA256SUMS` for installation without PyPI.
[Documentation versioning](versioning.md) explains how to match documentation to your install.
Version 0.8.0 is also published on PyPI. Its registry files match the GitHub release hashes;
a fresh registry install passes doctor/demo, strict-default rejection, agent/PDF and offline-runtime checks.
See [publication evidence](releases/0.8.0-publication.json) and the [publishing workflow](pypi-publication.md).

From a checkout, the equivalent install is `python -m pip install ./python`.
Install `[interactive]` for supported Plotly HTML, `[parquet]` for a Parquet reader, and
`[statistics]` for SciPy t/Mann–Whitney tests and Student-t scaling-exponent confidence intervals. For example:

```sh
python -m pip install "graphunslopify[interactive,parquet,statistics] @ https://github.com/unluckyjet/GraphUnslopify/releases/download/v0.8.0/graphunslopify-0.8.0-py3-none-any.whl"
```

MP4 export additionally requires FFmpeg. Core static figures and permutation significance do
not require those optional extras. Scaling point fits work without SciPy with explicit
`interval: "none"`; the default requested `t95` interval needs `[statistics]` and remains
unavailable/incomplete under strict policy when that dependency or residual degrees of freedom
are missing. See [scaling validation](scaling-validation.md). The supported interactive combinations are documented in
[interactive-exports.md](interactive-exports.md).

## Your own figure

```sh
graphunslopify describe results.csv
graphunslopify render path/to/figure.json --out-dir figures --strict --json
graphunslopify translate path/to/figure.json --output figures/figure.py
graphunslopify run figures/figure.py --strict --json
```

Data and palette-lock paths in a JSON spec resolve beside that spec, independently of the terminal's
current directory. The generated script's relative paths resolve in its working directory; the
`run` command sets that directory to the script's parent unless `--cwd` is supplied. Python SDK
paths resolve from the caller's directory before switching to the requested output directory.
The SDK leaves the original spec unchanged. JSON specs can set `data.format` to csv, parquet or json;
JSON rendering expects a regular JSON table, not JSON Lines.

A failed or untested required runtime check exits nonzero with `--strict`; select
`--fail-on-warning` to reject warnings too. The **0.8.0 wheel** defaults to strict verification. Older 0.7.0 installations
require explicit `--strict`. Explicit `--no-strict` or
`Figure.render(strict=False)` opts out while preserving actual report verdicts. Read
[runtime-reports.md](runtime-reports.md) before using reports as a submission gate.

`Figure.from_profile(path)` uses the local ranker and preserves the supplied source path. Roles,
units and the distinction between an x axis and replicate IDs are guesses. Review the candidate
against the experiment; a high rank does not validate experimental design.

## Offline use and configuration

The Python distribution includes a bundled copy of the canonical TypeScript emitter and Zod.
Its dependency [nodejs-wheel-binaries](https://github.com/njzjz/nodejs-wheel) supplies the Node
runtime through Python packaging. No Node/npm setup, server, account, or network request is
needed for translation or local-file rendering after the dependencies are installed.
Generated Python programs need no Node runtime to execute.

The runtime wheel supports 64-bit Linux (glibc 2.28+ or musl 1.2+), macOS 13.5+, and Windows on
its documented x86_64/ARM64 platforms. The repository tests clean installs on Linux, macOS and
Windows, including minimum Python 3.10 on Linux. Other architectures may need a source/system
runtime arrangement and are not part of that tested installation path.

To prepare an offline machine, build/download a wheelhouse on a matching OS, architecture and
Python version, then copy it to the offline machine:

```sh
python -m pip wheel "./python[interactive]" --wheel-dir wheelhouse
python -m pip install --no-index --find-links wheelhouse "graphunslopify[interactive]==0.8.0"
```

The translator defaults to `local`. `GRAPHUNSLOPIFY_API` selects an explicit HTTP service instead;
SDK `api="local"` or CLI `--api local` overrides it. SDK `api="https://your-service"` and CLI
`--api https://your-service` make the remote choice explicit. Remote translation sends the spec
or profile; the generated Python still reads the data locally. `GRAPHUNSLOPIFY_NODE` can select a
specific supported Node executable instead of the packaged runtime.

## Build and verify a distribution

```sh
npm ci
npm run build:translator
python -m pip install build
python -m build python --outdir dist
python scripts/install-smoke.py dist/graphunslopify-0.8.0-py3-none-any.whl
```

The smoke test creates a fresh virtual environment outside the checkout, installs the actual wheel,
then blocks external Python and Node connections (Python loopback remains available for runtime socket pairs). It checks the local emitter, CLI, SDK, strict reports,
known sample counts/endpoint values, relative paths, spaces in filenames, unchanged builder specs,
and PNG/SVG/PDF provenance. It also verifies that both network blockers reject a real connection
attempt. The built wheel contains the emitter, project MIT license and Zod's MIT notice.

After editing TypeScript source, rebuild and commit the translator. CI rejects a stale bundle.
The Python builder and HTTP/MCP clients all use the same emitter; there is no second statistical
or rendering implementation in the package.

The installation smoke helper removes its temporary virtual environment on exit while retaining
its public evidence files. Use `--keep-environment` for debugging; repeated runs require a fresh
work directory. Add `--agent` to install the optional SDK and verify a real local stdio session.

For development from the moving main branch, use `python -m pip install "https://github.com/unluckyjet/GraphUnslopify/archive/refs/heads/main.zip#subdirectory=python"`. Tagged releases provide a fixed source/docs snapshot; main can change.
