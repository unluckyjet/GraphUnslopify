# Paper review panel evidence

Collect three separate evidence views for the figures in an initialized paper.

```sh
graphunslopify project-review-panel ./paper --journal-profile nature-final-graphs
```

- **Readability** shows the saved native measurements or PDF page inspection.
- **Statistical claims** shows recorded check outcomes, uncertainty and evidence
  gaps. Numerical claims for PDF-only figures remain untested.
- **Journal formatting** checks the recorded PNG, SVG, PDF and other figure
  exports against a selected dated profile. It uses the current registered PDF
  only when its hash still matches the inspection. The report records each
  format's results, unavailable evidence and remaining manual checks.

Repeat `--figure` with the keys from `project-review` to select particular
figures. Use `--expected-revision` to bind the collection to a current saved
review. Omit `--journal-profile` when a venue has yet to be selected. The report
will show where a profile is required. Figure execution and any model review
are separate actions.
