function loadPage(page, btn) {
  document.getElementById("contentFrame").src = page;

  document
    .querySelectorAll(".nav-btn")
    .forEach((b) => b.classList.remove("active"));

  btn.classList.add("active");
}
