/** Review exact project-local wording changes before accepting them. */
export function createResearchIntent(panel, api) {
  const $ = (id) => panel.querySelector(`#intent-${id}`);
  const [category, name, value, forget] = [$("category"), $("name"), $("value"), $("forget")];
  const labels = Object.fromEntries(Array.from(category.options, item => [item.value, item.textContent]));
  let state, proposal;
  let busy = false, historyLimit = 20;

  function add(parent, tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    parent.append(node);
    return node;
  }

  function status(message) {
    $("status").textContent = message;
  }

  function update() {
    $("fields").disabled = busy || !state;
    $("refresh").disabled = busy;
    $("accept").disabled = busy || !proposal;
    $("cancel").disabled = busy;
    value.required = !forget.checked;
    value.disabled = forget.checked;
  }

  function clearReview() {
    proposal = undefined;
    $("proposal").hidden = true;
    $("diff").replaceChildren();
    update();
  }

  function renderHistory() {
    const root = $("history");
    root.replaceChildren();
    for (const event of state.history.slice(-historyLimit).reverse()) {
      const row = add(root, "li", new Date(event.accepted_at).toLocaleString());
      const entries = add(row, "ul", "");
      for (const [kind, values] of Object.entries(event.changes)) {
        for (const [key, wording] of Object.entries(values)) {
          add(entries, "li", `${labels[kind]} · ${key} · ${wording ?? "Forgotten"}`);
        }
      }
    }
    $("older").hidden = state.history.length <= historyLimit;
  }

  function showState(result) {
    state = result;
    const root = $("current");
    root.replaceChildren();
    let count = 0;
    for (const [kind, title] of Object.entries(labels)) {
      const entries = Object.entries(state.entries[kind]);
      if (!entries.length) continue;
      add(root, "h3", title);
      const list = add(root, "ul", "");
      for (const [key, wording] of entries) add(list, "li", `${key} · ${wording}`);
      count += entries.length;
    }
    if (!count) add(root, "p", "No accepted wording yet.");
    historyLimit = 20;
    renderHistory();
  }

  async function perform(operation) {
    if (busy) return;
    busy = true;
    update();
    try {
      await operation();
    } catch (error) {
      status(error.message);
    } finally {
      busy = false;
      update();
    }
  }

  const refresh = () => perform(async () => {
    clearReview();
    state = undefined;
    $("current").replaceChildren();
    $("history").replaceChildren();
    $("older").hidden = true;
    status("Loading accepted research intent…");
    showState(await api("/api/research-intent"));
    status("Research intent is up to date.");
  });

  panel.addEventListener("toggle", () => {
    if (panel.open && !state) void refresh();
  });
  $("refresh").addEventListener("click", refresh);
  $("older").addEventListener("click", () => { historyLimit += 20; renderHistory(); });
  $("form").addEventListener("input", clearReview);
  $("cancel").addEventListener("click", clearReview);
  $("form").addEventListener("submit", event => {
    event.preventDefault();
    if (!state) return;
    void perform(async () => {
      clearReview();
      const request = {
        changes: { [category.value]: { [name.value.trim()]: forget.checked ? null : value.value.trim() } },
        expected_revision: state.revision,
      };
      const review = await api("/api/research-intent/review", request);
      proposal = { ...request, review_sha256: review.review_sha256 };
      for (const row of review.changes) {
        add($("diff"), "li", `${labels[row.category]} · ${row.name} · ${row.before ?? "Absent"} → ${row.after ?? "Forgotten"}`);
      }
      $("proposal").hidden = false;
      status("Review the exact wording before accepting.");
    });
  });
  $("accept").addEventListener("click", () => {
    if (!proposal) return;
    void perform(async () => {
      const request = proposal;
      clearReview();
      showState(await api("/api/research-intent/accept", request));
      $("form").reset();
      status("Accepted research intent saved.");
    });
  });
}
