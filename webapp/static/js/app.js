import { api } from "./api.js";
import { clear, h } from "./dom.js";
import { askReviewer, renderReviewerChip } from "./ui.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderNewReview } from "./views/new-review.js";
import { renderWorkspace } from "./views/workspace.js";

const THEME_KEY = "tds-review.theme";

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(stored || (prefersDark ? "dark" : "light"));
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  });
}

let cleanup = null;

async function route() {
  const host = document.getElementById("main");
  const hash = location.hash.replace(/^#/, "") || "/";
  const parts = hash.split("?")[0].split("/").filter(Boolean);
  if (cleanup) { cleanup(); cleanup = null; }
  // A fresh container per navigation: a slow view that finishes after the user has moved on
  // renders into a detached node instead of replacing the newer page.
  const main = h("div", { class: "route" });
  clear(host).append(main);
  document.querySelectorAll("[data-nav]").forEach((a) => a.removeAttribute("aria-current"));
  let nav = null;
  if (parts.length === 0) {
    nav = "reviews";
    cleanup = await renderDashboard(main);
  } else if (parts[0] === "new") {
    nav = "new";
    cleanup = await renderNewReview(main);
  } else if (parts[0] === "cases" && parts[1]) {
    cleanup = await renderWorkspace(main, decodeURIComponent(parts[1]));
  } else {
    location.hash = "#/";
    return;
  }
  if (nav) document.querySelector(`[data-nav="${nav}"]`)?.setAttribute("aria-current", "page");
  if (main.isConnected) host.focus({ preventScroll: true });
}

initTheme();
renderReviewerChip();
document.getElementById("reviewer-chip").addEventListener("click", () => askReviewer(true));
window.addEventListener("hashchange", route);
route();

api.liveConfig().then((config) => {
  if (!config.enabled) return;
  const flag = document.querySelector(".offline-flag");
  flag.textContent = `Offline by default; ${config.execution_kind === "SIMULATED" ? "simulated" : "external AI"} opt-in available`;
  flag.title = `Configured model: ${config.model}. Every external request needs explicit confirmation.`;
}).catch(() => {});
