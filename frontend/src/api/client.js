const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  return res;
}

export async function health() {
  const r = await handle(await fetch(`${API}/health`));
  return r.json();
}

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const r = await handle(await fetch(`${API}/upload`, { method: "POST", body: fd }));
  return r.json();
}

export async function getScore(sid) {
  return (await handle(await fetch(`${API}/score/${sid}`))).json();
}

export async function redflags(sid) {
  return (await handle(await fetch(`${API}/redflags/${sid}`, { method: "POST" }))).json();
}

export async function rewrite(sid) {
  return (await handle(await fetch(`${API}/rewrite/${sid}`, { method: "POST" }))).json();
}

export async function jdmatch(sid, jdText) {
  return (await handle(await fetch(`${API}/jdmatch/${sid}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText }),
  }))).json();
}

// Returns { blob, before, after }
export async function generatePdf(sid, template = "auto") {
  // Backend route is @app.post("/generate/{sid}") with `template` as a
  // query param and no JSON body - so this MUST be a POST.
  const res = await handle(await fetch(
    `${API}/generate/${sid}?template=${template}`,
    { method: "POST" },
  ));
  const blob = await res.blob();
  return {
    blob,
    before: res.headers.get("X-Overall-Before"),
    after: res.headers.get("X-Overall-After"),
  };
}

export async function rescore(sid) {
  return (await handle(await fetch(`${API}/rescore/${sid}`))).json();
}

export async function originalPdfBlob(sid) {
  const res = await fetch(`${API}/original/${sid}`);
  if (!res.ok) return null;
  return await res.blob();
}
