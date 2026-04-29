let currentSubjectId = null;
let selectedTopicsByChapter = {};
let lastQuizMeta = null;

let GAP_FILTERS = {
  subject_id: null,
  chapter_id: null,
  allowed_topic_ids: null,
};

function getQueryParam(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

function parseCsvInts(csv) {
  if (!csv) return [];
  return String(csv)
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => Number(x))
    .filter((n) => Number.isFinite(n) && n > 0);
}

function buildLoadSubjectsUrl() {
  const subject = getQueryParam("subject");
  const chapter = getQueryParam("chapter");
  const topics = getQueryParam("topics");

  const hasFilters = !!(subject || chapter || topics);
  if (!hasFilters) return window.TEST_URLS.loadSubjects;

  const url = new URL(window.TEST_URLS.loadSubjects, window.location.origin);
  if (subject) url.searchParams.set("subject", subject);
  if (chapter) url.searchParams.set("chapter", chapter);
  if (topics) url.searchParams.set("topics", topics);
  url.searchParams.set("include_filters", "1");
  return url.toString();
}

function applyGapFiltersFromResponse(data) {
  const f = data && data.filters ? data.filters : null;
  if (!f) return;

  GAP_FILTERS.subject_id = f.subject_id ? Number(f.subject_id) : null;
  GAP_FILTERS.chapter_id = f.chapter_id ? Number(f.chapter_id) : null;

  if (Array.isArray(f.allowed_topic_ids) && f.allowed_topic_ids.length > 0) {
    GAP_FILTERS.allowed_topic_ids = new Set(f.allowed_topic_ids.map(Number));
  } else {
    GAP_FILTERS.allowed_topic_ids = null;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadSubjects();
});

function loadSubjects() {
  const container = document.getElementById("subject-buttons");
  container.innerHTML = "";

  const loadUrl = buildLoadSubjectsUrl();

  fetch(loadUrl, { credentials: "same-origin" })
    .then(async (res) => {
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) throw new Error("loadSubjects failed");
      return data;
    })
    .then((data) => {
      applyGapFiltersFromResponse(data);

      if (!data.subjects || data.subjects.length === 0) {
        container.innerHTML = `<div class="text-muted small">
          No subjects found for your grade/board.
        </div>`;
        console.log("DEBUG load_subjects:", data.debug);
        return;
      }

      let autoClickBtn = null;
      let autoClickSub = null;

      data.subjects.forEach((sub) => {
        const btn = document.createElement("button");
        btn.className = "btn btn-outline-primary subject-btn";
        btn.innerHTML = `<i class="bi bi-book me-2"></i>${sub.name}`;
        btn.onclick = () => selectSubject(sub.id, btn, sub.name);
        container.appendChild(btn);

        if (
          GAP_FILTERS.subject_id &&
          Number(sub.id) === Number(GAP_FILTERS.subject_id)
        ) {
          autoClickBtn = btn;
          autoClickSub = sub;
        }
      });

      console.log("DEBUG load_subjects:", data.debug);

      if (autoClickBtn && autoClickSub) {
        selectSubject(autoClickSub.id, autoClickBtn, autoClickSub.name);
      }
    })
    .catch((err) => {
      console.error(err);
      container.innerHTML = `<div class="text-danger small">
        Failed to load subjects. Check console/network.
      </div>`;
    });
}

function selectSubject(subjectId, clickedBtn, subjectName) {
  currentSubjectId = subjectId;

  document.querySelectorAll(".subject-btn").forEach((btn) => {
    const active = btn === clickedBtn;
    btn.classList.toggle("active", active);
    btn.classList.toggle("btn-primary", active);
    btn.classList.toggle("btn-outline-primary", !active);
  });

  const url = window.TEST_URLS.loadChapters.replace(
    "{subject_id}",
    String(subjectId),
  );

  fetch(url, { credentials: "same-origin" })
    .then((res) => res.json())
    .then((data) => renderChapters(subjectName, data.chapters || []))
    .catch((e) => {
      console.error(e);
      document.getElementById("chapters-container").innerHTML =
        `<div class="text-danger">Failed to load chapters.</div>`;
    });
}

