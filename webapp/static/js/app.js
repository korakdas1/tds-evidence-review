import { clear } from "./dom.js";
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
  const main = document.getElementById("main");
  const hash = location.hash.replace(/^#/, "") || "/";
  const parts = hash.split("?")[0].split("/").filter(Boolean);
  if (cleanup) { cleanup(); cleanup = null; }
  clear(main);
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
  main.focus({ preventScroll: true });
}

initTheme();
renderReviewerChip();
document.getElementById("reviewer-chip").addEventListener("click", () => askReviewer(true));
window.addEventListener("hashchange", route);
route();
