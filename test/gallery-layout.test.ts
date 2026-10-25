import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { translate } from "../src/translate.ts";
import { resolvePlottingPython } from "../scripts/python.ts";

const python = resolvePlottingPython();

test("fitted gallery labels stay below the data with every name, font size and bar value intact", { skip: !python }, () => {
  const spec = JSON.parse(readFileSync(new URL("../examples/specs/10-faceted-benchmarks.json", import.meta.url), "utf8"));
  const dir = mkdtempSync(join(tmpdir(), "gu-gallery-layout-"));
  spec.data.path = fileURLToPath(new URL(`../examples/${spec.data.path}`, import.meta.url));
  spec.output = { ...spec.output, stem: "figure", formats: ["png"], dpi: 100 };
  const translated = translate(spec);
  assert.ok(translated.status === "translated" && translated.ok);
  writeFileSync(join(dir, "figure.py"), translated.code);
  writeFileSync(join(dir, "driver.py"), [
    "import figure as m, numpy as np, pandas as pd",
    "original = m.check",
    "def checked(fig):",
    "    fig.canvas.draw()",
    "    renderer = fig.canvas.get_renderer()",
    "    data = pd.read_csv(m.DATA_PATH)",
    "    axes = [ax for ax in fig.axes if ax.get_visible()]",
    "    assert len(axes) == data['dataset'].nunique()",
    "    for ax, dataset in zip(axes, data['dataset'].unique()):",
    "        labels = [label for label in ax.get_xticklabels() if label.get_visible() and label.get_text()]",
    "        names = [label.get_text() for label in labels]",
    "        assert names == ['baseline', '+augment', '+distill', 'ours'], names",
    "        for label in labels:",
    "            assert label.get_fontsize() == m.RC_PARAMS['xtick.labelsize']",
    "            assert label.get_window_extent(renderer).y1 < ax.bbox.y0, 'tick intrudes into plotted data'",
    "        expected = data[data['dataset'] == dataset].groupby('model')['accuracy'].mean().reindex(names)",
    "        assert np.allclose([bar.get_height() for bar in ax.patches], expected)",
    "    return original(fig)",
    "m.check = checked",
    "raise SystemExit(m.run_cli(['--strict', '--json']))",
  ].join("\n"));
  const report = JSON.parse(execFileSync(python!, ["driver.py"], { cwd: dir, encoding: "utf8", stdio: "pipe" }));
  assert.equal(report.status, "passed");
});
