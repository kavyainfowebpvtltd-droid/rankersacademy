function loadPage(page, btn, sessionPayload) {
  if (sessionPayload) {
    localStorage.setItem("tra4_session", sessionPayload);
  }

  document.getElementById("contentFrame").src = page;

  document
    .querySelectorAll(".nav-btn")
    .forEach((b) => b.classList.remove("active"));

  btn.classList.add("active");
}
