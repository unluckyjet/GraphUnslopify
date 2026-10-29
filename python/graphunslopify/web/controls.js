// Schema-backed controls edit only their own paths in the authored specification.
const words = (name) => name.replaceAll("_", " ");
const get = (value, path) => path.reduce((item, key) => item?.[key], value);
const claimNames = {
  beats_everywhere: "Above reference at every x",
  beats_on_average: "Higher mean than reference",
  beats_at_end: "Above reference at the last x",
  gap_widens: "Gap from reference grows",
  gap_narrows: "Gap from reference shrinks",
  monotone_increasing: "Never decreases as x grows",
  monotone_decreasing: "Never increases as x grows",
  converges: "Settles within tolerance of reference",
  no_worse_than: "No more than tolerance below reference",
  within_tolerance: "Within tolerance of reference",
};
const names = {
  marker: "Show markers",
  sort_x: "Sort x values",
  trendline: "Trend line",
  baseline_zero: "Start bars at zero",
  stacked: "Stack parts of a whole",
  show_points: "Show observations",
  show_box: "Show quartiles",
  notch: "Notched boxes",
  complementary: "Show upper-tail probability",
  null_value: "No-effect reference value",
  pair: "Paired observation ID",
  baseline: "Baseline condition",
  outcome: "Observed 0/1 outcome field",
  event: "Observed event indicator field",
  bins: "Probability bins",
  distribution: "Reference distribution",
  interval: "Fit interval",
  normalize: "Matrix normalization",
  value: "Cell value / count field",
  annotate_cells: "Show cell values",
  start: "Starting total",
  category_order: "Category order",
  columns: "Panel columns",
  value_label: "Cell-value label / unit",
  diverging: "Center colours at zero",
  precision: "Decimal places",
  highlight: "Highlight cells",
  higher_is_better: "Higher values are better",
  orientation: "Bar direction",
  value_labels: "Show value labels",
};

function put(spec, path, value) {
  let node = spec;
  for (const key of path.slice(0, -1)) {
    if (node[key] === undefined) node[key] = {};
    if (!node[key] || typeof node[key] !== "object")
      throw Error(
        `Correct ${path.join(".")} in Advanced JSON before editing its controls.`,
      );
    node = node[key];
  }
  if (value === undefined) delete node[path.at(-1)];
  else node[path.at(-1)] = value;
}

