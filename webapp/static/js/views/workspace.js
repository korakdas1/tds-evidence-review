import { api } from "../api.js";
import { h, icon, clear, formatTime } from "../dom.js";
import {
  CASE_STATUS, CATEGORIES, DECISIONS, DOC_STATUS, EVENTS, FACTS, FIELDS, FINDINGS, ISSUES, METHODS,
  REASONS, REPORT_STATUS, TEXT_STATUS, explainFailure, factAnswer, statement,
} from "../lexicon.js";
import { askReviewer, modal, toast } from "../ui.js";
import { metadataFields, readMetadata } from "./new-review.js";
import { progressFill } from "./dashboard.js";

const PRIORITY = ["contradiction", "ai_suggestion", "validated", "rejected", "unvalidated"];
const CORRECTIONS = {
  personnel_supplied: ["yes", "no", "unknown"],
  worker_supervisor: ["customer", "vendor", "unknown", "conflicting"],
};
const ORDER_CHECK = {
  AGREES_NOT_PROOF_OF_VISUAL_ORDER: "Two readings agree (not proof of visual order)",
  DISAGREES: "Two readings disagree",
  NOT_CHECKED: "Not checked",
};

export async function renderWorkspace(main, caseId) {
  const state = { view: null, role: "contract", mode: "text", page: 1, tab: "evidence", selected: null, unlocked: {}, frame: 0, runId: null };
  main.append(loadingShell());
  try {
    state.view = await api.case(caseId);
  } catch (error) {
    clear(main).append(h("div", { class: "page" }, h("div", { class: "panel empty" },
      h("h3", {}, "This review could not be opened"), h("p", {}, error.message), h("a", { class: "btn", href: "#/" }, "Back to reviews"))));
    return null;
  }
  const firstPage = (state.view.evidence || []).flatMap((c) => c.occurrences.flatMap((o) => o.fragments)).find((f) => f.verified);
  if (firstPage) state.page = firstPage.page_number;

  const root = h("div", { class: "ws" });
  const head = h("div");
  const viewer = h("section", { class: "pane pane-doc", "aria-label": "Document viewer" });
  const analysis = h("section", { class: "pane pane-analysis", "aria-label": "Evidence analysis" });
  const split = h("div", { class: "split" }, viewer, analysis);
  clear(main).append(root);

  const reload = async (runId = state.runId) => {
    state.view = await api.case(caseId, runId);
    drawAll(true);
  };

  const record = async (body) => {
    const reviewer = await askReviewer();
    if (!reviewer) return false;
    try {
      state.view = await api.record(caseId, { ...body, reviewer, run_id: state.view.run.id });
      toast(body.kind === "NOTE" ? "Note added" : body.kind === "CASE_STATUS" ? "Status changed" : "Decision recorded");
      drawAll(true, false);
      return true;
    } catch (error) {
      toast(error.message, "error");
      return false;
    }
  };

  const ctx = { state, record, reload, caseId, selectCard, showSource, drawViewer: () => drawViewer() };

  function drawAll(keepScroll = false, redrawViewer = true) {
    if (state.view.untrusted) {
      // The server withheld the stored analysis; show diagnostics and history only.
      clear(root).append(...renderUntrusted(ctx));
      return;
    }
    if (!split.isConnected) {
      clear(root).append(head, split);
      redrawViewer = true;
    }
    const body = analysis.querySelector(".tab-body");
    const scroll = keepScroll && body ? body.scrollTop : 0;
    clear(head).append(renderHead(ctx));
    // Decisions do not change the documents, so the viewer (and an open PDF) is left alone.
    if (redrawViewer) drawViewer();
    drawAnalysis();
    if (keepScroll) analysis.querySelector(".tab-body").scrollTop = scroll;
  }

  function drawViewer() {
    clear(viewer).append(...renderViewer(ctx));
  }

  function drawAnalysis() {
    clear(analysis).append(...renderAnalysis(ctx, (tab, focus) => {
      state.tab = tab;
      drawAnalysis();
      if (focus) analysis.querySelector(`#tab-${tab}`)?.focus();
    }));
  }

  function selectCard(key, scroll = true) {
    state.selected = key;
    if (state.tab !== "evidence") { state.tab = "evidence"; drawAnalysis(); }
    analysis.querySelectorAll(".ev").forEach((el) => el.classList.toggle("selected", el.dataset.key === key));
    viewer.querySelectorAll("mark.hl").forEach((m) => m.classList.toggle("active", m.dataset.keys.split(" ").includes(key)));
    if (scroll) analysis.querySelector(`.ev[data-key="${key}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function showSource(card, fragment) {
    state.role = "contract";
    state.mode = "text";
    state.page = fragment.page_number;
    drawViewer();
    selectCard(card.key, false);
    const mark = [...viewer.querySelectorAll("mark.hl")].find((m) => m.dataset.keys.split(" ").includes(card.key));
    if (mark) {
      mark.scrollIntoView({ behavior: "smooth", block: "center" });
      mark.classList.remove("pulse");
      void mark.offsetWidth;
      mark.classList.add("pulse");
    }
  }

  drawAll();
  if (state.selected) selectCard(state.selected);
  return null;
}

/* ------------------------------------------------------------------ header */

function renderHead(ctx) {
  const { view } = ctx.state;
  const status = CASE_STATUS[view.case_status] || CASE_STATUS.AWAITING_REVIEW;
  const finding = FINDINGS[view.finding.factual_evidence_status];
  const report = REPORT_STATUS[view.report_status] || { label: view.report_status };
  const pct = view.progress.total ? Math.round((view.progress.done / view.progress.total) * 100) : 0;
  const frag = h("div");
  frag.append(h("header", { class: "ws-head" },
    h("div", { class: "ws-title-row" },
      h("div", {},
        h("div", { class: "crumbs" }, h("a", { href: "#/" }, "Reviews"), h("span", { "aria-hidden": "true" }, "/"), h("span", {}, view.case.reference)),
        h("div", { class: "row" }, h("h1", {}, view.case.title), h("span", { class: `pill ${status.cls}` }, status.label),
          view.case.origin === "SAMPLE" ? h("span", { class: "pill plain" }, "Synthetic sample") : null)),
      canReview(view) ? h("div", { class: "ws-actions" },
        h("button", { class: "btn btn-small", type: "button", onclick: () => addNote(ctx) }, "Add note"),
        h("button", { class: "btn btn-small", type: "button", onclick: () => changeStatus(ctx) }, "Change status"),
        h("a", { class: "btn btn-small", href: api.exportUrl(view.case.id), download: "" }, icon("download"), "Export record")) : null),
    h("div", { class: "summary-strip" },
      cell("Automated factual finding", !integrityOk(view) ? "Not shown: integrity check failed"
        : finding ? finding.title : view.finding.factual_evidence_status, integrityOk(view) ? "" : "withheld"),
      cell("Document reading", report.label),
      cell("Statutory proposal", view.finding.statutory_proposal === "WITHHELD" ? "Withheld for human review" : "Present", "withheld"),
      h("div", { class: "summary-cell" }, h("div", { class: "label" }, "Your review"),
        h("div", { class: "value" }, `${view.progress.done} of ${view.progress.total} checks recorded`),
        h("div", { class: "progress-track" }, progressFill(pct))))));
  if (!documentsAvailable(view)) {
    frag.append(h("div", { class: "guard ink-missing", role: "status" }, icon("alert"),
      h("span", {}, h("b", {}, "A stored PDF no longer matches its fingerprint. "),
        "The analysis itself is intact, but highlights, the original PDF, quotation checks and document checks are unavailable.")));
  }
  if (!integrityOk(view)) {
    frag.append(h("div", { class: "guard ink-contradiction", role: "alert" }, icon("alert"),
      h("span", {}, h("b", {}, "Integrity check failed. "),
        "The stored analysis or review history no longer matches its recorded fingerprints. Do not rely on this case; decisions are disabled.")));
  }
  frag.append(h("div", { class: "guard" }, icon("shield"),
    h("span", {}, "Your decisions are kept as an append-only review history. They never change the automated findings, release a statutory proposal or authorise withholding.")));
  if (!view.is_latest) {
    frag.append(h("div", { class: "guard ink-missing" }, icon("info"),
      h("span", {}, `You are viewing run ${view.run.sequence}, an earlier analysis. It is read-only. `),
      h("button", { class: "btn btn-small", type: "button", onclick: () => { ctx.state.runId = null; ctx.reload(null); } }, "Show the latest run")));
  }
  return frag;
}

function integrityOk(view) {
  return !view.untrusted && view.integrity?.status !== "FAILED";
}

function documentsAvailable(view) {
  return view.integrity?.status !== "DOCUMENTS_UNAVAILABLE";
}

const CHECK_LABELS = {
  report_row_hash: "Stored analysis matches its own fingerprint",
  history_anchor: "Stored analysis matches the fingerprint recorded in the review history",
  history_chain: "Review history entries are linked without gaps or edits",
  case_record: "Case title and reference match the history",
};

function renderUntrusted(ctx) {
  const { view } = ctx.state;
  const checks = Object.entries(view.integrity.checks);
  const passed = (key, value) => ({ report_row_hash: "VERIFIED", history_anchor: "MATCHES", history_chain: "INTACT", case_record: "MATCHES" })[key] === value;
  const head = h("header", { class: "ws-head" },
    h("div", { class: "crumbs" }, h("a", { href: "#/" }, "Reviews"), h("span", { "aria-hidden": "true" }, "/"), h("span", {}, view.case.reference)),
    h("div", { class: "row" }, h("h1", {}, view.case.title), h("span", { class: "pill ink-contradiction" }, "Integrity check failed"),
      h("span", { class: "spacer" }),
      h("a", { class: "btn btn-small", href: api.exportUrl(view.case.id), download: "" }, icon("download"), "Export forensic record")));
  const banner = h("div", { class: "guard ink-contradiction", role: "alert" }, icon("alert"),
    h("span", {}, h("b", {}, "This case cannot be trusted. "),
      "The server withheld the stored finding, evidence and page text because they no longer match their recorded fingerprints. Only diagnostics are shown. Re-create the case from the original documents."));
  const body = h("div", { class: "page" },
    h("section", { class: "panel side-card", "aria-label": "Integrity diagnostics" },
      h("h2", {}, "Integrity diagnostics"),
      h("p", { class: "muted small" }, view.integrity.limitation),
      h("table", { class: "page-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Check"), h("th", {}, "Result"))),
        h("tbody", {}, checks.map(([key, value]) => h("tr", {},
          h("td", {}, CHECK_LABELS[key] || key),
          h("td", {}, h("span", { class: `pill ${passed(key, value) ? "ink-validated" : "ink-contradiction"}` }, value)))),
        view.documents.map((d) => h("tr", {}, h("td", {}, `Stored ${d.role} file${d.name ? ` (${d.name})` : ""}`),
          h("td", {}, h("span", { class: `pill ${d.integrity === "VERIFIED" ? "ink-validated" : "ink-contradiction"}` }, d.integrity)))))),
      h("div", { class: "hash" }, `Stored report fingerprint ${view.forensic.stored_report_sha256}`),
      h("div", { class: "hash" }, `Fingerprint recorded in history ${view.forensic.anchored_report_sha256.join(", ") || "none"}`)),
    h("section", { class: "panel side-card", "aria-label": "Recorded history" },
      h("h2", {}, view.events_verified ? "Recorded history" : "Recorded history (unverified)"),
      ...historyTab(ctx)));
  return [head, banner, body];
}

function canReview(view) {
  return view.is_latest && integrityOk(view);
}

// Keyboard support for tab lists: arrow keys, Home and End move between tabs (WAI-ARIA tabs pattern).
function tabKeys(event, keys, current, select) {
  const index = keys.indexOf(current);
  const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: keys.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  select(keys[(next + keys.length) % keys.length]);
}

function cell(label, value, cls = "") {
  return h("div", { class: "summary-cell" }, h("div", { class: "label" }, label), h("div", { class: `value ${cls}` }, value));
}

/* ------------------------------------------------------------------ viewer */

function renderViewer(ctx) {
  const { state } = ctx;
  const docs = state.view.documents;
  const doc = docs.find((d) => d.role === state.role) || docs[0];
  state.role = doc.role;
  const pageCount = doc.pages.length;
  if (state.page > pageCount) state.page = 1;
  const redraw = () => ctx.drawViewer();

  const bar = h("div", { class: "viewer-bar" });
  if (docs.length > 1) {
    bar.append(h("div", { class: "seg", role: "group", "aria-label": "Document" }, docs.map((d) =>
      h("button", { type: "button", "aria-pressed": String(d.role === doc.role), onclick: () => { state.role = d.role; state.page = 1; redraw(); } },
        d.role === "contract" ? "Contract" : "Invoice"))));
  }
  bar.append(h("div", { class: "seg", role: "group", "aria-label": "View" },
    [["text", "Extracted text"], ["pdf", "Original PDF"], ["layout", "Layout reading"]].map(([mode, label]) =>
      h("button", { type: "button", "aria-pressed": String(state.mode === mode), onclick: () => { state.mode = mode; redraw(); } }, label))));
  if (pageCount) {
    bar.append(h("div", { class: "page-nav", role: "group", "aria-label": "Pages" }, doc.pages.map((p) =>
      h("button", {
        type: "button", class: `page-dot ${p.issues.length ? "flag" : ""}`, "aria-current": String(p.page_number === state.page),
        "aria-label": `Page ${p.page_number}${p.issues.length ? ", needs checking" : ""}`, title: p.issues.length ? "This page needs checking" : `Page ${p.page_number}`,
        onclick: () => { state.page = p.page_number; redraw(); },
      }, p.page_number))));
  }

  const body = h("div", { class: "viewer-body" });
  const page = doc.pages[state.page - 1];
  if (doc.integrity !== "VERIFIED") {
    body.append(notice("contradiction", "alert", "The stored file no longer matches the analysed fingerprint.",
      " Highlights and the original PDF are hidden because the saved positions might not belong to this file."));
  }
  if (!pageCount) {
    body.append(notice("contradiction", "alert", "This document could not be read.",
      ` ${doc.issues.map((i) => ISSUES[i] || i).join(" ")}`));
    return [bar, body];
  }

  if (state.mode === "pdf") {
    body.classList.add("pdf-wrap");
    if (!doc.file_url) {
      body.append(notice("missing", "info", "The original file is unavailable for display.", ""));
    } else if (doc.active_content && !state.unlocked[doc.role]) {
      body.append(notice("missing", "alert", "This PDF contains scripts or automatic actions.",
        " The review never ran them. Your browser's PDF viewer might. Open it only if you trust where the file came from.",
        h("div", { class: "row" }, h("button", { class: "btn btn-small", type: "button", onclick: () => { state.unlocked[doc.role] = true; redraw(); } }, "Open in the browser viewer anyway"))));
    } else {
      state.frame += 1;
      body.append(
        h("p", { class: "offset-note" }, icon("info"), h("span", {}, `Page ${state.page} of ${pageCount} in your browser's own PDF viewer. Highlights only appear in the extracted text, because the saved positions are text positions, not places on the page. If the PDF does not appear, `,
          h("a", { href: `${doc.file_url}#page=${state.page}`, target: "_blank", rel: "noopener noreferrer" }, "open it in a new tab"), ".")),
        h("iframe", { class: "pdf-frame", title: `Original PDF: ${doc.name}, page ${state.page}`, src: `${doc.file_url}?view=${state.frame}#page=${state.page}&view=FitH`, referrerpolicy: "no-referrer" }));
    }
    return [bar, body];
  }

  if (page.issues.length) {
    body.append(h("div", { class: "notice ink-missing", style: null }, icon("alert"),
      h("div", {}, h("b", {}, `Page ${page.page_number} needs checking. `), page.issues.map((i) => ISSUES[i] || i).join(" "))));
    body.lastChild.classList.add("sheet-gap");
  }

  const layout = state.mode === "layout";
  const text = layout ? page.layout_text : page.text;
  const spans = layout || doc.role !== "contract" || doc.integrity !== "VERIFIED" ? [] : spansFor(state.view, page.page_number);
  const status = DOC_STATUS[page.status] || { label: page.status, ink: "rejected" };
  const pre = text && text.trim() ? highlight(text, spans, ctx) :
    h("pre", { class: "page-text empty-page" }, layout ? "No layout reading is available for this page." : "No selectable text was found on this page. Nothing is inferred; read the original PDF.");
  body.append(h("article", { class: "sheet", "aria-label": `${doc.name}, page ${page.page_number}` },
    h("div", { class: "sheet-head" },
      h("span", {}, `${doc.name}, page ${page.page_number} of ${pageCount}, ${layout ? "layout reading" : "extracted text"}`),
      h("span", { class: `pill ink-${status.ink}` }, status.label)),
    pre));
  body.append(h("p", { class: "offset-note" }, icon("info"), layout
    ? "A second reading of the same page that follows the visual layout. Compare it with the extracted text to spot column or reading-order problems. Highlights are not shown here."
    : doc.role === "contract"
      ? "Highlights mark character positions in the extracted text, not positions on the printed page. Use the original PDF view to confirm what the page shows."
      : "The invoice is shown for inspection only. It is not analysed and nothing is highlighted."));
  return [bar, body];
}

