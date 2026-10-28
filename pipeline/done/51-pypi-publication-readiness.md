---
id: 51
slug: pypi-publication-readiness
status: done
priority: P1
title: Prepare verified release uploads through PyPI Trusted Publishing
source_idea: user 2026-10-28 adoption review, follow-up item6
---

# Publication readiness, not registry publication

The manual publish-pypi.yml workflow verifies an existing stable GitHub release
on main and defaults to no upload. It requires latest successful exact-tag-revision
general/Figure CI, GitHub asset digests/sizes and SHA256SUMS, embedded wheel/sdist
name/version, strict Twine checks and a fresh installed-wheel smoke with agent.
Only those verified distributions reach the separate optional upload job. OIDC
permission belongs only to that job; PyPA action is pinned to a reviewed commit.

GitHub pypi/testpypi environments are created. Exact PyPI pending-publisher fields
and a verification-only command are documented. No PyPI account configuration or
upload is fabricated. Its public endpoint returned404 at review; name reservation
is not guaranteed. Existing GitHub wheel remains the public installer.

Measured locally on real v0.7.0 release7ffa107: release CI and all three asset
hashes match, Twine wheel/sdist pass, fresh install/doctor/demo/audits/agent and
external-network blocking pass. Three negative controls reject altered bytes,
version mismatch even with consistent hashes, and duplicate checksum records.

The workflow publishes selected existing assets, not moving-main source. It
explicitly preserves0.7.0 and its legacy opt-in strict policy. A future release
must include newer defaults/features before attributing them to PyPI installs.
After account setup, actual upload and separate fresh registry install still
need to be observed. Required seven local gates and exact-commit general/Figure
CI plus a real verification-only workflow dispatch are checked before advancing.
