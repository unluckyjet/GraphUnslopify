export function createStatisticalPower(root, api) {
  const designs = {
    one_sample: ["One sample", "Use independent observations with normally distributed outcomes.", "Planned independent observations", "Planning outcome SD"],
    paired: ["Matched pairs", "Use independent complete pairs and normally distributed within-pair differences.", "Planned independent complete pairs", "Planning SD of within-pair differences"],
    pooled: ["Independent groups, common variance", "Use independent groups with normal outcomes and a common variance.", "Planned independent units in group A", "Planning common SD"],
    welch: ["Independent groups, Welch", "Use independent groups with normal outcomes and separate planning variances.", "Planned independent units in group A", "Planning SD in group A"],
  };
  function add(parent, tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  }
  add(root, "p", "Plan a mean-difference test from assumptions you supply. Power is the chance of rejecting the null if the planned difference is true.");
  const form = add(root, "form");
  const fields = add(form, "div");
  fields.className = "power-fields";
  function field(text, type) {
    const label = add(fields, "label");
    const name = add(label, "span", text);
    const input = add(label, type === "select" ? "select" : "input");
    if (type === "number") {
      input.type = "number";
      input.step = "any";
    }
    input.required = true;
    return { label, name, input };
  }
  function choices(text, options) {
    const item = field(text, "select");
    for (const [value, label] of Object.entries(options)) item.input.add(new Option(label, value));
    return item.input;
  }
  const design = choices("Study design", { "": "Choose a design", ...Object.fromEntries(Object.entries(designs).map(([key, value]) => [key, value[0]])) });
  const calculation = choices("Calculate", { power: "Power for a planned difference", detectable_effect: "Detectable difference for target power" });
  const alternative = choices("Test alternative", { "": "Choose a direction", two_sided: "Two-sided (either direction)", greater: "Greater (positive difference)", less: "Less (negative difference)" });
  const scale = choices("Difference units", { standardized: "Standard deviations", raw: "Original outcome units" });
  const scaleLabel = scale.closest("label");
  const n = field("Planned independent units", "number"), other = field("Planned independent units in group B", "number");
  n.input.step = other.input.step = "1";
  n.input.min = other.input.min = "2";
  const alpha = field("Significance level (alpha)", "number");
  const sd = field("Planning SD", "number"), sdOther = field("Planning SD in group B", "number");
  const effect = field("Planned difference", "number"), target = field("Target power (0 to 1)", "number");
  const assumptions = add(form, "p");
  const confirm = add(form, "label", "I have specified the planning assumptions for this design");
  const confirmed = add(confirm, "input");
  confirmed.type = "checkbox"; confirmed.required = true;
  confirm.className = "power-confirm";
  const submit = add(form, "button", "Calculate planning power");
  const status = add(root, "p");
  status.setAttribute("role", "status");
  const result = add(root, "section");
  result.setAttribute("aria-label", "Planning calculation");
  const format = (number, digits) => Number(number.toPrecision(digits)).toString();
  let generation = 0;

  function update() {
    generation++;
    submit.disabled = false;
    status.textContent = "";
    result.replaceChildren();
    const selected = designs[design.value];
    const welch = design.value === "welch", grouped = welch || design.value === "pooled";
    const useSD = welch || scale.value === "raw";
    const solving = calculation.value === "detectable_effect";
    const enable = (item, visible) => {
      item.label.hidden = !visible;
      item.input.disabled = !visible;
    };
    scaleLabel.hidden = welch; scale.disabled = welch;
    n.name.textContent = selected?.[2] || "Planned independent units";
    sd.name.textContent = selected?.[3] || "Planning SD";
    effect.name.textContent = useSD ? "Planned difference in outcome units" : "Planned difference in standard deviations";
    enable(other, grouped); enable(sd, useSD); enable(sdOther, welch);
    enable(effect, !solving); enable(target, solving);
    assumptions.textContent = selected
      ? selected[1] + " Use fixed sample sizes and one pre-specified test."
      : "Choose a design to review its assumptions.";
  }
  design.onchange = () => {
    confirmed.checked = false;
    for (const item of [n, other, sd, sdOther, effect]) item.input.value = "";
    update();
  };
  scale.onchange = () => { effect.input.value = ""; update(); };
  form.addEventListener("input", update);
  form.onsubmit = async event => {
    event.preventDefault();
    const version = ++generation;
    const value = item => item.input.disabled ? null : item.input.valueAsNumber;
    submit.disabled = true;
    status.textContent = "Calculating under the declared assumptions…";
    result.replaceChildren();
    try {
      const response = await api("/api/statistical-power", {
        design: design.value, calculation: calculation.value, alternative: alternative.value,
        n: value(n), n_other: value(other), alpha: value(alpha),
        sd: value(sd), sd_other: value(sdOther), effect: value(effect),
        target_power: value(target), assumptions_confirmed: confirmed.checked,
      });
      if (version !== generation) return;
      const answer = response.result;
      const difference = answer.difference_scale === "standardized" ? " SD" : " in outcome units";
      add(result, "h4", "Estimated power " + format(answer.power * 100, 5) + "%");
      const label = response.inputs.calculation === "detectable_effect" ? "Detectable difference " : "Planned difference ";
      add(result, "p", label + format(answer.difference, 6) + difference + ".");
      add(result, "p", "Rejection probability at zero effect " + format(answer.null_rejection_probability * 100, 5) + "%.");
      add(result, "p", response.method.name + ". " + response.scope);
      const details = add(result, "details");
      add(details, "summary", "Calculation inputs and method");
      add(details, "pre", JSON.stringify(response, null, 2));
      status.textContent = "Planning calculation ready.";
    } catch (problem) {
      if (version === generation) status.textContent = problem.message;
    } finally {
      if (version === generation) submit.disabled = false;
    }
  };
  update();
}
