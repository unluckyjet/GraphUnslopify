# Security policy

## Report a vulnerability privately

Use [Report a vulnerability](https://github.com/unluckyjet/GraphUnslopify/security/advisories/new)
for suspected arbitrary code execution, unauthorized file access, disclosure of
private data, or bypasses of local editor/project authorization and path boundaries.
This is the repository's private GitHub reporting channel. See
[GitHub's reporting instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

Include the affected release or source commit, operating system, Python/Node
versions, a minimal synthetic reproduction, expected/actual behavior and likely
impact. Include only evidence you are authorized to share. Keep credentials,
private datasets, other users' files and working public exploit details out of
public issues and pull requests.

If the private form is unavailable, open an issue asking for a private reporting
channel **without disclosing the vulnerability or exploit**. Ordinary plotting
bugs, false warnings and statistical disagreements belong in the
[issue forms](https://github.com/unluckyjet/GraphUnslopify/issues/new/choose), unless
they also expose a security boundary failure.

## Versions and scope

Report affected released versions even if a newer source commit exists. Identify
whether the issue reproduces on the latest published release or current main;
source-only features are separate from the0.8.0 release. Fixes, backports and
disclosure timing need case-by-case review; this policy does not promise a response
deadline, a backport or a bug bounty.

The translator produces Python; rendering and script-based audits execute code
locally. Use trusted scripts, dependencies and inputs, and review executable
content before running it. The tool is not an operating-system sandbox.
Local browser interfaces bind to loopback and use session authorization; keep their
URLs/tokens local and close the server when finished. Figure provenance is
evidence metadata, not authentication of data origin. Scientific verification
does not establish that a program or dataset is safe.
