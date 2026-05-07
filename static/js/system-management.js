function hideIframeScrollbars(frame) {
  if (!frame) return;

  try {
    const doc = frame.contentDocument || frame.contentWindow?.document;
    if (!doc || !doc.head) return;

    let styleTag = doc.getElementById("admin-portal-scrollbar-hide");
    if (!styleTag) {
      styleTag = doc.createElement("style");
      styleTag.id = "admin-portal-scrollbar-hide";
      styleTag.textContent = `
        html, body, * {
          scrollbar-width: none !important;
          -ms-overflow-style: none !important;
        }
        *::-webkit-scrollbar {
          display: none !important;
          width: 0 !important;
          height: 0 !important;
        }
      `;
      doc.head.appendChild(styleTag);
    }
  } catch (error) {
    console.warn("Unable to hide iframe scrollbars:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const frame = document.getElementById("contentFrame");
  if (!frame) return;

  frame.addEventListener("load", () => hideIframeScrollbars(frame));

  if (frame.contentDocument?.readyState === "complete") {
    hideIframeScrollbars(frame);
  }
});
