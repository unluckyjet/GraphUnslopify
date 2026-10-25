# Literal text and figure disclosure

Captions, descriptions, table headings and category names are plain text in generated LaTeX.
Characters with TeX meanings (`\ { } $ & # % _ ^ ~`) are escaped once, so a caption such as
`Model_A scores 50% & ...` remains text. The figure spec and embedded provenance retain the original
strings; only the LaTeX representation is escaped. Newlines/tabs become spaces in this representation.
A string containing `\input{...}` is literal text rather than a command to load another file.

Set `output.latex: true` to write a figure block. Tables always write a `booktabs` tabular alongside
Markdown and the rendered image. Numeric interval text and intended bold highlighting are retained.
Use an ordinary output filename such as `figure_1`; TeX file/path syntax is separate from text.
These text fields do not offer raw TeX execution or caption math markup. Author custom math in the
surrounding manuscript when needed. Unicode font coverage still depends on the document's engine
and fonts; escaping does not supply missing glyphs or tagged-PDF structure.

A minimal non-ACM document can include a figure block with:

```tex
\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{booktabs} % for generated tables
\newcommand{\Description}[1]{\par\noindent #1}
\begin{document}
\input{figure_1.tex}
\end{document}
```

ACM templates provide `\Description` themselves; follow the manuscript template's accessibility
instructions rather than redefining its command. The simple article fallback above visibly prints
the description and is used for compilation checks, not as an accessibility tagging implementation.
The escape commands follow the [LaTeX kernel's text symbol definitions](https://github.com/latex3/latex2e/blob/develop/base/ltoutenc.dtx).

The generated methods disclosure identifies the tool and spec hash, says the plotting code was
generated, and states that the tool does not establish the origin of the supplied data. It does not
certify that observations are real, human-collected or free of generated/synthetic content. Data
fingerprints support change detection, not an origin claim. The public demo explicitly uses
synthetic data.

## Evidence

`python -m pytest python/tests/test_text_exports.py -q` exercises actual emitted Python, actual
LaTeX sidecars, unchanged original author strings/inputs, table interval highlighting and disclosure.
With `pdflatex` and `booktabs` installed, it compiles a document with all ten special characters and
extracts the PDF text to verify both labels and the known mean/range `4.00 [2.00, 6.00]`. The original
unescaped code fails real compilation with a runaway caption argument. Render CI requires the
compiler, saves its source/PDF/log evidence, and fails if this proof cannot run. Other Python jobs
still exercise the export text contracts when no TeX distribution is installed.
