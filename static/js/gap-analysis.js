function toggleContent(btn) {
  const extra = btn.previousElementSibling;
  if (extra.classList.contains("d-none")) {
    extra.classList.remove("d-none");
    btn.innerText = "Show Less";
  } else {
    extra.classList.add("d-none");
    btn.innerText = "Show More";
  }
}

let activePopup = null;

document.querySelectorAll(".unknown-pill").forEach((pill) => {
  pill.addEventListener("mouseenter", () => {
    if (activePopup) activePopup.style.display = "none";
    const popup = pill.querySelector(".hover-popup");
    popup.style.display = "block";
    activePopup = popup;
  });

  pill.addEventListener("mouseleave", () => {
    const popup = pill.querySelector(".hover-popup");
    popup.style.display = "none";
    activePopup = null;
  });
});

document.querySelectorAll(".zero-pill").forEach((pill) => {
  pill.addEventListener("mouseenter", () => {
    if (activePopup) activePopup.style.display = "none";
    const popup = pill.querySelector(".hover-popup");
    popup.style.display = "block";
    activePopup = popup;
  });

  pill.addEventListener("mouseleave", () => {
    const popup = pill.querySelector(".hover-popup");
    popup.style.display = "none";
    activePopup = null;
  });
});

function closePopup(btn) {
  const popup = btn.closest(".hover-popup");
  popup.style.display = "none";
  activePopup = null;
}
