---
id: 79
slug: native-excel-input
status: done
priority: P1
title: Preserve native workbook inputs and explicit worksheet selection throughout the figure workflow
source_idea: User visual-workspace advice and native Excel authoring requirement
---

# 79 — Native Excel import

Parent: [workspace roadmap](../visual-workspace-roadmap.md).
Prerequisite78: b95f833 exact main40895079839 all9 / Figure40895079807 passed.

## Backend checkpoint79a

Native `.xlsx/.xlsm/.xls` readers, canonical `data.format: excel`/`data.sheet`,
SDK inference/worksheet selection, CLI `describe --sheet`, ranked suggestions,
generated Python, audit fingerprints and dependency provenance must use the same
selected worksheet and original bytes. Multi-sheet ambiguity and unknown sheets
must fail explicitly. Retain literal text IDs, numeric/date objects and missing
values; do not manufacture formula results or scientific independence.

One self-contained `workbook.py` is embedded by build:translator. Use the explicit
calamine engine with the optional Excel extra (pandas>=2.2/python-calamine),
avoiding current pandas' deprecated xlrd path. Keep base CSV installations and
legacy runtime reports compatible. Current PyPI0.8.0 remains immutable.

Measured local focused evidence:10 real-file/compiled/actual-artist/strict-runtime
controls pass, including genuine synthetic legacy XLS, exact selected-sheet
bar heights7/11/13 and identifiers001/NA/010, three actual export formats,
schema-valid reports, source preservation and reader-version evidence.
Final seven gates227 Node/1439 Python pass, zero skips/one existing upstream
warning; Ruff89 and fresh installed/offline native XLS smoke pass with actual
three-format exports, schema-valid reports and unchanged source hash. Actual
Python3.10.22 focused26 controls pass, plus final10 expanded workbook cases. All25
pre-existing recipe programs remain byte-identical to b95f833. Backend be160ba
exact main40901467484 all9 and Figure40901467426 passed; the downloaded actual
Linux3.10 CI wheel reader/translator/schemas byte-match source and its Excel
dependency metadata is verified.

## Browser checkpoint79b (implemented; exact pushed CI pending)

- Accept and preserve workbooks in an owned upload, list available worksheets,
  and require selection before a multi-sheet input is usable.
- Bind selected profile/suggestions/spec/render/bundle to that exact immutable
  worksheet selection; prevent stale responses from replacing current evidence.
- Add accessible worksheet selection and file-picker format guidance.
- Verify actual browser upload, ambiguity, switching, rendering, exported source
  workbook bytes, consent, reproduction and packaged assets. Preserve loopback
  token/Host/origin/path boundaries and current control/advanced JSON behavior.

Do not mark79 complete after79a alone. Commit/push each coherent checkpoint and
check exact CI before advancing. Central layout/drop/explorer remains80.

## Browser acceptance evidence

Actual API tests11 pass: staging/explicit selection, token/origin/unknown-sheet
refusal, immutable selected IDs, selected-spec rebinding, source-byte preservation,
consent-controlled original-workbook ZIP and extracted strict reproduction.
Full local gates227 Node/1444 Python pass, zero skips/one existing upstream warning;
Ruff89 passes. Actual3.10.22 focused21 cases pass. Real source and fresh installed
offline Chromium each pass26 workflows/all21 kinds with zero external requests
or JS errors. Held old worksheet responses cannot replace current inputs; actual
extracted marks match001/NA/010 to7/11/13. Desktop/mobile screenshots inspected;
390px has no horizontal overflow. ZIP consent explicitly includes all worksheets and resets when the data file changes.

The real browser run exposed inherited automatic SEM suggestions on singleton
categories. Suggested bars now leave intervals to an explicit author choice and
avoid an unused legend. Strict verification remains unchanged and retains actual
failed/incomplete outcomes. A candidate may be a box; the browser test explicitly
chooses bars via the native kind control and checks real label/value associations.

Fresh installed assets come from /tmp/graphunslopify-workbook-editor-installed;
the durable driver is scripts/preview-check.ts. CI installs the Excel extra for
this browser gate and retains native installed-export evidence alongside wheels.
New exact main/Figure CI must pass before milestone80; no PyPI release is made.
