# Research workspaces

**Current source after0.8.0.** Install the source checkout for these commands.
The published0.8.0 package retains its standalone notebook/editor features.

Use one paper manifest from a terminal, JupyterLab, a VS Code notebook or editor
task, and a LaTeX manuscript. Each entry point runs the same local strict audit.
Your existing data, specs, `.vscode` files and global kernel settings stay intact.

## Try a complete example

```sh
graphunslopify demo paper-demo --json
graphunslopify audit-init paper-demo
graphunslopify workflow-init paper-demo
python paper-demo/graphunslopify-workflow/run.py
```

`workflow-init` validates the existing manifest structure and exclusively creates a visible
`graphunslopify-workflow/` child folder beside it. It refuses an existing folder,
including an empty one. `--folder NAME` chooses another portable child name.
The workflow never merges into existing editor configuration.

Generated files include:

| File | Purpose |
| --- | --- |
| `owner.json`, `workflow.json` | Ownership ID and portable relative manifest configuration. Keep them with the workflow. |
| `review.ipynb` | Cleared project notebook with status table and verified inline PNGs. |
| `paper.code-workspace` | Native VS Code workspace with process tasks and extension recommendations. |
| `run.py` | Small driver using the selected Python interpreter and package runner. |
| `latex/paper.tex`, `latex/include.tex` | Example manuscript and wrapper for an existing manuscript. |
| `latex/figures.tex` | Generated acceptance guard or accepted figure include. Replaced by workflow runs. |
| `.gitignore` | Keeps generated audit evidence, staging and TeX build files out of commits by default. |

Existing manifest path rules are preserved: file-based specs resolve data beside
the spec; inline specs and manifest overrides resolve beside the manifest. They
do not follow the calling terminal. Copy the project and its workflow folder
together to move them. No raw input CSV is copied
into staged manuscript figures; images/reports may still contain your research.

## JupyterLab and VS Code notebooks

Install current source in the selected kernel environment. Existing notebook
installations can use the base package; `./python[notebook]` also supplies
JupyterLab, ipykernel and NBClient.

```sh
jupyter lab paper-demo/graphunslopify-workflow/review.ipynb
```

Run All. The notebook finds its own ownership ID from either the notebook folder
(Jupyter's usual kernel directory) or the project root (common in VS Code).
An unrelated configuration is not silently selected. Other kernel directories
receive an explicit path/cwd correction rather than running a different project.

The first code cell runs the manifest audit and shows actual statuses and saved
PNG bytes. The final cell raises on nonzero acceptance, retaining the earlier
report/images and the failed cell. Successful image display never overrides a
failed claim. For customization, the API is:

```python
from graphunslopify.workflow import run_workflow, notebook_html
from IPython.display import HTML, display

result = run_workflow("paper-demo/graphunslopify-workflow/workflow.json")
display(HTML(notebook_html(result)))
if result["exit_code"]:
    raise RuntimeError("Review the failed figure workflow")
```

`run_workflow` returns evidence on rejection. It also accepts `baseline`,
`baseline_root`, `fail_on_warning`, `fail_on_change` and `timeout`, like the audit.
Explicit relative baseline arguments follow the calling process directory; use
`CONFIG.parent / ...` or absolute paths to make customized notebook cells portable.

## VS Code tasks

Open the generated `paper.code-workspace`, select the Python environment with the
source package installed, then use **Terminal: Run Task**:

- **Audit all figures** runs the strict audit.
- **Prepare checked LaTeX figures** stages accepted exports.
- **Build example manuscript** depends on preparation, then invokes `pdflatex`.

Tasks use `type: process`, separate arguments and the Python extension's
`${command:python.interpreterPath}`. Paths containing spaces/Unicode do not become
shell commands. The Python extension resolves the selected environment; the
Jupyter extension supports notebook editing. These are recommendations in the
workspace, not automatic global installations.

This uses VS Code's documented [selected-interpreter task command](https://code.visualstudio.com/docs/debugtest/tasks)
and [workspace-scoped tasks](https://code.visualstudio.com/docs/editing/workspaces/multi-root-workspaces).
Tests execute the generated process argv with a real interpreter and cwd; the
VS Code GUI/extension installation itself is not automated by these checks.

## LaTeX manuscript inclusion

```sh
python paper-demo/graphunslopify-workflow/run.py --latex
cd paper-demo/graphunslopify-workflow/latex
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error paper.tex
```

Preparation audits first. Only accepted, hash-verified PDF or PNG exports are
copied into a fresh owned `latex/runs/<run-id>/` directory. PDFs are preferred.
Captions and computed descriptions remain literal text; TeX control characters
are escaped. Double-column specifications use `figure*` for a two-column manuscript;
single-column specifications use `figure`. Every include uses the recorded manuscript target width. A smaller
line width raises a TeX error instead of silently shrinking a figure below its
inspection context. Use the intended column/figure layout or regenerate/recheck
for a narrower target.

For an existing manuscript compiled from the project root:

```tex
\usepackage{graphicx}
% Where the figures belong:
\input{graphunslopify-workflow/latex/include.tex}
```

The wrapper sets its own relative graphic root, so source project folder names
can contain spaces/Unicode while staged filenames remain portable. The example uses Latin Modern outline fonts and explicit pdfTeX Unicode maps,
so text ligatures remain searchable/copyable on minimal TeX installations. Install
the `lmodern` TeX package alongside `graphicx` and `geometry` to build it. See
[Latin Modern](https://www.ctan.org/pkg/lm) and the
[pdfTeX Unicode mapping documentation](https://ctan.math.washington.edu/tex-archive/systems/doc/pdftex/manual/pdftex-a.pdf).
This does not change your existing manuscript font setup. The example
uses an8-inch text block; it is a build demonstration, not a journal template.
Your manuscript owns fonts, float placement and Unicode-capable engine choices.
Descriptions are retained via `\Description`, with a no-op fallback when no
accessibility package defines it. This does not certify tagged PDF accessibility.

Every attempt in a recognized owned folder invalidates the previous include
**before** parsing `workflow.json` or running an audit. Keep `owner.json` intact
with the generated folder; an unrecognized folder is refused without writing. A bad config, missing source,
failed claim or unavailable required export leaves a `\PackageError` guard.
A successful non-LaTeX audit also leaves the guard: explicitly prepare the current
manuscript exports before compiling. Accepted preparation replaces it and retains
old run files. External edits made without running the workflow are not monitored.

`workflow.report.json` records the full audit, source `audit_status`, overall
acceptance/exit, errors and LaTeX status. A passed source audit can still have
workflow exit2 if manuscript preparation is unavailable. `latex.status: prepared`
always has `compiled: false`; only the actual TeX command establishes compilation.
The VS Code build task stops on failed preparation and honors TeX's own exit.

## Verification and remaining integration work

`python/tests/test_workflow.py` uses actual audits, notebook kernels in both cwd
contexts, generated editor argv and real TeX compilation/guard rejection/recovery.
It checks moved projects, captions, widths, stale-config/input failures, symlink
refusal and input/editor preservation. Real TeX cases are mandatory in render CI.
`scripts/check-research-workflow.py` and installed-wheel `--require-workflow` check
the actual outside-checkout CLI/editor-process path offline on four platforms.

This workspace milestone covers JupyterLab, VS Code and LaTeX. Experiment-tracking
integration is the next separate checkpoint; the full review item9 stays open
until that is implemented and measured.
