# Compact versioned runtime comparison

The protocol and accepted1b baseline were frozen before runtime changes. The comparison
keeps all30 original variants/all21 chart kinds, input/spec hashes, requested exports,
scientific gates and the original strict failure.

The [measured v1 results](results/measured-v1/README.md) preserve900 formal executions
and360 smoke executions. Median entry size falls from118,491.5 to33,256.5bytes while
complete package source/resources grow from1,828,626 to1,897,739bytes. Native case
medians improve in20/30 and regress in10/30; direct results also include regressions.
There is no general speed, human-productivity or independent-execution claim.

See the per-case median/P90 CSV, first-start/setup fields, original-source profiling,
whole runtime/bundle member inventories and all raw archives. Eleven pinned scientific
components are not a minimal dependency closure. Third-party dependencies stay external.
The same actual Python binary and6,980 library/resource files across11 scientific
distributions match between the native and no-package direct environments.

## Run

Use matching scientific libraries and a second interpreter with no GraphUnslopify
distribution/import. Preserve its virtual-environment executable path. Run serially:

```sh
python scripts/runtime-benchmark.py --smoke --python /path/to/no-package/bin/python --out-dir /outside/checkout/smoke
python scripts/runtime-benchmark.py --python /path/to/no-package/bin/python --out-dir /outside/checkout/formal
```

The actual native geometry guard requires comparable frozen drawing conditions;
different platforms/library/font versions may correctly refuse comparison. Run the
[published scientific-file audit](results/measured-v1/audit-scientific-files.py)
with each interpreter to reproduce the additional environment-byte proof; compare
the resulting distributions and interpreter-binary hashes. `scripts/publish-runtime-benchmark.py --help`
documents the publication inputs. Required local checks and exact-commit CI are
additional delivery gates. The immutable public0.8.0 release is not changed here.
