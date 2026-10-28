# Published-data figures

Run from the repository root after `python -m pip install -e ./python`:

```sh
python scripts/prepare-paper-data.py
graphunslopify audit examples/published-papers --out-dir paper-audit
python scripts/paper-benchmark.py --out-dir paper-benchmark
```

Choose new output directories to preserve previous evidence. The manifest covers
four positive descriptive figures. The benchmark additionally injects false or
unavailable claims/SD and compares actual artists with separate stdlib calculations.

Sources, licenses, methods, exact measured limits and visual comparisons:
[published-paper validation](../../docs/validation/published-papers.md).
Dataset attribution: [notices](../../benchmarks/papers/NOTICE.md).
