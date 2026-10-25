import { z } from "zod";

/**
 * What the figure is supposed to show, stated so the data can be asked.
 *
 * The integrity literature keeps describing the same failure. A caption asserts
 * a gain while the axis is truncated, or says "consistently outperforms" over a
 * chart where it does not. Neither is visible to a pixel checker, because the
 * checker cannot read the manuscript, and neither is visible to a spec checker,
 * because the spec does not carry the claim.
 *
 * So the spec carries the claim, and the generated script tests it against the
 * data before the figure is written. A claim that fails is an error before
 * submission rather than a comment from reviewer two.
 */

export const CLAIM_KINDS = [
  "beats_everywhere",
  "beats_on_average",
  "beats_at_end",
  "gap_widens",
  "gap_narrows",
  "monotone_increasing",
  "monotone_decreasing",
  "converges",
  "no_worse_than",
  "within_tolerance",
] as const;

export const ClaimSpec = z.object({
  kind: z.enum(CLAIM_KINDS).describe("The shape of the assertion the figure is making."),
  subject: z.string().min(1).describe("The series the claim is about."),
  reference: z
    .string()
    .min(1)
    .optional()
    .describe("The series it is compared against. Required by every comparative claim."),
  tolerance: z
    .number()
    .min(0)
    .optional()
    .describe("Allowed slack in y units, for no_worse_than and within_tolerance."),
  text: z
    .string()
    .min(1)
    .optional()
    .describe("The sentence the caption will make, recorded alongside the verdict."),
});
export type ClaimSpec = z.infer<typeof ClaimSpec>;

export const COMPARATIVE: ReadonlySet<string> = new Set([
  "beats_everywhere",
  "beats_on_average",
  "beats_at_end",
  "gap_widens",
  "gap_narrows",
  "converges",
  "no_worse_than",
  "within_tolerance",
]);

export const NEEDS_TOLERANCE: ReadonlySet<string> = new Set(["within_tolerance"]);

/** Plain English for each kind, used in the printed verdict. */
export const CLAIM_WORDING: Record<(typeof CLAIM_KINDS)[number], string> = {
  beats_everywhere: "is above {reference} at every x",
  beats_on_average: "has a higher mean than {reference}",
  beats_at_end: "is above {reference} at the largest x",
  gap_widens: "pulls further ahead of {reference} as x grows",
  gap_narrows: "closes on {reference} as x grows",
  monotone_increasing: "never decreases as x grows",
  monotone_decreasing: "never increases as x grows",
  converges: "settles to within tolerance of {reference}",
  no_worse_than: "is never more than the tolerance below {reference}",
  within_tolerance: "stays within tolerance of {reference}",
};

/**
 * The Python that tests each claim.
 *
 * These run on the summarised frame, so a claim about a mean over seeds is
 * tested against that mean rather than against the raw draws.
 */
