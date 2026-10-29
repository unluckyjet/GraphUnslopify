import { emitPython } from "./codegen/index.ts";
import { FigureSpec } from "./schema.ts";
import { hasErrors, verify, type Finding } from "./verify.ts";
import { explainSpecIssue, type DiagnosticAdvice } from "./diagnostics.ts";

/**
 * The one entry point. Parse, check, emit.
 *
 * Both the MCP tool and the HTTP endpoint call `translate` and neither holds
 * logic of its own. Data never reaches this function. The generated script
 * reads the user's own file, so results stay on the machine that produced them.
 */

export type SpecIssue = { path: string; message: string } & DiagnosticAdvice;

export type TranslateResult =
  | {
      status: "translated";
      ok: boolean;
      findings: Finding[];
      filename: string;
      code: string;
    }
  | {
      status: "invalid_spec";
      issues: SpecIssue[];
    };

/** Clients disagree on whether a JSON argument arrives parsed or as a string. */
function coerce(input: unknown): unknown {
  if (typeof input !== "string") return input;
  try {
    return JSON.parse(input);
  } catch {
    return input;
  }
}

export function translate(input: unknown): TranslateResult {
  const parsed = FigureSpec.safeParse(coerce(input));

  if (!parsed.success) {
    return {
      status: "invalid_spec",
      issues: parsed.error.issues.map((issue) => explainSpecIssue(
        issue.path.length > 0 ? issue.path.join(".") : "(root)", issue.message,
      )),
    };
  }

  const spec = parsed.data;
  const findings = verify(spec);

  return {
    status: "translated",
    ok: !hasErrors(findings),
    findings,
    filename: `${spec.output.stem}.py`,
    code: emitPython(spec),
  };
}
