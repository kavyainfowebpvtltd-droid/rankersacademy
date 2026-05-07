(function () {
  const STORAGE_KEY = "rankersAdminTheme";

  function getTheme() {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  }

  function setThemeAttribute(doc, theme) {
    if (!doc) return;
    doc.documentElement.setAttribute("data-admin-theme", theme);
    if (doc.body) doc.body.setAttribute("data-admin-theme", theme);
  }

  function syncThemeLinks(doc, theme) {
    if (!doc) return;
    doc.querySelectorAll('link[href*="admin-dark-overrides.css"], link[data-theme-dark-link], link[href*="admin-light-overrides.css"], link[data-theme-light-link]').forEach((link) => {
      const href = link.getAttribute("href") || "";
      const isDark = link.hasAttribute("data-theme-dark-link") || href.includes("admin-dark-overrides.css");
      const isLight = link.hasAttribute("data-theme-light-link") || href.includes("admin-light-overrides.css");

      if (isDark) link.disabled = theme !== "dark";
      if (isLight) link.disabled = theme !== "light";
    });
  }

  function updateToggleButton(doc, theme) {
    const button = doc.getElementById("adminThemeToggle");
    if (!button) return;

    const icon = button.querySelector("i");
    const label = button.querySelector(".admin-theme-toggle-label");

    button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    button.setAttribute("title", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");

    if (icon) {
      icon.className = theme === "dark" ? "bi bi-moon-stars" : "bi bi-sun";
    }

    if (label) {
      label.textContent = theme === "dark" ? "Dark" : "Light";
    }
  }

  function applyToDocument(doc, theme) {
    setThemeAttribute(doc, theme);
    syncThemeLinks(doc, theme);
    updateToggleButton(doc, theme);
  }

  function applyToIframes(theme) {
    document.querySelectorAll("iframe").forEach((frame) => {
      try {
        const childDocument = frame.contentDocument || frame.contentWindow?.document;
        applyToDocument(childDocument, theme);
      } catch (error) {
        // Cross-origin frames are ignored; current admin frames are same-origin.
      }
    });
  }

  function applyTheme(theme) {
    applyToDocument(document, theme);
    applyToIframes(theme);
  }

  function saveAndApplyTheme(theme) {
    localStorage.setItem(STORAGE_KEY, theme);
    applyTheme(theme);
  }

  function watchForThemeLinks() {
    const observer = new MutationObserver(() => applyTheme(getTheme()));
    observer.observe(document.head || document.documentElement, { childList: true, subtree: true });
  }

  const initialTheme = getTheme();
  setThemeAttribute(document, initialTheme);
  syncThemeLinks(document, initialTheme);
  watchForThemeLinks();

  window.AdminTheme = {
    get: getTheme,
    set: saveAndApplyTheme,
    toggle() {
      saveAndApplyTheme(getTheme() === "dark" ? "light" : "dark");
    },
    apply: applyTheme,
  };

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(getTheme());

    const button = document.getElementById("adminThemeToggle");
    if (button) {
      button.addEventListener("click", () => window.AdminTheme.toggle());
    }

    document.querySelectorAll("iframe").forEach((frame) => {
      frame.addEventListener("load", () => applyToIframes(getTheme()));
    });
  });

  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY) {
      applyTheme(getTheme());
    }
  });
})();