function spansFor(view, pageNumber) {
  const spans = [];
  for (const card of view.evidence) {
    for (const occurrence of card.occurrences) {
      for (const f of occurrence.fragments) {
        if (f.page_number === pageNumber && f.verified) spans.push({ start: f.start, end: f.end, key: card.key, category: card.category });
      }
    }
  }
  return spans;
}

function highlight(text, spans, ctx) {
  const pre = h("pre", { class: "page-text" });
  const cuts = new Set([0, text.length]);
  for (const s of spans) { cuts.add(s.start); cuts.add(s.end); }
  const points = [...cuts].sort((a, b) => a - b);
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    const covering = spans.filter((s) => s.start <= a && s.end >= b);
    const piece = text.slice(a, b);
    if (!covering.length) { pre.append(piece); continue; }
    covering.sort((x, y) => PRIORITY.indexOf(x.category) - PRIORITY.indexOf(y.category));
    const keys = [...new Set(covering.map((s) => s.key))];
    const mark = h("mark", {
      class: `hl ink-${covering[0].category} ${keys.includes(ctx.state.selected) ? "active" : ""}`, dataset: { keys: keys.join(" ") },
      tabindex: "0", title: "Show this evidence",
      onclick: () => ctx.selectCard(keys[0]),
      onkeydown: (e) => { if (e.key === "Enter") ctx.selectCard(keys[0]); },
    }, piece);
    pre.append(mark);
  }
  return pre;
}

