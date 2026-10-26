# Public numerical and illustration fixtures

The JSON specs resolve their data beside the spec. From the repository root after installation:

    graphunslopify render examples/references/qq.figure.json --out-dir figures --strict

The Q–Q illustration has 80 standard-normal and 80 Student-t(df=3) synthetic observations,
drawn with NumPy default_rng seed 20261025. The committed CSV fixes the actual observations
independently of future random-generator changes. It reproduces the data/spec used for the
README Q–Q image at docs/seventh-pass-qq.png; numeric tests separately assert known answers in
python/tests/test_qq_references.py. The illustration is not a distributional test or an independent
coverage benchmark. See docs/qq-validation.md for the mathematical contract and limits.

To refresh the tracked image with portable relative paths and the canonical source fingerprint,
run this from the repository root, then copy the resulting PNG into docs/seventh-pass-qq.png:

```python
import json
from pathlib import Path
from graphunslopify.transport import local_request

folder = Path("examples/references")
spec = json.loads((folder / "qq.figure.json").read_text())
result = local_request("convert", spec)
assert result["ok"], result
(folder / "qq.py").write_text(result["code"], encoding="utf8", newline="\n")
```

```sh
graphunslopify run examples/references/qq.py --strict
cp examples/references/qq.png docs/seventh-pass-qq.png
```

Generated programs/images/reports in this fixture folder are development outputs; the tracked
inputs are the JSON/CSV and the published PNG. The image fingerprint regression checks input and
emitter correspondence, while independent numerical tests check quantities and actual artists.

The scaling illustration uses 12 x values spaced uniformly in log10 from 1 to 1000 for each of
two synthetic series. Their generating `(coefficient, exponent)` values are `(3, -0.14)` and
`(2.7, -0.22)`, with independent log10 noise from NumPy default_rng seed 20261025, normal
standard deviation 0.015. The committed CSV fixes the observations. Fitting noisy synthetic
data does not establish a real-world power law or validate population interval coverage.
See docs/scaling-validation.md and python/tests/test_scaling_references.py for independent
hand/SciPy quantities and actual artists.

Install `[statistics]` to reproduce the conditional t95 intervals in the scaling image metadata.
Use the regeneration recipe above with `scaling` in place of `qq` and copy `scaling.png` to
`docs/seventh-pass-scaling-fit.png`. Source/data fingerprints are checked for this image too.

The annotated heatmap and confusion illustrations now have committed synthetic inputs too.
`heatmap.csv` contains 20 invented cafe customer counts over five weekdays and four hours;
`confusion.csv` contains 16 invented weighted class counts. Neither describes measured research.
Their JSON files reproduce `docs/third-pass-heatmap.png` and `docs/seventh-pass-confusion.png`.
Use the same regeneration recipe with `heatmap` or `confusion`. Earlier versions of these
illustrations had no committed input data; these fixtures replace those unreproducible examples.
Fingerprints tie both images to these inputs and the canonical emitter. Separate artist,
inspector, raster and offline-browser controls check cell values and annotation contrast;
see `docs/cell-contrast.md` for the criterion and limits.
