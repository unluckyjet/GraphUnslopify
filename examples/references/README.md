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
