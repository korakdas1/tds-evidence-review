import { api } from "../api.js";
import { h, icon, clear, relativeTime } from "../dom.js";
import { CASE_STATUS, FINDINGS, METHODS } from "../lexicon.js";
import { handoff, runOverlay, toast } from "../ui.js";

const FILTERS = [
  ["ALL", "All"],
  ["AWAITING_REVIEW", "Awaiting review"],
  ["IN_REVIEW", "In review"],
  ["ESCALATED_TO_QUALIFIED_TAX_REVIEW", "Escalated"],
  ["REVIEW_RECORD_COMPLETE", "Record complete"],
];
const INK_ORDER = ["contradiction", "validated", "ai_suggestion", "rejected", "unvalidated"];

export async function renderDashboard(main) {
  let filter = "ALL";
  const listHost = h("div", { class: "panel case-list", "aria-busy": "true" }, skeletonRows());
  const filterHost = h("div", { class: "filters", role: "toolbar", "aria-label": "Filter reviews by status" });
  const sampleHost = h("div", {}, h("div", { class: "skeleton sk-line" }), h("div", { class: "skeleton sk-line" }));

  main.append(h("div", { class: "page" },
    h("div", { class: "page-head" },
      h("div", {},
        h("h1", {}, "Evidence reviews"),
        h("p", {}, "Check what a vendor contract actually says about who supplies and supervises the workers, with every finding traced to its page and characters. The tool gathers evidence; tax treatment stays with a qualified reviewer.")),
      h("a", { class: "btn btn-primary", href: "#/new" }, icon("plus"), "New review")),
    h("div", { class: "dash-grid" },
      h("section", { "aria-label": "Review cases" }, filterHost, listHost),
      h("aside", {},
        h("div", { class: "panel side-card" },
          h("h3", {}, "Start from a contract"),
          h("p", { class: "muted small" }, "Drop a contract PDF here to begin. You will add an invoice and the transaction details next."),
          h("div", { class: "divider" }),
          dropzone()),
        h("div", { class: "panel side-card" },
          h("h3", {}, "Synthetic samples"),
          h("p", { class: "muted small" }, "Invented documents that show each kind of finding. Opening one creates a new case."),
          sampleHost),
        h("div", { class: "panel side-card" },
          h("h3", {}, "Reading the colours"),
          h("p", { class: "muted small" }, "Colour always tells you who is making a claim."),
          inkKey())))));

  let cases = [];
  try {
    cases = await api.cases();
  } catch (error) {
    clear(listHost).append(h("div", { class: "empty" }, h("h3", {}, "Reviews could not be loaded"), h("p", {}, error.message)));
  }
  listHost.removeAttribute("aria-busy");

  const draw = () => {
    clear(filterHost);
    for (const [key, label] of FILTERS) {
      const count = key === "ALL" ? cases.length : cases.filter((c) => c.status === key).length;
      filterHost.append(h("button", {
        class: "filter", type: "button", "aria-pressed": String(filter === key),
        onclick: () => { filter = key; draw(); },
      }, label, h("b", {}, count)));
    }
    const shown = cases.filter((c) => filter === "ALL" || c.status === filter);
    clear(listHost);
    if (!cases.length) {
      listHost.append(h("div", { class: "empty" },
        h("h3", {}, "No reviews yet"),
        h("p", {}, "Upload a contract PDF to start a review, or open a synthetic sample to see how verified evidence, AI suggestions and contradictions are shown."),
        h("a", { class: "btn btn-primary", href: "#/new" }, icon("plus"), "New review")));
      return;
    }
    if (!shown.length) {
      listHost.append(h("div", { class: "empty" }, h("p", {}, "No reviews have this status.")));
      return;
    }
    listHost.append(h("div", { class: "case-head", "aria-hidden": "true" },
      h("span", {}, "Case"), h("span", {}, "Automated finding"), h("span", {}, "Your review"), h("span", {}, "Status")));
    for (const item of shown) listHost.append(caseRow(item));
  };
  draw();

  try {
    const samples = await api.samples();
    clear(sampleHost);
    for (const sample of samples) sampleHost.append(sampleItem(sample));
  } catch (error) {
    clear(sampleHost).append(h("p", { class: "field-error" }, error.message));
  }
  return null;
}