/* ------------------------------------------------------------------ analysis */

function renderAnalysis(ctx, setTab) {
  const { view, tab } = ctx.state;
  const docFlags = view.documents.some((d) => d.status !== "EXTRACTED");
  const tabs = [
    ["evidence", "Evidence", view.evidence.length + (view.missing_information.length ? 1 : 0)],
    ["transaction", "Transaction", null],
    ["documents", "Documents", docFlags ? "!" : null],
    ["history", "History", view.events.length],
  ];
  const keys = tabs.map(([key]) => key);
  const bar = h("div", { class: "tabs", role: "tablist", "aria-label": "Analysis sections",
    onkeydown: (event) => tabKeys(event, keys, tab, (key) => setTab(key, true)) }, tabs.map(([key, label, count]) =>
    h("button", { class: "tab", type: "button", role: "tab", "aria-selected": String(tab === key), id: `tab-${key}`,
      "aria-controls": "analysis-panel", tabindex: tab === key ? "0" : "-1", onclick: () => setTab(key) },
      label, count !== null && count !== 0 ? h("span", { class: "count", "aria-label": `(${count})` }, count) : null)));
  const body = h("div", { class: "tab-body", role: "tabpanel", id: "analysis-panel", tabindex: "0", "aria-labelledby": `tab-${tab}` });
  if (tab === "evidence") body.append(...evidenceTab(ctx));
  if (tab === "transaction") body.append(...transactionTab(ctx));
  if (tab === "documents") body.append(...documentsTab(ctx));
  if (tab === "history") body.append(...historyTab(ctx));
  return [bar, body];
}

