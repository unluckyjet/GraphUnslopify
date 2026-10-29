/** Reviewed advice shared by the compiler, standalone programs and Python package. */
export type DiagnosticAdvice = { consequence: string; correction: string };
export const DIAGNOSTIC_ADVICE: Record<string, DiagnosticAdvice> = Object.create(null);

function family(codes: string[], consequence: string, correction: string): void {
  for (const code of codes) {
    if (DIAGNOSTIC_ADVICE[code]) throw Error(`Duplicate diagnostic advice: ${code}`);
    DIAGNOSTIC_ADVICE[code] = { consequence, correction };
  }
}

family(["invalid_spec"],
  "No runnable figure was translated, so the requested data and claims have not been verified.",
  "Correct the indicated field using the expected type, range or required value in the problem message. Check JSON syntax and the canonical schema, then translate and audit again.");
family(["axis_limits_inverted"],
  "The requested view has no increasing lower-to-upper range and cannot represent the intended coordinates.",
  "Set the lower limit below the upper limit in the stated units. If an inverted display is scientifically intended, use an explicitly supported representation rather than reversed limits.");
family(["log_scale_nonpositive_limit", "reference_line_off_log_axis", "log_bar_baseline"],
  "A logarithmic axis cannot display zero or negative coordinates, so the requested baseline or reference cannot be represented faithfully.",
  "Check the quantity and units. Use a justified linear scale for nonpositive values, or a positive log-domain view/reference when appropriate; never replace zero with an invented small value.");
family(["log_domain_hidden"],
  "Finite observations disappear on a log axis, so the visible sample can differ from the data used to support a conclusion.",
  "Inspect the reported nonpositive observations and analysis plan. Use a justified linear scale that represents them, or explicitly justify and disclose any scientifically appropriate selection; do not silently drop them.");
family(["data_outside_view", "bar_mark_clipped", "bar_interval_clipped"],
  "The visible figure omits plotted coordinates or true uncertainty/value extents and can overstate the apparent evidence.",
  "Inspect which marks or interval endpoints are outside the view. Widen the limits to show the complete intended evidence, or explicitly justify/disclose the restricted view; do not truncate intervals to fit.");
family(["truncated_bar_axis", "axis_break_on_length_marks"],
  "Cutting a length-bearing mark breaks the relationship between its visible length and the measured magnitude.",
  "Show complete bar/extents with a justified zero baseline, or choose a position-based representation if the scientific comparison needs a restricted range. Do not keep a cut that changes the apparent ratios.");
family(["axis_exaggeration"],
  "A narrow numeric view can make small changes look large relative to the quantity's magnitude; the warning alone does not prove the chosen view is inappropriate.",
  "Review the absolute range, units and scientific question. Show a broader context or disclose the zoom and its reason so readers can judge the effect size.");
family(["temporal_y_axis", "temporal_x_on_categories", "temporal_log_axis", "temporal_axis_limits"],
  "The requested time encoding is not implemented for this axis/kind and could be read as an unrelated numeric or categorical comparison.",
  "Confirm whether values are dates or category names. Use supported linear temporal x for a time series, otherwise keep explicit categorical/numeric meaning; select dates with a documented data filter instead of numeric temporal limits.");
family(["unknown_field"],
  "A field reference does not match the declared columns, so the tool cannot establish that it is drawing the intended quantity or experimental unit.",
  "Check the actual local data headers and data.columns, then correct the indicated field. Review any suggested spelling against the source; a nearby name is not evidence that it is the intended variable.");
family(["unsupported_identity_roles", "duplicate_identity_order"],
  "Conflicting roles or repeated identifiers can change category membership, duplicate displayed observations or coerce names into measurements.",
  "Use distinct identifier and numeric measurement columns, preserve lexical IDs such as leading-zero names, and list each series/category once. Recheck the intended ordering and grouping.");
family(["emphasis_without_group", "annotation_series_without_group", "direct_labels_without_group", "legend_without_group", "series_order_without_group"],
  "A series-specific instruction has no grouping variable, so it cannot distinguish the intended entities and may have no visible effect.",
  "Declare the real group column when there are multiple series. If the figure intentionally has one series, remove the inapplicable series-specific instruction rather than inventing a grouping variable.");