export function emitClaimTests(claims: ClaimSpec[], out: string[]): void {
  // Always emitted. main() calls verify_claims unconditionally, and both
  // functions short-circuit on an empty CLAIMS list, so a figure with no claims
  // costs a function definition rather than a branch at every call site.
  void claims;

  out.push(
    "",
    "def _aligned(frame, subject, reference):",
    '    """Require complete, finite x coverage for the named series."""',
    "    if GROUP is None or Y_FIELD not in frame:",
    "        return None",
    "    columns = [subject] if reference is None else [subject, reference]",
    "    selected = frame[frame[GROUP].isin(columns)]",
    "    if selected.empty or selected[X_FIELD].isna().any() or selected.duplicated([X_FIELD, GROUP]).any():",
    "        return None",
    "    pivot = selected.pivot_table(index=X_FIELD, columns=GROUP, values=Y_FIELD, aggfunc=\"mean\", dropna=False, observed=True)",
    "    if any(column not in pivot.columns for column in columns):",
    "        return None",
    "    pair = pivot[columns].sort_index()",
    "    if not len(pair) or not np.isfinite(pair.to_numpy(dtype=float)).all():",
    "        return None",
    "    return pair",
    "",
    "",
    "def _interval_overlap(frame, subject, reference):",
    '    """How many shared x values have overlapping intervals, or None.',
    "",
    "    None when there is nothing to measure: no reference, no grouping, or no",
    "    uncertainty in the spec, in which case _low was never written.",
    '    """',
    '    if reference is None or GROUP is None or "_low" not in frame:',
    "        return None",
    '    lows = frame.pivot_table(index=X_FIELD, columns=GROUP, values="_low", aggfunc="mean")',
    '    highs = frame.pivot_table(index=X_FIELD, columns=GROUP, values="_high", aggfunc="mean")',
    "    for column in (subject, reference):",
    "        if column not in lows.columns or column not in highs.columns:",
    "            return None",
    "    shared = lows.index.intersection(highs.index).sort_values()",
    "    bounds = [",
    "        lows.loc[shared, subject].to_numpy(dtype=float),",
    "        highs.loc[shared, subject].to_numpy(dtype=float),",
    "        lows.loc[shared, reference].to_numpy(dtype=float),",
    "        highs.loc[shared, reference].to_numpy(dtype=float),",
    "    ]",
    "    usable = np.all([np.isfinite(edge) for edge in bounds], axis=0)",
    "    if not usable.any():",
    "        return None",
    "    mine_low, mine_high, their_low, their_high = (edge[usable] for edge in bounds)",
    "    touching = (mine_low <= their_high) & (their_low <= mine_high)",
    "    return int(np.sum(touching)), int(usable.sum())",
    "",
    "",
    "def overlap_phrase(measured):",
    "    # Counts, not a p-value. Non-overlapping intervals imply a difference;",
    "    # overlapping ones do not imply its absence, and Cumming's mapping from",
    "    # overlap to significance is conditioned on n. Report what was measured.",
    "    if measured is None or measured[0] == 0:",
    "        return None",
    "    return f\"the intervals overlap at {measured[0]} of {measured[1]} x values\"",
    "",
    "",
    "def check_claim(frame, claim):",
    '    """Return (holds, detail). None means the claim could not be tested."""',
    '    subject, reference = claim["subject"], claim.get("reference")',
    '    tolerance = claim.get("tolerance") or 0.0',
    "    pair = _aligned(frame, subject, reference)",
    "    if pair is None:",
    '        return None, "named series are missing, have incomplete x coverage, duplicate x values, or non-finite measurements"',
    "",
    "    mine = pair[subject].to_numpy(dtype=float)",
    "    theirs = pair[reference].to_numpy(dtype=float) if reference else None",
    '    kind = claim["kind"]',
    '    if kind in ("gap_widens", "gap_narrows", "monotone_increasing", "monotone_decreasing", "converges") and len(mine) < 2:',
    '        return None, "at least two x values are required for a trend claim"',
    "",
    '    if kind == "beats_everywhere":',
    "        losses = int(np.sum(mine <= theirs))",
    "        return losses == 0, f\"{losses} of {len(mine)} x values are not above {reference}\"",
    "",
    '    if kind == "beats_on_average":',
    "        gap = float(mine.mean() - theirs.mean())",
    '        return gap > 0, f"mean difference is {gap:+.4g}"',
    "",
    '    if kind == "beats_at_end":',
    "        gap = float(mine[-1] - theirs[-1])",
    '        return gap > 0, f"difference at the largest x is {gap:+.4g}"',
    "",
    '    if kind in ("gap_widens", "gap_narrows"):',
    "        gap = mine - theirs",
    "        half = max(len(gap) // 2, 1)",
    "        early, late = float(gap[:half].mean()), float(gap[half:].mean())",
    "        change = late - early",
    '        widening = kind == "gap_widens"',
    "        holds = change > 0 if widening else change < 0",
    '        return holds, f"gap moves from {early:+.4g} to {late:+.4g}, a change of {change:+.4g}"',
    "",
    '    if kind in ("monotone_increasing", "monotone_decreasing"):',
    "        steps = np.diff(mine)",
    '        rising = kind == "monotone_increasing"',
    "        breaks = int(np.sum(steps < -tolerance if rising else steps > tolerance))",
    '        return breaks == 0, f"{breaks} of {len(steps)} steps go the wrong way"',
    "",
    '    if kind == "converges":',
    "        tail = max(len(mine) // 5, 1)",
    "        spread = float(np.abs(mine - theirs)[-tail:].max())",
    '        return spread <= tolerance, f"largest gap over the final fifth is {spread:.4g}"',
    "",
    '    if kind == "no_worse_than":',
    "        deficit = float(np.max(theirs - mine))",
    '        return deficit <= tolerance, f"largest shortfall against {reference} is {deficit:.4g}"',
    "",
    '    if kind == "within_tolerance":',
    "        spread = float(np.max(np.abs(mine - theirs)))",
    '        return spread <= tolerance, f"largest absolute difference is {spread:.4g}"',
    "",
    '    return None, f"no test implemented for {kind}"',
    "",
    "",
    "def verify_claims(frame):",
    '    """Test every claim. Returns True when none of them failed."""',
    "    if not CLAIMS:",
    "        return True",
    '    print("claims:")',
    "    ok = True",
    "    for claim in CLAIMS:",
    "        holds, detail = check_claim(frame, claim)",
    '        wording = claim["wording"].replace("{reference}", str(claim.get("reference")))',
    '        sentence = f"{claim[\'subject\']} {wording}"',
    "        if holds is None:",
    '            print(f"  UNTESTED  {sentence} ({detail})")',
    "            continue",
    "        if holds:",
    '            print(f"  HOLDS     {sentence} ({detail})")',
    '            overlap = overlap_phrase(_interval_overlap(frame, claim["subject"], claim.get("reference")))',
    "            if overlap is not None:",
    '                print(f"            but {overlap}, so the spread does not separate them")',
    "        else:",
    "            ok = False",
    '            print(f"  FAILS     {sentence} ({detail})")',
    '            print(f"            the figure does not support this. Do not write it in the caption.")',
    "    return ok",
    "",
  );
}