function evidenceTab(ctx) {
  const { view } = ctx.state;
  const f = view.finding;
  const finding = FINDINGS[f.factual_evidence_status] || { title: f.factual_evidence_status, body: "" };
  const out = [];
  if (!integrityOk(view)) {
    // Never present an unverifiable stored analysis as a finding.
    return [notice("contradiction", "alert", "The automated finding is not shown.",
      " This case failed an integrity check, so the stored analysis cannot be trusted. Re-create the case from the original documents.")];
  }
  const reliedOn = (fact) => factAnswer(fact, f.validated_facts[fact]);
  const textLevel = (fact) => f.text_level_facts[fact] !== f.validated_facts[fact]
    ? h("div", { class: "small muted" }, `Text reading: ${factAnswer(fact, f.text_level_facts[fact])}, on hold`) : null;
  out.push(h("section", { class: "finding", "aria-label": "Automated finding" },
    h("div", { class: "label" }, "Automated factual finding. This is not a tax decision."),
    h("h2", {}, finding.title),
    h("p", {}, finding.body),
    h("div", { class: "facts" },
      h("div", { class: "fact-box" }, h("div", { class: "q" }, FACTS.personnel_supplied.question), h("div", { class: "a" }, reliedOn("personnel_supplied")), textLevel("personnel_supplied")),
      h("div", { class: "fact-box" }, h("div", { class: "q" }, FACTS.worker_supervisor.question), h("div", { class: "a" }, reliedOn("worker_supervisor")), textLevel("worker_supervisor"))),
    h("div", { class: "row" },
      h("span", { class: "pill ink-missing" }, "Statutory proposal withheld"),
      h("span", { class: "pill ink-reviewer" }, "Human review required"),
      h("span", { class: "pill plain" }, `${f.factual_evidence_status}`)),
    f.run_status !== "OK" ? notice("contradiction", "alert", "The analysis could not complete.",
      ` ${f.validation_failures.filter((v) => !f.document_issues.includes(v)).map(explainFailure).join(" ")}`) : null,
    f.document_issues.length ? notice("missing", "alert", "The text is on hold until the document is checked.",
      ` ${f.document_issues.map((i) => ISSUES[i] || i).join(" ")} Facts found in the text are shown below but are not relied on.`) : null));

  const groups = {};
  for (const card of view.evidence) (groups[card.category] ||= []).push(card);
  const replay = view.run.method === "supplied_extraction";
  for (const category of ["contradiction", "validated", "ai_suggestion"]) {
    const info = CATEGORIES[category];
    let sub = info.sub;
    if (category === "ai_suggestion" && replay) sub += " In this run, suggestions came from a supplied extraction (simulated). No model was called.";
    out.push(group(category, info.title, sub, groups[category] || [], info.empty, ctx));
  }
  out.push(h("section", { class: "group ink-missing", "aria-label": "Missing information" },
    h("div", { class: "group-head" }, h("h3", {}, "Missing information"), h("span", { class: "n" }, view.missing_information.length)),
    h("p", { class: "group-sub" }, "What the review still needs before anyone can rely on the facts."),
    view.missing_information.length
      ? h("ul", { class: "missing-list" }, view.missing_information.map((m) => h("li", {}, m)))
      : h("div", { class: "group-empty" }, "Nothing reported as missing by the automated checks.")));
  for (const category of ["rejected", "unvalidated"]) {
    if (groups[category]) out.push(group(category, CATEGORIES[category].title, CATEGORIES[category].sub, groups[category], "", ctx));
  }
  return out;
}

