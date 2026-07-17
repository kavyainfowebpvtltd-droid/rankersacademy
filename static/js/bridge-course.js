// Student Bridge Course - Dynamic Data Fetching from Database

// Store all subjects and lectures
let allSubjects = [];
let currentSubjectId = null;
let currentLectureId = null; // Track current lecture being watched
let player = null; // YouTube player instance
let videoStartTime = null; // Track when video started playing

// Get student info from localStorage (set during login)
const userProfile = window.bridgeCourseUser || {
  name: localStorage.getItem("userName") || "John Smith",
  grade: localStorage.getItem("userClass") || "10th",
  section: "A",
  board: localStorage.getItem("userBoard") || "State Board",
};

// Initialize on page load
async function initModule() {
  // 1. Set student meta info in header
  document.getElementById("studentMeta").innerText =
    `Grade ${userProfile.grade}  | ${userProfile.board}`;
  document.querySelector(".user-name").innerText = userProfile.name;
  document.querySelector(".user-avatar").innerText = getInitials(
    userProfile.name,
  );

  // 2. Load subjects from database
  await loadSubjectsFromDB();
}

// Load subjects from the database
async function loadSubjectsFromDB() {
  try {
    const params = new URLSearchParams({
      grade: userProfile.grade,
      board: userProfile.board,
    });
    const response = await fetch(
      `/bridgecourse/api/subjects/?${params.toString()}`,
    );
    const data = await response.json();

    allSubjects = data.map((s) => ({
      id: s.id,
      name: s.subject_name,
      grade: s.grade,
      board: s.board,
      lectures: [],
    }));

    // Load lectures for each subject
    for (let i = 0; i < allSubjects.length; i++) {
      const lecturesResponse = await fetch(
        `/bridgecourse/api/lectures/?subject_id=${allSubjects[i].id}`,
      );
      const lecturesData = await lecturesResponse.json();
      allSubjects[i].lectures = lecturesData.map((l) => ({
        id: l.id,
        day: l.day_number,
        topic: l.topic_name,
        lectureNumber: l.lecture_number,
        videoUrl: l.video_url,
        notesFile: l.notes_file,
      }));
    }

    // Render subject tabs
    renderSubjectTabs();

    // Load first subject's lectures
    if (allSubjects.length > 0) {
      renderLectures(allSubjects[0].id, 0);
    }
  } catch (error) {
    console.error("Error loading subjects:", error);
    showError("Failed to load subjects. Please refresh the page.");
  }
}

// Render subject tabs
function renderSubjectTabs() {
  const tabContainer = document.getElementById("subjectTabs");
  tabContainer.innerHTML = "";

  if (allSubjects.length === 0) {
    tabContainer.innerHTML = `
      <li class="nav-item">
        <span class="nav-link text-muted">No subjects available</span>
      </li>
    `;
    return;
  }

  allSubjects.forEach((subject, index) => {
    const li = document.createElement("li");
    li.className = "nav-item";
    li.innerHTML = `
      <button class="nav-link ${index === 0 ? "active" : ""}" 
              onclick="renderLectures(${subject.id}, ${index})">
        ${subject.name}
      </button>
    `;
    tabContainer.appendChild(li);
  });
}

