# Unverified preview and final checks

Current source can display the actual figure while its checks and requested
exports finish. The early image is labelled **Unverified preview**. Download
links, bundle export and diagnostic/text targets remain unavailable until the
current final response arrives. Editing the intent immediately discards the
early image; late responses or image decoding cannot restore an older result.

The original strict script runs once. A failed claim still ends with failed
checks and its current report; an early image is never a certificate. Progress
can be unavailable or arrive too late to be useful, in which case the final
result is shown normally. Public PyPI0.8.0 predates this source feature.

![Actual unverified editor with exports and inspector controls disabled](staged-preview-unverified.png)

This is a controlled correctness test using the original24-row fixture. The
genuine checker is deliberately held and then released; the screenshot does not
measure ordinary preview latency. The actual current PNG has already been saved,
while final scientific acceptance has not completed.

![Original false claim remains explicitly failed after final checks](staged-preview-failed.png)

## Current evidence and limits

Source107 browser workflows (the existing101 plus six staged cases) and six
controlled minimum-Python workflows pass. The new cases exercise genuine
pre-check availability, original strict failures, late metadata/image decoding,
live-off invalidation and refusal of malformed progress acceptance. Existing
source/claim/undo/draft/consent and export checks remain in the complete suite.
Fresh107 GUI and all60 packaged files also pass outside the checkout. Seven
stable checks pass232 Node/1904 Python/zero skips/one upstream warning, Ruff152
on419 unchanged source/test/fixture files. Exact1d66224 main all-nine/Figure CI
passed2026-10-31 07:19UTC; all four actual CI wheels contain the matching60
package files.

The [frozen comparison](../../benchmarks/staged/protocol.json) separately measures
first image and final result, including extra copy/hash/transport/decode work,
original negatives and a PNG-only control. Its612 formal/108 smoke records are
measured in the corrected source run: all612 outcomes and433 frozen source
files conform, with source/minimum/fresh108 also passing. No general speed or human usability gain is established by
controlled holds. [Backend/methods](../../benchmarks/staged/README.md);
[full scope](../../pipeline/done/85-incremental-staged-preview.md).


The observed benefit is an earlier current image, with final-time costs retained.
One dense-data title-b edit shows406.2ms→289.1ms first-image medians and
406.2ms→415.1ms final-result medians. All42 exact edits have seven ordinary
median/p90s in the [complete report](../../benchmarks/staged/results/staged-preview-v1/comparison.md).
These local developer-selected measurements establish no general human speed
advantage. The benchmark checkpoint's seven232/1904/Ruff153 checks pass on446 unchanged
files; push/exact CI is under acceptance.
