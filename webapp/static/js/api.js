// Thin client for the local API. Every POST carries the CSRF header the server requires.
async function request(method, path, body, headers = {}) {
  const init = { method, headers: { "X-TDS-Review": "1", ...headers }, credentials: "same-origin" };
  if (body !== undefined) {
    if (body instanceof ArrayBuffer || body instanceof Blob) init.body = body;
    else {
      init.body = JSON.stringify(body);
      init.headers["Content-Type"] = "application/json";
    }
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new Error("The local review server is not responding. Check that review_app.py is still running.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

export const api = {
  liveConfig: () => request("GET", "/api/live/config"),
  prepareLive: (body) => request("POST", "/api/live/prepare", body),
  health: () => request("GET", "/api/health"),
  cases: () => request("GET", "/api/cases"),
  case: (id, run) => request("GET", `/api/cases/${encodeURIComponent(id)}${run ? `?run=${encodeURIComponent(run)}` : ""}`),
  samples: () => request("GET", "/api/samples"),
  openSample: (id) => request("POST", `/api/samples/${encodeURIComponent(id)}/cases`),
  upload: async (file) => request("POST", "/api/documents", await file.arrayBuffer(),
    { "Content-Type": "application/pdf", "X-Filename": encodeURIComponent(file.name) }),
  createCase: (body) => request("POST", "/api/cases", body),
  rerun: (id, body) => request("POST", `/api/cases/${encodeURIComponent(id)}/runs`, body),
  record: (id, body) => request("POST", `/api/cases/${encodeURIComponent(id)}/events`, body),
  exportUrl: (id) => `/api/cases/${encodeURIComponent(id)}/export`,
};
