# External reference data

The nine univariate inputs and certified reference values come from the
[NIST Statistical Reference Datasets, SRD140](https://doi.org/10.18434/T43G6C).
[sources.json](sources.json) pins the publisher URLs, exact original-byte hashes,
observation counts, reference strings and publisher difficulty/source labels.

Original data files and derived observation CSVs are fetched/prepared locally;
they are not distributed in this repository or its CI artifacts. The repository's
MIT license covers its code, not third-party input data. Consult the
[publisher's SRD/data policy](https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications)
for source-data rights and attribution. Do not describe this corpus as MIT or
assume every NIST database is public domain.

NIST's “observed” category includes PiDigits, a mathematical digit sequence, and
Lottery, a general-interest dataset; it is not a count of five laboratory studies.
Michelso, Lew and Mavro include scientific measurement datasets. Four NumAcc
datasets are generated numerical-stability challenges. See each publisher file
for its original reference and measurement meaning.

The certified mean/sample-SD answers are external to GraphUnslopify. Running our
benchmark on them is still a project-run evaluation, not a NIST endorsement,
independent researcher study or evidence of human development time saved.
