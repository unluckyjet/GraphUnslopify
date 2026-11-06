export function createFigureComments(root, { api, token }) {
  const get = id => root.querySelector("#" + id);
  const image = get("comments-image"), status = get("comments-status");
  const content = get("comments-content"), controls = get("comments-controls");
  const reload = get("comments-reload"), pins = get("comment-pins"), threads = get("comment-threads");
  const author = get("comments-author"), form = get("comment-create");
  const x = get("comment-x"), y = get("comment-y"), body = get("comment-body");
  let selected, view, generation = 0;

  function add(parent, tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
  }

  function busy(value) {
    controls.disabled = value;
    reload.disabled = value;
  }

  function render() {
    pins.replaceChildren();
    threads.replaceChildren();
    if (!view.threads.length) add(threads, "p", "No comments on this render yet.");
    view.threads.forEach((thread, index) => {
      const number = index + 1;
      const resolved = thread.status_history.at(-1)?.resolved === true;
      const article = add(threads, "article");
      const heading = add(article, "h4", "Comment " + number + (resolved ? " · Resolved" : " · Open"));
      heading.tabIndex = -1;
      add(article, "p", thread.author + " · " + thread.at + " · pixel (" + thread.x + ", " + thread.y + ")");
      add(article, "p", thread.body);
      for (const reply of thread.replies) {
        const response = add(article, "div");
        response.className = "comment-reply";
        add(response, "p", reply.author + " · " + reply.at);
        add(response, "p", reply.body);
      }
      if (thread.status_history.length) {
        const changes = add(article, "details");
        add(changes, "summary", "Resolution history");
        for (const change of thread.status_history) {
          add(changes, "p", (change.resolved ? "Resolved by " : "Reopened by ") + change.author + " · " + change.at);
        }
      }
      if (!resolved) {
        const replyForm = add(article, "form");
        const label = add(replyForm, "label", "Reply to comment " + number);
        const input = add(label, "textarea");
        input.required = true; input.maxLength = 2000; input.rows = 2;
        add(replyForm, "button", "Post reply");
        replyForm.onsubmit = event => {
          event.preventDefault();
          save({ operation: "reply", thread: thread.id, body: input.value });
        };
      }
      const button = add(article, "button", resolved ? "Reopen comment " + number : "Resolve comment " + number);
      button.type = "button"; button.className = "quiet";
      button.onclick = () => save({ operation: resolved ? "reopen" : "resolve", thread: thread.id });
      const pin = add(pins, "button", String(number));
      pin.type = "button";
      pin.dataset.resolved = String(resolved);
      pin.setAttribute("aria-label", "Go to comment " + number);
      pin.style.left = (thread.x + 0.5) * 100 / view.anchor.width + "%";
      pin.style.top = (thread.y + 0.5) * 100 / view.anchor.height + "%";
      pin.onclick = () => heading.focus();
    });
  }

  async function load() {
    if (!selected || !root.open) return;
    const version = ++generation;
    const query = new URLSearchParams(selected);
    busy(true);
    content.hidden = true;
    status.textContent = "Verifying the saved render…";
    try {
      const next = await api("/api/figure-comments?" + query);
      if (version !== generation) return;
      query.set("index", next.anchor.index);
      const response = await fetch("/api/artifact?" + query, { headers: { "X-Preview-Token": token } });
      if (!response.ok) throw Error("The saved PNG is unavailable.");
      const bytes = await response.arrayBuffer();
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
        value => value.toString(16).padStart(2, "0")).join("");
      if (digest !== next.anchor.sha256) throw Error("The saved PNG changed before display.");
      const source = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(Error("Could not display the saved PNG."));
        reader.readAsDataURL(new Blob([bytes], { type: "image/png" }));
      });
      if (version !== generation) return;
      image.src = source;
      await image.decode();
      if (version !== generation) return;
      if (image.naturalWidth !== next.anchor.width || image.naturalHeight !== next.anchor.height) {
        throw Error("The displayed image dimensions differ from the saved render.");
      }
      view = next;
      x.max = next.anchor.width - 1;
      y.max = next.anchor.height - 1;
      status.textContent = "Saved audit " + next.anchor.event + " · " + next.anchor.figure;
      render();
      content.hidden = false;
    } catch (problem) {
      if (version === generation) status.textContent = problem.message;
    } finally {
      if (version === generation) busy(false);
    }
  }

  async function save(values) {
    if (!view || controls.disabled || !author.reportValidity()) return;
    const version = generation;
    busy(true);
    try {
      const next = await api("/api/figure-comments", {
        ...selected, ...values, author: author.value, anchor_key: view.anchor_key,
        expected_revision: view.revision,
      });
      if (version !== generation) return;
      view = next;
      if (values.operation === "create") body.value = "";
      render();
      status.textContent = "Saved comments for audit " + next.anchor.event + " · " + next.anchor.figure;
    } catch (problem) {
      if (version === generation) status.textContent = problem.message;
    } finally {
      if (version === generation) busy(false);
    }
  }

  form.onsubmit = event => {
    event.preventDefault();
    save({ operation: "create", x: x.valueAsNumber, y: y.valueAsNumber, body: body.value });
  };
  image.onclick = event => {
    if (!view || controls.disabled) return;
    const rect = image.getBoundingClientRect();
    const pixel = (offset, drawn, source) => Math.max(0, Math.min(source - 1, Math.floor(offset * source / drawn)));
    x.value = pixel(event.clientX - rect.left, rect.width, view.anchor.width);
    y.value = pixel(event.clientY - rect.top, rect.height, view.anchor.height);
    body.focus();
  };
  root.ontoggle = () => { if (root.open && !view && !reload.disabled) load(); };
  reload.onclick = load;

  return {
    mount(next) {
      selected = next;
      view = undefined;
      generation++;
      busy(false);
      content.hidden = true;
      root.hidden = !next;
      form.reset();
      pins.replaceChildren();
      threads.replaceChildren();
      image.removeAttribute("src");
      if (next && root.open) load();
    },
  };
}
