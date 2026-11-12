const $ = (id) => document.getElementById(id);
const PROFILE_FIELDS = ["business", "audience", "voice", "goals"];
const status = (msg) => ($("status").textContent = msg);

function serverUrl() {
  return ($("server").value.trim() || "http://localhost:8000").replace(/\/$/, "");
}

// The extension only asks for access to the one server the user configured.
async function ensureAccess(server) {
  const origins = [`${new URL(server).origin}/*`];
  if (await chrome.permissions.contains({ origins })) return true;
  return chrome.permissions.request({ origins });
}

async function api(path, options = {}) {
  const res = await fetch(serverUrl() + path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${$("apiKey").value.trim()}`, ...options.headers },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Server error (${res.status})`);
  return body;
}

async function load() {
  const { server = "", apiKey = "" } = await chrome.storage.sync.get(["server", "apiKey"]);
  $("server").value = server;
  $("apiKey").value = apiKey;
  if (!apiKey) return;
  try {
    const { profile } = await api("/v1/profile");
    PROFILE_FIELDS.forEach((f) => ($(f).value = profile[f] || ""));
  } catch {
    status("Couldn't load your profile from the server.");
  }
}

$("signup").addEventListener("click", async () => {
  try {
    if (!(await ensureAccess(serverUrl()))) return status("PromptSmith needs access to the server to continue.");
    const { api_key } = await api("/v1/keys", { method: "POST" });
    $("apiKey").value = api_key;
    await chrome.storage.sync.set({ server: serverUrl(), apiKey: api_key });
    status("Free key created and saved (20 prompts a day).");
  } catch (e) {
    status(`Couldn't create a key: ${e.message}`);
  }
});

$("save").addEventListener("click", async () => {
  try {
    if (!(await ensureAccess(serverUrl()))) return status("PromptSmith needs access to the server to continue.");
    await chrome.storage.sync.set({ server: serverUrl(), apiKey: $("apiKey").value.trim() });
    const profile = Object.fromEntries(PROFILE_FIELDS.map((f) => [f, $(f).value.trim()]));
    await api("/v1/profile", { method: "PUT", body: JSON.stringify(profile) });
    status("Saved.");
  } catch (e) {
    status(`Couldn't save: ${e.message}`);
  }
});

load();
