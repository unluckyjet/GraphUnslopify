---
id: 59
slug: getting-started-tour
status: done
priority: P1
title: Provide a short verified installation and complete first-figure walkthrough
source_idea: review2026-10-28 item16 minimal install, five-minute tutorial, complete example; latest review prioritizes first-time usability
---

# First complete figure

Build on the existing packaged doctor/demo/CLI rather than a second demo generator.

1. A concise guide gives Python/venv setup for macOS/Linux and Windows, pinned available
installation, a complete generated public example and expected files/results. No account,
npm setup or optional extras are required for the core walkthrough.
2. Walk from a first figure through report/provenance inspection, rerunning saved Python,
a deliberately false claim rejected by default strict policy and recovery. Explain file paths,
unit IDs/mean versus significance, own-data adaptation and existing-demo overwrite protection.
3. Link the short guide from the root/package installation entry points. Preserve graphics and
keep published0.8.0 behavior distinct from newer source-only features.
4. Verify the actual documented flow against a fresh public0.8.0 registry install and a fresh
current source wheel outside the checkout, including actual export/data/script evidence,
strict pass/fail/pass and runtime network blocking. Preserve a durable stdlib-only verifier
and include it in installed-wheel CI. Do not claim measured novice completion time.
5. Run seven gates, lint and relevant packaging checks; push this milestone and verify exact
CI before advancing. Leave other review items explicit.


## Delivery evidence

The short `docs/getting-started.md` supplies platform venv setup, pinned PyPI
installation, the complete generated24-row example, report/artifact explanation,
rerunning Python/provenance, false-claim rejection/recovery, own-data roles and
common first-run corrections. Root/package/installation/homepage entries link it.
Graphics and the core demo generator remain unchanged.

`scripts/check-getting-started.py` executes the actual installed CLI and verifies
sample counts, claims, strict0/2/0, unchanged input bytes/data fingerprint and
PNG/SVG/PDF byte counts/hashes/embedded spec/data/source evidence. It refuses to
reuse a nonempty work folder; that refusal was tested without input mutation.
Installed-wheel smoke invokes it under existing Python/Node network blockers on
all four distribution CI platforms. Its0.8+ guard preserves the legacy0.7 helper
path. CI also lints both verification helpers.

The public registry wheel was downloaded anonymously and matches the published
06371cb20500bd7388b91169a92a3237a87defbdb4f5692e31c2df2b1e195b22 digest.
A genuine fresh public-index0.8.0 install passes the full smoke and walkthrough
with runtime networking blocked; automated walkthrough3.608s after installation.
A fresh current source-wheel agent/PDF/offline smoke and walkthrough also pass
(3.678s). These are automated command times, not measured novice completion times.
Desktop1440x1000 and mobile390x844 homepage link/bounds checks and image review pass.

Seven local gates pass:222 Node/1158 Python, zero local skips/warnings;15 matching
baselines,16 renders,25 recipes and7 composition cases. Ruff67 pass. No emitter,
bundle or published figure changes. Exact general/Figure/Pages CI and live homepage
source/link are checked after push before advancing. Public0.8.0/tag/artifacts
are not replaced by these source-only documentation/verification changes.
