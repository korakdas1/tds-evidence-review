import { api } from "../api.js";
import { h, icon, clear, formatBytes } from "../dom.js";
import { handoff, runOverlay, toast } from "../ui.js";

const EXTRACTION_TEMPLATE = {
  personnel_supplied: "yes",
  worker_supervisor: "customer",
  supporting_quotes: [
    { fact: "personnel_supplied", value: "yes", quote: "Exact sentence copied from the contract" },
    { fact: "worker_supervisor", value: "customer", quote: "Exact sentence copied from the contract" },
  ],
  missing_facts: [],
  contradictory_evidence: [],
};

export function metadataFields(values = {}) {
  const today = new Date().toISOString().slice(0, 10);
  const field = (name, label, control, hint) => h("div", { class: "field" },
    h("label", { for: `f-${name}` }, label), control, hint ? h("span", { class: "hint" }, hint) : null);
  const input = (name, attrs = {}) => h("input", { class: "input", id: `f-${name}`, name, value: values[name] ?? "", ...attrs });
  const residency = h("select", { class: "select", id: "f-payee_residency", name: "payee_residency" },
    [["India resident", "Resident in India"], ["Non-resident", "Non-resident"], ["", "Not established yet"]]
      .map(([value, label]) => h("option", { value, selected: (values.payee_residency ?? "India resident") === value }, label)));
  return h("div", { class: "stack" },
    h("div", { class: "two-col" },
      field("id", "Case reference", input("id", { required: true, maxlength: "120", placeholder: "For example INV-2026-0142", value: values.id ?? `REV-${today.replaceAll("-", "")}` }),
        "Your own reference, such as the invoice or vendor number."),
      field("invoice_description", "Invoice description", input("invoice_description", { required: true, maxlength: "500", placeholder: "What the invoice charges for" }))),
    h("div", { class: "two-col" },
      field("payer_type", "Payer type", input("payer_type", { required: true, list: "payer-types", maxlength: "200", value: values.payer_type ?? "Indian resident private company" }),
        "The prototype only proposes references for Indian resident private company payers."),
      field("payee_legal_form", "Vendor legal form", input("payee_legal_form", { required: true, list: "payer-types", maxlength: "200", value: values.payee_legal_form ?? "Indian resident private company" }))),
    h("div", { class: "two-col" },
      field("payee_residency", "Vendor residency", residency, "Non-resident vendors are outside this prototype's scope."),
      h("div")),
    h("div", { class: "two-col" },
      field("credit_date", "Credit date", input("credit_date", { type: "date", required: true })),
      field("payment_date", "Payment date", input("payment_date", { type: "date", required: true }))),
    h("p", { class: "hint small muted" }, "The earlier of the two dates decides which Income-tax Act applies: before 1 April 2026 the 1961 Act, from then on the 2025 Act."),
    h("datalist", { id: "payer-types" },
      ["Indian resident private company", "Indian resident public company", "Individual", "Partnership firm", "Limited liability partnership"]
        .map((v) => h("option", { value: v }))));
}

export function readMetadata(form) {
  const names = ["id", "invoice_description", "payer_type", "payee_residency", "payee_legal_form", "credit_date", "payment_date"];
  return Object.fromEntries(names.map((n) => [n, (form.querySelector(`[name="${n}"]`)?.value ?? "").trim()]));
}

