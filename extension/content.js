// Adds a floating "Enhance" button above the chat input. Clicking it sends the rough text
// to the PromptSmith server (through background.js) and replaces it with the finished prompt.

(() => {
  const btn = document.createElement("button");
  btn.className = "promptsmith-btn";
  btn.type = "button";
  btn.textContent = "✦ Enhance";
  btn.title = "PromptSmith: turn this into a full prompt";
  btn.hidden = true;

  const toast = document.createElement("div");
  toast.className = "promptsmith-toast";
  toast.hidden = true;

  document.documentElement.append(btn, toast);

  let composer = null;
  let toastTimer = null;

  function showToast(message, undoText) {
    toast.textContent = message;
    if (undoText !== undefined) {
      const undo = document.createElement("button");
      undo.type = "button";
      undo.textContent = "Undo";
      undo.onclick = () => {
        if (composer) writeComposer(composer, undoText);
        toast.hidden = true;
      };
      toast.append(" ", undo);
    }
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast.hidden = true), 10000);
  }

  function place() {
    composer = findComposer();
    if (!composer) {
      btn.hidden = true;
      return;
    }
    const r = composer.getBoundingClientRect();
    btn.style.top = `${Math.max(8, r.top - 36)}px`;
    btn.style.left = `${Math.max(8, r.right - btn.offsetWidth)}px`;
    btn.hidden = false;
  }

  btn.addEventListener("mousedown", (e) => e.preventDefault()); // keep focus in the composer
  btn.addEventListener("click", async () => {
    if (!composer) return;
    const rough = readComposer(composer);
    if (!rough) {
      showToast("Type a rough request first, e.g. “LinkedIn post about my launch, keep it short”.");
      return;
    }
    btn.disabled = true;
    btn.textContent = "Enhancing…";
    try {
      const res = await chrome.runtime.sendMessage({ type: "enhance", request: rough });
      if (res?.error) {
        showToast(res.error);
      } else {
        writeComposer(composer, res.prompt);
        showToast(`Enhanced (${res.remaining_today} left today).`, rough);
      }
    } catch (e) {
      showToast("PromptSmith couldn't reach its server. Check the extension settings.");
    } finally {
      btn.disabled = false;
      btn.textContent = "✦ Enhance";
    }
  });

  new MutationObserver(place).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", place);
  window.addEventListener("scroll", place, true);
  place();
})();
