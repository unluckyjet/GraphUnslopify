# PyPI publication

Status: **0.8.0 published and independently installed from public PyPI** on 2026-10-28.
The [registry](https://pypi.org/project/graphunslopify/0.8.0/) wheel/sdist hashes match
the GitHub release. A fresh registry install passes the full offline-runtime smoke,
agent/PDF workflows and rejection of a false claim without an explicit strict flag.
[Machine-readable publication evidence](releases/0.8.0-publication.json) records exact
source/CI/hash identities. The 0.7.0 tag and artifacts remain unchanged.

## Initial account setup (completed)

These were the initial registration fields; existing-project publishers are managed
under that project's Publishing settings. Sign in at [PyPI's pending publisher page](https://pypi.org/manage/account/publishing/)
and register a GitHub Trusted Publisher with these exact fields:

| Field | Value |
| --- | --- |
| PyPI project name | `graphunslopify` |
| Owner | `unluckyjet` |
| Repository | `GraphUnslopify` |
| Workflow filename | `publish-pypi.yml` |
| Environment | `pypi` |

For TestPyPI, repeat at [its publisher page](https://test.pypi.org/manage/account/publishing/)
with environment `testpypi`. No password/token needs to be shared in chat or added
to this repository. These are separate accounts/publisher configurations.
GitHub environments use the same names; the upload job alone gets OIDC permission.

This follows [PyPI's new-project setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [Trusted Publisher usage](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
A pending publisher does not reserve a package name.

## Verify a candidate without uploading

The [workflow](../.github/workflows/publish-pypi.yml) is manual, runs only from
main and defaults to `publish=false`. Select an already published stable release:

```sh
gh workflow run publish-pypi.yml --ref main -f release_tag=v0.8.0 -f index=testpypi -f publish=false
```

Its verification job resolves the exact release revision, requires the latest
general and Figure CI runs for that revision to succeed, downloads the existing
wheel/sdist/checksum manifest, compares GitHub asset digests/sizes and manifest
hashes, and checks embedded package name/version. Then it runs strict Twine
metadata checks and the real fresh/offline-runtime installation smoke test.
The prepared distributions and `readiness.json` are retained as workflow artifacts.

The local equivalent (GitHub CLI authenticated, Python with Twine installed):

```sh
python scripts/prepare-pypi-release.py --tag v0.8.0 --out-dir /fresh/candidate
python -m twine check --strict /fresh/candidate/dist/*
python scripts/install-smoke.py /fresh/candidate/dist/graphunslopify-0.8.0-py3-none-any.whl --agent
```

The helper refuses nonempty output directories. It never extracts sdist members
into the filesystem or rebuilds/replaces an existing release. These checks bind
the selected release/artifact identities and exercise the wheel; they are not an
independent security audit or proof against a compromised publisher.

## Publish and verify

After account setup, select the intended release and set `publish=true` with
`index=testpypi` first, then `index=pypi`. Only the verified distribution artifact
from that workflow run reaches the upload job. It uses the PyPA publishing action
pinned to a reviewed commit and Trusted Publishing, with no stored PyPI token.

The existing0.7.0 release has its original opt-in strict policy. Publishing that
wheel does **not** put unreleased main changes on PyPI. To distribute the new
strict defaults or subsequent features, create/test a new versioned release
first; preserve0.7.0 and its hashes. Never relabel the old wheel as new behavior.

After an actual upload, verify the public registry's version/files/hashes, then
install `graphunslopify==VERSION` in a fresh environment outside this checkout and
run `graphunslopify doctor` and `graphunslopify demo`. Only then change the public
quickstart to a simple PyPI install and record the actual publication evidence.

For a genuine fresh registry installation rather than a local-wheel install:

```sh
python scripts/install-smoke.py /path/to/verified/graphunslopify-0.8.0-py3-none-any.whl --registry-version 0.8.0 --agent --pdf
```

The wheel supplies reference metadata/license checks; pip installs the pinned
version from the public PyPI index into a new outside-checkout environment.
Network blockers then exercise the installed package, including strict defaults.
Keep negative controls outside folders used by later manifest discovery.
