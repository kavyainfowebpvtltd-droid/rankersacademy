(function () {
  "use strict";

  const ScanState = {
    IDLE: "idle",
    LOADING: "loading",
    SUCCESS: "success",
    ERROR: "error",
    OFFLINE: "offline",
  };

  let state = ScanState.IDLE;
  let isProcessing = false;
  let offlineQueue = [];
  let isOnline = true;
  let timeoutRef = null;

  const inputRef = document.getElementById("barcode-input");
  const successAudioRef = document.getElementById("success-audio");
  const errorAudioRef = document.getElementById("error-audio");

  const wifiIcon = document.getElementById("wifi-icon");
  const statusText = document.getElementById("status-text");
  const pendingBadge = document.getElementById("pending-badge");
  const pendingCount = document.getElementById("pending-count");

  const idleState = document.getElementById("idle-state");
  const loadingState = document.getElementById("loading-state");
  const successState = document.getElementById("success-state");
  const errorState = document.getElementById("error-state");
  const offlineState = document.getElementById("offline-state");

  const studentPhoto = document.getElementById("student-photo");
  const photoFallback = document.getElementById("photo-fallback");
  const studentName = document.getElementById("student-name");
  const studentClass = document.getElementById("student-class");
  const studentBatch = document.getElementById("student-batch");
  const actionText = document.getElementById("action-text");
  const actionIcon = document.getElementById("action-icon");
  const scanTimestamp = document.getElementById("scan-timestamp");
  const errorMessage = document.getElementById("error-message");

  const scanUrl =
    (window.qrKioskConfig && window.qrKioskConfig.scanUrl) || "/attendance/kiosk/scan/";

  function init() {
    loadOfflineQueue();
    setupEventListeners();
    startAutoFocus();
    startOfflineSync();
    updateOnlineStatus();
  }

  function setupEventListeners() {
    inputRef.addEventListener("change", handleInputChange);
    inputRef.addEventListener("keydown", handleKeyDown);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
  }

  function startAutoFocus() {
    setInterval(function () {
      if (document.activeElement !== inputRef) {
        inputRef.focus();
      }
    }, 300);
  }

  function loadOfflineQueue() {
    const stored = localStorage.getItem("offlineScans");
    if (!stored) {
      return;
    }

    try {
      offlineQueue = JSON.parse(stored);
      updatePendingBadge();
    } catch (error) {
      console.error("Failed to parse offline scans", error);
    }
  }

  function persistOfflineQueue() {
    localStorage.setItem("offlineScans", JSON.stringify(offlineQueue));
    updatePendingBadge();
  }

  function startOfflineSync() {
    setInterval(function () {
      if (offlineQueue.length > 0 && isOnline) {
        syncOfflineData();
      }
    }, 10000);
  }

  function updateOnlineStatus() {
    isOnline = navigator.onLine;
    updateOnlineIndicator();
  }

  function handleOnline() {
    isOnline = true;
    updateOnlineIndicator();
    syncOfflineData();
  }

  function handleOffline() {
    isOnline = false;
    updateOnlineIndicator();
  }

  function updateOnlineIndicator() {
    if (isOnline) {
      wifiIcon.className = "bi bi-wifi";
      statusText.textContent = "Online";
      statusText.classList.remove("text-orange-400");
    } else {
      wifiIcon.className = "bi bi-wifi-off";
      statusText.textContent = "Offline";
      statusText.classList.add("text-orange-400");
    }

    updatePendingBadge();
  }

  function updatePendingBadge() {
    if (offlineQueue.length > 0) {
      pendingBadge.classList.remove("d-none");
      pendingCount.textContent = offlineQueue.length;
    } else {
      pendingBadge.classList.add("d-none");
    }
  }

  async function syncOfflineData() {
    const scansToSync = [...offlineQueue];

    for (let i = 0; i < scansToSync.length; i += 1) {
      const scan = scansToSync[i];

      try {
        await processScanAPI(scan.barcode, scan.timestamp, true);
        offlineQueue = offlineQueue.filter(function (item) {
          return item.timestamp !== scan.timestamp;
        });
        persistOfflineQueue();
      } catch (error) {
        if (error && error.isNetworkError) {
          break;
        }

        offlineQueue = offlineQueue.filter(function (item) {
          return item.timestamp !== scan.timestamp;
        });
        persistOfflineQueue();
      }
    }
  }

  function getKioskId() {
    let kioskId = localStorage.getItem("kioskId");
    if (!kioskId) {
      kioskId = "KIOSK_" + Date.now() + "_" + Math.random().toString(36).slice(2, 9);
      localStorage.setItem("kioskId", kioskId);
    }
    return kioskId;
  }

  async function processScanAPI(barcode, timestamp) {
    try {
      const response = await fetch(scanUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          barcode: barcode,
          scanned_at: timestamp,
          kiosk_id: getKioskId(),
        }),
      });

      const payload = await response.json().catch(function () {
        return {};
      });

      if (!response.ok || payload.success === false) {
        const error = new Error(payload.message || "Scan failed");
        error.isNetworkError = false;
        throw error;
      }

      return payload;
    } catch (error) {
      if (error instanceof TypeError) {
        error.isNetworkError = true;
      }
      throw error;
    }
  }

  async function handleScan(barcode) {
    if (!barcode || !barcode.trim() || isProcessing) {
      return;
    }

    isProcessing = true;
    setState(ScanState.LOADING);

    const timestamp = new Date().toISOString();

    try {
      const result = await processScanAPI(barcode.trim(), timestamp);
      showSuccess(result);
    } catch (error) {
      if (error && error.isNetworkError) {
        offlineQueue.push({ barcode: barcode.trim(), timestamp: timestamp });
        persistOfflineQueue();
        showOffline();
      } else {
        showError(error.message || "Scan failed");
      }
    }
  }

  function showSuccess(result) {
    setState(ScanState.SUCCESS);

    studentName.textContent = result.studentName || "Student";
    studentClass.textContent = result.studentClass || "";
    studentBatch.textContent = result.studentBatch || "";
    actionText.textContent = result.actionText || "Attendance Recorded";
    scanTimestamp.textContent = `${result.date || ""} ${result.timestamp || ""}`.trim();

    const iconMap = {
      checkin: "bi bi-check-circle-fill",
      late_entry: "bi bi-exclamation-triangle-fill",
      checkout: "bi bi-box-arrow-right",
      already_checked_in: "bi bi-info-circle-fill",
      already_checked_out: "bi bi-info-circle-fill",
    };
    actionIcon.className = iconMap[result.action] || "bi bi-check-circle-fill";

    playSuccessAudio();
    renderStudentPhoto(result.photoUrl, resetAfterDelay);
  }

  function showError(message) {
    setState(ScanState.ERROR);
    errorMessage.textContent = message || "Invalid QR code";
    playErrorAudio();
    resetAfterDelay();
  }

  function showOffline() {
    setState(ScanState.OFFLINE);
    resetAfterDelay();
  }

  function resetAfterDelay() {
    if (timeoutRef) {
      clearTimeout(timeoutRef);
    }

    timeoutRef = setTimeout(function () {
      resetUI();
    }, 2000);
  }

  function resetUI() {
    setState(ScanState.IDLE);
    isProcessing = false;
    studentPhoto.src = "";
    studentPhoto.classList.add("d-none");
    photoFallback.classList.add("d-none");
    inputRef.value = "";
    inputRef.focus();
  }

  function showPhotoFallback() {
    studentPhoto.src = "";
    studentPhoto.classList.add("d-none");
    photoFallback.classList.remove("d-none");
  }

  function renderStudentPhoto(photoUrl, onReady) {
    studentPhoto.onload = null;
    studentPhoto.onerror = null;

    if (!photoUrl) {
      showPhotoFallback();
      if (typeof onReady === "function") {
        onReady();
      }
      return;
    }

    photoFallback.classList.remove("d-none");
    studentPhoto.classList.add("d-none");

    const preloader = new Image();
    preloader.onload = function () {
      studentPhoto.onload = null;
      studentPhoto.onerror = null;
      studentPhoto.src = photoUrl;
      studentPhoto.classList.remove("d-none");
      photoFallback.classList.add("d-none");
      if (typeof onReady === "function") {
        onReady();
      }
    };
    preloader.onerror = function () {
      showPhotoFallback();
      if (typeof onReady === "function") {
        onReady();
      }
    };
    preloader.src = photoUrl;
  }

  function setState(newState) {
    hideAllStates();
    state = newState;

    if (state === ScanState.IDLE) {
      idleState.classList.remove("d-none");
    } else if (state === ScanState.LOADING) {
      loadingState.classList.remove("d-none");
    } else if (state === ScanState.SUCCESS) {
      successState.classList.remove("d-none");
    } else if (state === ScanState.ERROR) {
      errorState.classList.remove("d-none");
    } else if (state === ScanState.OFFLINE) {
      offlineState.classList.remove("d-none");
    }
  }

  function hideAllStates() {
    idleState.classList.add("d-none");
    loadingState.classList.add("d-none");
    successState.classList.add("d-none");
    errorState.classList.add("d-none");
    offlineState.classList.add("d-none");
  }

  function handleInputChange(event) {
    const value = event.target.value;
    if (value.indexOf("\n") !== -1 || value.indexOf("\r") !== -1) {
      handleScan(value.replace(/[\n\r]/g, "").trim());
      event.target.value = "";
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      handleScan(inputRef.value.trim());
      inputRef.value = "";
    }
  }

  function playSuccessAudio() {
    if (!successAudioRef) {
      return;
    }

    successAudioRef.currentTime = 0;
    successAudioRef.play().catch(function () {});
  }

  function playErrorAudio() {
    if (!errorAudioRef) {
      return;
    }

    errorAudioRef.currentTime = 0;
    errorAudioRef.play().catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
