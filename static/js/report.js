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
  const isDarkTheme = () =>
    document.documentElement.getAttribute("data-admin-theme") !== "light";

  function getChartTheme() {
    if (isDarkTheme()) {
      return {
        gridColor: "rgba(255, 255, 255, 0.09)",
        tickColor: "#aeb4c2",
        tooltipBackground: "rgba(11, 12, 18, 0.96)",
        tooltipBorder: "rgba(255, 255, 255, 0.12)",
        palette: ["#ff8a1f", "#8b35ff", "#33d6a6"],
      };
    }

    return {
      gridColor: "#e5e7eb",
      tickColor: "#475569",
      tooltipBackground: "rgba(17, 24, 39, 0.92)",
      tooltipBorder: "rgba(17, 24, 39, 0.08)",
      palette: ["#3b82f6", "#14b8a6", "#10b981"],
    };
  }

  function applyChartTheme(chart) {
    const theme = getChartTheme();

    chart.data.datasets.forEach((dataset, index) => {
      dataset.backgroundColor = theme.palette[index] || dataset.backgroundColor;
    });

    chart.options.plugins.tooltip.backgroundColor = theme.tooltipBackground;
    chart.options.plugins.tooltip.borderColor = theme.tooltipBorder;
    chart.options.scales.y.grid.color = theme.gridColor;
    chart.options.scales.y.ticks.color = theme.tickColor;
    chart.options.scales.x.ticks.color = theme.tickColor;
    chart.update("none");
  }

  const chartTheme = getChartTheme();

  const barData = {
    labels: labels,
    datasets: [
      {
        label: "Current Progress",
        data: current,
        backgroundColor: chartTheme.palette[0],
        borderRadius: 4,
        barPercentage: BAR_PERCENTAGE,
        categoryPercentage: CATEGORY_PERCENTAGE,
      },
      {
        label: "Latest Score",
        data: latest,
        backgroundColor: chartTheme.palette[1],
        borderRadius: 4,
        barPercentage: BAR_PERCENTAGE,
        categoryPercentage: CATEGORY_PERCENTAGE,
      },
      {
        label: "Remaining",
        data: remaining,
        backgroundColor: chartTheme.palette[2],
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
          backgroundColor: chartTheme.tooltipBackground,
          borderColor: chartTheme.tooltipBorder,
          borderWidth: 1,
          bodyColor: "#ffffff",
          titleColor: "#ffffff",
          padding: 10,
          cornerRadius: 8,
          usePointStyle: true,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          grid: { borderDash: [4, 4], color: chartTheme.gridColor },
          ticks: {
            color: chartTheme.tickColor,
            font: { size: 11, family: "Inter" },
          },
        },
        x: {
          grid: { display: false },
          ticks: {
            color: chartTheme.tickColor,
            font: { size: 11, family: "Inter" },
          },
        },
      },
      interaction: {
        mode: "index",
        intersect: false,
      },
    },
  });

  const observer = new MutationObserver(() => {
    if (canvas._chartInstance) {
      applyChartTheme(canvas._chartInstance);
    }
  });

  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-admin-theme"],
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
