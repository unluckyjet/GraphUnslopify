import { translate } from "../src/translate.ts";
import { explainSpecIssue } from "../src/diagnostics.ts";

/**
 * Same translation over plain HTTP, for curl and for clients that do not speak
 * MCP. Accepts a bare spec, or one wrapped as {"spec": ...}.
 */
export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { status: "invalid_spec", issues: [explainSpecIssue("(root)", "body is not valid JSON")] },
      { status: 400 },
    );
  }

  const spec = body !== null && typeof body === "object" && "spec" in body ? body.spec : body;

  const result = translate(spec);
  const status = result.status === "invalid_spec" ? 400 : result.ok ? 200 : 422;
  return Response.json(result, { status });
}
