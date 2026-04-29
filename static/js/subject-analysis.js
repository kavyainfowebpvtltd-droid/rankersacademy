function animateBars() {
  document.querySelectorAll(".progress-bar").forEach((bar) => {
    bar.style.width = "0%";
    setTimeout(() => (bar.style.width = bar.dataset.progress + "%"), 100);
  });
}

function toggleChapter(header) {
  const card = header.closest(".chapter-card");
  const topicsSection = card.querySelector(".topics-section");
  const divider = card.querySelector(".chapter-divider");
  const arrowIcon = header.querySelector(".bi");

  const isExpanded =
    topicsSection.style.maxHeight !== "0px" &&
    topicsSection.style.maxHeight !== "";

  if (isExpanded) {
    topicsSection.style.maxHeight = "0px";
    divider.style.opacity = "0";
    arrowIcon.style.transform = "rotate(0deg)";
  } else {
    topicsSection.style.maxHeight = topicsSection.scrollHeight + "px";
    divider.style.opacity = "1";
    arrowIcon.style.transform = "rotate(180deg)";
  }
}

window.onload = function () {
  animateBars();

  document.querySelectorAll(".topics-section").forEach((section) => {
    section.style.maxHeight = "0px";
  });
};
