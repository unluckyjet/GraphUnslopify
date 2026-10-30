---
id: 82
slug: model-backed-drafts
status: done
priority: P1
title: Ground real model-backed figure drafts in selected data and explicit review
source_idea: User visual-workspace advice natural-language figure generation
---

# 82 — Model-backed figure drafts

Prerequisite9d79aa8 exact main41038823610 all9/Figure41038823929 passed.
81's complete role/identity/export acceptance is in docs/workspace/direct-editing-acceptance.md.

The user can request a figure in ordinary language, inspect a real model's
proposed canonical specification and disclosed assumptions, then explicitly apply
it and run deterministic scientific verification. Keep offline manual controls,
JSON, existing source consent, undo, ownership and strict evidence intact.

## Required behavior

- Use an actual configured model provider; keyword rules, canned responses and
  browser mockups do not substitute for model-backed drafts. Provider availability
  and external configuration requirements remain explicit. No connection assumed.
- Ground each request in the actual selected immutable dataset and current schema.
  Show which provider and data/profile information will be sent; require explicit
  review/consent before transmission. Keep credentials out of reports/vault/logs.
  Raw observations are not silently sent as metadata.
- Proposed fields/units/design/uncertainty/claims must be grounded in known columns
  and author-declared context. Disclose unresolved assumptions/questions. Do not
  fabricate observations, confidence, successful checks or experimental independence.
- Parse/validate untrusted model output with the canonical compiler; bind local
  data/output ownership on the server. Do not execute model code or accept arbitrary
  file paths/client-supplied dataset profiles.
- A draft is unapplied/unverified. Review source choices/assumptions and explicitly
  Apply; rerender with original strict checks. Preserve unrelated current intent
  where appropriate and retain current shared undo. Data/spec/provider changes and
  late requests cannot revive stale proposals, evidence or exports.
- Fail/provider-unavailable/invalid-output states remain honest and recoverable;
  offline manual authoring continues to work. Add no new chart kinds.

## Acceptance evidence

- Actual model request/response against public synthetic selected data with recorded
  provider/model/protocol and sanitized source binding; no secrets or private data.
  HTTP doubles are negative/contract evidence only, not proof of a real model call.
- Actual source/fresh-installed browser propose/review/apply/strict rerender/undo,
  disclosure/consent, unavailable/invalid response and stale-selection refusal.
- Original data/numeric claims/independence boundaries and deterministic validation
  remain enforceable; no inferred source role certifies sampling design.
- All seven gates, relevant runtime/offline/installed controls and exact main/Figure
  CI per coherent checkpoint. Keep external dependencies explicit rather than
  calling an unmeasured model connection complete.
- Update canonical Obsidian notes and preserve the full83–89 roadmap. This milestone
  does not establish a measured authoring-speed or researcher-adoption advantage.

## Backend checkpoint82a

`drafts.py` implements opt-in real-provider transport, server-prepared data/schema
grounding, exact request disclosure, one-attempt consent, ownership/scientific
context guards and canonical untrusted-patch validation. See
[backend boundary and verification](../../docs/workspace/model-drafts.md).
Backend82a was verified at90022f2 exact main41047929069 all9/Figure41047929222.
The82b editor integration below implements the remaining browser path; its production6275b8c exact main41056713354 all9/Figure41056713193 passed.
The closing acceptance below adds original byte/numeric evidence.

82a local evidence: all seven gates234 Node/1550 Python,39 focused controls on
actual3.10.22/3.12.14, actual source/fresh-installed model inference followed by
strict PNG/SVG/PDF exports, and five preserved exploratory source failures.
Exact commit CI remains required after pushing this checkpoint.

## Editor integration checkpoint82b

Session-only provider configuration, exact selected-data disclosure, explicit
transmission consent, reviewed unverified proposals, shared undo and forced
strict apply work in the actual editor. Backend owner/provider/client/revision
fences and browser epochs discard late results. Unknown/invalid outputs remain
quarantined; no model or template runs automatically.

All seven local gates234 Node/1565 Python pass on stable product hashes.54 related
contracts pass on actual3.10.22 and in the3.12.14 full suite. Source and fresh
offline installed Chrome pass65 workflows/21 required-kind controls, including12
model cases. Separate actual local-model browser positives pass from both source
and installation with strict PNG/SVG/PDF, original numeric boundaries and undo.
Negative cases remain controlled; a real exploratory title mismatch is preserved.
[Evidence](../../docs/workspace/model-drafts.md).

Production6275b8c exact main41056713354 all9/Figure41056713193 passed. Live OpenAI account inference, human usability and productivity are
untested; do not equate passing canonical validation with satisfying a prompt.

## Closing acceptance

[Requirement audit](../../docs/workspace/model-draft-acceptance.md) verifies the
full scoped82 behavior. Source/fresh-installed66 workflows and actual local-model
13-case runs additionally retain the applied runtime report, compare original
source digest/row counts, explicitly download unchanged CSV bytes and replay
actual x/y marks `[1,2,3,4]` / `[51,54,56,59]` from the exported strict script.
All seven gates reran234/1565 on stable source hashes, with no production changes
from6275b8c. The final closing checkpoint's own exact CI is checked before any83
implementation.83–89 remain pending in the full roadmap.
