---
id: 18
slug: package-local-translator
status: done
priority: P1
title: Licensed local Python distribution without a hosted translator dependency
source_idea: accepted distribution and offline workflow roadmap
---

# Package the canonical local translator

Declare MIT licensing and ship a Python wheel/source archive containing a bundled copy of the
same TypeScript emitter, Zod's notice and the project license. Python packaging installs the Node
runtime too; no separate npm/server setup is needed. Local translation is the default, with HTTP
an explicit per-call/CLI/environment choice. Keep one generator and expose local conversion,
schema, validation, suggestions, recipes, scoring and bounded repair through a JSON transport.

Add doctor/demo/translate/render CLI commands and a short onboarding path above the gallery.
Document offline wheelhouse installation, optional dependencies, data-path resolution and strict
exit policy. Fix Python 3.10's typing.Self incompatibility, preserve supplied profile filenames,
allow an API override for suggestions, resolve nested input/output paths without mutating the
builder, and preserve custom translator overrides. Profile-based choices remain guesses.

## Verification

214 Node tests (zero skipped), 109 Python tests and all eight local gates pass: 15 source baselines,
16 render cases, 25 recipes, seven compositions, strict gallery 15/15. New tests compare bundled
output/findings exactly with source and exercise the actual local SDK/CLI and structured failures.

Built both source archive and wheel. A fresh macOS/Python 3.12 virtual environment outside the
checkout installed the wheel, used packaged Node 24.19, and generated/strictly verified the demo.
After installation, Python and Node network calls were blocked and both blockers were tested.
Known 24-row/unit counts and endpoint mean 56.5, SDK/profile paths, separate output directory,
spaces in paths, immutable author specs and PNG/SVG/PDF provenance passed. Wheel contents include
all required bundle/license resources. CI adds clean-install jobs for Linux Python 3.10/3.12,
macOS 3.12 and Windows 3.12, plus a stale-bundle guard; results are checked after pushing.

Tagged releases and versioned release documentation remain later roadmap requirements. No claim
of registry publication is made.
