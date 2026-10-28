# Homepage and hosted translation

The product homepage is https://unluckyjet.github.io/GraphUnslopify/.
Its source is `public/index.html`, published by `.github/workflows/pages.yml`
from the main branch using GitHub Pages Actions. Repository settings must have
Pages enabled with build type `workflow`. The deployment environment is
`github-pages`; its URL and deployment status are visible in GitHub Actions.

This is a static overview with versioned installation instructions, the existing
figure gallery and evidence links. It does not execute uploaded data. The reused
gallery image is pinned to the existing v0.7.0 source, avoiding duplicated assets.

The existing Vercel service remains at `https://json-translator-three.vercel.app`
for `/api/health`, `/api/convert` and `/api/mcp`. GitHub Pages does not host those
server functions. A future Vercel alias/custom-domain change requires access to
that Vercel project; changing the repository homepage does not rename it.

Local review: `python -m http.server 8767 --directory public`, then open
`http://localhost:8767`. Check desktop/mobile layouts and image/link loading.
The root README preserves its complete graphics gallery.
