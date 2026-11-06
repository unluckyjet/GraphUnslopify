# Comments on saved figures

Open the paper workspace with `graphunslopify project-preview PAPER`. In
**Saved runs & changes**, choose an audit and a figure with a PNG export.
Open **Figure comments** and click the image, or enter X and Y in original
image pixels from the top-left corner. Enter a reviewer name and comment,
then select **Add comment**. The numbered pin opens its thread.

Use **Post reply**, **Resolve**, and **Reopen** to follow up. The thread keeps
the replies and a dated record of resolution changes. Reviewer names are
entered by the local users of the workspace.

Each thread belongs to the selected audit and its exact PNG bytes. A later
audit starts with its own view, even when the figure has the same name.
Select the earlier audit to see its original comments. The workspace
verifies the image before allowing changes. If another tab updates the
thread, reload comments and review the current state before retrying.

Comments are stored in `figure-comments.json` within the owned project
folder. Figure source, datasets and saved audit receipts remain intact.
The workspace stores comments locally. Standard review exports, model
requests and numerical verdicts exclude this file.
