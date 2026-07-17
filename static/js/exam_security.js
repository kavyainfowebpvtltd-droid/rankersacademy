(function () {
  const ACTIVE_CLASS = "exam-security-active";
  const INTERACTIVE_SELECTOR = [
    "input",
    "textarea",
    "button",
    "select",
    "label",
    ".option-label",
    ".option-card",
    ".btn",
    ".btn-custom",
    ".submit-btn",
    ".q-btn",
    ".modal",
    ".modal-dialog",
    ".modal-content",
    "[data-allow-selection]",
  ].join(", ");

  function getFullscreenElement() {
    return (
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.msFullscreenElement ||
      null
    );
  }

  function requestFullscreen(element) {
    const target = element || document.documentElement;
    if (target.requestFullscreen) {
      return target.requestFullscreen();
    }
    if (target.webkitRequestFullscreen) {
      target.webkitRequestFullscreen();
      return Promise.resolve();
    }
    if (target.msRequestFullscreen) {
      target.msRequestFullscreen();
      return Promise.resolve();
    }
    return Promise.reject(new Error("Fullscreen is not supported on this device."));
  }

  function exitFullscreen() {
    if (document.exitFullscreen) {
      return document.exitFullscreen();
    }
    if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
      return Promise.resolve();
    }
    if (document.msExitFullscreen) {
      document.msExitFullscreen();
      return Promise.resolve();
    }
    return Promise.resolve();
  }

  class ExamSecurityController {
    constructor(config) {
      this.config = Object.assign(
        {
          maxViolations: 3,
          alertContainerId: "examSecurityAlertContainer",
          modalId: "examSecurityWarningModal",
          modalMessageId: "examSecurityWarningMessage",
          modalCountId: "examSecurityViolationCount",
          modalLimitId: "examSecurityViolationLimit",
          modalButtonId: "examSecurityAcknowledgeButton",
        },
        config || {},
      );
      this.active = false;
      this.submitted = false;
      this.securityLocked = false;
      this.violationCount = Number(this.config.initialViolationCount || 0);
      this.lastViolationAt = 0;
      this.lastViolationType = "";
      this.violationCooldownMs = 1200;
      this.currentModalContext = null;
      this.boundHandlers = [];
      this.fullscreenAlertMessage = "Click anywhere on the test page to enter fullscreen mode.";
      this.alertContainer = document.getElementById(this.config.alertContainerId);
      this.modalElement = document.getElementById(this.config.modalId);
      this.modalMessage = document.getElementById(this.config.modalMessageId);
      this.modalCount = document.getElementById(this.config.modalCountId);
      this.modalLimit = document.getElementById(this.config.modalLimitId);
      this.modalButton = document.getElementById(this.config.modalButtonId);
      this.bsModal =
        this.modalElement && window.bootstrap
          ? new window.bootstrap.Modal(this.modalElement, {
              backdrop: "static",
              keyboard: false,
            })
          : null;
      this.setViolationCount(this.violationCount);
      this.bindModalActions();
    }

    bindModalActions() {
      if (!this.modalButton) {
        return;
      }

      this.modalButton.addEventListener("click", async () => {
        const modalContext = this.currentModalContext || {};

        if (modalContext.autoSubmit) {
          if (this.bsModal) {
            this.bsModal.hide();
          }
          return;
        }

        if (modalContext.type === "fullscreen") {
          try {
            await requestFullscreen(document.documentElement);
          } catch (error) {
            this.showAlert(
              "Please allow fullscreen access to continue the test.",
              "danger",
            );
            return;
          }
        }

        if (this.bsModal) {
          this.bsModal.hide();
        }
      });
    }

    attachListeners() {
      const register = (target, eventName, handler, options) => {
        target.addEventListener(eventName, handler, options);
        this.boundHandlers.push({ target, eventName, handler, options });
      };

      register(document, "copy", this.handleBlockedAction.bind(this), true);
      register(document, "cut", this.handleBlockedAction.bind(this), true);
      register(document, "paste", this.handleBlockedAction.bind(this), true);
      register(document, "contextmenu", this.handleBlockedAction.bind(this), true);
      register(document, "selectstart", this.handleSelectionStart.bind(this), true);
      register(document, "selectionchange", this.handleSelectionChange.bind(this), true);
      register(document, "dragstart", this.handleBlockedAction.bind(this), true);
      register(document, "drop", this.handleBlockedAction.bind(this), true);
      register(document, "keydown", this.handleKeyDown.bind(this), true);
      register(document, "fullscreenchange", this.handleFullscreenChange.bind(this), true);
      register(document, "webkitfullscreenchange", this.handleFullscreenChange.bind(this), true);
      register(document, "msfullscreenchange", this.handleFullscreenChange.bind(this), true);
      register(document, "visibilitychange", this.handleVisibilityChange.bind(this), true);
      register(window, "blur", this.handleWindowBlur.bind(this), true);
      register(window, "touchstart", this.handleTouchStart.bind(this), { passive: false, capture: true });
    }

    detachListeners() {
      this.boundHandlers.forEach(({ target, eventName, handler, options }) => {
        target.removeEventListener(eventName, handler, options);
      });
      this.boundHandlers = [];
    }

    start() {
      if (this.active) {
        return;
      }
      this.active = true;
      document.body.classList.add(ACTIVE_CLASS);
      this.attachListeners();
      this.syncHiddenInputs();
    }

    stop() {
      this.active = false;
      document.body.classList.remove(ACTIVE_CLASS);
      this.detachListeners();
    }

    markSubmitted() {
      this.submitted = true;
      this.stop();
    }

    async releaseAfterSubmission() {
      this.markSubmitted();
      try {
        await exitFullscreen();
      } catch (_error) {}
    }

    isFullscreenActive() {
      return !!getFullscreenElement();
    }

    async enterFullscreen() {
      await requestFullscreen(document.documentElement);
      if (this.isFullscreenActive()) {
        this.clearFullscreenAlerts();
      }
    }

    setViolationCount(nextValue) {
      this.violationCount = Math.max(0, Number(nextValue || 0));
      if (this.modalCount) {
        this.modalCount.textContent = String(this.violationCount);
      }
      if (this.modalLimit) {
        this.modalLimit.textContent = String(this.config.maxViolations);
      }
      this.syncHiddenInputs();
    }

    setSecurityLocked(locked) {
      this.securityLocked = !!locked;
      this.syncHiddenInputs();
    }

    syncHiddenInputs() {
      const violationInput = document.getElementById("violationCountInput");
      const lockedInput = document.getElementById("securityLockedInput");
      if (violationInput) {
        violationInput.value = String(this.violationCount);
      }
      if (lockedInput) {
        lockedInput.value = this.securityLocked ? "1" : "0";
      }
    }

    isInteractiveTarget(target) {
      return !!(target && target.closest && target.closest(INTERACTIVE_SELECTOR));
    }

    handleBlockedAction(event) {
      if (!this.active || this.submitted) {
        return;
      }

      if (event && typeof event.preventDefault === "function") {
        event.preventDefault();
      }
      if (event && typeof event.stopPropagation === "function") {
        event.stopPropagation();
      }
      this.showAlert("Copying, pasting, selection, and right-click are disabled during this test.", "warning", 1800);
    }

    handleSelectionStart(event) {
      if (!this.active || this.submitted) {
        return;
      }
      if (this.isInteractiveTarget(event.target)) {
        return;
      }
      event.preventDefault();
    }

    handleSelectionChange() {
      if (!this.active || this.submitted) {
        return;
      }

      const selection = window.getSelection ? window.getSelection() : null;
      if (!selection || selection.isCollapsed) {
        return;
      }

      const anchorNode = selection.anchorNode;
      const anchorElement = anchorNode && anchorNode.nodeType === 1 ? anchorNode : anchorNode && anchorNode.parentElement;
      if (this.isInteractiveTarget(anchorElement)) {
        return;
      }

      try {
        selection.removeAllRanges();
      } catch (_error) {}
    }

    handleTouchStart(event) {
      if (!this.active || this.submitted) {
        return;
      }
      if (this.isInteractiveTarget(event.target)) {
        return;
      }

      if (event.touches && event.touches.length > 1) {
        event.preventDefault();
      }
    }

    handleKeyDown(event) {
      if (!this.active || this.submitted) {
        return;
      }

      const key = String(event.key || "").toLowerCase();
      const ctrlOrMeta = !!(event.ctrlKey || event.metaKey);
      const shiftKey = !!event.shiftKey;
      const restrictedCtrlKeys = new Set(["c", "x", "v", "a", "u", "s", "p", "f", "g"]);
      const isRestrictedCombo =
        (ctrlOrMeta && restrictedCtrlKeys.has(key)) ||
        (ctrlOrMeta && shiftKey && (key === "i" || key === "j")) ||
        key === "f12" ||
        key === "printscreen";

      if (!isRestrictedCombo) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      if (key === "f12" || key === "printscreen" || (ctrlOrMeta && shiftKey && (key === "i" || key === "j"))) {
        this.showAlert("Developer tools and screenshots are blocked during this test.", "danger", 2200);
        return;
      }

      this.showAlert("That browser shortcut is disabled during this test.", "warning", 1600);
    }

    handleFullscreenChange() {
      if (!this.active || this.submitted) {
        return;
      }
      if (this.isFullscreenActive()) {
        this.clearFullscreenAlerts();
        return;
      }

      this.recordViolation("fullscreen", "Fullscreen mode was exited during the test. Please return to fullscreen immediately.");
    }

    handleVisibilityChange() {
      if (!this.active || this.submitted) {
        return;
      }
      if (document.hidden) {
        this.recordViolation("tab-switch", "Tab or app switching was detected. Stay on the test page to continue.");
      }
    }

    handleWindowBlur() {
      if (!this.active || this.submitted) {
        return;
      }

      window.setTimeout(() => {
        if (!this.active || this.submitted) {
          return;
        }
        if (document.hidden) {
          return;
        }
        if (document.hasFocus && document.hasFocus()) {
          return;
        }
        this.recordViolation("focus-loss", "Focus moved away from the test window. Please stay on the test page.");
      }, 50);
    }

    recordViolation(type, message) {
      const now = Date.now();
      if (
        this.lastViolationType === type &&
        now - this.lastViolationAt < this.violationCooldownMs
      ) {
        return;
      }

      this.lastViolationAt = now;
      this.lastViolationType = type;
      this.setViolationCount(this.violationCount + 1);

      const reachedLimit = this.violationCount >= this.config.maxViolations;
      this.setSecurityLocked(reachedLimit);

      if (typeof this.config.onViolation === "function") {
        this.config.onViolation({
          type,
          count: this.violationCount,
          locked: reachedLimit,
        });
      }

      if (reachedLimit) {
        this.showWarningModal(
          "Maximum security warnings reached. The test will be submitted automatically.",
          {
            type,
            autoSubmit: true,
          },
        );
        if (typeof this.config.onMaxViolations === "function") {
          window.setTimeout(() => {
            this.config.onMaxViolations({
              type,
              count: this.violationCount,
            });
          }, 900);
        }
        return;
      }

      this.showWarningModal(message, {
        type,
        autoSubmit: false,
      });
    }

    showWarningModal(message, context) {
      this.currentModalContext = context || null;
      if (this.modalMessage) {
        this.modalMessage.textContent = message;
      }
      if (this.modalButton) {
        this.modalButton.textContent = context && context.autoSubmit ? "Submitting..." : "Return to Test";
        this.modalButton.disabled = !!(context && context.autoSubmit);
      }
      if (this.bsModal) {
        this.bsModal.show();
      }
    }

    showAlert(message, type, timeoutMs) {
      if (!this.alertContainer || !message) {
        return;
      }
      if (message === this.fullscreenAlertMessage && this.isFullscreenActive()) {
        this.clearFullscreenAlerts();
        return;
      }
      if (message === this.fullscreenAlertMessage) {
        this.clearFullscreenAlerts();
      }

      const alert = document.createElement("div");
      alert.className = `alert alert-${type || "warning"} alert-dismissible fade show`;
      if (message === this.fullscreenAlertMessage) {
        alert.dataset.fullscreenPrompt = "true";
      }
      alert.setAttribute("role", "alert");
      alert.innerHTML = `
        <div class="d-flex align-items-center justify-content-between gap-3">
          <span>${message}</span>
          <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
      `;
      this.alertContainer.appendChild(alert);

      const closeAlert = () => {
        if (!alert.parentNode) {
          return;
        }
        alert.remove();
      };

      const delay = Number(timeoutMs || 0);
      if (delay > 0) {
        window.setTimeout(closeAlert, delay);
      }
    }

    clearFullscreenAlerts() {
      if (!this.alertContainer) {
        return;
      }
      this.alertContainer
        .querySelectorAll('[data-fullscreen-prompt="true"]')
        .forEach((alert) => alert.remove());
    }
  }

  window.ExamSecurityController = ExamSecurityController;
})();
