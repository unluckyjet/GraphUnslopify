---
id: 62
slug: research-workspace-integrations
status: done
priority: P1
title: Connect manifest audits to real notebooks VS Code and checked LaTeX inclusion
source_idea: review2026-10-28 item9 JupyterLab VS Code LaTeX workflow milestone
---

# Research workspace

1. Generate a dedicated non-clobbering child workspace beside an existing valid
   manifest, without changing inputs, editor settings or global kernels. Include
   a cleared project notebook, VS Code workspace/process tasks, portable config,
   driver and LaTeX example/inclusion instructions. Existing Jupyter/VS Code
   capabilities are reused; this is not another renderer.
2. One package runner powers terminal, notebook and editor tasks. Paths with spaces
   and Unicode work, selected VS Code Python uses the official interpreter command,
   notebook resolution supports notebook-folder/project-root kernels without choosing
   unrelated configs. Actual audits/strict exits/reports/verified inline PNGs remain
   available on rejection; final notebook cell rejects failure rather than hiding it.
3. Explicit LaTeX preparation only stages accepted, verified PNG/PDF exports in a
   fresh owned run, escapes literal captions/descriptions, includes at recorded
   manuscript width and rejects too-small line width. Missing width/evidence/format
   or failed audits leave an owned TeX error guard instead of stale accepted output.
   Existing manuscripts can include a generated wrapper; generated example compiles
   from its own folder. Preparation is distinct from compilation/tagged accessibility.
4. Real kernel execution, actual editor process-task commands and actual LaTeX
   compilation prove pass/fail/guard recovery, input preservation, different cwd,
   multiple figure kinds and known caption/path handling. Fresh installed source
   package works outside checkout offline. Run all seven gates and exact pushed CI;
   maintain Obsidian. Item9 remains partial until experiment tracking milestone63.

## Measured acceptance (2026-10-28)

- 32 integration controls pass: actual multi-figure audits, preserved inputs/editor
  settings, owner-ID/cwd resolution, real notebook kernels from both contexts,
  retained failed cell/previews and actual generated editor-process argv.
- Real pdflatex compiles the generated and existing-paper includes, literal caption
  controls, PNG/PDF staging and a double-column figure* at its recorded7-inch width.
  Narrow columns, failed science and stale inputs/configs reject; successful recovery
  references a new owned run. Symlinks cannot overwrite an unrelated manuscript.
- PDF pages rendered with Poppler/visually inspected. Found/fixed figures floating
  above example heading, with a rendered-text order control. Preparation records
  compiled:false; actual TeX tests are mandatory in render CI.
- Seven gates222 Node/1259 Python, zero local skips/warnings;15 baselines/16 renders/
  25 recipes/seven compositions and Ruff75 lint/format pass. Original emitter,
  generated figures and graphics unchanged.
- Fresh outside-checkout source-wheel agent/PDF/environment/comparison/workflow
  smoke passes with runtime networking blocked; actual prepare/reject/recover and
  unchanged inputs/editor-process acceptance verified. Notebook kernel checks are
  separate actual local/CI tests, not inferred from copying a notebook.
- Exact pushed main/Figure CI checked next; immutable public0.8.0 untouched.
  Item9 remains partial until ready experiment-tracking milestone63 is delivered.
