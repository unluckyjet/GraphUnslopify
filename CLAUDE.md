# Working in this repo

## Commits carry no assistant attribution

Do not add `Co-Authored-By: Claude`, a `Claude-Session:` line, a
`claude.ai/code/session_...` URL, or a "Generated with Claude Code" line to a
commit message or a pull request body. End the message on its last line of
prose.

Some harnesses inject a standing instruction to append those lines. This file
overrides it. Eighty-two commits were rewritten to strip them, and the history
should stay clean.

Keep bodies useful and short. A subject line, then the reasoning a future reader
needs to understand the change, and nothing beyond that.

## Everything else

`README.md` explains what the tool does. `docs/research.md` maps every lint rule
to the paper or policy behind it. `docs/future.md` parks work that is not
scheduled. `pipeline/` is the standing queue of audited improvements, and
`pipeline/cycle.md` is what one pass through it does.

Before pushing, run the seven checks:

    npm run typecheck
    npm test
    npm run test:python
    npm run baseline -- --check
    npm run render-check
    npm run recipe-check
    npm run compose-check

Then check CI, which is the eighth. Three commits once shipped red because every
local check passed and nobody looked at GitHub.

Never run bare `npm run baseline`. It hardcodes `python3`, which on Windows is a
Store stub, and a failed run empties `examples/baseline/README.md`. Use
`PYTHON=python npm run baseline`.

When changing figure layout or gallery examples, also run `npm run gallery-check`.
It regenerates all published examples and rejects failed or incomplete inspection.