export function createControls(root, { read, change, edit, error }) {
  let schema,
    flushTimer,
    openStates = new Map(),
    columns = [],
    signature = "",
    bindings = [],
    current;
  const el = (tag, text, parent) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent?.append(node);
    return node;
  };
  const section = (title, open = false) => {
    const details = el("details", undefined, root);
    details.open = openStates.get(title) ?? open;
    el("summary", title, details);
    const grid = el("div", undefined, details);
    grid.className = "setting-grid";
    return grid;
  };
  function field(
    parent,
    path,
    node,
    label,
    required = false,
    column = false,
    config = {},
  ) {
    if (!node) return;
    const wrap = el("label", undefined, parent);
    el("span", label, wrap);
    const id = "control-" + path.join("-");
    const choices =
      node.enum || (node.type === "boolean" ? [true, false] : null);
    const display = (value) => {
      if (typeof value === "boolean") return value ? "Yes" : "No";
      if (path[0] === "claims" && path.at(-1) === "kind")
        return claimNames[value] || words(value);
      if (path.join(".") === "uncertainty.kind")
        return (
          {
            ci: "Confidence interval",
            sem: "Standard error of the mean",
            std: "Standard deviation",
            iqr: "Interquartile range",
            range: "Observed range",
          }[value] || words(value)
        );
      return words(String(value));
    };
    const tuple = Array.isArray(node.items);
    const list = node.type === "array" && node.items?.type === "string";
    const input = el(
      choices || column
        ? "select"
        : list || config.multiline
          ? "textarea"
          : "input",
      undefined,
      wrap,
    );
    input.id = id;
    input.setAttribute("aria-label", label);
    if (choices || column) {
      input.add(
        new Option(
          config.empty ||
            (node.default !== undefined
              ? `Default: ${display(node.default)}`
              : required
                ? "Choose…"
                : "Not set"),
          "",
        ),
      );
      for (const value of choices || columns)
        input.add(new Option(display(value), String(value)));
    } else if (node.type === "number" || node.type === "integer") {
      input.type = "number";
      input.step = node.type === "integer" ? "1" : "any";
      if (node.minimum !== undefined) input.min = node.minimum;
      if (node.maximum !== undefined) input.max = node.maximum;
    } else if (!list && !config.multiline) input.type = "text";
    if (list || config.multiline) input.rows = 3;
    if (config.multiline || config.wide) wrap.classList.add("wide");
    if (node.default !== undefined && !(choices || column))
      input.placeholder = `Default: ${node.default}`;
    if (node.minLength !== undefined) input.minLength = node.minLength;
    input.required = required && node.default === undefined;
    const help = el(
      "small",
      config.help ||
        (tuple
          ? "Lower and upper bounds, separated by a comma. Clear for automatic limits."
          : list
            ? "One value per line, in display order."
            : node.description || ""),
      wrap,
    );
    help.id = id + "-help";
    input.setAttribute("aria-describedby", help.id);
    const binding = {
      input,
      path,
      dirty: false,
      node,
      label,
      config,
      parse() {
        const value = input.value;
        if (input.validity.badInput)
          throw Error(`${label}: finish entering a valid number.`);
        if (value === "") {
          if (input.required) throw Error(`${label}: choose or enter a value.`);
          return undefined;
        }
        if (!input.checkValidity())
          throw Error(`${label}: ${input.validationMessage}`);
        if (node.type === "boolean") return value === "true";
        if (node.type === "number" || node.type === "integer") {
          const number = Number(value);
          if (!Number.isFinite(number))
            throw Error(`${label}: enter a finite number.`);
          return number;
        }
        if (tuple) {
          const parts = value.split(",").map((v) => v.trim());
          if (
            parts.length !== 2 ||
            parts.some((v) => !v || !Number.isFinite(Number(v)))
          )
            throw Error(
              `${label}: enter two finite bounds, for example 0, 10.`,
            );
          return parts.map(Number);
        }
        if (list) return value.split(/\r?\n/).filter((v) => v.length > 0);
        return value;
      },
      sync(spec) {
        if (binding.dirty) return;
        const value = get(spec, path);
        const display =
          value === undefined
            ? ""
            : Array.isArray(value)
              ? value.join(tuple ? ", " : "\n")
              : String(value);
        if (
          column &&
          display &&
          ![...input.options].some((x) => x.value === display)
        )
          input.add(new Option(display, display));
        if (input.value !== display) input.value = display;
        input.disabled = Boolean(config.disabled?.(spec));
      },
    };
    input.addEventListener("input", () => {
      binding.dirty = true;
      edit();
      clearTimeout(flushTimer);
      flushTimer = setTimeout(flush, 500);
    });
    input.addEventListener("change", () => {
      binding.dirty = true;
      edit();
      flush();
    });
    bindings.push(binding);
  }
  function flush() {
    clearTimeout(flushTimer);
    const pending = bindings.filter((b) => b.dirty);
    if (!pending.length) return true;
    try {
      const spec = structuredClone(read());
      const values = pending.map((b) => {
        try {
          const v = b.parse();
          b.input.removeAttribute("aria-invalid");
          return v;
        } catch (problem) {
          b.input.setAttribute("aria-invalid", "true");
          b.input.closest("details").open = true;
          throw problem;
        }
      });
      for (let i = 0; i < pending.length; i++) {
        const binding = pending[i];
        if (binding.config.uncertainty && values[i] === undefined)
          delete spec.uncertainty;
        else put(spec, binding.path, values[i]);
      }
      pending.forEach((b) => {
        b.dirty = false;
      });
      error("");
      change(spec);
      return true;
    } catch (problem) {
      error(problem.message);
      return false;
    }
  }
  function build(spec) {
    openStates = new Map(
      [...root.querySelectorAll(":scope > details")].map((node) => [
        node.firstElementChild.textContent,
        node.open,
      ]),
    );
    root.replaceChildren();
    bindings = [];
    const props = current.properties;
    const labels = section("Labels and units", true);
    field(labels, ["title"], props.title, "Figure title", false, false, {
      wide: true,
    });
    for (const axis of ["x", "y"]) {
      const shape = props[axis].properties;
      for (const key of ["label", "unit"])
        field(
          labels,
          [axis, key],
          shape[key],
          `${axis.toUpperCase()} ${key === "percent" ? "proportion as percent" : key}`,
          key === "label",
        );
    }
    field(labels, ["caption"], props.caption, "Figure caption", false, false, {
      multiline: true,
    });
    const axes = section("Axis scales and limits");
    for (const axis of ["x", "y"]) {
      const shape = props[axis].properties;
      for (const key of ["scale", "limits", "percent"])
        field(
          axes,
          [axis, key],
          shape[key],
          `${axis.toUpperCase()} ${key === "percent" ? "proportion as percent" : key}`,
        );
      if (axis === "x" && ["line", "scatter"].includes(spec.kind))
        field(axes, [axis, "temporal"], shape.temporal, "X values are dates");
    }
    if (props.aggregation || props.uncertainty) {
      const summary = section("Summaries and uncertainty");
      field(summary, ["aggregation"], props.aggregation, "Summary statistic");
      if (props.uncertainty) {
        const u = props.uncertainty.properties;
        field(
          summary,
          ["uncertainty", "kind"],
          u.kind,
          "Uncertainty meaning",
          current.required.includes("uncertainty"),
          false,
          {
            uncertainty: true,
            empty: current.required.includes("uncertainty")
              ? "Choose interval…"
              : "No uncertainty",
            help: "CI: confidence interval; SEM: standard error of the mean; STD: standard deviation; IQR: quartiles. Review whether this suits the chosen summary.",
          },
        );
        for (const [key, label] of [
          ["over", "Independent observation ID"],
          ["level", "CI confidence level"],
          ["display", "Interval display"],
        ])
          field(
            summary,
            ["uncertainty", key],
            u[key],
            label,
            false,
            key === "over",
            {
              disabled: (s) => !s.uncertainty?.kind,
              ...(key === "over"
                ? {
                    help: "Choose the seed/subject/unit ID assumed independent. Technical repeats are summarized first. An ID does not prove independence.",
                  }
                : {}),
            },
          );
      }
    }
    const common = new Set(
      schema.oneOf.flatMap((branch) =>
        Object.keys(branch.properties).filter((key) =>
          schema.oneOf.every((other) => key in other.properties),
        ),
      ),
    );
    const special = Object.entries(props).filter(
      ([key, node]) =>
        !common.has(key) &&
        !["aggregation", "uncertainty"].includes(key) &&
        ((node.type !== "object" && node.type !== "array") ||
          node.items?.type === "string"),
    );
    if (special.length) {
      const group = section("Chart-specific settings");
      for (const [key, node] of special)
        field(
          group,
          [key],
          node,
          names[key] || words(key),
          current.required.includes(key),
          ["pair", "outcome", "event", "value"].includes(key),
        );
    }
    const exports = section("Manuscript and exports");
    for (const [key, label] of [
      ["size", "Manuscript width"],
      ["dpi", "Raster DPI"],
      ["stem", "Filename stem"],
      ["interactive", "Interactive HTML"],
      ["latex", "LaTeX sidecar"],
    ])
      field(exports, ["output", key], props.output.properties[key], label);
    // Format selection is handled as individual toggles so existing combinations survive.
    for (const fmt of props.output.properties.formats.items.enum) {
      const wrap = el("label", undefined, exports);
      wrap.className = "check";
      const input = el("input", undefined, wrap);
      input.type = "checkbox";
      input.id = "control-format-" + fmt;
      el(
        "span",
        fmt.toUpperCase() + (fmt === "png" ? " (required for preview)" : ""),
        wrap,
      );
      const binding = {
        input,
        path: ["output", "formats"],
        dirty: false,
        config: {},
        parse() {
          return props.output.properties.formats.items.enum.filter(
            (name) => root.querySelector("#control-format-" + name).checked,
          );
        },
        sync(s) {
          if (!binding.dirty)
            input.checked =
              fmt === "png" ||
              (
                s.output?.formats || props.output.properties.formats.default
              ).includes(fmt);
          input.disabled = fmt === "png";
        },
      };
      input.onchange = () => {
        binding.dirty = true;
        edit();
        flush();
      };
      bindings.push(binding);
    }
    const appearance = section("Legend and paper style");
    field(
      appearance,
      ["series_order"],
      props.series_order,
      "Series display order",
    );
    for (const [object, keys] of [
      ["legend", ["show", "position", "title", "style"]],
      ["style", ["preset", "venue", "grid", "despine"]],
    ])
      for (const key of keys)
        field(
          appearance,
          [object, key],
          props[object].properties[key],
          `${words(object)} ${words(key)}`,
        );
    const claims = section("Claims to check");
    claims.classList.add("claim-controls");
    el(
      "p",
      "Claims test literal numeric relationships, not significance, causality or independence. Name series exactly as they appear in your group column.",
      claims,
    ).className = "muted";
    const rows = Array.isArray(spec.claims) ? spec.claims : [];
    rows.forEach((row, index) => {
      const box = el("fieldset", undefined, claims);
      el("legend", "Claim " + (index + 1), box);
      const shape = props.claims.items.properties;
      for (const [key, label] of [
        ["kind", "Numeric relationship"],
        ["subject", "Subject series"],
        ["reference", "Reference series"],
        ["tolerance", "Tolerance in Y units"],
        ["text", "Claim wording"],
      ])
        field(
          box,
          ["claims", index, key],
          shape[key],
          label,
          ["kind", "subject"].includes(key),
        );
      const remove = el("button", "Remove claim " + (index + 1), box);
      remove.type = "button";
      remove.className = "quiet";
      remove.onclick = () => {
        if (!flush()) return;
        const s = structuredClone(read());
        s.claims.splice(index, 1);
        if (!s.claims.length) delete s.claims;
        edit();
        change(s);
      };
    });
    const add = el("button", "Add claim", claims);
    add.type = "button";
    add.id = "add-claim";
    add.onclick = () => {
      if (!flush()) return;
      const s = structuredClone(read());
      if (s.claims !== undefined && !Array.isArray(s.claims)) {
        error("Correct claims in Advanced JSON first.");
        return;
      }
      s.claims = [...(s.claims || []), {}];
      edit();
      change(s);
    };
    el(
      "p",
      "Panels, filters, smoothing and other advanced options remain available in Advanced JSON. Unrelated settings are preserved when you use these controls.",
      root,
    ).className = "muted";
  }
  return {
    flush,
    discard() {
      clearTimeout(flushTimer);
      bindings.forEach((b) => {
        b.dirty = false;
        b.input.removeAttribute("aria-invalid");
      });
      error("");
    },
    disable(message) {
      root.disabled = true;
      error(message);
    },
    sync(spec, canonical, fields) {
      if (!canonical) return;
      schema = canonical;
      columns = fields;
      current = schema.oneOf.find(
        (branch) => branch.properties.kind.const === spec.kind,
      );
      if (!current) {
        root.disabled = true;
        error(
          "Choose a supported figure kind, or correct it in Advanced JSON.",
        );
        return;
      }
      const next = JSON.stringify([
        spec.kind,
        columns,
        Array.isArray(spec.claims) ? spec.claims.length : 0,
      ]);
      if (next !== signature) {
        build(spec);
        signature = next;
      }
      root.disabled = false;
      bindings.forEach((b) => b.sync(spec));
    },
  };
}