family(["emphasis_series_unknown", "annotation_series_unknown", "annotation_without_series"],
  "The highlighted or annotated entity is not unambiguously identified and could direct attention to the wrong observations.",
  "Check the actual series names and series_order, then name the intended series explicitly. Do not choose a different entity just because it is available.");
family(["annotation_unavailable", "qq_annotation_unavailable"],
  "The requested annotation could not be resolved to the displayed evidence, so its text or arrow cannot support the claimed location.",
  "Read the unresolved-target reason and inspect the displayed summaries/quantiles and panel. Correct the intended target or remove the unsupported annotation; do not place it at an arbitrary point.");
family(["annotation_snapped_to_observation"],
  "The displayed anchor differs from the requested coordinate and may imply more positional precision than the observed data provide.",
  "Review the requested and resolved coordinates in the annotation report and the actual figure. Use an observed target when appropriate, or state the intended coordinate explicitly with a supported annotation.");
family(["crossover_needs_two_series"],
  "A crossover cannot be evaluated with only one represented series.",
  "Declare the genuinely comparable series and their grouping, or replace the crossover annotation with a statement supported by the available observations.");
family(["direct_labels_on_categories"],
  "End-of-line placement is not meaningful for an unordered categorical layout and can detach names from the intended marks.",
  "Use a legend for categorical comparisons. Keep direct line labels only when the ordered/continuous endpoint has the intended meaning.");
family(["too_many_series", "too_many_bars_per_group"],
  "At the intended manuscript width, readers may not reliably separate the entities or associate their values with the correct names.",
  "Consider shared-scale facets or a more focused comparison. Preserve and disclose the population/series selection; do not silently remove inconvenient results to reduce clutter.");
family(["too_many_stack_segments", "stacked_costs_a_baseline"],
  "Most stacked segments do not share a baseline, so differences between those components are hard to compare accurately.",
  "If component comparison is the question, consider grouped bars or separate panels with a shared baseline. Keep a stack when the part-to-whole question is intended and make the components identifiable.");
family(["shading_is_the_weakest_channel"],
  "A colour/shading impression may not communicate the exact cell values needed for a quantitative comparison.",
  "Show readable cell annotations or provide a numeric table, and inspect foreground/background contrast. Keep the colour scale and numeric values consistent.");
family(["line_implies_continuity"],
  "Connecting unordered categories suggests meaningful intermediate values or continuity that the specification alone cannot establish.",
  "Confirm whether x represents time or an ordered continuum. Retain a line when justified; otherwise choose a discrete representation. This requires scientific judgment and is not an automatic line-to-bar conversion.");
family(["low_dpi_raster"],
  "Raster marks and text may lose detail when the figure is printed or resized to its publication width.",
  "Use an appropriate vector export or increase output.dpi for the required manuscript width and venue, then inspect the written file at its final size. Raising DPI does not fix clipped or misleading content.");
family(["transform_needs_baseline", "transform_needs_group", "baseline_series_unknown"],
  "A relative/difference transform lacks an identified comparison series and cannot establish the intended reference quantity.",
  "Declare the actual group field and preselected baseline, using a name present in the data/order. Confirm the baseline's scientific meaning before recomputing the transform.");
family(["series_from_columns_conflicts_with_group", "invalid_series_reshape"],
  "An ambiguous wide-to-long reshape can overwrite fields or change which measurements belong to each entity.",
  "Use distinct retained/source/output column names, set y to the new value field, and let the reshape create its grouping field. Check the resulting identity/value mapping against the source table.");
family(["uncertainty_without_aggregation", "uncertainty_aggregation_unsupported"],
  "The requested interval is not defined for the selected summary in this implementation, so the apparent uncertainty could describe a different quantity.",
  "Choose the estimator and experimental unit first. Use a supported mean/median summary with its matching interval, or provide a separately justified analysis for sums/counts instead of attaching an unrelated interval.");
family(["median_sem_unsupported"],
  "The standard error of a mean does not quantify uncertainty of a median.",
  "Keep the intended estimator: use a justified bootstrap interval for median uncertainty or IQR for observational spread, or use mean with SEM if a mean is the scientific target.");
family(["iqr_around_a_mean", "std_around_a_median"],
  "The chosen center and spread describe different summary conventions and can mislead readers about what the interval represents.",
  "Decide whether the center is a mean or median and whether the interval is spread or estimation uncertainty. Use mean with SD/mean-appropriate uncertainty, or median with IQR/bootstrap uncertainty; review any proposed estimator change.");
