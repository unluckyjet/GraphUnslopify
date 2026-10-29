---
id: 70
slug: public-contribution-infrastructure
status: ready
priority: P2
title: Provide public contribution, issue, security and roadmap infrastructure
source_idea: review2026-10-28 item20 contribution guidelines issue templates security policy public roadmap
---

# Provide public contribution, issue, security and roadmap infrastructure

1. Publish a discoverable contribution guide with reproducible environment setup,
   the seven required gates, generated-resource/gallery requirements and clear
   scientific evidence expectations. Preserve source/release distinctions.
2. Provide usable GitHub issue forms for ordinary bugs, scientific-result problems
   and concrete workflow requests, plus a concise pull-request template. Ask for
   actual version/reproduction/reference evidence without collecting private data.
3. Publish a truthful security policy and enable/verify the repository's private
   vulnerability channel. Separate scientific bugs from security boundary failures;
   do not invent support guarantees, a bounty or a response SLA.
4. Publish a public roadmap linked from README, preserving the actual open PDF,
   scientific benchmarking and user-deferred research-trial work. Reconcile69 only
   after exact045dab3 main40826638872 all9/Figure40826638949 green (verified).
5. Validate local links/form structure and required setup/check commands; run all
   seven gates before this separate commit/push. Verify exact pushed main/Figure
   CI before advancing. Do not mark the full20-item goal complete from this work.

## Implementation and local evidence,2026-10-28

- Root contribution/security/public-roadmap documents and README links; three
  GitHub forms (bug/scientific result/workflow), issue chooser/security link and
  a PR template. Existing52 README graphics unchanged. A repository `.venv/`
  created by the setup guide is ignored and `git check-ignore` confirms it.
- All three forms parse as YAML and have unique valid IDs, supported field types,
  required labels/validation values and complete chooser links.123 initial
  relative document links validate; guide extra names match pyproject and all
  required/conditional check commands match the repository. Final links rechecked.
- GitHub private-vulnerability-reporting API was false before configuration;
  authorized PUT succeeded and independent GET returns enabled:true. No report
  was submitted. Policy does not invent support/SLA/bounty promises. Community
  profile before push lacks contribution/issue/PR metadata; served-file recognition
  and new exact CI are checked after push.
- Seven local gates pass:225 Node/1338 Python (zero skips/one retained upstream
  SQLAlchemy warning),15 baselines/16 renders/25 recipes/7 compositions. No runtime,
  emitter or figure changes; no distribution behavior attributed to public0.8.0.
- Prior69 exact045dab3 main40826638872 all9/Figure40826638949 was green before70.
  The remaining PDF inspection, broader independent benchmarks and user-deferred
  trials remain explicit. Exact pushed main/Figure CI is required before advancing.
