document.addEventListener("DOMContentLoaded", function () {
  const payloadEl = document.getElementById("chart-payload");
  if (!payloadEl) {
    console.error(
      "chart-payload JSON script not found. Add {{ chart_payload|json_script:'chart-payload' }} in report.html",
    );
    return;
  }

  if (typeof Chart === "undefined") {
    console.error(
      "Chart.js not loaded. Make sure Chart.js is included BEFORE report.js.",
    );
    return;
  }

  let payload = {};
  try {
    payload = JSON.parse(payloadEl.textContent || "{}");
  } catch (e) {
    console.error("Invalid chart payload JSON:", e);
    return;
  }

  const labels = payload.labels || [];
  const current = payload.current_progress || [];
  const latest = payload.latest_scores || [];
  const remaining = payload.remaining || [];

  const canvas = document.getElementById("mainBarChart");
  if (!canvas) {
    console.error("Canvas #mainBarChart not found in report.html");
    return;
  }

  canvas.style.width = "100%";
  canvas.style.height = "100%";

  const ctx = canvas.getContext("2d");

  if (canvas._chartInstance) {
    canvas._chartInstance.destroy();
  }

  const BAR_PERCENTAGE = 0.42;
  const CATEGORY_PERCENTAGE = 0.62;

  const barData = {
    labels: labels,
    datasets: [
      {
        label: "Current Progress",
        data: current,
        backgroundColor: "#3b82f6",
        borderRadius: 4,
        barPercentage: BAR_PERCENTAGE,
        categoryPercentage: CATEGORY_PERCENTAGE,
      },
      {
        label: "Latest Score",
        data: latest,
        backgroundColor: "#14b8a6",
        borderRadius: 4,
        barPercentage: BAR_PERCENTAGE,
        categoryPercentage: CATEGORY_PERCENTAGE,
      },
      {
        label: "Remaining",
        data: remaining,
        backgroundColor: "#10b981",
        borderRadius: 4,
        barPercentage: BAR_PERCENTAGE,
        categoryPercentage: CATEGORY_PERCENTAGE,
      },
    ],
  };

  canvas._chartInstance = new Chart(ctx, {
    type: "bar",
    data: barData,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.9)",
          padding: 10,
          cornerRadius: 8,
          usePointStyle: true,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          grid: { borderDash: [4, 4], color: "#f3f4f6" },
          ticks: { font: { size: 11, family: "Inter" } },
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 11, family: "Inter" } },
        },
      },
      interaction: {
        mode: "index",
        intersect: false,
      },
    },
  });
});

function generatePDF(mode = "print") {
  const metaEl = document.getElementById("student-meta");
  let studentId = null;

  try {
    const meta = JSON.parse(metaEl?.textContent || "{}");
    studentId = meta.student_id;
  } catch (e) {
    studentId = null;
  }

  if (!studentId) {
    console.error("student_id not found in #student-meta");
    window.print();
    return;
  }

  const download = mode === "download" ? "1" : "0";
  const url = `/dashboard/students/${studentId}/pdf-report/?download=${download}`;

  const w = window.open(url, "_blank", "noopener,noreferrer");
  if (!w) window.location.href = url;
}
