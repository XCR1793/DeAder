const el = (id) => document.getElementById(id);

const urlInput = el("url");
const goBtn = el("go");
const tokenBtn = el("tokenBtn");
const statusEl = el("status");
const barEl = el("bar");
const barFill = el("barFill");

function getToken() {
  return localStorage.getItem("deader_token") || "";
}

function setToken(token) {
  if (!token) localStorage.removeItem("deader_token");
  else localStorage.setItem("deader_token", token);
}

async function api(path, opts = {}) {
  const headers = Object.assign({ "content-type": "application/json" }, opts.headers || {});
  const token = getToken();
  if (token) headers["x-auth-token"] = token;

  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      msg = data?.detail || data?.error || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function setStatus(text, progress01) {
  statusEl.textContent = text || "";
  if (typeof progress01 === "number") {
    barEl.style.display = "block";
    const pct = Math.max(0, Math.min(100, Math.round(progress01 * 100)));
    barFill.style.width = `${pct}%`;
  } else {
    barEl.style.display = "none";
    barFill.style.width = "0%";
  }
}

async function poll(jobId) {
  while (true) {
    const j = await api(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "GET" });
    if (j.status === "downloading" || j.status === "queued") {
      const pct = typeof j.progress === "number" ? j.progress : 0;
      const extra = [];
      if (j.eta_seconds != null) extra.push(`ETA ${j.eta_seconds}s`);
      if (j.speed) extra.push(j.speed);
      setStatus(`${j.status}… ${Math.round(pct * 100)}%${extra.length ? ` (${extra.join(", ")})` : ""}`, pct);
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    if (j.status === "finished") {
      setStatus("Opening player…", 1);
      // If user uses query-token auth, keep it working across navigation.
      const token = getToken();
      const url = token ? `${j.watch_url}?token=${encodeURIComponent(token)}` : j.watch_url;
      window.location.assign(url);
      return;
    }
    if (j.status === "error") {
      setStatus(`Error: ${j.error || "unknown error"}`);
      return;
    }
    setStatus(`Unknown status: ${j.status}`);
    return;
  }
}

goBtn.addEventListener("click", async () => {
  const url = (urlInput.value || "").trim();
  if (!url) {
    setStatus("Paste a URL first.");
    return;
  }
  try {
    setStatus("Creating job…", 0);
    const { id } = await api("/api/jobs", { method: "POST", body: JSON.stringify({ url }) });
    await poll(id);
  } catch (e) {
    setStatus(`Error: ${e.message || e}`);
  }
});

tokenBtn.addEventListener("click", () => {
  const cur = getToken();
  const next = window.prompt("Server token (DEADER_TOKEN). Leave blank to clear.", cur || "");
  if (next == null) return;
  setToken(next.trim());
  setStatus(next.trim() ? "Token saved." : "Token cleared.");
});

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") goBtn.click();
});

setStatus("");