family(["replicate_matches_grouping_key"],
  "An experimental-unit identifier reused as a point/group key cannot vary within that point and can produce a false replicate count.",
  "Use the actual independent seed/subject/experiment ID in uncertainty.over and separate it from x, group and facet keys. Technical repeated rows do not create additional independent units.");
family(["band_on_categories"],
  "A continuous shaded region between unordered categories implies unsupported intermediate uncertainty.",
  "Use interval bars for the categorical points. Retain a band only for a genuinely ordered/continuous domain supported by the analysis.");
family(["facet_by_the_group", "facet_keys_identical", "facet_repeat_conflict", "unsupported_repeat"],
  "The requested panel arrangement cannot represent the distinct cohorts or metrics under the supported layout contract.",
  "Use distinct supported facet keys or repeated numeric metrics, and keep the requested cohorts/units explicit. Split the figure into separate supported panels when the combined layout is unavailable.");
family(["too_many_panels_per_row"],
  "Narrow panels can make labels and effect differences unreadable at the manuscript's actual column width.",
  "Use fewer panels per row or a justified wider output size, then inspect the exported figure at its final width. Keep shared scales and cohort labels clear.");
family(["reference_line_outside_limits"],
  "The reference is not visible, so readers cannot make the intended comparison against it.",
  "Confirm the reference's units and meaning, then expand the appropriate limits or explicitly justify the restricted view. Do not move a scientific threshold merely to fit the plot.");
family(["unaggregated_bar"],
  "Repeated values at the same category draw on top of one another and may look like a summary that was never computed.",
  "Inspect whether rows are repeats. If a summary is intended, declare its estimator and independent unit; otherwise use a representation that shows the individual observations.");
family(["stacked_without_group", "stacked_uncertainty_unsupported", "stacking_signed_values"],
  "The requested segments, signed differences or uncertainty cannot be represented faithfully by the supported stack.",
  "Use a real grouping field for valid part-to-whole stacks. For signed effects or individual uncertainty, choose supported grouped/position-based marks instead of silently dropping intervals or negative components.");
family(["significance_without_uncertainty", "claims_without_uncertainty"],
  "A test or summary-level claim can look decisive while the reader cannot see observational spread or estimation uncertainty.",
  "Declare the real experimental unit and show estimator-appropriate uncertainty alongside the comparison. Check effect sizes and assumptions; an ID or a small p-value does not establish independence.");
family(["significance_design_invalid", "possibly_paired_samples"],
  "The comparison's dependence structure may not match the experiment, which can invalidate its standard error or test interpretation. Reused labels alone do not prove dependence.",
  "Confirm the study design from the experiment records. For the same matched units use supported paired design and pair_by matching uncertainty.over; for genuinely independent units use the independent contract. More complex clustering needs a suitable external analysis.");
family(["significance_estimator_mismatch"],
  "The test and displayed center target different quantities; a rank comparison is not automatically a test of median equality.",
  "Choose the scientific estimand before choosing the test. Use the supported mean-difference or distribution/rank contract with matching displayed summaries/uncertainty, and describe the tested quantity accurately.");
family(["significance_group_unsupported"],
  "Pooling separately displayed cohorts or stack segments would test a different population from the plotted comparison.",
  "Use supported per-cohort facets or an explicitly justified single-cohort selection, then compare categories within that population. Disclose the selection and do not silently pool groups.");
family(["significance_pair_invalid", "uncorrected_multiple_comparisons"],
  "Duplicate/self comparisons or an uncorrected family can distort the number of hypotheses and increase false discoveries.",
  "Specify distinct planned comparisons once, then use the supported Holm or appropriate Benjamini-Hochberg family correction. Do not select the family after seeing which comparisons pass.");
family(["paired_complete_case_selection", "paired_units_excluded"],
  "Matched complete cases can differ from all available observations, so the test/effect may describe a selected population rather than every displayed value.",
  "Inspect unmatched/nonfinite counts and justify the analysis population. Show the matched cohort consistently or disclose its difference from the displayed summaries; do not hide excluded units or assume they are missing at random.");