function group(category, title, sub, cards, empty, ctx) {
  return h("section", { class: `group ink-${category}`, "aria-label": title },
    h("div", { class: "group-head" }, h("h3", {}, title), h("span", { class: "n" }, cards.length)),
    h("p", { class: "group-sub" }, sub),
    cards.length ? cards.map((card) => evidenceCard(card, ctx)) : h("div", { class: "group-empty" }, empty));
}

function evidenceCard(card, ctx) {
  const { view, selected } = ctx.state;
  const primary = card.assertions.filter((a) => a.reviewable);
  const alsoContradiction = card.assertions.some((a) => !a.reviewable);
  const el = h("article", { class: `ev ink-${card.category} ${selected === card.key ? "selected" : ""}`, dataset: { key: card.key } });
  el.append(h("div", { class: "stack", style: null }, primary.map((a) => {
    let status = TEXT_STATUS[a.text_status] || { label: a.text_status, ink: "unvalidated" };
    // Each clause may pass the rule checks on its own; together they conflict.
    if (card.category === "contradiction" && a.fact !== "contradiction") status = { label: "Conflicts with another clause", ink: "contradiction" };
    return h("div", { class: "ev-assert" },
      a.fact === "contradiction"
        ? h("span", { class: "a" }, "Cited as conflicting with another clause")
        : [h("span", { class: "q" }, FACTS[a.fact]?.question || a.fact), h("span", { class: "a" }, factAnswer(a.fact, a.value))],
      h("span", { class: `pill ink-${status.ink}` }, status.label));
  })));
  if (alsoContradiction) el.append(h("div", { class: "small muted" }, "Also listed among the contradictory clauses."));
  el.append(h("blockquote", {}, card.quote));
  if (card.sentence_context && card.sentence_context !== card.quote) {
    el.append(h("p", { class: "context" }, `Full sentence: ${card.sentence_context}`));
  }
  const sources = h("div", { class: "sources" });
  if (card.mapping_status !== "MAPPED_TO_EXTRACTED_TEXT") {
    sources.append(h("span", { class: "source bad" }, icon("alert"), "Not located in the page text"));
  }
  for (const occurrence of card.occurrences) {
    if (occurrence.cross_page) {
      const pages = occurrence.fragments.map((f) => f.page_number);
      sources.append(h("span", { class: "source bad" }, icon("alert"), `Runs across pages ${Math.min(...pages)} to ${Math.max(...pages)}, check visually`));
    }
    for (const f of occurrence.fragments) {
      sources.append(h("button", {
        class: `source ${f.verified ? "ok" : "bad"}`, type: "button",
        title: f.verified ? "Location re-checked against the stored text. Click to show it." : "This location could not be verified",
        onclick: () => f.verified ? ctx.showSource(card, f) : null,
      }, icon(f.verified ? "check" : "alert"), `Contract page ${f.page_number}, characters ${f.start} to ${f.end}`));
    }
  }
  el.append(sources);
  if (card.suspended_by_document_review) {
    el.append(h("p", { class: "hold" }, "On hold: the document needs a visual check before this can be relied on."));
  }
  const reasons = [...new Set(card.assertions.flatMap((a) => a.review_reasons))];
  if (reasons.length) el.append(h("ul", { class: "reasons" }, reasons.map((r) => h("li", {}, REASONS[r] || r))));
  if (canReview(view)) el.append(reviewBox(card, primary, ctx));
  return el;
}

function reviewBox(card, assertions, ctx) {
  const box = h("div", { class: "review-box" });
  if (!documentsAvailable(ctx.state.view)) {
    box.append(h("p", { class: "small muted" }, "Quotation checks are unavailable because the stored PDF failed its integrity check."));
  } else box.append(question({
    prompt: "Does this text appear in the original PDF exactly as quoted?",
    help: "Compare it with the Original PDF view. This checks the words only.",
    kind: "QUOTE_CHECK", target: card.key, current: card.quote_decision, ctx,
  }));
  for (const a of assertions) {
    const isConflict = a.fact === "contradiction";
    box.append(question({
      prompt: isConflict ? "Do you agree this clause conflicts with another?"
        : `Do you agree this sentence shows that ${statement(a.fact, a.value)}?`,
      help: "Agreeing records your reading of the text. It does not classify the payment.",
      kind: "INTERPRETATION_REVIEW", target: a.key, current: a.decision, fact: isConflict ? null : a.fact, automated: a.value, ctx,
    }));
  }
  return box;
}

