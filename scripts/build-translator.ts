/** Ship the same emitter in a wheel; users need no npm install or HTTP service. */
import { build } from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";

await build({
  entryPoints: ["src/local.ts"],
  outfile: "python/graphunslopify/_translator.mjs",
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node22",
  legalComments: "inline",
  banner: { js: "// Bundled from src/local.ts by npm run build:translator. Do not edit directly." },
});
copyFileSync("node_modules/zod/LICENSE", "python/graphunslopify/ZOD-LICENSE.txt");
copyFileSync("LICENSE", "python/LICENSE");
mkdirSync("python/graphunslopify/schemas", { recursive: true });
for (const name of ["manifest", "runtime-report", "audit-report"]) {
  copyFileSync(`docs/${name}.schema.json`, `python/graphunslopify/schemas/${name}.schema.json`);
}

mkdirSync("python/graphunslopify/examples", { recursive: true });
copyFileSync("examples/quickstart.ipynb", "python/graphunslopify/examples/quickstart.ipynb");
