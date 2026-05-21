(function () {
  function parseJsonScript(id, fallbackValue) {
    const element = document.getElementById(id);
    if (!element) {
      console.error(`Missing JSON script element: ${id}`);
      return fallbackValue;
    }

    try {
      return JSON.parse(element.textContent || "null");
    } catch (error) {
      console.error(`Unable to parse JSON from ${id}`, error);
      return fallbackValue;
    }
  }

  function createFallbackSecurityController(config) {
    return {
      config: config || {},
      securityLocked: false,
      start() {},
      stop() {},
      markSubmitted() {},
      setViolationCount() {},
      setSecurityLocked(locked) {
        this.securityLocked = !!locked;
      },
      async enterFullscreen() {
        return Promise.resolve();
      },
      showAlert(message) {
        const syncBanner = document.getElementById("syncStatusBanner");
        if (syncBanner) {
          syncBanner.style.display = "block";
          syncBanner.textContent = message;
          syncBanner.className = "alert py-2 px-3 mb-3 alert-warning";
        }
      },
    };
  }

  const config = window.SCHOLARSHIP_TEST_CONFIG || {};
  const questions = parseJsonScript("scholarship-questions-data", []);
  const savedProgress = parseJsonScript("scholarship-progress-data", {});

  const state = {
    currentQuestionIndex: 0,
    answers: {},
    timerInterval: null,
    syncTimer: null,
    syncInFlight: false,
    isSubmitted: false,
    pendingAutoSubmit: false,
    autoSubmitReason: "",
    tabSwitchCount: 0,
    violationCount: Number(config.initialViolationCount || 0),
    initialized: false,
    activated: false,
    activationInFlight: false,
    timeRemaining: Number(config.timeRemainingSeconds || 0),
  };

  const refs = {
    startButton: document.getElementById("startExamButton"),
    startModalEl: document.getElementById("examStartModal"),
    syncStatusBanner: document.getElementById("syncStatusBanner"),
    successModalEl: document.getElementById("successModal"),
    warningModalEl: document.getElementById("warningModal"),
    timeUpModalEl: document.getElementById("timeUpModal"),
    finalCountEl: document.getElementById("finalCount"),
  };

  const startModal =
    refs.startModalEl && window.bootstrap
      ? new window.bootstrap.Modal(refs.startModalEl, {
          backdrop: "static",
          keyboard: false,
        })
      : null;

  let security;
  try {
    const SecurityController = window.ExamSecurityController;
    security = SecurityController
      ? new SecurityController({
          maxViolations: Number(config.maxViolations || 3),
          initialViolationCount: state.violationCount,
          onViolation(violation) {
            if (violation.type === "tab-switch" || violation.type === "focus-loss") {
              state.tabSwitchCount += 1;
            }
            state.violationCount = violation.count;
            persistDraftLocally();
            scheduleProgressSync(0);
          },
          onMaxViolations() {
            autoSubmit("security_violation");
          },
        })
      : createFallbackSecurityController({
          maxViolations: Number(config.maxViolations || 3),
        });
  } catch (error) {
    console.error("Unable to initialize exam security controller", error);
    security = createFallbackSecurityController({
      maxViolations: Number(config.maxViolations || 3),
    });
  }

  function renderQuestionPanelMessage(message, options) {
    const opts = options || {};
    const questionContext = document.getElementById("questionContext");
    const sectionInstructions = document.getElementById("sectionInstructions");
    const questionText = document.getElementById("questionText");
    const answerInputWrap = document.getElementById("answerInputWrap");
    const optionsGrid = document.getElementById("optionsGrid");

    if (questionContext) {
      questionContext.hidden = true;
    }
    if (sectionInstructions) {
      sectionInstructions.innerHTML = "";
      sectionInstructions.style.display = "none";
    }
    if (questionText) {
      questionText.innerHTML = message || "";
    }
    if (answerInputWrap) {
      answerInputWrap.innerHTML = opts.actionHtml || "";
    }
    if (optionsGrid) {
      optionsGrid.innerHTML = "";
    }

    if (opts.actionHtml) {
      const inlineStartButton = document.getElementById("inlineStartExamButton");
      if (inlineStartButton) {
        inlineStartButton.addEventListener("click", beginSecureTest);
      }
    }
  }

  function getQuestionByIndex(index) {
    return questions[index] || null;
  }

  function clampQuestionIndex(index) {
    if (!questions.length) {
      return 0;
    }
    return Math.min(Math.max(Number(index) || 0, 0), questions.length - 1);
  }

  function getTotalQuestions() {
    return questions.length || Number(config.totalQuestions || 0);
  }

  function isQuestionAnswered(question) {
    if (!question) {
      return false;
    }
    const value = state.answers[question.id];
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return value != null && String(value).trim() !== "";
  }

  function getAnsweredCount() {
    return questions.filter(isQuestionAnswered).length;
  }

  function readLocalProgress() {
    try {
      const raw = localStorage.getItem(config.localProgressKey);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      console.error("Unable to read local progress", error);
      return null;
    }
  }

  function getProgressTimestamp(progress) {
    if (!progress || !progress.saved_at) {
      return 0;
    }
    const parsed = Date.parse(progress.saved_at);
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function getProgressPayload() {
    return {
      answers: state.answers,
      current_question_index: state.currentQuestionIndex,
      tab_switch_count: state.tabSwitchCount,
      violation_count: state.violationCount,
      security_locked: security.securityLocked,
    };
  }

  function persistDraftLocally() {
    try {
      const payload = Object.assign({}, getProgressPayload(), {
        saved_at: new Date().toISOString(),
      });
      localStorage.setItem(config.localProgressKey, JSON.stringify(payload));
    } catch (error) {
      console.error("Unable to persist local progress", error);
    }
  }

  function clearPersistedDraft() {
    try {
      localStorage.removeItem(config.localProgressKey);
    } catch (error) {
      console.error("Unable to clear local progress", error);
    }
  }

  function mergeInitialProgress() {
    const localProgress = readLocalProgress();
    const preferredProgress =
      getProgressTimestamp(localProgress) > getProgressTimestamp(savedProgress)
        ? localProgress
        : savedProgress;

    state.answers =
      preferredProgress && typeof preferredProgress.answers === "object"
        ? preferredProgress.answers
        : {};
    state.currentQuestionIndex = clampQuestionIndex(
      preferredProgress ? preferredProgress.current_question_index : 0,
    );
    state.tabSwitchCount =
      Number(preferredProgress && preferredProgress.tab_switch_count) || 0;
    state.violationCount = Math.max(
      Number(config.initialViolationCount || 0),
      Number(preferredProgress && preferredProgress.violation_count) || 0,
    );
    security.setViolationCount(state.violationCount);
    security.setSecurityLocked(
      Boolean(preferredProgress && preferredProgress.security_locked) ||
        config.securityStatus === "locked",
    );
  }

  function setSyncBanner(message, type) {
    if (!refs.syncStatusBanner) {
      return;
    }

    if (!message) {
      refs.syncStatusBanner.style.display = "none";
      refs.syncStatusBanner.textContent = "";
      refs.syncStatusBanner.className = "alert py-2 px-3 mb-3";
      return;
    }

    refs.syncStatusBanner.style.display = "block";
    refs.syncStatusBanner.textContent = message;
    refs.syncStatusBanner.className =
      "alert py-2 px-3 mb-3 alert-" + (type || "warning");
  }

  function updateConnectionBanner() {
    if (!navigator.onLine) {
      setSyncBanner(
        "Internet connection lost. Your test is saved in this browser and will sync automatically when the network returns.",
        "warning",
      );
      return;
    }

    if (state.pendingAutoSubmit && state.autoSubmitReason === "security_violation") {
      setSyncBanner(
        "Security limit reached. The test will be submitted automatically as soon as the server is reachable.",
        "danger",
      );
      return;
    }

    if (state.pendingAutoSubmit) {
      setSyncBanner(
        "Time is up. Waiting to reconnect so the test can be submitted automatically.",
        "danger",
      );
      return;
    }

    setSyncBanner("", "");
  }

  function normalizeStoredAnswer(question, value) {
    if (!question) {
      return value;
    }
    if (question.multi_select) {
      return Array.isArray(value)
        ? value.filter((item) => item != null && String(item).trim() !== "")
        : [];
    }
    return value == null ? "" : value;
  }

  function setAnswerValue(question, value) {
    const normalizedValue = normalizeStoredAnswer(question, value);
    const shouldDelete = Array.isArray(normalizedValue)
      ? normalizedValue.length === 0
      : String(normalizedValue).trim() === "";

    if (shouldDelete) {
      delete state.answers[question.id];
    } else {
      state.answers[question.id] = normalizedValue;
    }
  }

  function getTypeLabel(question) {
    const labels = {
      mcq: question.multi_select ? "Multiple Select" : "Multiple Choice",
      tf: "True / False",
      fitb: "Fill in the Blank",
      int: "Integer Type",
    };
    return labels[question.type] || "Question";
  }

  function renderQuestionInput(question, answerInputWrap, optionsGrid) {
    if (question.type === "fitb" || question.type === "int") {
      const value = state.answers[question.id] || "";
      answerInputWrap.innerHTML = `
        <input
          type="${question.type === "int" ? "number" : "text"}"
          class="answer-input"
          id="questionAnswerInput"
          placeholder="${question.input_placeholder || "Type your answer"}"
          value="${escapeHtml(value)}"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
        />
      `;

      const input = document.getElementById("questionAnswerInput");
      if (input) {
        input.addEventListener("input", (event) => {
          setAnswerValue(question, event.target.value);
          updateNavigator();
          persistDraftLocally();
          scheduleProgressSync(500);
        });
      }
      return;
    }

    const selectedValue = state.answers[question.id];
    const selectedValues = Array.isArray(selectedValue) ? selectedValue : [];
    const inputType = question.multi_select ? "checkbox" : "radio";

    (question.options || []).forEach((option) => {
      const checked = question.multi_select
        ? selectedValues.includes(option.value)
        : selectedValue === option.value;

      const wrapper = document.createElement("label");
      wrapper.className = "option-label";
      wrapper.innerHTML = `
        <input
          type="${inputType}"
          name="question-${question.id}"
          class="option-input"
          value="${option.value}"
          ${checked ? "checked" : ""}
        />
        <div class="option-card ${checked ? "selected" : ""}">
          <span class="option-bullet">${option.label}</span>
          <span class="option-text">${option.text_html || ""}</span>
        </div>
      `;

      const input = wrapper.querySelector("input");
      input.addEventListener("click", (event) => {
        if (!question.multi_select && state.answers[question.id] === option.value) {
          event.preventDefault();
          setAnswerValue(question, "");
          loadQuestion(state.currentQuestionIndex);
        }
      });
      input.addEventListener("change", (event) => {
        updateAnswer(question, option.value, event.target.checked);
      });

      const optionText = wrapper.querySelector(".option-text");
      if (optionText) {
        optionText.innerHTML = option.text_html || "";
      }

      optionsGrid.appendChild(wrapper);
    });
  }

  function loadQuestion(index, shouldSync) {
    const question = getQuestionByIndex(index);
    if (!question) {
      return;
    }

    state.currentQuestionIndex = clampQuestionIndex(index);

    const questionText = document.getElementById("questionText");
    const questionContext = document.getElementById("questionContext");
    const questionSection = document.getElementById("questionSection");
    const questionType = document.getElementById("questionType");
    const sectionInstructions = document.getElementById("sectionInstructions");
    const answerInputWrap = document.getElementById("answerInputWrap");
    const optionsGrid = document.getElementById("optionsGrid");

    questionText.innerHTML = question.question_html || "";
    answerInputWrap.innerHTML = "";
    optionsGrid.innerHTML = "";

    if (question.section_name || question.type) {
      questionContext.hidden = false;
      questionSection.textContent = question.section_name || "Scholarship Test";
      questionType.textContent = getTypeLabel(question);
    } else {
      questionContext.hidden = true;
    }

    sectionInstructions.innerHTML = question.section_instructions || "";
    sectionInstructions.style.display = question.section_instructions
      ? "block"
      : "none";

    renderQuestionInput(question, answerInputWrap, optionsGrid);

    const questionLabel = document.getElementById("currentQuestionNum");
    if (questionLabel) {
      questionLabel.textContent = `Question ${String(state.currentQuestionIndex + 1).padStart(2, "0")} of ${getTotalQuestions()}`;
    }

    updateNavigator();
    persistDraftLocally();
    if (shouldSync !== false) {
      scheduleProgressSync(400);
    }
  }

  function updateAnswer(question, value, checked) {
    if (question.multi_select) {
      const currentValues = Array.isArray(state.answers[question.id])
        ? state.answers[question.id].slice()
        : [];
      const nextValues = checked
        ? Array.from(new Set(currentValues.concat(value)))
        : currentValues.filter((item) => item !== value);
      setAnswerValue(question, nextValues);
    } else {
      setAnswerValue(question, value);
    }

    loadQuestion(state.currentQuestionIndex);
  }

  function buildQuestionNavigator() {
    const grid = document.getElementById("questionGrid");
    if (!grid) {
      return;
    }

    grid.innerHTML = "";
    for (let index = 0; index < getTotalQuestions(); index += 1) {
      const btn = document.createElement("div");
      btn.className = "q-btn";
      btn.id = "qdot-" + index;
      btn.textContent = index + 1;
      btn.addEventListener("click", () => {
        loadQuestion(index);
      });
      grid.appendChild(btn);
    }
  }

  function updateNavButtons() {
    const prevBtn = document.querySelector(".btn-prev");
    const nextBtn = document.querySelector(".btn-next");

    if (prevBtn) {
      prevBtn.disabled = state.currentQuestionIndex === 0;
      prevBtn.style.opacity = state.currentQuestionIndex === 0 ? "0.5" : "1";
      prevBtn.style.pointerEvents =
        state.currentQuestionIndex === 0 ? "none" : "auto";
    }

    if (nextBtn) {
      nextBtn.disabled = state.currentQuestionIndex === questions.length - 1;
      nextBtn.style.opacity =
        state.currentQuestionIndex === questions.length - 1 ? "0.5" : "1";
      nextBtn.style.pointerEvents =
        state.currentQuestionIndex === questions.length - 1 ? "none" : "auto";
    }
  }

  function updateNavigator() {
    for (let index = 0; index < getTotalQuestions(); index += 1) {
      const dot = document.getElementById("qdot-" + index);
      const question = getQuestionByIndex(index);
      if (!dot || !question) {
        continue;
      }

      dot.classList.remove("answered", "not-answered", "current");
      dot.classList.add(
        isQuestionAnswered(question) ? "answered" : "not-answered",
      );

      if (index === state.currentQuestionIndex) {
        dot.classList.add("current");
      }
    }

    const answeredCountEl = document.getElementById("answeredCount");
    if (answeredCountEl) {
      answeredCountEl.textContent = String(getAnsweredCount());
    }

    const progressFill = document.querySelector(".progress-fill");
    if (progressFill) {
      progressFill.style.width = getTotalQuestions()
        ? `${(getAnsweredCount() / getTotalQuestions()) * 100}%`
        : "0%";
    }

    updateNavButtons();
  }

  function updateTimerDisplay() {
    const minutes = Math.max(0, Math.floor(state.timeRemaining / 60));
    const seconds = Math.max(0, state.timeRemaining % 60);
    const timerDisplay = document.getElementById("timerDisplay");
    if (timerDisplay) {
      timerDisplay.textContent = `Timer: ${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
  }

  function stopTimer() {
    if (state.timerInterval) {
      clearInterval(state.timerInterval);
      state.timerInterval = null;
    }
  }

  function startTimer() {
    stopTimer();
    updateTimerDisplay();

    state.timerInterval = window.setInterval(() => {
      state.timeRemaining = Math.max(0, state.timeRemaining - 1);
      updateTimerDisplay();

      if (state.timeRemaining > 0 && state.timeRemaining % 15 === 0) {
        persistDraftLocally();
        scheduleProgressSync(0);
      }

      if (state.timeRemaining <= 0) {
        stopTimer();
        autoSubmit("time_expired");
      }
    }, 1000);
  }

  function scheduleProgressSync(delay) {
    if (!state.activated || (state.isSubmitted && !state.pendingAutoSubmit)) {
      return;
    }

    clearTimeout(state.syncTimer);
    state.syncTimer = window.setTimeout(() => {
      flushProgress({ silent: true });
    }, delay == null ? 600 : delay);
  }

  async function flushProgress(options) {
    const opts = options || {};
    if (
      !state.activated ||
      state.syncInFlight ||
      !navigator.onLine ||
      (state.isSubmitted && !state.pendingAutoSubmit)
    ) {
      return false;
    }

    state.syncInFlight = true;
    persistDraftLocally();

    try {
      const response = await fetch(config.progressUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify(getProgressPayload()),
        keepalive: !!opts.keepalive,
      });

      const data = await response.json();

      if (response.ok && data.success) {
        if (!state.pendingAutoSubmit) {
          setSyncBanner("", "");
        }
        if (typeof data.time_remaining_seconds === "number") {
          state.timeRemaining = Math.min(
            state.timeRemaining,
            data.time_remaining_seconds,
          );
          updateTimerDisplay();
        }
        return true;
      }

      if (response.status === 409 && data.redirect) {
        clearPersistedDraft();
        window.location.href = data.redirect;
        return false;
      }

      if (data.error === "Test time has expired") {
        autoSubmit("time_expired");
        return false;
      }

      if (!opts.silent) {
        setSyncBanner(
          data.error ||
            "Unable to save progress right now. Your latest answers remain stored in this browser.",
          "warning",
        );
      }
      return false;
    } catch (error) {
      console.error("Progress sync failed", error);
      if (!opts.silent) {
        setSyncBanner(
          "Unable to reach the server. Your latest answers remain stored in this browser and will sync automatically.",
          "warning",
        );
      }
      return false;
    } finally {
      state.syncInFlight = false;
    }
  }

  function bindStaticActions() {
    const prevBtn = document.querySelector(".btn-prev");
    const nextBtn = document.querySelector(".btn-next");
    const submitBtn = document.querySelector(".submit-btn");

    if (prevBtn && prevBtn.dataset.bound !== "true") {
      prevBtn.addEventListener("click", () => {
        if (state.currentQuestionIndex > 0) {
          loadQuestion(state.currentQuestionIndex - 1);
        }
      });
      prevBtn.dataset.bound = "true";
    }

    if (nextBtn && nextBtn.dataset.bound !== "true") {
      nextBtn.addEventListener("click", () => {
        if (state.currentQuestionIndex < questions.length - 1) {
          loadQuestion(state.currentQuestionIndex + 1);
        }
      });
      nextBtn.dataset.bound = "true";
    }

    if (submitBtn) {
      submitBtn.onclick = () => {
        if (state.timeRemaining > 0 || getAnsweredCount() === 0) {
          showWarningModal();
        } else {
          submitTest(false, "manual_submit");
        }
      };
    }
  }

  function initializeTest() {
    if (!questions || questions.length === 0) {
      renderQuestionPanelMessage(
        '<div class="alert alert-warning mb-0">No questions are available for this test. Please contact admin.</div>',
      );
      return;
    }

    if (!state.initialized) {
      mergeInitialProgress();
      buildQuestionNavigator();
      bindStaticActions();
      state.initialized = true;
    }

    security.start();
    loadQuestion(state.currentQuestionIndex, false);
    updateNavigator();
    updateTimerDisplay();
    updateNavButtons();
    persistDraftLocally();
    updateConnectionBanner();

    if (state.activated && !state.pendingAutoSubmit) {
      startTimer();
    }

    if (state.activated && navigator.onLine) {
      scheduleProgressSync(300);
    }
  }

  async function activateTestSession() {
    if (state.activationInFlight) {
      return false;
    }

    state.activationInFlight = true;
    try {
      const response = await fetch(config.activateUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({
          violation_count: state.violationCount,
          security_locked: security.securityLocked,
        }),
      });
      const data = await response.json();

      if (response.ok && data.success) {
        state.activated = true;
        state.timeRemaining = Number(data.time_remaining_seconds || state.timeRemaining);
        config.startedAt = data.started_at || config.startedAt;
        if (data.saved_progress && typeof data.saved_progress === "object") {
          state.violationCount = Math.max(
            state.violationCount,
            Number(data.saved_progress.violation_count) || 0,
          );
          security.setViolationCount(state.violationCount);
          security.setSecurityLocked(Boolean(data.saved_progress.security_locked));
        }
        return true;
      }

      if (response.status === 409 && data.redirect) {
        window.location.href = data.redirect;
        return false;
      }

      security.showAlert(
        data.error || "Unable to activate the test right now.",
        "danger",
      );
      return false;
    } catch (error) {
      console.error("Activation failed", error);
      security.showAlert(
        "Unable to contact the server. Please check your internet connection and try again.",
        "danger",
      );
      return false;
    } finally {
      state.activationInFlight = false;
    }
  }

  async function beginSecureTest() {
    try {
      await security.enterFullscreen();
    } catch (error) {
      security.showAlert(
        "Please allow fullscreen access to start the test.",
        "danger",
      );
      return;
    }

    if (startModal) {
      startModal.hide();
    }

    initializeTest();

    const activated = await activateTestSession();
    if (!activated) {
      if (startModal) {
        startModal.show();
      }
      return;
    }

    initializeTest();
  }

  function autoSubmit(reason) {
    state.pendingAutoSubmit = true;
    state.autoSubmitReason = reason || "time_expired";
    if (reason === "security_violation") {
      security.setSecurityLocked(true);
    }

    if (refs.finalCountEl) {
      refs.finalCountEl.textContent = String(getAnsweredCount());
    }

    persistDraftLocally();
    updateConnectionBanner();

    if (!navigator.onLine) {
      return;
    }

    submitTest(true, state.autoSubmitReason);
  }

  function showWarningModal() {
    if (!refs.warningModalEl) {
      return;
    }

    const answered = getAnsweredCount();
    const warningAnsweredCountEl = document.getElementById("warningAnsweredCount");
    const warningTotalCountEl = document.getElementById("warningTotalCount");
    const modalTitle = refs.warningModalEl.querySelector(".modal-title");
    const modalMessage = refs.warningModalEl.querySelector(".modal-message");

    if (warningAnsweredCountEl) {
      warningAnsweredCountEl.textContent = String(answered);
    }
    if (warningTotalCountEl) {
      warningTotalCountEl.textContent = String(getTotalQuestions());
    }

    if (answered === 0) {
      modalTitle.textContent = "No Questions Attempted!";
      modalMessage.innerHTML =
        "You have not attempted any question. Are you sure you want to submit the test?";
    } else if (state.timeRemaining > 0) {
      const minutes = Math.floor(state.timeRemaining / 60);
      const seconds = state.timeRemaining % 60;
      const timeLeft = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
      modalTitle.textContent = "Time Remaining!";
      modalMessage.innerHTML = `You still have <strong>${timeLeft}</strong> remaining and have answered <strong>${answered}</strong> out of <strong>${getTotalQuestions()}</strong> questions. Are you sure you want to submit?`;
    } else {
      modalTitle.textContent = "Submit Test?";
      modalMessage.innerHTML = `You have answered <strong>${answered}</strong> out of <strong>${getTotalQuestions()}</strong> questions. Are you sure you want to submit?`;
    }

    refs.warningModalEl.classList.add("active");
  }

  function closeWarningModal() {
    if (refs.warningModalEl) {
      refs.warningModalEl.classList.remove("active");
    }
  }

  async function submitTest(isAutoSubmit, submissionReason) {
    if (state.isSubmitted) {
      return;
    }

    state.isSubmitted = true;
    clearTimeout(state.syncTimer);
    stopTimer();
    security.markSubmitted();
    persistDraftLocally();

    try {
      const response = await fetch(config.submitUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({
          answers: state.answers,
          violation_count: state.violationCount,
          security_locked: security.securityLocked,
          submission_reason: submissionReason || "manual_submit",
        }),
      });

      const data = await response.json();

      if (data.success) {
        clearPersistedDraft();
        state.pendingAutoSubmit = false;
        await security.releaseAfterSubmission();
        window.location.href = data.redirect;
        return;
      }

      if (data.redirect) {
        clearPersistedDraft();
        await security.releaseAfterSubmission();
        window.location.href = data.redirect;
        return;
      }

      throw new Error(data.error || "Unable to submit the test");
    } catch (error) {
      console.error(error);
      state.isSubmitted = false;
      state.pendingAutoSubmit = !!isAutoSubmit;

      if (!state.pendingAutoSubmit) {
        security.start();
      }

      if (state.pendingAutoSubmit) {
        updateConnectionBanner();
      } else {
        setSyncBanner(
          navigator.onLine
            ? "Unable to submit right now. Your latest answers are still saved."
            : "You are offline. Your latest answers are still saved in this browser.",
          "warning",
        );
        startTimer();
      }
    }
  }

  function getCSRFToken() {
    const name = "csrftoken";
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let index = 0; index < cookies.length; index += 1) {
        const cookie = cookies[index].trim();
        if (cookie.substring(0, name.length + 1) === `${name}=`) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function closeLegacyTabSwitchModal() {
    const modal = document.getElementById("tabSwitchModal");
    if (modal) {
      modal.classList.remove("active");
    }
  }

  function bindGlobalEvents() {
    if (refs.startButton) {
      refs.startButton.addEventListener("click", beginSecureTest);
    }

    window.addEventListener("offline", () => {
      persistDraftLocally();
      updateConnectionBanner();
    });

    window.addEventListener("online", () => {
      updateConnectionBanner();
      if (state.pendingAutoSubmit) {
        submitTest(true, state.autoSubmitReason || "time_expired");
      } else {
        scheduleProgressSync(0);
      }
    });

    window.addEventListener("beforeunload", () => {
      persistDraftLocally();
      flushProgress({ keepalive: true, silent: true });
    });
  }

  window.closeWarningModal = closeWarningModal;
  window.submitExam = function submitExam() {
    closeWarningModal();
    submitTest(false, "manual_submit");
  };
  window.goToSuccess = function goToSuccess() {
    window.location.href = config.successUrl;
  };
  window.closeTabSwitchModal = closeLegacyTabSwitchModal;

  function initializePage() {
    bindGlobalEvents();
    updateTimerDisplay();
    updateConnectionBanner();
    if (config.startedAt || config.status === "in_progress") {
      state.activated = true;
      initializeTest();
      return;
    }

    renderQuestionPanelMessage("Click Start Test to load questions.", {
      actionHtml: `
        <div class="pt-3">
          <button type="button" class="btn btn-primary px-4 py-2 rounded-pill" id="inlineStartExamButton">
            Start Test
          </button>
          <div class="small text-muted mt-3">
            Fullscreen permission is required before the test begins.
          </div>
        </div>
      `,
    });

    if (startModal) {
      startModal.show();
    }
  }

  function boot() {
    try {
      initializePage();
    } catch (error) {
      console.error("Scholarship test bootstrap failed", error);
      renderQuestionPanelMessage(
        '<div class="alert alert-danger mb-0">Unable to initialize this test properly. Please refresh the page and try again.</div>',
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