function question({ prompt, help, kind, target, current, fact, automated, ctx }) {
  const wrap = h("div", { class: "review-q" });
  const draw = (choosing) => {
    clear(wrap).append(h("div", { class: "prompt" }, prompt, h("small", {}, help)));
    if (current && !choosing) {
      wrap.append(stamp(kind, current, () => draw(true)));
      return;
    }
    const compose = h("div");
    const chips = h("div", { class: "choice-row" }, Object.entries(DECISIONS[kind]).map(([value, label]) =>
      h("button", { class: "chip-btn", type: "button", "aria-pressed": "false", onclick: (e) => {
        chips.querySelectorAll(".chip-btn").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
        openCompose(value);
      } }, label)));
    const openCompose = (decision) => {
      const note = h("textarea", { class: "textarea", maxlength: "4000", placeholder: "Note (optional). For example, what you compared it with.", "aria-label": "Note" });
      let correction = null;
      const parts = [];
      if (kind === "INTERPRETATION_REVIEW" && decision === "DISAGREE" && fact && CORRECTIONS[fact]) {
        correction = h("select", { class: "select", "aria-label": "Your reading" },
          h("option", { value: "" }, "No correction, just disagree"),
          CORRECTIONS[fact].filter((v) => v !== automated).map((v) => h("option", { value: v }, factAnswer(fact, v))));
        parts.push(h("div", { class: "field" }, h("span", { class: "field-label" }, "What does the text show instead?"), correction,
          h("span", { class: "hint" }, "Your correction is recorded beside the automated result. It does not change it.")));
      }
      const save = h("button", { class: "btn btn-primary btn-small", type: "button" }, "Record decision");
      save.addEventListener("click", async () => {
        save.disabled = true;
        const ok = await ctx.record({ kind, target, decision, note: note.value, correction: correction && correction.value ? correction.value : null });
        if (!ok) save.disabled = false;
      });
      clear(compose).append(h("div", { class: "compose" }, ...parts, note,
        h("div", { class: "row" }, h("span", { class: "disclaimer" }, "Saved with your name and the time. The app keeps it; to change your mind, record a new decision."), h("span", { class: "spacer" }),
          current ? h("button", { class: "btn btn-quiet btn-small", type: "button", onclick: () => draw(false) }, "Cancel") : null, save)));
    };
    wrap.append(chips, compose);
  };
  draw(false);
  return wrap;
}

function stamp(kind, decision, onChange) {
  const label = DECISIONS[kind][decision.decision] || decision.decision;
  const correction = decision.correction;
  return h("div", { class: "stamp" },
    h("div", { class: "stamp-top" }, icon("check"), h("b", {}, label),
      h("span", { class: "who" }, `${decision.actor}, ${formatTime(decision.created_at)}`),
      h("button", { class: "change", type: "button", onclick: onChange }, "Record a new decision")),
    correction ? h("div", { class: "note" }, `Your reading: ${factAnswer(correction.fact, correction.reviewer_value)}. The automated result (${factAnswer(correction.fact, correction.automated_value)}) is unchanged.`) : null,
    decision.note ? h("div", { class: "note" }, decision.note) : null);
}

/* ------------------------------------------------------------------ transaction */

function transactionTab(ctx) {
  const { view } = ctx.state;
  const meta = view.run.metadata;
  const date = view.finding.date_selection;
  const out = [];
  out.push(h("div", { class: "section-title" }, h("h3", {}, "Transaction details"), h("span", { class: "spacer" }),
    canReview(view) ? h("button", { class: "btn btn-small", type: "button", onclick: () => correctDetails(ctx) }, icon("refresh"), "Correct details and run again") : null));
  out.push(h("p", { class: "muted small" }, "Entered manually. Nothing here was read from the PDFs."));
  out.push(h("div", { class: "kv" }, Object.entries(FIELDS).flatMap(([k, label]) => [h("div", { class: "k" }, label), h("div", {}, meta[k] || h("span", { class: "muted" }, "Not provided"))])));

  out.push(h("div", { class: "section-title" }, h("h3", {}, "Which Act applies")));
  out.push(date.status === "RESOLVED"
    ? h("div", { class: "kv" }, h("div", { class: "k" }, "Applicable Act"), h("div", {}, date.applicable_act),
      h("div", { class: "k" }, "Deciding date"), h("div", {}, `${date.trigger_date} (the earlier of credit and payment)`))
    : notice("missing", "alert", "The Act could not be selected.", ` ${date.validation_failures.join(" ")}`));

  out.push(h("div", { class: "section-title" }, h("h3", {}, "How this run was analysed")));
  out.push(h("div", { class: "kv" },
    h("div", { class: "k" }, "Method"), h("div", {}, METHODS[view.run.method] || view.run.method),
    h("div", { class: "k" }, "Run"), h("div", {}, `${view.run.sequence} of ${view.runs.length}, ${formatTime(view.run.created_at)}`),
    h("div", { class: "k" }, "Model or network calls"), h("div", {}, "0"),
    h("div", { class: "k" }, "Simulated extraction replays"), h("div", {}, String(view.run.simulated_client_invocations)),
    h("div", { class: "k" }, "Saved report fingerprint"), h("div", { class: "hash" }, `${view.run.report_sha256} (${view.run.report_integrity === "VERIFIED" ? "verified" : "MISMATCH"})`)));
  if (view.run.supplied_extraction) {
    out.push(notice("ai_suggestion", "info", "Supplied extraction.", " This was provided by hand and replayed through the existing validators. It is not a model output."));
    out.push(h("pre", { class: "json" }, JSON.stringify(view.run.supplied_extraction, null, 2)));
  }

  out.push(h("div", { class: "section-title" }, h("h3", {}, "Why human review is required")));
  out.push(h("ul", { class: "reasons ink-reviewer" }, view.finding.human_review_reasons.map((r) => h("li", {}, r))));

  out.push(h("div", { class: "section-title" }, h("h3", {}, "Legal reference texts")));
  out.push(h("p", { class: "muted small" }, "Reference material checked by the project team. These are not advice and are not applied automatically to PDFs."));
  for (const s of view.finding.legal_sources) {
    out.push(h("div", { class: "ref" }, h("b", {}, s.statutory_reference), h("span", {}, s.rule),
      h("span", { class: "meta" }, `${s.verification_status.replaceAll("_", " ").toLowerCase()}. Source: ${s.source_url}`)));
  }
  out.push(h("div", { class: "section-title" }, h("h3", {}, "Limits of this analysis")));
  out.push(h("ul", { class: "reasons ink-unvalidated" }, view.limitations.map((l) => h("li", {}, l))));
  return out;
}

