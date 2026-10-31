# Central figure workspace evidence

Captured2026-10-29 from the actual local editor, using the unchanged synthetic
24-row sample. `before.png` comes from6d7a085, extracted read-only from Git;
`after.png` comes from the milestone80 worktree. The JSON files record viewport,
matched header-relative crop, actual DOM rectangles and source-asset SHA256s.
The central figure and new column details are marked on the [comparison board](comparison.html).
The board embeds its panes and opens as a standalone file; [PNG](comparison.png)
is the same composed board. Its second marker uses the empty right edge of the
data detail region to keep the helper text visible.

Both `*-figure.png` files are original renderer exports, not screenshot crops.
Decoded RGBA dimensions1953x1691 and every pixel match between before and after.
The interface changed; the demo figure's intent and drawn output did not.

The placement references are [Retool](https://mobbin.com/screens/ca7c6cd0-39cd-4956-9359-20c8456a14a4),
[Databricks](https://mobbin.com/screens/5b995fc9-de89-490c-a906-1a5e33345f37) and
[Rows](https://mobbin.com/screens/9091edab-43d4-4bbd-9ca3-dce92b2bac3f), inspected
through Mobbin. Only structure informs the change; GraphUnslopify retains its own
palette, typography, data and controls. No usability or task-speed improvement
has been measured.

## Reproduce

Install source and its optional Excel/Parquet readers, then run the real browser
checks with `PYTHON=python npm run preview-check`. These cover31 workflows/all21
kinds, real file picker/File API drops, profile facts, explicit recommendation
apply/undo, worksheet races, strict failures, stale results, exports and actual
extracted-bundle reproduction. `npm run project-check` checks the paper editor,
which shares the base stylesheet. CI retains actual browser artifacts.

To capture a chosen checkout without changing it:

```sh
PYTHON=python GRAPHUNSLOPIFY_CAPTURE_SOURCE=/path/to/checkout \
  node --experimental-strip-types scripts/capture-workspace.ts /path/to/output after
```

`GRAPHUNSLOPIFY_BROWSER` optionally selects an installed Chromium/Chrome executable.
Capture the same viewport/crop and sample on both revisions. The durable script
saves the real rendered figure as well as screenshots and measured metadata;
it does not execute screenshot lookalikes. Current changes are source additions
after the immutable PyPI0.8.0 release.


Complete [spatial diagnostics and owned-layout acceptance](spatial-layout-acceptance.md)
records milestone83, exact CI evidence and retained strict limits. Measured worker milestone84 is accepted at179784f with exact main/Figure CI.
[Numerical reuse85a](../../benchmarks/incremental/README.md) is under acceptance;
staged preview85b and full review-workspace milestones86–89 remain open.
