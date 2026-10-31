import { RUNTIME_HELPERS } from "./runtime-source.ts";
/** Runtime context is captured by the generated program, never by translation. */
export function emitEnvironment(out: string[], excel = false): void {
  const optional = ["graphunslopify", "plotly", "scipy", "pypdf"];
  if (excel) optional.push("python-calamine");
  out.push("", `RUNTIME_OPTIONAL_PACKAGES = ${JSON.stringify(optional)}`,
    "", RUNTIME_HELPERS.capture_environment, "");
}