family(["paired_technical_repeats_averaged"],
  "Several rows for one unit/condition contribute one unit mean, not several independent observations.",
  "Confirm that averaging technical repeats matches the protocol and inspect the reported row/unit counts. Keep the real independent unit IDs rather than relabelling repeats to inflate n.");
family(["paired_interval_unavailable", "uncertainty_unavailable"],
  "The available independent observations do not establish the requested uncertainty; an absent interval is not zero uncertainty.",
  "Review unit IDs, exclusions and sample counts. Collect additional independent observations when scientifically possible, or clearly report the interval as unavailable/use a justified supported point-only analysis. Do not invent repeats or zero-width intervals.");
family(["pair_is_the_condition", "paired_difference_group_ignored", "unsupported_paired_semantics"],
  "The requested pairing or extra grouping does not identify the supported within-unit condition difference and could silently change the compared observations.",
  "Use distinct condition, numeric measurement and real unit-ID fields. Keep pairing explicit and use supported facets/separate analyses for other cohorts; do not reuse a condition name as the unit identifier.");
family(["sort_overrides_category_order"],
  "The requested ordering has no effect under the selected sort, so readers may see a different ranking or comparison sequence.",
  "Choose one intended ordering rule and inspect the actual displayed categories. Remove the conflicting sort or explicit order rather than assuming both apply.");
family(["trendline_on_log_axis"],
  "A straight fit in linear coordinates can suggest a different relationship when displayed on transformed axes.",
  "Choose the fitting domain from the scientific model, label any transform, and use a supported fit that matches that domain. Do not pick axes solely to make the relationship look linear.");
family(["dual_axis_in_use", "dual_axis_with_group"],
  "Independently chosen scales can create an apparent alignment/correlation and make it unclear which quantity belongs to which axis.",
  "Prefer separate clearly labelled panels. If a supported dual axis is scientifically necessary, state the units and justification and inspect both scales; do not tune them to manufacture agreement.");
family(["smoothing_raw_repeats"],
  "Smoothing across repeated rows can mix experimental repeats with the x trajectory and obscure their actual variation.",
  "Define the intended within-point summary and independent unit first, then apply justified smoothing to that trajectory. Preserve the raw-repeat/exclusion evidence.");
family(["diverging_counts"],
  "A zero-centered diverging colour scale suggests signed deviations even though counts are nonnegative.",
  "Use the supported sequential count scale, or explicitly compute and label a scientifically meaningful signed quantity before choosing a diverging representation.");
family(["animation_with_vector_output"],
  "Static vector files do not contain the animation's changing evidence, so a still cannot establish that every frame is correct.",
  "Review the actual animation and its frame/time mapping separately. Use and label static exports as stills; ensure the required motion export was produced rather than assuming the PDF/SVG animates.");
family(["trace_on_categories", "grow_outside_bars"],
  "The selected animation motion implies an axis/mark meaning that this categorical or non-bar representation does not provide.",
  "Use a supported reveal/draw style for the actual mark/domain, or a bar grow style when bars are intended. Review frame ordering and avoid introducing unsupported continuity.");
family(["interactive_not_supported", "unsupported_layer_coordinates", "incomplete_layer"],
  "The requested overlay or interactive output cannot reproduce the stated coordinate/feature semantics and may omit or misplace scientific evidence.",
  "Read the named unsupported features. Use supported coordinates and complete band/rule parameters, or export a supported static/separate view; do not silently omit the scientific layer.");
family(["invalid_axis_break", "x_break_unsupported", "axis_break_composition_unsupported"],
  "The requested cut cannot be implemented with the stated axis/range/layout, so the resulting geometry would not express the intended view.",
  "Use a supported y-axis cut with from below to, without conflicting limits or composition. For unsupported arrangements, choose a complete unbroken view or separate clearly labelled panels.");
family(["table_composition_unsupported", "unsupported_table_axes"],
  "Table row identities/cell values do not have the plotted-axis semantics assumed by these options; unsupported composition can misstate what each cell means.",
  "Use supported table summaries, cell formatting and static/Markdown/LaTeX output. Remove incompatible plotted-axis/composition options or use a separate plot when those visual semantics are required.");
family(["unsupported_grouping", "comparison_without_group"],
  "The requested entity comparison is not represented by this kind/group combination; silently ignoring or pooling the groups would change its scientific meaning.",
  "Choose a kind that draws the intended groups or supported facets. Supply the real grouping column for a series comparison, and remove grouping only when pooling is explicitly intended.");
