document.addEventListener("DOMContentLoaded", () => {
  function parseNumberFromText(text) {
    const m = String(text || "").match(/-?\d+(\.\d+)?/);
    return m ? Number(m[0]) : 0;
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function animateValue(id, start, end, duration, suffix = "", decimals = 0) {
    const el = document.getElementById(id);
    if (!el) return;

    const startTime = performance.now();
    const isFloat = decimals > 0;

    function tick(now) {
      const progress = clamp((now - startTime) / duration, 0, 1);
      const value = start + (end - start) * progress;

      const out = isFloat
        ? value.toFixed(decimals)
        : Math.round(value).toString();
      el.innerText = out + suffix;

      if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  function setOverallCircle(percent) {
    const circle = document.getElementById("circle");
    if (!circle) return;

    const p = clamp(percent, 0, 100);
    const degree = p * 3.6;
    circle.style.background = `conic-gradient(#5bb2e2 ${degree}deg, #e5e7eb ${degree}deg)`;
  }

  const percentTextEl = document.getElementById("percentText");
  const strongEl = document.getElementById("strong");
  const focusEl = document.getElementById("focus");
  const avgEl = document.getElementById("avg");

  const overallTarget = percentTextEl
    ? parseNumberFromText(percentTextEl.innerText)
    : 0;
  const strongTarget = strongEl ? parseNumberFromText(strongEl.innerText) : 0;
  const focusTarget = focusEl ? parseNumberFromText(focusEl.innerText) : 0;
  const avgTarget = avgEl ? parseNumberFromText(avgEl.innerText) : 0;

  if (strongEl) strongEl.innerText = "0";
  if (focusEl) focusEl.innerText = "0";
  if (avgEl) avgEl.innerText = "0%";

  animateValue("strong", 0, strongTarget, 800);
  animateValue("focus", 0, focusTarget, 800);

  const avgDecimals = String(avgTarget).includes(".") ? 2 : 0;
  animateValue("avg", 0, avgTarget, 900, "%", avgDecimals);

  let current = 0;
  const step = overallTarget > 0 ? Math.max(overallTarget / 80, 0.5) : 1;
  const circleInterval = setInterval(() => {
    if (current >= overallTarget) {
      current = overallTarget;
      clearInterval(circleInterval);
    } else {
      current = Math.min(current + step, overallTarget);
    }

    if (percentTextEl) {
      const decimals = String(overallTarget).includes(".") ? 2 : 0;
      percentTextEl.innerText = Number(current).toFixed(decimals) + "%";
    }
    setOverallCircle(current);
  }, 15);

  const subjectCards = document.querySelectorAll(".subject-card");
  if (!subjectCards.length) return;

  const observer = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;

        const card = entry.target;

        const percentEl = card.querySelector(".subject-percent");
        const bar = card.querySelector(".subject-progress-bar");

        const targetPercent = percentEl
          ? parseNumberFromText(percentEl.innerText)
          : 0;

        if (percentEl) percentEl.innerText = "0%";
        if (bar) bar.style.width = "0%";

        let curr = 0;
        const decimals = String(targetPercent).includes(".") ? 2 : 0;
        const s = targetPercent > 0 ? Math.max(targetPercent / 80, 0.5) : 1;

        const timer = setInterval(() => {
          if (curr >= targetPercent) {
            curr = targetPercent;
            clearInterval(timer);
          } else {
            curr = Math.min(curr + s, targetPercent);
          }

          if (percentEl)
            percentEl.innerText = Number(curr).toFixed(decimals) + "%";
          if (bar) bar.style.width = curr + "%";
        }, 15);

        obs.unobserve(card);
      });
    },
    { threshold: 0.4 },
  );

  subjectCards.forEach((card) => observer.observe(card));
});
