---
id: 22
slug: local-agent-bridge
status: done
priority: P1
title: Local stdio agent tools and environment-specific configuration
source_idea: accepted lightweight agent integration roadmap
---

# Local agent bridge

Expose the canonical compiler through the official MCP SDK over local stdio. Seven read-only
operations provide schema, recipes, suggestions, validation, scoring, bounded fixes and generated
Python; schema is also a resource. Preserve structured results and tool errors for schema and
semantic failures, including error/code coexistence. Never open user data or execute generated
programs in this server. Clients run the strict local CLI for data/geometry verification.

Print generic JSON or Codex TOML using the active Python executable, without changing personal
configuration. Document the local agent loop, data boundaries and optional SDK dependency.
Verify the Codex form against official documentation and installed CLI using a read-only override.

A real agent probe exposed the ranker's unrelated default results.csv. Canonical suggestions now
preserve profile paths and CSV/JSON/Parquet formats; JSON Lines gets no misleading reader candidate
and the Python/agent adapters explain conversion. The same fix reaches HTTP and Python consumers.

## Verification

Actual subprocess sessions exercise modern and legacy handshakes, every tool, schema resource,
canonical code/result parity, recipes/repairs/suggestions, non-existent data paths and structured
schema/semantic errors. Config output names the active environment; Codex accepted command/args
through a read-only override. No personal settings changed and no model/API call was required.

All local gates pass: 215 Node (zero skipped), 137 Python, 15 baselines, 16 renders, 25 recipes and
seven compositions. A fresh wheel with the agent extra negotiates stdio with external Python/Node
connections blocked (local Python socket pairs allowed); both blockers are probed. The temporary
venv is removed on exit unless explicitly retained, preventing repeated smoke runs filling disk.
During work, eight verified owned old test environments were removed after a no-space install.

CI tests full Python 3.10/3.12 suites and optional-agent wheel smoke on Linux/macOS/Windows. Results
are checked after pushing. Visual editor, broader references, naming/release and final audit remain.
