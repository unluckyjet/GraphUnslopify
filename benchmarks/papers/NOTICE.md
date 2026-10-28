# Public research datasets

These files have their own data licenses; the repository's MIT code license
does not replace them. No private data or volunteer observations are included.
Exact download locations, retrieval date, SHA-256 hashes and published count
references are in [sources.json](sources.json).

- **Palmer penguins:** CC0-1.0, as stated by the
  [palmerpenguins authors](https://allisonhorst.github.io/palmerpenguins/).
  Data collected by Kristen Gorman and Palmer Station Antarctica LTER. Package:
  Horst AM, Hill AP, Gorman KB (2020),
  [doi:10.5281/zenodo.3960218](https://doi.org/10.5281/zenodo.3960218).
  Related paper: Gorman KB, Williams TD, Fraser WR (2014),
  [doi:10.1371/journal.pone.0090081](https://doi.org/10.1371/journal.pone.0090081).
  This is the simplified package CSV pinned to an immutable upstream commit.
  The authors' website also describes LTER data-use and collaboration requests.
- **Iris:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), stated by
  the [UCI repository](https://archive.ics.uci.edu/dataset/53/iris).
  Fisher R (1936), Iris [Dataset],
  [doi:10.24432/C56C76](https://doi.org/10.24432/C56C76).
  Related paper: Fisher RA (1936), The use of multiple measurements in taxonomic
  problems, Annals of Eugenics 7:179–188,
  [doi:10.1111/j.1469-1809.1936.tb02137.x](https://doi.org/10.1111/j.1469-1809.1936.tb02137.x).
  `sources/bezdekIris.data` and `sources/iris.data` are original UCI archive
  members. The former includes the documented row35/38 corrections and is used
  in the examples. The latter is retained to make their differences inspectable.
  Generated headered/long CSV views add column names and reshape the corrected
  source; measurement values/species are unchanged. No endorsement is implied.