family(["unsupported_survival_semantics", "unsupported_calibration_semantics", "unsupported_qq_semantics", "unsupported_scaling_semantics"],
  "This estimator has derived quantities and field roles that cannot be replaced by the requested raw-axis transform/overlay or ambiguous identifiers.",
  "Keep the estimator's original input domain and distinct supported field roles. Use its documented derived survival/calibration/quantile/scaling quantities for claims and annotations; justify any external preprocessing separately.");
family(["claim_without_group", "claim_without_reference", "claim_series_unknown", "claim_compares_a_series_to_itself", "claims_need_series"],
  "The hypothesis does not identify a supported distinct subject/reference comparison, so the tool cannot check the intended scientific statement.",
  "Use actual supported series/group names and the comparator chosen by the study question, or remove an inapplicable claim. Do not change the hypothesis merely to obtain a passing verdict.");
family(["claim_without_tolerance"],
  "A closeness/plateau claim without a tolerance has no defined scientific threshold.",
  "Specify a domain-justified tolerance in the quantity's units before interpreting the result. Do not pick a tolerance after seeing the data just to make the claim hold.");
family(["nonfinite_measurements", "missing_plot_keys", "missing_unit_ids"],
  "Some rows cannot contribute to the intended quantity/group/unit calculation, so the analysed observations may differ from the source sample.",
  "Inspect the affected fields and reported exclusion counts. Correct genuine data errors or document a justified missing-data policy, then rerun; do not fill missing values with zero or silently discard rows to improve a result.");
family(["unlisted_series_retained"],
  "The displayed population includes observed series absent from the requested order; dropping them silently would hide results.",
  "Review the actual series and intended analysis population. Extend the explicit order, or declare and disclose a scientifically justified selection rather than treating ordering as a filter.");
family(["unequal_sample_sizes"],
  "Plotted estimates have different amounts of independent evidence and may have different uncertainty or selection patterns.",
  "Inspect per-point unit counts and missingness, show appropriate uncertainty/count context and justify comparisons. Do not duplicate or selectively remove observations merely to balance n.");
family(["empty_panel"],
  "A requested panel contains no analysable observations and cannot support its intended estimate or claim.",
  "Check facet keys, filters, missingness and the intended population. Correct a genuine mapping error or explicitly disclose the unavailable panel; do not invent observations.");
family(["density_unavailable", "qq_constant_sample"],
  "The observed sample cannot establish the requested distribution shape; a fabricated curve would imply evidence that is absent.",
  "Inspect sample size, finite values and measurement resolution. Show the actual observations or a justified summary when shape is unavailable; do not add artificial noise or copy rows to force a density/distribution fit.");
family(["scaling_interval_unavailable", "scaling_residual_variance_unavailable"],
  "The requested fit uncertainty/residual variance is not established by this sample or installed capability; an unavailable estimate is not zero error.",
  "Read the recorded reason and check distinct positive scales, independent evidence and residual degrees of freedom. Install the matching statistics extra if that is the missing capability, or explicitly report a justified point-only fit without inventing uncertainty.");
family(["output_skipped"],
  "A requested output is missing, so a completed still or another format does not establish the entire requested export contract.",
  "Read the format-specific reason, provide the matching optional renderer/encoder when required, and rerun. Alternatively make an explicit supported export request; do not present a skipped format as produced.");
family(["inspection_unavailable", "inspection_outdated"],
  "Final readability/colour/data-view checks were not completed by the required inspection implementation, so successful rendering is incomplete verification.",
  "Install the graphunslopify inspector matching the generator, using the same checkout for unreleased source. Regenerate and rerun with the intended final export width; disabling inspection does not make these checks pass.");
family(["export_size_unavailable"],
  "The physical written size is unknown, so the tool cannot establish text legibility in the final manuscript context.",
  "Supply intact supported static exports, correct any reported file/size problem and rerun inspection at the intended manuscript width. Do not substitute an assumed canvas size for missing written-file evidence.");
family(["text_too_small", "text_near_minimum"],
  "Text may be unreadable after the actual export is placed at the intended publication width.",
  "Inspect the named text in the written file at its final width. Use a suitable output size/venue layout, fewer crowded panels or shorter accurate labels; rerun final-width inspection rather than only zooming the screen preview.");
