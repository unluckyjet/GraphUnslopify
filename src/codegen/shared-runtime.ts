import {
  RUNTIME_ABI, RUNTIME_COMPONENTS, RUNTIME_HELPERS, RUNTIME_SOURCE_SHA256,
} from "./runtime-source.ts";

/** Use the actual canonical library code with this program's own globals. */
export function shareRuntime(source: string): string {
  // Advice is actual packaged runtime data, covered by the component hashes.
  for (const name of ["DIAGNOSTIC_ADVICE", "UNKNOWN_DIAGNOSTIC"]) {
    const definition = new RegExp(`^${name} = json\\.loads\\([^\\n]+\\)\\n`, "gm");
    if ([...source.matchAll(definition)].length !== 1) throw new Error(`Missing canonical ${name}`);
    source = source.replace(definition, "");
  }
  for (const [name, helper] of Object.entries(RUNTIME_HELPERS)) {
    const start = source.indexOf(helper);
    if (start < 0 || source.indexOf(helper, start + helper.length) >= 0) {
      throw new Error(`Cannot bind canonical runtime helper ${name}: expected one exact definition`);
    }
    source = source.slice(0, start) + source.slice(start + helper.length);
  }
  const expected = {
    abi: RUNTIME_ABI, source_sha256: RUNTIME_SOURCE_SHA256,
    required: Object.keys(RUNTIME_HELPERS), components: RUNTIME_COMPONENTS,
  };
  const loader = `# This readable entry uses the exact scientific runtime below.
# Download a complete bundle to archive the runtime with the figure.
EXPECTED_RUNTIME = ${JSON.stringify(expected, null, 2)}
try:
    from graphunslopify import figure_runtime as _figure_runtime
except ImportError as _runtime_problem:
    raise RuntimeError("This figure needs its matching GraphUnslopify scientific runtime. "
                       "Install the source version that generated it or use its complete standalone bundle. "
                       + str(_runtime_problem)) from _runtime_problem
if (type(getattr(_figure_runtime, "RUNTIME_ABI", None)) is not int
        or _figure_runtime.RUNTIME_ABI != EXPECTED_RUNTIME["abi"]
        or hashlib.sha256(Path(_figure_runtime.__file__).read_bytes()).hexdigest()
           != EXPECTED_RUNTIME["source_sha256"]):
    raise RuntimeError("GraphUnslopify scientific runtime ABI/source mismatch. "
                       "Install the matching source version or use its complete standalone bundle.")
RUNTIME_BINDING = _figure_runtime.bind(globals(), **EXPECTED_RUNTIME)
`;
  const marker = "\nSTATIC_FINDINGS = ";
  if (!source.includes(marker)) throw new Error("Missing canonical runtime initialization boundary");
  return source.replace(marker, `\n${loader}\nSTATIC_FINDINGS = `)
    .replace(/\n{3,}/g, "\n\n\n");
}
