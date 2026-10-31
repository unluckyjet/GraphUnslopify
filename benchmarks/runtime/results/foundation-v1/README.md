# Runtime foundation conformance

This is the first milestone of item 86. Ordinary generated scripts remain inline. Compact default emission, complete standalone export and full footprint/startup comparisons remain open.

| Actual environment | Cases / kinds | Strict executions | Expected outcomes per path |
| --- | ---: | ---: | --- |
| Source Python 3.12 | 30 / 21 | 90 | 29 pass, 1 strict failure |
| Minimum Python 3.10 | 30 / 21 | 90 | 29 pass, 1 strict failure |
| Fresh wheel Python 3.12 | 30 / 21 | 90 | 29 pass, 1 strict failure |

Each case executes its accepted inline program, then canonical helpers bound to that actual program context, then the current inline emitter. No substitute scientific calculation is used. Actual artifact byte hashes and embedded program/spec/data provenance are verified; the expected program source-digest change is normalized only after validation. PNG dimensions/pixels, SVG drawing XML, PDF drawing streams, scientific report/environment/policy and table/LaTeX text must agree. The fresh package's 61 invoked files match actual source; scientific dependencies resolve inside its fresh environment.

[verification.json](verification.json) records all outcomes, package hashes and the raw archive binding. [raw-evidence.zip](raw-evidence.zip) retains the actual programs, data, reports and exports for all 270 executions plus exact producer sources. Source/minimum/fresh conformance runs may overlap; no timings are interpreted from them. These are developer-controlled checks, not independent scientific execution or general human utility results.

[published-pixels.json](published-pixels.json) checks all 15 published baseline PNGs. [reference-refresh.json](reference-refresh.json) checks seven other published PNGs, all 14 reference input files and all 10 original benchmark protocols. Pixels and inputs remain unchanged. The first full gate run caught seven stale reference-image program fingerprints: 1905 passed, seven failed. The existing reference refresher preserves the original incomplete density result. The complete repeat passes: both CI Ruff invocations (157 files), typecheck,232 Node tests/zero skips,1912 Python tests/zero skips/one upstream SQLAlchemy warning, baseline source check, rendering, recipes, composition and all15 strict gallery examples. All828 protected executable/config/fixture/golden paths remain unchanged. [local-gates.json](local-gates.json), [local-gate-metadata.json](local-gate-metadata.json), [tested-source-manifest.json](tested-source-manifest.json). Exact-commit CI follows the push.

The actual baseline packet is `../../baseline-1b942e3.zip`; its literal binding and future complete comparison conditions are in [../../protocol.json](../../protocol.json). Neither compact runtime performance nor genuine standalone reproduction has been established by this partial milestone.

Final pre-push byte audit finds a pre-existing17-CRLF example CSV differing from Git's LF blob. Parsed frames are identical. Its working copy is restored to existing committed bytes (no Git content change), then **all seven/Ruff/gallery checks pass again**, with all828 tested paths now matching actual index blobs. The receipts above are this final repeat. [preexisting-fixture-byte-audit.json](preexisting-fixture-byte-audit.json), [tested-index-binding.json](tested-index-binding.json).
