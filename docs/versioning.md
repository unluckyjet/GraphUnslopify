# Versions and release artifacts

Run `graphunslopify version` to identify the installed Python release, then select the matching
Git tag's documentation. `graphunslopify doctor` also checks the bundled compiler/package version.
The package, emitter and Node metadata share one release version; tests enforce agreement.

For 0.8.0:

- [Release assets and hashes](https://github.com/unluckyjet/GraphUnslopify/releases/tag/v0.8.0)
- [Versioned quickstart](https://github.com/unluckyjet/GraphUnslopify/blob/v0.8.0/README.md)
- [Versioned documentation](https://github.com/unluckyjet/GraphUnslopify/tree/v0.8.0/docs)
- [Core numerical reference matrix](https://github.com/unluckyjet/GraphUnslopify/blob/v0.8.0/docs/scientific-validation.md)

The wheel contains the Python runtime, local translator, schemas, notebook, editor assets and
project/Zod licenses. Python packaging installs the platform Node runtime dependency. The source
distribution can build the same package. `SHA256SUMS` covers both downloadable distributions.
The GitHub tag also provides the full repository/source and documentation archives.

Installation can download dependencies. Local translation and rendering need no hosted service
after installation; optional HTTP transport remains explicit. See [installation](installation.md)
for extras, platform requirements, strict policy and offline wheelhouse preparation.

Main-branch source/docs can change after a release. Use the matching tag for reproducible
instructions and a full reviewed commit to freeze a reusable action reference. Old figure
provenance remains readable; do not relabel historical figures as a new tool version.

0.8.0 adds strict defaults, source-free PDF review packets and public-paper data examples
to the locally packaged21-kind workflow. Version0.7.0 retains its older opt-in strict default.
[Release notes](releases/0.8.0.md) summarize capabilities. References establish tested computation,
not experimental design, independence, appropriate inference or exhaustive optional combinations.
