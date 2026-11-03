import { h, icon, clear, initials } from "./dom.js";

const REVIEWER_KEY = "tds-review.reviewer";

// Files dropped on the dashboard are handed to the new-review form without a round trip.
export const handoff = { file: null };

export function toast(message, kind = "ok") {
  const root = document.getElementById("toasts");
  const el = h("div", { class: `toast ${kind === "error" ? "error" : ""}` }, icon(kind === "error" ? "alert" : "check"), message);
  root.append(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 3200);
}

export function modal({ title, intro, body, actions, wide }) {
  const root = document.getElementById("modal-root");
  const previous = document.activeElement;
  let resolveFn;
  const done = new Promise((resolve) => { resolveFn = resolve; });
  // The page behind an open dialog is inert: not focusable, clickable or exposed to assistive tech.
  const background = [document.querySelector(".topbar"), document.getElementById("main")];
  background.forEach((el) => { if (el) el.inert = true; });
  const close = (value) => {
    background.forEach((el) => { if (el) el.inert = false; });
    clear(root);
    document.removeEventListener("keydown", onKey);
    previous?.focus?.();
    resolveFn(value);
  };
  const onKey = (event) => {
    if (event.key === "Escape") close(null);
    if (event.key !== "Tab") return;
    // Keep keyboard focus inside the dialog while it is open.
    const items = [...dialog.querySelectorAll("button, input, select, textarea, a[href]")].filter((el) => !el.disabled && el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
  };
  const titleId = `m-${Math.random().toString(36).slice(2)}`;
  const dialog = h("div", { class: `modal ${wide ? "wide" : ""}`, role: "dialog", "aria-modal": "true", "aria-labelledby": titleId },
    h("div", { class: "modal-head" }, h("h2", { id: titleId }, title), intro ? h("p", {}, intro) : null),
    body,
    h("div", { class: "modal-foot" }, actions(close)));
  const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(null); } }, dialog);
  clear(root).append(backdrop);
  document.addEventListener("keydown", onKey);
  (dialog.querySelector("input, textarea, select") || dialog.querySelector("button"))?.focus();
  return done;
}

export function getReviewer() {
  return localStorage.getItem(REVIEWER_KEY) || "";
}

export function renderReviewerChip() {
  const chip = document.getElementById("reviewer-chip");
  const name = getReviewer();
  clear(chip).append(
    h("span", { class: "avatar" }, name ? initials(name) : "?"),
    h("span", { class: "chip-label" }, name ? `Reviewing as ${name}` : "Set reviewer name"));
}

export async function askReviewer(force = false) {
  const current = getReviewer();
  if (current && !force) return current;
  const input = h("input", { class: "input", id: "reviewer-name", value: current, maxlength: "80", autocomplete: "name", placeholder: "For example, A. Sharma" });
  const result = await modal({
    title: "Who is reviewing?",
    intro: "Your name is stamped on every decision in the review history. It is self-declared on this computer, not a verified login.",
    body: h("div", { class: "field" }, h("label", { for: "reviewer-name" }, "Reviewer name"), input),
    actions: (close) => [
      h("button", { class: "btn btn-quiet", type: "button", onclick: () => close(null) }, "Cancel"),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => {
        const value = input.value.trim();
        if (!value) { input.setAttribute("aria-invalid", "true"); input.focus(); return; }
        close(value);
      } }, "Save name"),
    ],
  });
  if (result) {
    localStorage.setItem(REVIEWER_KEY, result);
    renderReviewerChip();
  }
  return result;
}

export function runOverlay(steps, live = false) {
  const items = steps.map((label) => h("li", {}, h("span", { class: "step-icon", "aria-hidden": "true" }), label));
  const overlay = h("div", { class: "overlay", role: "alertdialog", "aria-live": "polite", "aria-label": "Running evidence review" },
    h("div", { class: "panel run-card" },
      h("div", {}, h("h3", {}, "Running the evidence review"),
        h("p", { class: "muted small" }, live ? "The confirmed contract text is being sent to the configured external provider. Tax treatment still requires human review." : "Everything runs on this computer. No model or network is used.")),
      h("ol", { class: "run-steps" }, items)));
  document.body.append(overlay);
  return {
    step(index) {
      items.forEach((item, i) => { item.className = i < index ? "done" : i === index ? "active" : ""; });
    },
    close() { overlay.remove(); },
  };
}

export async function confirmLive(prepared) {
  return await modal({
    title: "Send this contract to an external AI provider?",
    intro: prepared.notice,
    body: h("div", { class: "stack" },
      h("p", {}, `Configured model: ${prepared.model}. Mode: ${prepared.execution_kind}.`),
      h("p", {}, "One request only, zero-dollar price limit, no paid fallback. Confirmation expires after five minutes and applies only to these documents and transaction details.")),
    actions: (close) => [
      h("button", { class: "btn btn-quiet", type: "button", onclick: () => close(false) }, "Cancel, keep data local"),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => close(true) }, "Confirm this one external request"),
    ],
  });
}