family(["labels_collide", "tick_labels_collide", "legend_covers_data"],
  "Overlapping labels or legend coverage can hide values and associate text with the wrong evidence.",
  "Inspect the named objects, then move the legend to a supported outside position, simplify/rotate appropriate labels or use a suitable wider/panel layout. Retain scientific context and recheck the actual export.");
family(["overplotting"],
  "Dense marker ink may hide observations or make frequency hard to judge; this is a density heuristic, not a measured count of overlapping pairs.",
  "Inspect the actual points and intended distribution. Consider justified transparency, smaller markers or supported summaries/facets while preserving sample counts and avoiding undisclosed selection.");
family(["series_indistinguishable", "greyscale_collision"],
  "Readers may not reliably identify the series under colour-vision differences or greyscale printing.",
  "Use distinct supported marker/line/hatch channels and a colour-safe presentation, then inspect the exported legend and marks in the relevant viewing conditions. Colour alone is insufficient.");
family(["series_colour_drifts_between_panels"],
  "The same named entity changes appearance across panels and can be mistaken for a different entity.",
  "Use one stable series identity/order and a shared palette lock for the intended entities. Check sparse panels and complete legend mappings rather than assigning colours independently per panel.");
family(["cell_text_low_contrast", "cell_text_contrast_untested"],
  "A cell's numeric annotation is unreadable or its foreground/background contrast was not established, weakening quantitative interpretation.",
  "Inspect the actual cell text/background pair and transparency in the final export. Use the supported automatic contrast choice on an assessable background, correct unavailable colours, then rerun; do not assume a value threshold proves contrast.");
family(["runtime_error"],
  "Execution did not complete its verification contract; partially written files are not a complete accepted result.",
  "Read the actual exception and execution log, check source paths/columns/types and required capabilities, correct the underlying cause and rerun the strict audit. Keep failed evidence; suppressing checks is not a repair.");
family(["claim_failed"],
  "The evaluated data/summary do not support this stated relationship. A readable figure does not turn a failed hypothesis into evidence.",
  "Review the predeclared claim, comparison population, mappings and uncertainty against the actual results. Correct genuine input/analysis errors or report the unsupported claim; do not reverse comparators or change thresholds merely to pass.");
family(["repeated_x_values"],
  "Multiple observations occupy the same series/x coordinate, so overlapping raw marks can hide multiplicity or suggest a single trajectory through repeated measurements.",
  "Check whether raw observations or a unit-level summary answer the question. Show individual observations explicitly, or use a justified summary and uncertainty over the correct independent units; do not average unrelated subjects or time points merely to remove overlap.");
family(["palette_lock_unavailable"],
  "The requested shared appearance lock could not be used, so a series may change visual identity between figures even when the individual plot renders.",
  "Use a matching GraphUnslopify installation with its lockfile module available, verify the requested local palette-lock path and rerun the paper figures. Review actual cross-figure series appearances before relying on consistent colours or marks.");
family(["check_untested"],
  "The required scientific or verification check was not established; absence of a failed verdict is not evidence that it passed.",
  "Read the recorded reason, provide the required valid data/capability and justified assumptions, then rerun. If the check remains unavailable, report it as untested rather than manufacturing evidence or disabling it to obtain a pass.");

export const UNKNOWN_DIAGNOSTIC: DiagnosticAdvice = {
  consequence: "This unrecognized finding has no reviewed catalog entry; its scientific consequences have not been classified.",
  correction: "Preserve the code and original message, consult that producer's documentation and review the source evidence before rerunning. No automatic scientific correction is inferred.",
};

export function diagnosticAdvice(code: string): DiagnosticAdvice {
  return DIAGNOSTIC_ADVICE[code] ?? UNKNOWN_DIAGNOSTIC;
}

export function explainFinding<T extends { code: string; message: string }>(finding: T): T & DiagnosticAdvice {
  return { ...finding, ...diagnosticAdvice(finding.code) };
}

export function explainSpecIssue(path: string, message: string): { path: string; message: string } & DiagnosticAdvice {
  return { path, message, ...diagnosticAdvice("invalid_spec"),
    correction: `Correct ${path} using the expected value in the problem message. ${diagnosticAdvice("invalid_spec").correction}` };
}
