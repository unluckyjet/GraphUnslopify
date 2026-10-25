# Local figure editor

After [installing GraphUnslopify](installation.md), launch:

```sh
graphunslopify preview --open
```

Open the printed local URL if a browser does not open automatically. This command also works in
the VS Code integrated terminal; edit JSON here or in your normal editor and paste it into the
workspace. No editor extension, hosted translator, JavaScript CDN or external account is required.
The UI, translator, Node runtime and renderer are shipped in the Python distribution. Rendering
works offline after dependencies are installed.

## A complete edit and review

1. Select **Try sample data**, or choose a CSV, regular JSON table or Parquet file. The sample is
   public synthetic data. Parquet needs the `[parquet]` extra. Files are read by a loopback service
   on this computer; nothing is sent to the hosted API.
2. Review the inferred fields and experimental units. Choose a kind, x/y fields or group. A
   canonical recipe offers a starting spec; its placeholder fields still need your own data.
3. Edit the JSON for claims, uncertainty, named repeat IDs, panels and kind-specific options.
   All 21 canonical kinds use the same schema/compiler as the CLI and agent integration. Some
   combinations deliberately produce validation errors rather than approximate another chart.
4. Leave **Live preview** selected, or use **Render now** (Ctrl/Cmd+Enter in the spec editor).
   Every edit immediately clears the prior preview and exports. A late result from an older
   revision cannot become the current result. Only one render runs at a time, with a 120-second
   process-tree timeout; obsolete queued requests are skipped.
5. Review findings and each claim's panel, metric and verdict. Static errors prevent rendering.
   A failed runtime claim can leave a visible figure, marked **Failed checks**. **Verified** means
   the strict checks passed; it cannot establish independence, causality or the right study design.
6. When a finding offers a fix, expand **Review proposed change** and press **Apply fix**. The
   server recomputes current findings and applies only that verifier-owned patch. Findings without
   an actual automatic fix require an author edit.
7. Download an individual output, or **Download figure bundle**. The ZIP includes actual output
   artifacts, generated Python, normalized effective spec and the original runtime report. Source
   data is excluded unless **Include source data in ZIP** is selected. A chosen palette lock is
   included when the spec uses it. A PNG is explicitly added to requested formats for preview;
   the effective spec, generated program, report and provenance agree about it.

Extract a bundle with source data to a new directory, then reproduce it there:

```sh
python figure.py --strict --json --report verification.json
```

Replace `figure.py` with your chosen output stem. Without bundled data, place the selected data
beside the script under the relative filename in the exported spec (`data.csv`, `data.json` or
`data.parquet`). Keep the generated Python unchanged if comparing its embedded source digest.
Supported interactive HTML needs `[interactive]`; animations may need external encoders. Missing
exports stay visible as errors rather than disappearing behind a successful preview.

## Local file boundaries

The service binds only to `127.0.0.1`. Host/origin checks and a random session token protect API
requests. Data and palette paths in a submitted spec are rebound to files explicitly selected in
the workspace. The editor accepts a plain, portable output stem; filesystem paths and Windows
device names are rejected. Artifact downloads use a per-run whitelist, never arbitrary paths.

Uploads and generated previews live in a private temporary session directory and are removed on
normal shutdown. Save wanted outputs before stopping the service with Ctrl+C. Shutdown waits for
bounded workers before removing their files; an active render has at most its 120-second timeout.
The default file
limit is 100 MiB; use `--max-upload-mb 250` to increase it. `--port 9000` chooses another port;
`--port 0` asks the OS for a free one. This is a single-machine editing service; network hosting,
shared workspaces and persistent project storage are outside its supported workflow.

## Verification

`PYTHON=python npm run preview-check` launches the real CLI and Chromium, selects a real file,
edits specs, applies a current offered fix, checks static and runtime failures, delays an older
response to verify revision handling, downloads ZIPs with and without data, and rerenders an
extracted bundle outside the checkout. It verifies output digests/provenance and captures desktop
and mobile screenshots. It also checks zero external browser requests and JavaScript errors.
Install Chromium with `npx playwright install chromium`; on macOS the check can use installed
Google Chrome. `GRAPHUNSLOPIFY_BROWSER` can select a browser executable. CI runs this workflow and
retains its screenshots and exported evidence alongside the other rendering checks.