// Render lectures for a selected subject
function renderLectures(subjectId, subjectIndex) {
  // Update tab UI
  document
    .querySelectorAll(".nav-link")
    .forEach((btn) => btn.classList.remove("active"));
  const tabs = document.querySelectorAll(".nav-link");
  if (tabs[subjectIndex]) {
    tabs[subjectIndex].classList.add("active");
  }

  const subject = allSubjects.find((s) => s.id === subjectId);
  if (!subject) return;

  currentSubjectId = subjectId;

  document.getElementById("currentSubjectLabel").innerText =
    `${subject.name} Lectures`;
  document.getElementById("lessonCount").innerText =
    `${subject.lectures.length} Lessons`;

  const tableBody = document.getElementById("lectureTable");

  if (subject.lectures.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="5" class="text-center py-5 text-muted">No lectures uploaded for this subject yet.</td></tr>`;
    return;
  }

  tableBody.innerHTML = subject.lectures
    .map((l) => {
      const hasNotes = l.notesFile && l.notesFile !== "";
      const notesBtn = hasNotes
        ? `<button class="btn btn-sm btn-download" onclick="downloadNotes(${l.id}, '${l.topic.replace(/'/g, "\\'")}')">
             <i class="bi bi-download me-1"></i> Download Notes
           </button>`
        : `<span class="text-muted small">No notes</span>`;

      const videoBtn = l.videoUrl
        ? `<button class="btn btn-sm btn-watch" onclick="playVideo('${l.videoUrl.replace(/'/g, "\\'")}', '${l.topic.replace(/'/g, "\\'")}', ${l.id})">
             <i class="bi bi-play-circle-fill me-1"></i> Watch Now
           </button>`
        : `<span class="text-muted small">No video</span>`;

      return `
        <tr>
          <td class="ps-4 fw-bold text-secondary">${l.day || "-"}</td>
          <td class="fw-semibold text-dark">${l.topic}</td>
          <td><span class="badge bg-light text-dark border">${l.lectureNumber || "-"}</span></td>
          <td>${videoBtn}</td>
          <td class="text-end pe-4">${notesBtn}</td>
        </tr>
      `;
    })
    .join("");
}

// Play video in modal
function playVideo(url, title, lectureId) {
  // Convert various YouTube URL formats to embed format
  let embedUrl = url;

  if (url.includes("youtu.be")) {
    // Extract video ID from youtu.be format
    const videoId = url.split("/").pop().split("?")[0];
    embedUrl = `https://www.youtube.com/embed/${videoId}`;
  } else if (url.includes("youtube.com/watch")) {
    // Extract video ID from watch format
    const urlParams = new URL(url).searchParams;
    const videoId = urlParams.get("v");
    embedUrl = `https://www.youtube.com/embed/${videoId}`;
  } else if (url.includes("youtube.com/embed")) {
    // Already embed URL
    embedUrl = url;
  }

  // Store current lecture ID for tracking
  currentLectureId = lectureId;

  document.getElementById("videoFrame").src = embedUrl + "?autoplay=1";
  document.getElementById("videoTitle").innerText = title;

  const modal = new bootstrap.Modal(document.getElementById("videoModal"));
  modal.show();

  // Start tracking time when video is opened
  videoStartTime = Date.now();

  // Track when modal is closed (video ended/paused)
  const modalElement = document.getElementById("videoModal");
  const handleModalHide = function () {
    if (videoStartTime) {
      const watchTime = Math.floor((Date.now() - videoStartTime) / 1000);
      sendVideoProgress(watchTime);
      videoStartTime = null;
    }
    // Remove listener to prevent duplicate calls
    modalElement.removeEventListener("hidden.bs.modal", handleModalHide);
  };
  modalElement.addEventListener("hidden.bs.modal", handleModalHide);
}

// Send video progress to server
async function sendVideoProgress(watchTime) {
  if (!currentLectureId || !userProfile.phone) return;

  try {
    // Get current local date and time - use local timezone, not UTC
    // Format: YYYY-MM-DD HH:MM:SS to preserve local time accurately
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    const hours = String(now.getHours()).padStart(2, "0");
    const minutes = String(now.getMinutes()).padStart(2, "0");
    const seconds = String(now.getSeconds()).padStart(2, "0");
    const watchedAt = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;

    const response = await fetch("/bridgecourse/api/lectures/track-progress/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({
        phone_number: userProfile.phone,
        user_name: userProfile.name,
        lecture_id: currentLectureId,
        watch_time: watchTime,
        watched_at: watchedAt,
      }),
    });

    const data = await response.json();
    if (data.success) {
      console.log("Video progress tracked:", data);
    }
  } catch (error) {
    console.error("Error tracking video progress:", error);
  }
}

