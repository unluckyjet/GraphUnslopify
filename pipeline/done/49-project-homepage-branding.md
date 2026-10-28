---
id: 49
slug: project-homepage-branding
status: done
priority: P2
title: Correct repository identity and publish an accurate branded homepage
source_idea: user 2026-10-28 adoption review, follow-up items13/14
---

# Identity and homepage

Replace the stale three-kind/twelve-check landing page with the actual local
Python, figure/evidence, project-audit and agent workflows. Preserve the existing
gallery image, provide a version-correct runnable installation and explicit
published0.7.0/development strict-policy distinction. Link measured validation
without claiming external participants or independent scientific superiority.

Publish `public/` using GitHub Pages Actions under the GraphUnslopify repository
name. Update GitHub's description and homepage metadata after the separate push,
and verify the public site/metadata and exact-push CI before advancing. The
existing Vercel backend is healthy and remains linked as an API; no Vercel alias
or account access is invented. Deployment instructions are in docs/homepage.md.

Required acceptance: desktop/mobile visual review, actual image and documentation
links, seven local checks, clean diff, and passing general/Figure/homepage CI.