async function correctDetails(ctx) {
  const { view } = ctx.state;
  const formHost = h("form", { class: "stack" }, metadataFields(view.run.metadata));
  const reason = h("textarea", { class: "textarea", id: "f-reason", maxlength: "4000", placeholder: "For example, the payment date on the invoice was 20 October, not 2 October." });
  formHost.append(h("div", { class: "field" }, h("label", { for: "f-reason" }, "Why are you changing these details?"), reason));
  const reviewer = await askReviewer();
  if (!reviewer) return;
  await modal({
    title: "Correct details and run again",
    intro: "A new analysis run is created from the same stored documents. The earlier run and all decisions on it stay in the history.",
    body: formHost, wide: true,
    actions: (close) => {
      const go = h("button", { class: "btn btn-primary", type: "button" }, "Run again");
      go.addEventListener("click", async () => {
        if (!reason.value.trim()) { reason.setAttribute("aria-invalid", "true"); reason.focus(); return; }
        go.disabled = true;
        go.prepend(h("span", { class: "spinner", "aria-hidden": "true" }));
        try {
          ctx.state.view = await api.rerun(ctx.caseId, { reviewer, reason: reason.value, metadata: readMetadata(formHost) });
          ctx.state.runId = null;
          close(true);
          toast("Analysis run again. The earlier run is kept in the history.");
          await ctx.reload(null);
        } catch (error) {
          toast(error.message, "error");
          go.disabled = false;
          go.querySelector(".spinner")?.remove();
        }
      });
      return [h("button", { class: "btn btn-quiet", type: "button", onclick: () => close(null) }, "Cancel"), go];
    },
  });
}

/* ------------------------------------------------------------------ documents */

function documentsTab(ctx) {
  const { view } = ctx.state;
  const out = [h("p", { class: "muted small" }, "Text extraction cannot prove what a page visibly shows. Check each original for reading order, hidden or missing text and completeness.")];
  for (const doc of view.documents) {
    const status = DOC_STATUS[doc.status] || { label: doc.status, ink: "rejected" };
    const card = h("section", { class: "doc-card", "aria-label": doc.name },
      h("div", { class: "doc-card-head" }, icon("file"), h("h3", {}, doc.name),
        h("span", { class: "pill plain" }, doc.role === "contract" ? "Contract" : "Invoice"),
        h("span", { class: `pill ink-${status.ink}` }, status.label),
        h("span", { class: `pill ${doc.integrity === "VERIFIED" ? "ink-validated" : "ink-contradiction"}` },
          doc.integrity === "VERIFIED" ? "File fingerprint verified" : "File fingerprint mismatch")),
      h("div", { class: "small muted" }, doc.analysed_for_evidence ? "Analysed for evidence." : "Shown for inspection only. Not analysed, and no fields are read from it."),
      h("div", { class: "hash" }, `SHA-256 ${doc.sha256}${doc.extractor ? `, read with ${doc.extractor}` : ""}`));
    if (doc.issues.length) card.append(h("ul", { class: "reasons ink-missing" }, doc.issues.map((i) => h("li", {}, ISSUES[i] || i))));
    if (doc.pages.length) {
      card.append(h("table", { class: "page-table" },
        h("thead", {}, h("tr", {}, h("th", {}, "Page"), h("th", {}, "Status"), h("th", {}, "Two-reading check"), h("th", {}, ""))),
        h("tbody", {}, doc.pages.map((p) => h("tr", {},
          h("td", {}, p.page_number),
          h("td", {}, p.issues.length ? p.issues.map((i) => h("div", {}, ISSUES[i] || i)) : (DOC_STATUS[p.status]?.label || p.status)),
          h("td", {}, ORDER_CHECK[p.order_check] || p.order_check),
          h("td", {}, h("button", { class: "btn btn-quiet btn-small", type: "button", onclick: () => { ctx.state.role = doc.role; ctx.state.page = p.page_number; ctx.state.mode = "pdf"; ctx.drawViewer(); } }, "View")))))));
    }
    if (canReview(view) && documentsAvailable(view)) {
      card.append(h("div", { class: "review-box" }, question({
        prompt: "Have you checked the original for reading order, hidden or missing text and completeness?",
        help: "Confirming this does not release a statutory proposal. All PDF proposals stay withheld in this prototype.",
        kind: "DOCUMENT_CHECK", target: doc.role, current: doc.decision, ctx,
      })));
    }
    out.push(card);
  }
  return out;
}

/* ------------------------------------------------------------------ history */

