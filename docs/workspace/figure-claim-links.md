# Figure claim links

Link an exact manuscript excerpt or figure caption to a supported numerical
claim in a strict paper audit. The link records which figure and check the
author selected. The check uses the existing claim declaration in the figure
specification, including its series, metric, panel and tolerance when relevant.

## Link text in the paper workspace

Open **Figure claim links** in the scientific review pane. Choose a figure
and recorded check, then paste a unique excerpt from its caption or enter
the project-relative manuscript path and paste the passage. Review the
exact location, proposition and recorded result. Confirm that the selected
check represents the passage before saving.

Refresh the links after editing a manuscript. The panel distinguishes stale
text and stale figure evidence, and shows a contradiction when the current
recorded check fails. Open a linked figure audit to see its saved native
preview and findings.

## Create a link from the terminal

1. Run the project audit with the current figures and inputs.
2. Run `graphunslopify project-claim-links PAPER` to list available figure
   checks and existing links.
3. Create a local JSON draft using a figure ID and a check ID from that list.

```json
{
  "figure": "training",
  "check": "CHECK_ID_FROM_LIST",
  "anchor": {
    "kind": "manuscript",
    "path": "paper.tex",
    "text": "The proposed model exceeds the baseline at every epoch."
  }
}
```

The excerpt must occur exactly once in a project-relative Markdown, LaTeX or
text file. A caption anchor has `kind` set to `caption` and uses the current
figure caption as its source, with no `path`. Paths outside the paper folder
and symlinked sources are refused.

```sh
graphunslopify project-claim-links PAPER --draft claim.json
graphunslopify project-claim-links PAPER --draft claim.json --confirm REVIEW_SHA256
```

Confirm only after reviewing the returned excerpt, exact location, figure
check, and audit evidence. The review digest binds the current manuscript or
caption bytes, check result and link ledger. If any of those change before
saving, review the link again.

## Read or remove a link

Listing links is read-only. The report gives the current source excerpt hash,
location, selected check, and audit evidence hashes when those are available.

| Status | Meaning |
| --- | --- |
| `supported` | The current recorded check holds for the stated inputs. |
| `contradiction` | The current recorded check fails. Review the associated text and figure. |
| `untested` | The audit reported that it could not evaluate the selected check. |
| `stale_text` | The excerpt is absent, ambiguous, or unavailable. |
| `stale_figure` | A current intact audit or an unambiguous match for the check is unavailable. |

The list command exits with status 2 when any link needs attention. A new audit
can change a link's verdict without changing its author-confirmed association.
The project stores the association in its owned `claim-links.json` sidecar.
Use `--remove LINK_ID --links-revision REVISION_FROM_LIST` to remove one link.

The author confirms the correspondence between the text and the selected
structured check. The tool evaluates the check recorded by the audit. Reading
links performs no new audit and makes no broader judgment about the manuscript.
