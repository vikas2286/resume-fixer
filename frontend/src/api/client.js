const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ---- per-browser identity + admin bypass ---------------------------------
// A random UUID is generated on first visit and kept in localStorage; every
// request carries it as X-Client-Id so the backend can meter the daily AI
// limit.  Visiting the site once as /?admin=<ADMIN_TOKEN> stores the token
// (sent as X-Admin-Token) which makes that browser unlimited forever.
const CLIENT_ID_KEY = "rf_client_id";
const ADMIN_TOKEN_KEY = "rf_admin_token";

export function clientId() {
  let id = null;
  try { id = localStorage.getItem(CLIENT_ID_KEY); } catch { /* private mode */ }
  if (!id) {
    id = (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : "c-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    try { localStorage.setItem(CLIENT_ID_KEY, id); } catch { /* ignore */ }
  }
  return id;
}

// One-time admin activation: read ?admin=<token> from the URL, remember it,
// then strip it from the address bar so the secret isn't shared by copy-paste.
export function initAdminFromUrl() {
  try {
    const q = new URLSearchParams(window.location.search);
    const t = q.get("admin");
    if (t) {
      localStorage.setItem(ADMIN_TOKEN_KEY, t);
      q.delete("admin");
      const rest = q.toString();
      window.history.replaceState({}, "",
        window.location.pathname + (rest ? "?" + rest : "") + window.location.hash);
    }
  } catch { /* ignore */ }
}

export function isAdmin() {
  try { return !!localStorage.getItem(ADMIN_TOKEN_KEY); } catch { return false; }
}

function authHeaders(extra = {}) {
  const h = { "X-Client-Id": clientId(), ...extra };
  try {
    const t = localStorage.getItem(ADMIN_TOKEN_KEY);
    if (t) h["X-Admin-Token"] = t;
  } catch { /* ignore */ }
  return h;
}

async function handle(res) {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      if (j && j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* body wasn't JSON - keep statusText */ }
    const e = new Error(msg);
    e.status = res.status;
    throw e;
  }
  return res;
}

// Current daily-AI-usage state for this browser (remaining count, admin flag).
export async function getUsage() {
  return (await handle(await fetch(`${API}/usage`, { headers: authHeaders() }))).json();
}

export async function health() {
  const r = await handle(await fetch(`${API}/health`));
  return r.json();
}

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const r = await handle(await fetch(`${API}/upload`, {
    method: "POST", body: fd, headers: authHeaders(),
  }));
  return r.json();
}

export async function getScore(sid) {
  return (await handle(await fetch(`${API}/score/${sid}`, { headers: authHeaders() }))).json();
}

export async function redflags(sid) {
  return (await handle(await fetch(`${API}/redflags/${sid}`, {
    method: "POST", headers: authHeaders(),
  }))).json();
}

export async function rewrite(sid) {
  return (await handle(await fetch(`${API}/rewrite/${sid}`, {
    method: "POST", headers: authHeaders(),
  }))).json();
}

export async function jdmatch(sid, jdText) {
  return (await handle(await fetch(`${API}/jdmatch/${sid}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ jd_text: jdText }),
  }))).json();
}

// Returns { blob, before, after }
export async function generatePdf(sid, template = "auto") {
  // Backend route is @app.post("/generate/{sid}") with `template` as a
  // query param and no JSON body - so this MUST be a POST.
  const res = await handle(await fetch(
    `${API}/generate/${sid}?template=${template}`,
    { method: "POST", headers: authHeaders() },
  ));
  const blob = await res.blob();
  return {
    blob,
    before: res.headers.get("X-Overall-Before"),
    after: res.headers.get("X-Overall-After"),
  };
}

export async function rescore(sid) {
  return (await handle(await fetch(`${API}/rescore/${sid}`, { headers: authHeaders() }))).json();
}

export async function originalPdfBlob(sid) {
  const res = await fetch(`${API}/original/${sid}`, { headers: authHeaders() });
  if (!res.ok) return null;
  return await res.blob();
}
