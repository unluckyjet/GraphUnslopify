import { RUNTIME_HELPERS } from "./codegen/runtime-source.ts";
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
    RUNTIME_HELPERS._aligned,
    "",
    "",
    RUNTIME_HELPERS._interval_overlap,
    "",
    "",
    RUNTIME_HELPERS.overlap_phrase,
    "",
    "",
    RUNTIME_HELPERS.check_claim,
    "",
    "",
    RUNTIME_HELPERS.verify_claims,
    "",
  );
}