// Get CSRF token from cookies
function getCsrfToken() {
  const name = "csrftoken";
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// View notes - fetch notes file URL and open/download
async function viewNotes(lectureId, topicName) {
  try {
    const response = await fetch(
      `/bridgecourse/api/lectures/${lectureId}/notes/`,
    );

    if (!response.ok) {
      const error = await response.json();
      alert(error.error || "No notes available for this lecture");
      return;
    }

    const data = await response.json();

    if (data.notes_file) {
      // Open the notes file in a new tab for viewing
      window.open(data.notes_file, "_blank");
    } else {
      alert("No notes file available");
    }
  } catch (error) {
    console.error("Error fetching notes:", error);
    alert("Failed to load notes. Please try again.");
  }
}

// Download notes
async function downloadNotes(lectureId, topicName) {
  try {
    const response = await fetch(
      `/bridgecourse/api/lectures/${lectureId}/notes/`,
    );

    if (!response.ok) {
      const error = await response.json();
      alert(error.error || "No notes available for this lecture");
      return;
    }

    const data = await response.json();

    if (data.notes_file) {
      // Create a temporary link to download the file
      const link = document.createElement("a");
      link.href = data.notes_file;
      link.download = `${topicName}_notes.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      alert("No notes file available");
    }
  } catch (error) {
    console.error("Error downloading notes:", error);
    alert("Failed to download notes. Please try again.");
  }
}

// Show error message
function showError(message) {
  const tableBody = document.getElementById("lectureTable");
  tableBody.innerHTML = `<tr><td colspan="5" class="text-center py-5 text-danger">${message}</td></tr>`;
}

// Get initials from name
function getInitials(name) {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

// Check authentication
function checkAuth() {
  const isLoggedIn = localStorage.getItem("isLoggedIn");
  // For now, allow access (can be enabled when login is properly set up)
  // if (!isLoggedIn) {
  //   window.location.href = "login.html";
  //   return false;
  // }
  return true;
}

// Stop video when modal is closed
document
  .getElementById("videoModal")
  .addEventListener("hidden.bs.modal", function () {
    document.getElementById("videoFrame").src = "";
    this.classList.remove("maximized", "minimized");
    this.querySelector(".modal-dialog").classList.add("video-modal-half");
  });

// Maximize/Minimize Functionality
const videoModal = document.getElementById("videoModal");
const btnMaximize = document.getElementById("btnMaximize");
const btnMinimize = document.getElementById("btnMinimize");
const modalDialog = videoModal.querySelector(".modal-dialog");

btnMaximize?.addEventListener("click", function () {
  if (videoModal.classList.contains("maximized")) {
    videoModal.classList.remove("maximized");
    modalDialog.classList.add("video-modal-half");
    this.innerHTML = '<i class="bi bi-fullscreen"></i>';
    this.title = "Maximize";
  } else {
    videoModal.classList.remove("minimized");
    videoModal.classList.add("maximized");
    modalDialog.classList.remove("video-modal-half");
    this.innerHTML = '<i class="bi bi-fullscreen-exit"></i>';
    this.title = "Restore";
  }
});

btnMinimize?.addEventListener("click", function () {
  videoModal.classList.remove("maximized");
  videoModal.classList.add("minimized");
  modalDialog.classList.remove("video-modal-half");
});

videoModal?.addEventListener("shown.bs.modal", function () {
  if (btnMaximize) {
    btnMaximize.innerHTML = '<i class="bi bi-fullscreen"></i>';
    btnMaximize.title = "Maximize";
  }
  this.classList.remove("maximized", "minimized");
  modalDialog.classList.add("video-modal-half");
});

// Run on page load
window.onload = function () {
  if (checkAuth()) {
    initModule();
  }
};