export async function renderNewReview(main) {
  const files = { contract: null, invoice: null };
  const form = h("form", { class: "stack", novalidate: true });
  const errorHost = h("div", { role: "alert" });
  const extraction = h("textarea", { class: "textarea code", id: "f-extraction", spellcheck: "false", "aria-describedby": "extraction-hint" });
  const extractionBox = h("div", { class: "field", hidden: true },
    h("label", { for: "f-extraction" }, "Supplied extraction (JSON)"),
    extraction,
    h("span", { class: "hint", id: "extraction-hint" },
      "Five fields in the same format the pipeline expects from a model. It is checked by the same validators and recorded as simulated. Use only synthetic or properly authorised content."),
    h("div", {}, h("button", { class: "btn btn-small", type: "button", onclick: () => { extraction.value = JSON.stringify(EXTRACTION_TEMPLATE, null, 2); } }, "Insert template")));

  const methodChoice = (value, title, text, checked) => h("label", { class: "choice" },
    h("input", { type: "radio", name: "method", value, checked, onchange: () => { extractionBox.hidden = value !== "supplied_extraction"; } }),
    h("span", {}, h("strong", {}, title), h("p", {}, text)));

  const contractSlot = fileSlot("contract", "Contract PDF", "Required. The contract is the only document analysed for evidence.", files);
  const invoiceSlot = fileSlot("invoice", "Invoice PDF", "Optional. Shown for your inspection only. No fields are read from it.", files);
  const title = h("input", { class: "input", id: "f-title", name: "title", maxlength: "160", placeholder: "For example, Warehouse staffing, October" });

  form.append(
    h("section", { class: "panel form-section" },
      sectionHead(1, "Documents", "PDFs with selectable text, up to 5 MiB and 20 pages each. They are stored only in this computer's local data folder."),
      h("div", { class: "two-col" }, contractSlot, invoiceSlot)),
    h("section", { class: "panel form-section" },
      sectionHead(2, "Transaction details", "Type these in yourself. They are never read from the PDFs, and the review marks them as manually provided."),
      h("div", { class: "stack" },
        h("div", { class: "field" }, h("label", { for: "f-title" }, "Review title ", h("span", { class: "optional" }, "(optional)")), title),
        metadataFields())),
    h("section", { class: "panel form-section" },
      sectionHead(3, "How to analyse", "Both options run entirely on this computer."),
      h("div", { class: "choice-cards", role: "radiogroup", "aria-label": "Analysis method" },
        methodChoice("baseline", "Offline rule checks (recommended)", "The existing conservative checks read the contract text. No AI is involved, so no AI suggestions are produced.", true),
        methodChoice("supplied_extraction", "Replay a supplied extraction (advanced)", "Paste an extraction in the model's output format to see how the validators treat it. This is a simulation: no model is called, and the run is labelled as such.", false)),
      extractionBox),
    errorHost,
    h("div", { class: "row" },
      h("a", { class: "btn btn-quiet", href: "#/" }, "Cancel"),
      h("span", { class: "spacer" }),
      h("button", { class: "btn btn-primary", type: "submit" }, "Run evidence review")));

  main.append(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {},
      h("div", { class: "crumbs" }, h("a", { href: "#/" }, "Reviews"), h("span", { "aria-hidden": "true" }, "/"), h("span", {}, "New review")),
      h("h1", {}, "New evidence review"),
      h("p", {}, "Add the contract, enter what you know about the transaction, and run the checks. You review every finding afterwards."))),
    h("div", { class: "form-grid" }, form,
      h("aside", { class: "panel aside-note" },
        h("h3", {}, "What the review will and won't do"),
        h("ul", {},
          h("li", {}, "Finds exact sentences about who supplies and supervises workers, with page and character references."),
          h("li", {}, "Flags scanned pages, unusual layouts and contradictions instead of guessing."),
          h("li", {}, "Never decides the tax treatment, authorises withholding or approves anything."),
          h("li", {}, "Withholds every statutory proposal for PDFs until a qualified person has reviewed it."))))));

  // Editing after a failed submit clears the stale summary and the field's error state.
  const onEdit = (e) => { e.target.removeAttribute?.("aria-invalid"); clear(errorHost); };
  form.addEventListener("input", onEdit);
  form.addEventListener("change", onEdit);

  if (handoff.file) {
    contractSlot.setFile(handoff.file);
    handoff.file = null;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clear(errorHost);
    const metadata = readMetadata(form);
    const problems = [];
    if (!files.contract) problems.push("Add a contract PDF.");
    for (const [name, label] of [["id", "case reference"], ["invoice_description", "invoice description"], ["payer_type", "payer type"], ["payee_legal_form", "vendor legal form"], ["credit_date", "credit date"], ["payment_date", "payment date"]]) {
      const el = form.querySelector(`[name="${name}"]`);
      el.removeAttribute("aria-invalid");
      if (!metadata[name]) { problems.push(`Enter the ${label}.`); el.setAttribute("aria-invalid", "true"); }
    }
    const method = form.querySelector('input[name="method"]:checked').value;
    let supplied = null;
    if (method === "supplied_extraction") {
      try { supplied = JSON.parse(extraction.value); } catch { problems.push("The supplied extraction is not valid JSON."); }
    }
    if (problems.length) {
      errorHost.append(h("div", { class: "notice ink-contradiction" }, icon("alert"),
        h("div", {}, h("b", {}, "Some details need attention"), h("ul", {}, problems.map((p) => h("li", {}, p))))));
      errorHost.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const steps = ["Uploading the contract", files.invoice ? "Uploading the invoice" : "No invoice to upload", "Reading PDF text and checking evidence"];
    const overlay = runOverlay(steps);
    try {
      overlay.step(0);
      const contract = await api.upload(files.contract);
      overlay.step(1);
      const invoice = files.invoice ? await api.upload(files.invoice) : null;
      overlay.step(2);
      const view = await api.createCase({
        title: title.value.trim(), metadata, contract_sha256: contract.sha256,
        invoice_sha256: invoice ? invoice.sha256 : null, method, supplied_extraction: supplied,
      });
      overlay.step(3);
      toast("Evidence review created");
      location.hash = `#/cases/${encodeURIComponent(view.case.id)}`;
    } catch (error) {
      errorHost.append(h("div", { class: "notice ink-contradiction" }, icon("alert"), h("div", {}, h("b", {}, "The review could not run. "), error.message)));
    } finally {
      overlay.close();
    }
  });
  return null;
}