function renderChapters(subjectName, chapters) {
  const container = document.getElementById("chapters-container");
  container.innerHTML = `<h3 class="mb-4 text-center fw-bold">Current Subject: ${subjectName}</h3>`;

  selectedTopicsByChapter = {};
  lastQuizMeta = null;

  let filteredChapters = chapters;
  if (
    GAP_FILTERS.subject_id &&
    Number(GAP_FILTERS.subject_id) === Number(currentSubjectId) &&
    GAP_FILTERS.chapter_id
  ) {
    filteredChapters = chapters.filter(
      (c) => Number(c.id) === Number(GAP_FILTERS.chapter_id),
    );
  }

  const restrictTopics =
    GAP_FILTERS.subject_id &&
    Number(GAP_FILTERS.subject_id) === Number(currentSubjectId) &&
    GAP_FILTERS.allowed_topic_ids instanceof Set &&
    GAP_FILTERS.allowed_topic_ids.size > 0;

  filteredChapters.forEach((chap) => {
    selectedTopicsByChapter[chap.id] = new Set();

    let topicsToRender = chap.topics || [];
    if (restrictTopics) {
      topicsToRender = topicsToRender.filter((t) =>
        GAP_FILTERS.allowed_topic_ids.has(Number(t.id)),
      );
    }

    const topicsHtml = topicsToRender
      .map(
        (t) => `
      <div class="topic-item p-3" id="topic-${t.id}">
        <p class="fw-bold text-primary mb-2">${t.name}</p>
        <div class="form-check p-2 d-flex justify-content-between align-items-center">
          <label class="form-check-label point-text flex-grow-1" for="topic-check-${t.id}">${t.name}</label>
          <input class="form-check-input check-point"
                 id="topic-check-${t.id}"
                 type="checkbox"
                 onchange="toggleTopic(${chap.id}, ${t.id})">
        </div>
      </div>
    `,
      )
      .join("");

    container.innerHTML += `
      <div class="card chapter-card shadow-sm mb-4" id="chap-${chap.id}">
        <div class="card-header bg-white py-3 border-0">
          <h5 class="mb-0 fw-bold text-dark">${chap.name}</h5>
        </div>
        <div class="card-body pt-0">
          ${topicsHtml}
          <div id="proof-${chap.id}" class="proof-btn-container d-none">
            <p class="text-success fw-bold small mb-2">
              <i class="bi bi-check-circle-fill"></i> You have selected all topics in this chapter!
            </p>
            <button class="btn btn-success btn-sm rounded-pill px-4"
                    onclick="openQuiz(${chap.id})">
              Verify this chapter
            </button>
          </div>
        </div>
      </div>
    `;
  });

  if (
    GAP_FILTERS.subject_id &&
    Number(GAP_FILTERS.subject_id) === Number(currentSubjectId)
  ) {
    const firstChap = container.querySelector(".chapter-card");
    if (firstChap)
      firstChap.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

window.toggleTopic = function (chapterId, topicId) {
  const set = selectedTopicsByChapter[chapterId];
  const cb = document.getElementById(`topic-check-${topicId}`);

  if (cb.checked) set.add(topicId);
  else set.delete(topicId);

  const total = document.querySelectorAll(
    `#chap-${chapterId} input.check-point`,
  ).length;
  const proof = document.getElementById(`proof-${chapterId}`);
  proof.classList.toggle("d-none", set.size !== total);
};

window.openQuiz = function (chapterId) {
  const url = window.TEST_URLS.loadQuiz.replace(
    "{chapter_id}",
    String(chapterId),
  );
  lastQuizMeta = { chapterId, questions: [] };

  document.getElementById("quizTitle").innerText = "Chapter Proficiency Test";
  const container = document.getElementById("quiz-questions-container");
  container.innerHTML = "";

  fetch(url, { credentials: "same-origin" })
    .then((res) => res.json())
    .then((data) => {
      let quiz = data.quiz || [];

      const restrictTopics =
        GAP_FILTERS.subject_id &&
        Number(GAP_FILTERS.subject_id) === Number(currentSubjectId) &&
        GAP_FILTERS.allowed_topic_ids instanceof Set &&
        GAP_FILTERS.allowed_topic_ids.size > 0;

      if (restrictTopics) {
        quiz = quiz.filter((q) =>
          GAP_FILTERS.allowed_topic_ids.has(Number(q.topic_id)),
        );
      }

      lastQuizMeta.questions = quiz.map((q) => ({
        topic_id: q.topic_id,
        question_id: q.question_id,
      }));

      container.innerHTML = quiz
        .map(
          (q, i) => `
        <div class="quiz-question-card">
          <p class="fw-bold">Q${i + 1}: ${q.question}</p>
          ${q.question_image_url ? `<div class="mb-3"><img src="${q.question_image_url}" alt="Question image" style="max-width: 100%; max-height: 280px; border-radius: 12px; border: 1px solid #e5e7eb;" /></div>` : ""}
          ${Object.entries(q.options)
            .map(
              ([key, val]) => `
            <label class="option-item">
              <input type="radio" name="q${q.topic_id}" value="${key}"> ${val}
            </label>
          `,
            )
            .join("")}
        </div>
      `,
        )
        .join("");

      new bootstrap.Modal(document.getElementById("quizModal")).show();
    })
    .catch((e) => {
      console.error(e);
      container.innerHTML = `<div class="text-danger">Failed to load quiz.</div>`;
      new bootstrap.Modal(document.getElementById("quizModal")).show();
    });
};

window.submitQuiz = function () {
  if (!lastQuizMeta) return;

  const answers = {};
  lastQuizMeta.questions.forEach(({ topic_id, question_id }) => {
    const chosen = document.querySelector(`input[name="q${topic_id}"]:checked`);
    answers[String(topic_id)] = {
      question_id,
      selected: chosen ? chosen.value : null,
    };
  });

  fetch(window.TEST_URLS.submitQuiz, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": window.CSRF_TOKEN,
    },
    body: JSON.stringify({
      chapter_id: lastQuizMeta.chapterId,
      subject_id: currentSubjectId,
      answers,
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      const correct = new Set((data.correct_topics || []).map(Number));

      lastQuizMeta.questions.forEach(({ topic_id }) => {
        const cb = document.getElementById(`topic-check-${topic_id}`);
        cb.checked = correct.has(Number(topic_id));
      });

      const chapId = lastQuizMeta.chapterId;
      const set = selectedTopicsByChapter[chapId];
      set.clear();
      lastQuizMeta.questions.forEach(({ topic_id }) => {
        const cb = document.getElementById(`topic-check-${topic_id}`);
        if (cb.checked) set.add(topic_id);
      });

      bootstrap.Modal.getInstance(document.getElementById("quizModal")).hide();

      const total = document.querySelectorAll(
        `#chap-${chapId} input.check-point`,
      ).length;
      document
        .getElementById(`proof-${chapId}`)
        .classList.toggle("d-none", set.size !== total);
    })
    .catch((e) => console.error(e));
};

window.submitTest = function () {
  if (!currentSubjectId) {
    alert("Please select a subject first!");
    return;
  }

  const checkedTopicIds = Array.from(
    document.querySelectorAll("input.check-point:checked"),
  ).map((cb) => Number(cb.id.replace("topic-check-", "")));

  fetch(window.TEST_URLS.submitSelfDiagnostic, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": window.CSRF_TOKEN,
    },
    body: JSON.stringify({
      subject_id: currentSubjectId,
      correct_topics: checkedTopicIds,
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (!data.success) {
        alert(data.error || "Error submitting survey.");
        return;
      }

      const msg1 = document.getElementById("success-msg-1");
      const msg2 = document.getElementById("success-msg-2");

      if (msg1) {
        msg1.innerText = `You have covered ${data.subject_percent}% of the ${data.subject_name} Syllabus out of 100%.`;
      }

      if (msg2) {
        if (data.peers_above_count && Number(data.peers_above_count) > 0) {
          msg2.style.display = "block";
          msg2.innerText = `${data.peers_above_count} more student(s) from your school and grade have scored more than ${data.subject_percent}%.`;
        } else {
          msg2.style.display = "none";
          msg2.innerText = "";
        }
      }

      const modalEl = document.getElementById("successModal");
      const modal = new bootstrap.Modal(modalEl);
      modal.show();

      setTimeout(() => {
        const inst = bootstrap.Modal.getInstance(modalEl);
        if (inst) inst.hide();

        resetToSubjectSelection();
      }, 3000);
    })
    .catch((e) => {
      console.error(e);
      alert("Network error submitting survey.");
    });
};

window.resetTest = function () {
  location.reload();
};

document.addEventListener("DOMContentLoaded", () => {
  const successModalEl = document.getElementById("successModal");

  successModalEl.addEventListener("hidden.bs.modal", () => {
    resetToSubjectSelection();
  });
});

function resetToSubjectSelection() {
  document.getElementById("chapters-container").innerHTML = "";

  document.querySelectorAll(".subject-btn").forEach((btn) => {
    btn.classList.remove("active", "btn-primary");
    btn.classList.add("btn-outline-primary");
  });

  currentSubjectId = null;
  selectedTopicsByChapter = {};
  lastQuizMeta = null;

  GAP_FILTERS = { subject_id: null, chapter_id: null, allowed_topic_ids: null };

  window.scrollTo({ top: 0, behavior: "smooth" });

  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("subject");
    url.searchParams.delete("chapter");
    url.searchParams.delete("topics");
    window.history.replaceState({}, "", url.toString());
  } catch (_) {}

  loadSubjects();
}
