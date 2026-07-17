document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".js-view-student").forEach((btn) => {
    btn.addEventListener("click", () => {
      const raw = btn.getAttribute("data-student");
      if (!raw) return;

      let data;
      try {
        data = JSON.parse(raw);
      } catch (e) {
        console.error("Invalid student payload", e);
        return;
      }

      document.getElementById("viewName").innerText = data.name || "—";
      document.getElementById("viewEmail").innerText = data.email || "—";
      document.getElementById("viewAttempts").innerText = data.attempts ?? "0";
      document.getElementById("viewAvgScore").innerText =
        data.avg_score || "0%";

      document.getElementById("viewRoll").innerText = data.roll || "—";
      document.getElementById("viewMobile").innerText = data.mobile || "—";
      document.getElementById("viewScore").innerText = data.score || "—";
      document.getElementById("viewWeak").innerText = data.weak || "None";
      document.getElementById("viewLastAssessment").innerText =
        data.last_assessment || "N/A";

      const perf =
        data.status === "Excellent"
          ? "Advanced"
          : data.status === "Good"
            ? "Intermediate"
            : "Beginner";
      document.getElementById("viewPerformance").innerText = perf;

      const statusEl = document.getElementById("viewStatus");
      statusEl.innerText = "Active";

      statusEl.classList.remove(
        "bg-success-subtle",
        "text-success",
        "bg-primary-subtle",
        "text-primary",
        "bg-danger-subtle",
        "text-danger",
      );
      if (data.status === "Excellent") {
        statusEl.classList.add("bg-success-subtle", "text-success");
      } else if (data.status === "Good") {
        statusEl.classList.add("bg-primary-subtle", "text-primary");
      } else {
        statusEl.classList.add("bg-danger-subtle", "text-danger");
      }
    });
  });
});