function sectionHead(number, title, text) {
  return h("div", { class: "section-head" }, h("span", { class: "step-no", "aria-hidden": "true" }, number),
    h("div", {}, h("h2", {}, title), h("p", {}, text)));
}

function fileSlot(role, label, hint, files) {
  const id = `file-${role}`;
  const input = h("input", { type: "file", accept: "application/pdf,.pdf", id, class: "sr-only" });
  const host = h("div");
  const slot = h("div", { class: "file-slot" }, h("span", { class: "field-label", id: `${id}-label` }, label), host, h("span", { class: "hint small muted" }, hint), input);
  const draw = () => {
    clear(host);
    const file = files[role];
    if (file) {
      host.append(h("div", { class: "file-chip" }, icon("file"),
        h("div", { class: "grow" }, h("div", { class: "name" }, file.name), h("div", { class: "meta" }, formatBytes(file.size))),
        h("button", { class: "btn btn-quiet btn-small", type: "button", "aria-label": `Remove ${label}`, onclick: () => { files[role] = null; input.value = ""; draw(); } }, icon("x"))));
      return;
    }
    const zone = h("label", { class: "dropzone", for: id, tabindex: "0", "aria-labelledby": `${id}-label` },
      icon("upload"), h("strong", {}, "Choose a PDF"), h("span", { class: "small" }, "or drop it here"));
    zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
    zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("drag"); slot.setFile(e.dataTransfer.files[0]); });
    host.append(zone);
  };
  slot.setFile = (file) => {
    if (!file) return;
    if (!/\.pdf$/i.test(file.name)) { toast("Only PDF files can be reviewed", "error"); return; }
    if (file.size > 5 * 1024 * 1024) { toast("This PDF is larger than the 5 MiB limit", "error"); return; }
    files[role] = file;
    draw();
  };
  input.addEventListener("change", () => slot.setFile(input.files[0]));
  draw();
  return slot;
}