function historyTab(ctx) {
  const { view } = ctx.state;
  const out = [];
  const intact = view.chain.status === "INTACT";
  out.push(h("div", { class: `chain ${intact ? "" : "broken"}` }, icon(intact ? "chain" : "alert"),
    intact ? `History intact: ${view.chain.events} entries, each linked to the one before by a fingerprint. The app never edits or deletes entries. This local history is not signed, so it is tamper-evident, not tamper-proof.`
      : `History check failed at entry ${view.chain.broken_at}. The local database may have been altered.`));
  if (view.runs.length > 1) {
    out.push(h("div", { class: "section-title" }, h("h3", {}, "Analysis runs")));
    out.push(h("div", { class: "row" }, view.runs.map((r) => h("button", {
      class: `btn btn-small ${r.id === view.run.id ? "btn-primary" : ""}`, type: "button",
      onclick: () => { ctx.state.runId = r.id === view.runs.at(-1).id ? null : r.id; ctx.reload(ctx.state.runId); },
    }, `Run ${r.sequence}${r.id === view.runs.at(-1).id ? " (latest)" : ""}`))));
  }
  out.push(h("div", { class: "section-title" }, h("h3", {}, "Activity"), h("span", { class: "spacer" }),
    canReview(view) ? h("button", { class: "btn btn-small", type: "button", onclick: () => addNote(ctx) }, "Add note") : null));
  const sequence = Object.fromEntries(view.runs.map((r) => [r.id, r.sequence]));
  out.push(h("ol", { class: "timeline" }, [...view.events].reverse().map((e) => {
    const p = e.payload;
    const human = e.actor !== "system";
    const kindCls = e.kind === "ANALYSIS_RUN" ? "run" : human ? "human" : "system";
    const decision = p.decision && DECISIONS[e.kind] ? DECISIONS[e.kind][p.decision] : null;
    const body = h("div", { class: "tl-body" });
    if (e.kind === "QUOTE_CHECK" && p.target_label) body.append(h("div", { class: "target" }, `“${p.target_label}”`));
    if (e.kind === "INTERPRETATION_REVIEW" && p.target_label) {
      const [fact, value] = p.target_label.split("=");
      body.append(h("div", {}, fact === "contradiction" ? "Clause cited as conflicting" : `${FACTS[fact]?.question || fact} ${factAnswer(fact, value)}`));
    }
    if (e.kind === "DOCUMENT_CHECK") body.append(h("div", {}, p.target_label === "contract" ? "Contract" : "Invoice"));
    if (p.correction) body.append(h("div", {}, `Reviewer reading: ${factAnswer(p.correction.fact, p.correction.reviewer_value)}. Automated result unchanged.`));
    if (e.kind === "ANALYSIS_RUN") {
      body.append(h("div", {}, `${METHODS[p.method] || p.method}. ${FINDINGS[p.factual_evidence_status]?.title || p.factual_evidence_status}. Statutory proposal withheld.`));
      if (p.reason) body.append(h("div", {}, `Reason: ${p.reason}`));
      if (p.changed_fields) {
        body.append(h("div", {}, Object.entries(p.changed_fields).map(([k, v]) =>
          h("div", { class: "small" }, `${FIELDS[k] || k}: ${v.before || "blank"} → ${v.after || "blank"}`))));
      }
    }
    if (e.kind === "CASE_CREATED") body.append(h("div", {}, p.origin === "SAMPLE" ? "From a synthetic sample" : "From uploaded documents"));
    if (p.note) body.append(h("div", {}, p.note));
    return h("li", { class: `tl ${kindCls}` }, h("span", { class: "tl-dot", "aria-hidden": "true" }),
      h("div", { class: "tl-head" }, h("b", {}, EVENTS[e.kind] || e.kind), decision ? h("span", {}, decision) : null,
        h("span", { class: "tl-time" }, `${human ? e.actor : "System"}, ${formatTime(e.created_at)}`)),
      body,
      e.run_id ? h("div", { class: "tl-run-label" }, `Run ${sequence[e.run_id]}`) : null);
  })));
  return out;
}

/* ------------------------------------------------------------------ dialogs */

async function addNote(ctx) {
  const note = h("textarea", { class: "textarea", id: "f-note", maxlength: "4000" });
  const ok = await modal({
    title: "Add a note",
    intro: "Notes are saved in the review history with your name and the time.",
    body: h("div", { class: "field" }, h("label", { for: "f-note" }, "Note"), note),
    actions: (close) => [
      h("button", { class: "btn btn-quiet", type: "button", onclick: () => close(null) }, "Cancel"),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => {
        if (!note.value.trim()) { note.setAttribute("aria-invalid", "true"); note.focus(); return; }
        close(note.value);
      } }, "Add note"),
    ],
  });
  if (ok) await ctx.record({ kind: "NOTE", decision: null, note: ok });
}

async function changeStatus(ctx) {
  const { view } = ctx.state;
  const outstanding = view.progress.total - view.progress.done;
  const options = [
    ["IN_REVIEW", "In review", "You are still working through the evidence."],
    ["ESCALATED_TO_QUALIFIED_TAX_REVIEW", "Escalate to a tax specialist", "Hand over for a qualified decision on the tax treatment."],
    ["REVIEW_RECORD_COMPLETE", "Review record complete", "Your evidence checks are recorded. The tax treatment still needs qualified sign-off outside this tool."],
  ];
  if (view.case_status === "REVIEW_RECORD_COMPLETE" || view.case_status === "ESCALATED_TO_QUALIFIED_TAX_REVIEW") {
    options.push(["REOPENED", "Reopen", "Return the case to review."]);
  }
  const list = h("div", { class: "choice-cards", role: "radiogroup" }, options.map(([value, title, text], i) =>
    h("label", { class: "choice" }, h("input", { type: "radio", name: "status", value, checked: i === 0 }), h("span", {}, h("strong", {}, title), h("p", {}, text)))));
  const note = h("textarea", { class: "textarea", id: "f-status-note", maxlength: "4000" });
  const result = await modal({
    title: "Change status",
    intro: "No status approves a tax treatment or authorises withholding.",
    body: h("div", { class: "stack" }, list,
      outstanding ? notice("missing", "info", `${outstanding} checks are not recorded yet.`, " You can still change the status. The history will show what was checked.") : null,
      h("div", { class: "field" }, h("label", { for: "f-status-note" }, "Note ", h("span", { class: "optional" }, "(optional)")), note)),
    actions: (close) => [
      h("button", { class: "btn btn-quiet", type: "button", onclick: () => close(null) }, "Cancel"),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => close(list.querySelector("input:checked").value) }, "Change status"),
    ],
  });
  if (result) await ctx.record({ kind: "CASE_STATUS", decision: result, note: note.value });
}

/* ------------------------------------------------------------------ helpers */

function notice(ink, iconName, title, text, extra) {
  return h("div", { class: `notice ink-${ink}` }, icon(iconName), h("div", { class: "stack" }, h("div", {}, h("b", {}, title), text), extra || null));
}

function loadingShell() {
  return h("div", { class: "page", "aria-busy": "true" },
    h("div", { class: "skeleton sk-line", style: null }),
    h("div", { class: "panel side-card" }, [0, 1, 2, 3, 4].map(() => h("div", { class: "skeleton sk-line" }))));
}
