# Exported provenance

PNG, SVG and PDF exports embed the same version 1 evidence envelope:

- `schema_version`: 1.
- `tool`: generator name/version.
- `spec`: complete parsed figure specification; `spec_hash` identifies its serialization.
- `data_sha256_prefix`: first 16 hexadecimal digits of the local data SHA-256.
- `script_sha256`: full SHA-256 of the executed source file, or null when no source file is available.
- `alt_text`: the computed description, including counts and supported claim caveats.

```sh
graphunslopify provenance figure.svg
```

```python
from graphunslopify import read_provenance
metadata = read_provenance("figure.pdf")
spec = metadata["spec"]
```

This reads metadata without executing code or loading the experimental dataset.
Reading evidence does not authenticate it or establish that the current data
still match the stored fingerprint. Rerender and use the strict runtime report
to perform the implemented checks.

| Format | Version 1 payload | Additional fields retained |
| --- | --- | --- |
| PNG | `GraphUnslopify` text metadata | `Description`: spec JSON; `Comment`: alt text |
| SVG | Dublin Core `source` | `description`: alt text; `identifier`: spec hash |
| PDF | Info dictionary `Keywords` | `Subject`: spec JSON; `Title`: figure title |

Legacy generated PNG/PDF files can recover their specification as version 0.
Fields that were absent remain empty/null. Old SVGs that omitted the spec cannot
recover it. Missing, corrupt, or unsupported provenance raises `ProvenanceError`
(a ValueError); the CLI prints an error object and exits 1.

SVG also includes a native `<title>`/`<desc>` linked by ARIA attributes. PDF
metadata preserves descriptions but does not create a tagged-PDF structure tree;
that belongs to the manuscript/accessibility publishing pipeline.

SVG resource IDs use a salt derived from the spec hash, rather than a random
value. SVG/PDF creation timestamps are omitted. An actual rerender test verifies
identical PNG, SVG and PDF bytes for identical inputs in the same environment.
Different renderer/font/library versions can still change the output.
