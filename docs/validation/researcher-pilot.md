# Researcher pilot: test usefulness on real work

Status: **deferred at the user's request on 2026-10-28; prepared, not conducted**.
The current validation route is [published papers and public datasets](published-papers.md).
There are no external participants, feedback,
human timing results or independent scientific validation yet. This protocol is
ready for a researcher to use on a real project; it does not require uploading
private data. The project-authored [automated comparison](benchmark.md) answers
a narrower question.

## Questions and participants

Can a researcher produce a correct figure, identify a planted problem and review
a later data change more reliably with GraphUnslopify than with their usual
Matplotlib workflow? Which part costs more effort than it saves?

Start with 3–5 volunteers who already make scientific figures, across at least
two research areas. This is a usability pilot, too small to establish population
effects. Record experience with Python/statistics and prior exposure to this
tool. A researcher who did not implement the tool should select and label the
held-out tasks before seeing its findings. Retain negative results.

## One session, approximately 45–60 minutes

1. The participant selects a non-sensitive or public dataset from their work,
   explains what one row means, the measurement unit, independent experimental
   unit and the intended claim. Record the data license/source or keep data local.
2. Use a familiar Matplotlib script and GraphUnslopify on equivalent tasks.
   Alternate which workflow comes first across participants. Offer the same task
   information and setup assistance; record help and installation failures.
3. Produce a descriptive figure. Record time from task start to first **correct**
   export, not merely first PNG. Correctness is judged against a written answer
   key by a reviewer unaware of which tool produced the result where possible.
4. Review variants chosen before the session: an incorrect comparison claim,
   unavailable uncertainty, and an unchanged clean control. Include at least one
   real issue reported by the researcher that was not chosen from tool rules.
   Record correct detections, false alarms, abstentions and missed issues separately.
5. Change the input data and reproduce the figure. Ask the participant to explain
   what changed, where evidence lives and whether the change affects their claim.
6. Ask: What was confusing? Which warning changed your action? Would you use this
   next week on your own work? What prevents that? Save brief attributed-to-ID
   notes rather than invented testimonials.

Use the pinned GitHub wheel in [installation](../installation.md) or record the
exact development commit and environment. Run `graphunslopify doctor` first.
`graphunslopify demo`, `preview`, and `audit examples/paper` provide orientation;
the scored tasks must use the participant's selected project, not only the demo.
Plan one dry run to check the protocol, and label it internal.

## Record and report

Copy [observations.csv](../../benchmarks/research/observations.csv) into a local
study directory. One row per task/workflow/participant. Keep names, contact
details and private datasets outside the repository. Participants should know
what will be recorded and agree before sharing quotes or artifacts publicly.

Report the actual participant count, domains, recruitment method, tool revisions,
task selection, counterbalancing, raw anonymized task outcomes (when shareable),
missing sessions and reasons for exclusion. Publish per-participant observations
before aggregate summaries. Report unsuccessful installs and unfinished tasks;
do not drop them from the denominator. Tool startup seconds are not researcher
time saved. Satisfaction is not correctness. “Would use” is not observed adoption.

Follow up only with participants who agree, to ask whether they actually used it
on another project. This document does not contact or enroll anyone.

## Independent scientific benchmark

The external reviewer should freeze a held-out collection of real figure/data/
claim bundles, record author/source/license and independent numeric answers,
then test both workflows without tuning rules to the held-out answers. Include
clean controls, realistic alternative assertion-based workflows and unsupported
cases. Report detection precision/recall on labelled **in-scope** errors, abstention
coverage, false alarms, numerical deviations and environment/reproduction failures.
Disclose who selected/labelled/evaluated each case and any developer involvement.
Do not call an author-selected synthetic suite independent evidence.