function caseRow(item) {
  const status = CASE_STATUS[item.status] || CASE_STATUS.AWAITING_REVIEW;
  const finding = FINDINGS[item.factual_status];
  const docs = item.documents.map((d) => d.name).join(" + ");
  const pct = item.progress.total ? Math.round((item.progress.done / item.progress.total) * 100) : 0;
  const tally = h("div", { class: "tally", "aria-label": tallyLabel(item.evidence_counts, item.missing_count) });
  for (const key of INK_ORDER) {
    for (let i = 0; i < (item.evidence_counts[key] || 0); i++) tally.append(h("span", { class: `ink-${key}` }));
  }
  for (let i = 0; i < item.missing_count; i++) tally.append(h("span", { class: "ink-missing" }));
  return h("a", { class: "case-row", href: `#/cases/${encodeURIComponent(item.id)}` },
    h("div", { class: "case-id" },
      h("div", { class: "case-title" }, item.title),
      h("div", { class: "case-meta" }, [item.reference, docs].filter(Boolean).join(", ") + (item.origin === "SAMPLE" ? " (synthetic sample)" : "")),
      h("div", { class: "case-meta" }, `${METHODS[item.method] || item.method}. Updated ${relativeTime(item.last_activity)}`)),
    h("div", {},
      h("div", { class: "finding-line" }, item.integrity === "FAILED" ? "Not shown: integrity check failed"
        : finding ? finding.title : item.factual_status),
      tally),
    h("div", { class: "progress" },
      h("span", {}, `${item.progress.done} of ${item.progress.total} checks`),
      h("div", { class: "progress-track" }, progressFill(pct))),
    h("div", { class: "stack" }, h("span", { class: `pill ${status.cls}` }, status.label),
      item.integrity === "FAILED" ? h("span", { class: "pill ink-contradiction" }, "Integrity check failed") : null));
}

export function progressFill(pct) {
  const fill = h("div", { class: "progress-fill" });
  fill.style.width = `${pct}%`;
  return fill;
}

function tallyLabel(counts, missing) {
  const parts = Object.entries(counts).map(([k, v]) => `${v} ${k.replace("_", " ")}`);
  if (missing) parts.push(`${missing} missing information`);
  return `Evidence: ${parts.join(", ") || "none"}`;
}

function sampleItem(sample) {
  const button = h("button", { class: "btn btn-small", type: "button" }, "Open");
  button.addEventListener("click", async () => {
    button.disabled = true;
    const overlay = runOverlay(["Copying the synthetic documents", "Reading PDF text and checking evidence", "Saving the case"]);
    overlay.step(1);
    try {
      const view = await api.openSample(sample.id);
      overlay.step(3);
      location.hash = `#/cases/${encodeURIComponent(view.case.id)}`;
    } catch (error) {
      toast(error.message, "error");
    } finally {
      overlay.close();
      button.disabled = false;
    }
  });
  return h("div", { class: "sample" },
    h("div", { class: "sample-title" }, h("span", {}, sample.title), button),
    h("p", {}, sample.summary));
}

function dropzone() {
  const input = h("input", { type: "file", accept: "application/pdf,.pdf", class: "sr-only", id: "dash-file", tabindex: "-1" });
  const zone = h("label", { class: "dropzone", for: "dash-file", tabindex: "0" },
    icon("upload"), h("strong", {}, "Drop a contract PDF"), h("span", { class: "small" }, "or click to choose. PDF only, up to 5 MiB."));
  const go = (file) => {
    if (!file) return;
    handoff.file = file;
    location.hash = "#/new";
  };
  input.addEventListener("change", () => go(input.files[0]));
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("drag"); go(e.dataTransfer.files[0]); });
  return h("div", {}, zone, input);
}

export function inkKey() {
  const rows = [
    ["validated", "Green", "validated by the rule checks"],
    ["ai_suggestion", "Violet", "suggested by an AI extraction, not verified"],
    ["contradiction", "Red", "clauses that contradict each other"],
    ["missing", "Amber", "information the review still needs"],
    ["rejected", "Grey", "blocked by a safety check"],
    ["reviewer", "Blue", "a decision made by a human reviewer"],
  ];
  return h("div", { class: "key-list" }, rows.map(([ink, name, text]) =>
    h("div", { class: `key-item ink-${ink}` }, h("span", { class: "key-swatch" }), h("span", {}, h("b", {}, name), `: ${text}`))));
}

function skeletonRows() {
  return [0, 1, 2].map(() => h("div", { class: "case-row" },
    h("div", {}, h("div", { class: "skeleton sk-line" }), h("div", { class: "skeleton sk-line" })),
    h("div", {}, h("div", { class: "skeleton sk-line" })),
    h("div", {}, h("div", { class: "skeleton sk-line" })),
    h("div", {}, h("div", { class: "skeleton sk-line" }))));
}
