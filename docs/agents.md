# Local agent integration

Install the optional MCP SDK alongside the local compiler. From a source checkout:

```sh
python -m pip install "./python[agent]"
graphunslopify mcp-config
```

The second command prints a client JSON entry using the active Python executable. Put it in a
client that accepts the `mcpServers` format. The executable points at the environment containing
the installed package and its dependencies, so launching does not depend on a shell activation.

`graphunslopify mcp` starts the server over stdin/stdout. The agent host launches and owns that
process; there is no HTTP port, hosted translator, credential or separate npm installation needed.
Protocol output stays on stdout; diagnostics use stderr. The server uses the official
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v2.3.0).

## Codex

Print a TOML entry for the current environment:

```sh
graphunslopify mcp-config --client codex
```

It has this shape:

```toml
[mcp_servers.graphunslopify]
command = "/absolute/path/to/environment/bin/python"
args = ["-m", "graphunslopify.cli", "mcp"]
```

Add the printed entry to your Codex MCP configuration, or register the same command with the CLI:

```sh
codex mcp add graphunslopify -- /absolute/path/to/environment/bin/python -m graphunslopify.cli mcp
codex mcp get graphunslopify --json
```

Use your actual executable path (on Windows it is usually under `Scripts/python.exe`). The config
generator prints text; it leaves personal settings unchanged. These instructions were checked
against the installed Codex CLI and the [official MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
A read-only per-command Codex override accepted the generated command/arguments during verification.

## Tools and a useful agent loop

| Tool | Result |
| --- | --- |
| get_figure_schema | Canonical JSON schema for all kinds/options |
| list_recipes | Known-good design names, or a complete named recipe |
| suggest_figures | Ranked candidates for a supplied dataset profile |
| validate_spec | Schema/semantic findings and resolved defaults |
| score_spec | Perceptual design cost/reasons and findings |
| apply_fixes | Bounded static-linter repairs and unresolved findings |
| figure_to_matplotlib | Reviewable generated Python, filename and findings |

The schema is also a resource at `graphunslopify://schema`. Tools have read-only/idempotent hints;
`apply_fixes` returns a changed spec without editing files. They all use the same packaged
TypeScript compiler as the Python builder and HTTP service.

1. Profile the actual local file with `graphunslopify describe results.csv`. Give the selected
   profile/column facts to the agent; roles and units remain guesses to review.
2. Ask for the schema or a recipe, then choose fields, units, repeat IDs and explicit claims.
   Suggestions preserve the profile’s actual filename and supported format; JSON Lines must be
   converted to a regular JSON table or CSV before rendering.
3. Validate, review offered fixes, and regenerate. Honor `isError`, `ok` and findings. A semantic
   error can coexist with reviewable code; code being present does not mean execution is approved.
4. Save the returned program and run `graphunslopify run figure.py --strict --json` with the
   appropriate input working directory. Actual data claims and geometric checks happen here.
5. Read the runtime report. Correct the spec or claim when it fails; do not suppress failed or
   untested required checks to obtain a green process. Use a paper manifest/Figure CI for the loop
   across many figures.

The compiler server does not open data files or execute generated programs. It receives only
specs/profiles explicitly supplied to its tools. Profiles can contain category names and summary
statistics. Local execution reads data on the machine running the program; the agent host controls
what model context it sends elsewhere. No experimental dataset upload is required by this server.

## Verification and compatibility

Tests launch actual stdio subprocesses with both modern discovery and legacy handshakes. They
exercise all seven tools, schema resource, canonical payload parity, repairs/suggestions and
schema/semantic errors. A nonexistent input path still compiles, verifying the server does not
need to read data. Core installs can print client configuration; starting the server requires
`[agent]`. Clean wheel smoke also launches the installed agent bridge with external Python/Node
connections blocked; Python loopback remains available for runtime socket pairs.

The optional dependency is MCP SDK 2.3 through 2.x. Python 3.10+ remains supported. The hosted HTTP
MCP endpoint remains available for clients choosing that transport. See [notebooks](notebooks.md),
[paper audits](paper-audits.md) and [Figure CI](figure-ci.md) for the subsequent local workflow.
