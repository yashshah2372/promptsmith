// Finds the chat input on each supported site and reads/writes its text.
// Kept free of chrome.* calls so it can be tested on a plain page.

const COMPOSER_SELECTORS = [
  "#prompt-textarea",                                   // ChatGPT (ProseMirror)
  'div.ProseMirror[contenteditable="true"]',            // Claude
  'rich-textarea .ql-editor[contenteditable="true"]',   // Gemini (Quill)
  'textarea[data-promptsmith], [contenteditable="true"][data-promptsmith]', // test pages
];

function findComposer(root = document) {
  for (const sel of COMPOSER_SELECTORS) {
    const el = root.querySelector(sel);
    if (el && el.offsetParent !== null) return el;
  }
  return null;
}

function readComposer(el) {
  return (el.tagName === "TEXTAREA" ? el.value : el.innerText).trim();
}

function writeComposer(el, text) {
  el.focus();
  if (el.tagName === "TEXTAREA") {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
    setter.call(el, text);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  // Rich editors (ProseMirror, Quill) keep their own state; going through insertText
  // makes them update it the same way a paste would, so the site's Send button sees the text.
  const range = document.createRange();
  range.selectNodeContents(el);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  if (!document.execCommand("insertText", false, text)) {
    el.innerText = text;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  }
}

if (typeof module !== "undefined") module.exports = { findComposer, readComposer, writeComposer };
