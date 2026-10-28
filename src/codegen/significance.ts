/** Matched and independent tests share the same declared units as the marks. */
export function emitSignificance(out: string[]): void {
  out.push(...String.raw`

def compare(left, right):
    """Return a p value, or None when the declared test cannot run."""
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    paired = SIGNIFICANCE_DESIGN == "paired"
    if paired:
        if left.shape != right.shape:
            raise ValueError("Paired samples must have equal lengths after matching IDs")
        finite = np.isfinite(left) & np.isfinite(right)
        left, right = left[finite], right[finite]
    else:
        left, right = left[np.isfinite(left)], right[np.isfinite(right)]
    if len(left) < 2 or len(right) < 2:
        return None
    if SIGNIFICANCE_METHOD == "bootstrap":
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        observed = left.mean() - right.mean()
        tolerance = abs(observed) * 100 * np.finfo(float).eps
        extreme = 0
        if paired:
            differences = left - right
            partitions = 2 ** len(differences)
            if partitions <= BOOTSTRAP_DRAWS:
                from itertools import product
                for signs in product((-1, 1), repeat=len(differences)):
                    difference = np.mean(differences * signs)
                    extreme += abs(difference) >= abs(observed) - tolerance
                return float(extreme / partitions)
            for _ in range(BOOTSTRAP_DRAWS):
                difference = np.mean(differences * rng.choice((-1, 1), size=len(differences)))
                extreme += abs(difference) >= abs(observed) - tolerance
        else:
            pooled = np.concatenate([left, right])
            partitions = math.comb(len(pooled), len(left))
            if partitions <= BOOTSTRAP_DRAWS:
                from itertools import combinations
                for indices in combinations(range(len(pooled)), len(left)):
                    mask = np.ones(len(pooled), dtype=bool)
                    mask[list(indices)] = False
                    difference = pooled[list(indices)].mean() - pooled[mask].mean()
                    extreme += abs(difference) >= abs(observed) - tolerance
                return float(extreme / partitions)
            for _ in range(BOOTSTRAP_DRAWS):
                draw = rng.permutation(pooled)
                difference = draw[:len(left)].mean() - draw[len(left):].mean()
                extreme += abs(difference) >= abs(observed) - tolerance
        return float((extreme + 1) / (BOOTSTRAP_DRAWS + 1))
    try:
        from scipy import stats
    except ImportError:
        print("scipy is not installed, so significance markers were skipped")
        return None
    if SIGNIFICANCE_METHOD == "ttest":
        return float(stats.ttest_rel(left, right).pvalue if paired
                     else stats.ttest_ind(left, right, equal_var=False).pvalue)
    if paired:
        raise ValueError("Mann-Whitney requires independent samples; use paired t or sign flips")
    return float(stats.mannwhitneyu(left, right, alternative="two-sided").pvalue)


def adjust_pvalues(values, method):
    """Adjust a panel's family, preserving input order."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("p-values must be finite numbers between zero and one")
    if method not in ("none", "holm", "benjamini_hochberg"):
        raise ValueError(f"unknown correction: {method}")
    if len(values) == 0 or method == "none":
        return values.copy()
    order = np.argsort(values, kind="stable")
    ordered = values[order]
    count = len(values)
    if method == "holm":
        adjusted = np.maximum.accumulate(ordered * np.arange(count, 0, -1))
    else:
        scaled = ordered * count / np.arange(1, count + 1)
        adjusted = np.minimum.accumulate(scaled[::-1])[::-1]
    result = np.empty_like(adjusted)
    result[order] = np.minimum(adjusted, 1.0)
    return result


def comparison_input(frame, left_name, right_name):
    left = frame.loc[frame[X_FIELD] == left_name]
    right = frame.loc[frame[X_FIELD] == right_name]
    evidence = {"design": SIGNIFICANCE_DESIGN, "method": SIGNIFICANCE_METHOD,
                "unit": SIGNIFICANCE_UNIT, "assumptions_verified": False,
                "assumptions": ["Units are independent across subjects/experiments; IDs cannot establish this."]}
    if SIGNIFICANCE_METHOD == "ttest":
        evidence["null_hypothesis"] = "equal population means (paired differences)" if SIGNIFICANCE_DESIGN == "paired" else "equal population means (Welch)"
        evidence["assumptions"].append("Normal differences for paired t, or adequate sampling approximation for Welch; not established by this render.")
    elif SIGNIFICANCE_METHOD == "mannwhitney":
        evidence["null_hypothesis"] = "identical distributions, not median equality without further assumptions"
    else:
        evidence["null_hypothesis"] = "within-pair labels exchangeable" if SIGNIFICANCE_DESIGN == "paired" else "independent samples exchangeable under the null"
        evidence["assumptions"].append("Label exchangeability under the selected null is author-declared, not established by a permutation calculation.")
    if SIGNIFICANCE_DESIGN != "paired":
        a, b = left[Y_FIELD].to_numpy(dtype=float), right[Y_FIELD].to_numpy(dtype=float)
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        evidence["sample_sizes"] = [len(a), len(b)]
        if SIGNIFICANCE_UNIT and SIGNIFICANCE_UNIT in frame:
            shared = len(set(left[SIGNIFICANCE_UNIT].dropna()) & set(right[SIGNIFICANCE_UNIT].dropna()))
            evidence["shared_unit_ids"] = shared
            if shared:
                finding("warning", "possibly_paired_samples", "Independent comparison uses shared unit IDs. Reused labels alone do not prove dependence; if these are the same subjects/experiments, declare paired design and pair_by.")
        else:
            evidence["assumptions"].append("Rows are treated as independent; identify actual experimental units with uncertainty.over when rows repeat units.")
        return a, b, evidence
    if not SIGNIFICANCE_PAIR_BY or SIGNIFICANCE_PAIR_BY != SIGNIFICANCE_UNIT:
        raise ValueError("Paired design requires pair_by equal to uncertainty.over")
    unit = SIGNIFICANCE_PAIR_BY
    if left[unit].duplicated().any() or right[unit].duplicated().any():
        raise ValueError("Paired inputs need one summarized observation per category and unit")
    a, b = left.set_index(unit)[Y_FIELD], right.set_index(unit)[Y_FIELD]
    common = a.index.intersection(b.index, sort=False)
    av, bv = a.reindex(common).to_numpy(dtype=float), b.reindex(common).to_numpy(dtype=float)
    finite = np.isfinite(av) & np.isfinite(bv)
    evidence.update(pair_by=unit, matched_pairs=int(finite.sum()),
                    left_only_units=int(len(a.index.difference(b.index))),
                    right_only_units=int(len(b.index.difference(a.index))),
                    nonfinite_pairs=int((~finite).sum()), sample_sizes=[int(finite.sum())] * 2,
                    population_scope="matched complete cases; bars summarize available units per category")
    if evidence["left_only_units"] or evidence["right_only_units"] or evidence["nonfinite_pairs"]:
        finding("warning", "paired_complete_case_selection", "Paired test excludes unmatched/nonfinite pairs while bars retain available units per category. This changes the comparison population; inspect exclusion counts and show matched units if comparing those displayed means.")
    evidence["assumptions"].append("Matched finite pairs only; incomplete pairs are excluded and may change the target population.")
    return av[finite], bv[finite], evidence


def mark_significance(ax, df, categories, positions):
    source = summary_input(df, Y_FIELD)
    index_of = {name: position for name, position in zip(categories, positions)}
    reach = source[Y_FIELD].max()
    step = abs(reach) * 0.06 if np.isfinite(reach) and reach else 1.0
    level = reach
    comparisons = []
    for left_name, right_name in SIGNIFICANCE_PAIRS:
        a, b, evidence = comparison_input(source, left_name, right_name)
        if SIGNIFICANCE_DESIGN == "paired":
            evidence["missing_pair_ids"] = int(df.loc[df[X_FIELD].isin([left_name, right_name]), SIGNIFICANCE_PAIR_BY].isna().sum())
        if left_name not in index_of or right_name not in index_of:
            significance_result(left_name, right_name, status="untested", reason="category absent from the data", **evidence)
            continue
        p = compare(a, b)
        if p is None or not np.isfinite(p):
            reason = "fewer than two finite observations" if min(len(a), len(b)) < 2 else "test unavailable or undefined"
            print(f"significance: {left_name} vs {right_name} skipped: {reason} (n={len(a)}, {len(b)})")
            significance_result(left_name, right_name, status="untested", reason=reason, **evidence)
            continue
        comparisons.append((left_name, right_name, p, evidence))
    # Unavailable planned tests remain in the family, conservatively assigned p=1.
    # Their actual report status is still untested, making strict verification incomplete.
    family_size = len(SIGNIFICANCE_PAIRS)
    values = [p for _, _, p, _ in comparisons] + [1.0] * (family_size - len(comparisons))
    adjusted = adjust_pvalues(values, SIGNIFICANCE_CORRECTION)[:len(comparisons)]
    for (left_name, right_name, raw_p, evidence), p in zip(comparisons, adjusted):
        significance_result(left_name, right_name, status="tested", raw_p=float(raw_p), adjusted_p=float(p),
                            correction=SIGNIFICANCE_CORRECTION, family_size=family_size,
                            tested_family_size=len(comparisons), alpha=SIGNIFICANCE_ALPHA, **evidence)
        level = level + step
        left_pos, right_pos = index_of[left_name], index_of[right_name]
        coords = [left_pos, left_pos, right_pos, right_pos]
        heights = [level, level + step * 0.3, level + step * 0.3, level]
        horizontal = RUN_REPORT["spec"].get("orientation") == "horizontal"
        ax.plot(heights if horizontal else coords, coords if horizontal else heights, color="#404040", linewidth=0.8)
        mark = "n.s." if p > SIGNIFICANCE_ALPHA else ("***" if p < 0.001 else "**" if p < 0.01 else "*")
        midpoint, height = (left_pos + right_pos) / 2, level + step * 0.35
        ax.text(height if horizontal else midpoint, midpoint if horizontal else height, mark,
                ha="left" if horizontal else "center", va="center" if horizontal else "bottom", fontsize=ANNOTATION_PT)
        adjustment = "no correction" if SIGNIFICANCE_CORRECTION == "none" else f"{SIGNIFICANCE_CORRECTION}-adjusted p = {p:.4g}"
        print(f"  {left_name} vs {right_name}: p = {raw_p:.4g}, {adjustment} ({mark}, {family_size} comparisons)")
`.split("\n"));
}
