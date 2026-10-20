(() => {
  const $ = (id) => document.getElementById(id);
  const drop = $("drop"), fileInput = $("file"), statusEl = $("status");
  let docId = null;

  function el(tag, props = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    }
    kids.flat().forEach((c) => c != null && node.append(c));
    return node;
  }
  const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };
  const setStatus = (msg, isError = false) => {
    statusEl.textContent = msg;
    statusEl.className = "status" + (isError ? " error" : "");
  };

  drop.addEventListener("click", () => fileInput.click());
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
  fileInput.addEventListener("change", () => fileInput.files[0] && upload(fileInput.files[0]));

  async function upload(file) {
    $("results").hidden = true;
    setStatus(`Reading ${file.name}. Long documents can take a minute or two.`);
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch("/api/analyze", { method: "POST", body: form });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Something went wrong.");
      render(data);
      setStatus("");
      $("results").scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  function fillList(id, items, mapper, emptyText) {
    const node = clear($(id));
    if (!items || !items.length) {
      node.append(el("li", { class: "empty", text: emptyText }));
      return;
    }
    items.forEach((i) => node.append(mapper(i)));
  }

  function render(d) {
    docId = d.id;
    const o = d.overview || {};
    const type = d.fields && d.fields.DocumentType ? ` · ${d.fields.DocumentType}` : "";
    $("docmeta").textContent = `${d.filename}${type} · ${d.page_count} page${d.page_count === 1 ? "" : "s"}`;
    $("plain-summary").textContent = o.plain_summary || "";

    const w = clear($("warnings"));
    (d.warnings || []).forEach((m) => w.append(el("div", { class: "notice", text: m })));

    fillList("parties", o.who_is_involved, (p) =>
      el("li", {}, el("b", { text: p.name }), " ", el("span", { class: "role", text: `(${p.role}) ${p.in_plain_terms || ""}` })),
      "The document doesn't name the parties clearly.");
    fillList("must", o.what_you_must_do, (t) => el("li", { text: t }), "Nothing specific found.");
    fillList("get", o.what_you_get, (t) => el("li", { text: t }), "Nothing specific found.");

    const dates = clear($("dates"));
    (o.key_dates_and_money || []).forEach((x) => {
      dates.append(el("dt", { text: x.label }), el("dd", { text: x.detail }));
    });
    if (!dates.children.length) dates.append(el("dd", { class: "empty", text: "No dates or amounts found." }));

    const flags = clear($("flags"));
    (o.red_flags || []).forEach((f) => {
      flags.append(el("div", { class: `flag ${f.severity || "medium"}` },
        el("b", { text: f.title }), el("span", { text: f.why_it_matters })));
    });
    if (!flags.children.length) flags.append(el("p", { class: "empty", text: "Nothing unusual stood out. Read the sections below anyway." }));

    const secs = clear($("sections"));
    d.sections.forEach((s) => secs.append(sectionRow(s)));

    fillList("lawyer", o.questions_for_a_lawyer, (q) => el("li", { text: q }), "No questions suggested.");
    $("disclaimer").textContent = d.disclaimer;
    $("answer").hidden = true;
    $("results").hidden = false;
  }

  function sectionRow(s) {
    const src = el("div", { class: "src", text: s.text });
    const orig = el("div", { class: "orig" },
      el("h3", {}, s.heading, s.page ? el("span", { class: "page", text: `  page ${s.page}` }) : null), src);
    if (s.text.length > 450) {
      const btn = el("button", { class: "more", type: "button", text: "Show full text" });
      btn.addEventListener("click", () => {
        const open = src.classList.toggle("open");
        btn.textContent = open ? "Show less" : "Show full text";
      });
      orig.append(btn);
    }
    const mean = el("div", { class: "mean" }, el("p", { text: s.plain_english || "" }));
    if (s.watch_out) mean.append(el("p", { class: "watch", text: `Watch out: ${s.watch_out}` }));
    if (s.jargon && s.jargon.length) {
      const j = el("p", { class: "jargon" });
      s.jargon.forEach((x, i) => {
        if (i) j.append("  ");
        j.append(el("b", { text: x.term }), ` means ${x.meaning}.`);
      });
      mean.append(j);
    }
    return el("div", { class: `row sev-${s.severity || "none"}` }, orig, mean);
  }

  $("ask-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("question").value.trim();
    if (!q || !docId) return;
    const btn = e.target.querySelector("button");
    btn.disabled = true;
    const box = $("answer");
    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_id: docId, question: q }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Could not answer.");
      clear(box).append(
        el("p", { text: data.answer }),
        el("small", { text: `From: ${(data.sections_used || []).join(", ") || "the document"} · Confidence: ${data.confidence || "unknown"}` }));
    } catch (err) {
      clear(box).append(el("p", { text: err.message }));
    } finally {
      box.hidden = false;
      btn.disabled = false;
    }
  });
})();
