// Render saved guidance when present; use the current catalog for legacy findings.
export function describeFinding(node, item, catalog = {}) {
  const heading = document.createElement("strong");
  heading.textContent = String(item.code || "Check result").replaceAll("_", " ");
  const problem = document.createElement("p");
  problem.textContent = item.message;
  node.append(heading, problem);
  const advice = (Object.hasOwn(catalog.advice || {}, item.code) ? catalog.advice[item.code] : catalog.unknown) || {};
  for (const [field, label] of [["consequence", "Why it matters"], ["correction", "Recommended correction"]]) {
    const value = item[field] || advice[field];
    if (!value) continue;
    const line = document.createElement("p"), title = document.createElement("strong");
    title.textContent = label + ": ";
    line.append(title, document.createTextNode(value));
    node.append(line);
  }
}
