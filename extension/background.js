// Talks to the PromptSmith server. Requests go from here rather than the content script so the
// API key never touches the page and calls aren't subject to the chat site's CORS rules.

const DEFAULTS = { server: "http://localhost:8000", apiKey: "" };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.sync.get(["server", "apiKey"])) };
}

async function enhance(request) {
  const { server, apiKey } = await settings();
  if (!apiKey) return { error: "Add your PromptSmith API key in the extension settings first." };
  const res = await fetch(`${server.replace(/\/$/, "")}/v1/enhance`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ request }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) return { error: "Your API key wasn't accepted. Check it in the extension settings." };
  if (!res.ok) return { error: body.error || `Server error (${res.status}).` };
  return body;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "enhance") return false;
  enhance(msg.request)
    .then(sendResponse)
    .catch(() => sendResponse({ error: "PromptSmith couldn't reach its server. Check the extension settings." }));
  return true; // keep the channel open for the async reply
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
