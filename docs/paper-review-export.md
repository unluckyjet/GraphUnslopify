# Export a paper review packet

Use **Download review packet** in the paper workspace to save the selected
collection's figure files and a readable audit report together. Install the
current source for this feature; published PyPI 0.8.0 predates it.

The ZIP opens locally through `index.html`. It includes the four evidence groups,
whole-paper checks, verified saved exports, machine-readable reports and a file
manifest. A reused figure retains its original execution ancestry. Downloading
the packet runs no scientific figure programs.

## Choose the evidence

| Selection | Packet contents |
| --- | --- |
| Current inputs | Latest available native run and current PDF visual evidence, with input freshness and unavailable evidence disclosed. |
| Saved native run | That run's original figures and whole-paper results, including figures removed from current definitions. Later PDFs are excluded. |
| Saved PDF inspection | That source's saved page/text/report evidence. Unrelated native results are excluded. |

Raw datasets, source programs and original PDFs are excluded. Reports and figure
files still contain their recorded results, labels and source metadata. The
packet supports review; it is not an executable reproduction bundle.

The report preserves failed, incomplete, untested and historical evidence.
Individual figures can pass while the whole paper remains rejected, for example
when baseline previews are unavailable. Both outcomes remain in the packet.
Source-free PDF numerical claims and original data remain **untested**.

## Command line

```sh
graphunslopify project-export paper/ --output paper-review.zip
```

For a particular historical run or inspection, add `--event EVENT_ID`. To require
the exact evidence previously reviewed, pass its `evidence_revision` from
`graphunslopify project-review paper/` as `--expected-revision REVISION`.

The destination must be new and outside the owned project evidence directory.
CLI exit 0 means the review packet was created; `native_audit_exit` retains the
selected scientific audit's separate result. An archived rejection remains a
rejection.

## Integrity and limits

`review.json` retains grouped evidence and selection context. `reports/` retains
the actual selected aggregate audit and relevant execution-ancestry reports;
`receipts/` retains their recorded inventories. `manifest.json` records the
included files' sizes and SHA-256 hashes, excluding itself. These hashes check
file consistency; they do not authenticate an author or establish scientific
validity.

Every included saved asset must match its recorded bytes. Missing or changed
assets are reported as unavailable, while intact evidence remains reviewable.
The tool does not repair old history or silently replace missing files with a
new render. Inputs, receipts, included files and ownership are checked again
before collection finishes. The browser also rejects a late response if its
review revision has changed.

The packet is bounded to 128 MiB of collected bytes and 4096 files. It contains
only explicit saved members. Figure HTML/SVG files are downloads; the report
embeds verified PNG previews and does not execute figure HTML. No network
service or account is required to open the report.

See [paper projects](project-management.md),
[reviewed changes and undo](reviewed-paper-changes.md) and
[selective regeneration](selective-paper-regeneration.md).
