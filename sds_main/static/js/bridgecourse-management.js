// ================================================
// BRIDGE COURSE MANAGEMENT - DATABASE INTEGRATED
// ================================================

let subjects = [];

// Load subjects from database on page load
async function loadSubjectsFromDB() {
  try {
    const response = await fetch("/bridgecourse/api/subjects/");
    const data = await response.json();
    subjects = data.map((s) => ({
      id: s.id,
      name: s.subject_name,
      grade: s.grade,
      board: s.board,
      lectures: [],
    }));

    for (let i = 0; i < subjects.length; i++) {
      const lecturesResponse = await fetch(
        `/bridgecourse/api/lectures/?subject_id=${subjects[i].id}`,
      );
      const lecturesData = await lecturesResponse.json();
      subjects[i].lectures = lecturesData.map((l) => ({
        id: l.id,
        day: l.day_number,
        topic: l.topic_name,
        lectureNumber: l.lecture_number,
        videoLink: l.video_url,
      }));
    }

    renderSubjects();
    populateSubjects();
  } catch (error) {
    console.error("Error loading subjects:", error);
  }
}

// ================================================
// SUCCESS MODAL — shown after lecture added
// ================================================
function showSuccessModal(message = "Lecture added successfully!") {
  // Remove existing modal if any
  const existing = document.getElementById("successModal");
  if (existing) existing.remove();

  const modalHTML = `
    <div class="modal fade" id="successModal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content rounded-4 shadow border-0 text-center p-4">
          <div style="font-size:3rem; color:#10b981; margin-bottom:12px;">
            <i class="bi bi-check-circle-fill"></i>
          </div>
          <h5 class="fw-bold mb-2">Success!</h5>
          <p class="text-muted mb-4" style="font-size:0.95rem;">${message}</p>
          <button class="btn btn-success rounded-pill px-4" data-bs-dismiss="modal">
            OK
          </button>
        </div>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML("beforeend", modalHTML);
  const modal = new bootstrap.Modal(document.getElementById("successModal"));
  modal.show();

  document
    .getElementById("successModal")
    .addEventListener("hidden.bs.modal", function () {
      this.remove();
    });
}

// Toast notification system
function showToast(message, type = "success") {
  const toast = document.createElement("div");
  toast.className = `toast-notification toast-${type}`;
  toast.innerHTML = `
        <i class="bi bi-${type === "success" ? "check-circle-fill" : "exclamation-circle-fill"}"></i>
        <span>${message}</span>
    `;

  const style = document.createElement("style");
  style.textContent = `
        .toast-notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 24px;
            border-radius: 12px;
            color: white;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 12px;
            z-index: 9999;
            animation: slideInRight 0.4s ease, fadeOut 0.4s ease 2.6s forwards;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .toast-success { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
        .toast-error   { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); }
        @keyframes slideInRight { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes fadeOut      { from { opacity: 1; }                                  to { opacity: 0; } }
    `;
  document.head.appendChild(style);
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// Validate form field (non-empty)
function validateField(fieldId, errorId) {
  const field = document.getElementById(fieldId);
  const error = document.getElementById(errorId);
  if (!field.value.trim()) {
    field.classList.add("is-invalid");
    if (error) error.style.display = "block";
    return false;
  } else {
    field.classList.remove("is-invalid");
    if (error) error.style.display = "none";
    return true;
  }
}

// Clear form fields
function clearFormFields(...fieldIds) {
  fieldIds.forEach((id) => {
    const field = document.getElementById(id);
    if (field) {
      field.value = "";
      field.classList.remove("is-invalid");
    }
  });
}

// ================================================
// ADD SUBJECT
// ================================================
async function addSubject() {
  const name = document.getElementById("subjectName").value.trim();
  const grade = document.getElementById("classSelect").value;
  const board = document.getElementById("boardSelect").value;

  const isNameValid = validateField("subjectName", "subjectNameError");
  const isGradeValid = validateField("classSelect", "classSelectError");
  const isBoardValid = validateField("boardSelect", "boardSelectError");

  if (!isNameValid || !isGradeValid || !isBoardValid) {
    showToast("Please fill in all required fields", "error");
    return;
  }

  const exists = subjects.some(
    (s) =>
      s.name.toLowerCase() === name.toLowerCase() &&
      s.grade === grade &&
      s.board === board,
  );
  if (exists) {
    showToast("This subject already exists!", "error");
    return;
  }

  try {
    const response = await fetch("/bridgecourse/api/subjects/add/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_name: name, grade, board }),
    });

    if (response.ok) {
      const result = await response.json();
      subjects.push({ id: result.id, name, grade, board, lectures: [] });
      renderSubjects();
      populateSubjects();
      bootstrap.Modal.getInstance(
        document.getElementById("addSubjectModal"),
      ).hide();
      clearFormFields("subjectName", "classSelect", "boardSelect");
      showToast(`Subject "${name}" added successfully!`, "success");
    } else {
      showToast("Failed to add subject", "error");
    }
  } catch (error) {
    console.error("Error adding subject:", error);
    showToast("Error adding subject", "error");
  }
}

// ================================================
// POPULATE SUBJECTS DROPDOWN
// ================================================
function populateSubjects() {
  const dropdown = document.getElementById("lectureSubject");
  const currentValue = dropdown.value;

  let optionsHtml = '<option value="">Select Subject</option>';
  if (subjects.length === 0) {
    optionsHtml = '<option value="">No subjects available</option>';
  } else {
    subjects.forEach((s, i) => {
      const selected = currentValue == i ? "selected" : "";
      optionsHtml += `<option value="${i}" ${selected}>${s.name} (${s.grade} - ${s.board})</option>`;
    });
  }
  dropdown.innerHTML = optionsHtml;
}

// ================================================
// ADD LECTURE — FULL VALIDATION
// ================================================
async function addLecture() {
  let isValid = true;

  const subject = document.getElementById("lectureSubject");
  const day = document.getElementById("lectureDay");
  const number = document.getElementById("lectureNumber");
  const topic = document.getElementById("lectureTopic");
  const video = document.getElementById("lectureVideo");
  const notes = document.getElementById("lectureNotes");

  // ── RESET all errors ──────────────────────────
  document
    .querySelectorAll(
      "#addLectureModal .form-control, #addLectureModal .form-select",
    )
    .forEach((el) => el.classList.remove("is-invalid"));
  document
    .querySelectorAll("#addLectureModal .invalid-feedback")
    .forEach((el) => (el.style.display = "none"));

  // ── SUBJECT ───────────────────────────────────
  if (subject.value === "") {
    subject.classList.add("is-invalid");
    document.getElementById("lectureSubjectError").style.display = "block";
    isValid = false;
  }

  // ── LECTURE DAY — digits only ─────────────────
  const dayRegex = /^[0-9]+$/;
  if (day.value.trim() === "") {
    day.classList.add("is-invalid");
    document.getElementById("lectureDayError").innerText =
      "Lecture day is required";
    document.getElementById("lectureDayError").style.display = "block";
    isValid = false;
  } else if (!dayRegex.test(day.value.trim())) {
    day.classList.add("is-invalid");
    document.getElementById("lectureDayError").innerText =
      "Only digits allowed (e.g., 1, 2, 3)";
    document.getElementById("lectureDayError").style.display = "block";
    isValid = false;
  }

  // ── LECTURE NUMBER — letters and digits allowed ─
  const numberRegex = /^[a-zA-Z0-9]+$/;
  if (number.value.trim() === "") {
    number.classList.add("is-invalid");
    document.getElementById("lectureNumberError").innerText =
      "Lecture number is required";
    document.getElementById("lectureNumberError").style.display = "block";
    isValid = false;
  } else if (!numberRegex.test(number.value.trim())) {
    number.classList.add("is-invalid");
    document.getElementById("lectureNumberError").innerText =
      "Only letters and digits allowed (e.g., L1, L2)";
    document.getElementById("lectureNumberError").style.display = "block";
    isValid = false;
  }

  // ── TOPIC — letters, numbers, spaces only ─────
  const topicRegex = /^[a-zA-Z0-9\s]+$/;
  if (topic.value.trim() === "") {
    topic.classList.add("is-invalid");
    document.getElementById("lectureTopicError").innerText =
      "Topic name is required";
    document.getElementById("lectureTopicError").style.display = "block";
    isValid = false;
  } else if (!topicRegex.test(topic.value.trim())) {
    topic.classList.add("is-invalid");
    document.getElementById("lectureTopicError").innerText =
      "Special characters are not allowed";
    document.getElementById("lectureTopicError").style.display = "block";
    isValid = false;
  }

  // ── VIDEO LINK ────────────────────────────────
  const urlPattern = /^(https?:\/\/)/i;
  if (video.value.trim() === "") {
    video.classList.add("is-invalid");
    document.getElementById("lectureVideoError").innerText =
      "Video link is required";
    document.getElementById("lectureVideoError").style.display = "block";
    isValid = false;
  } else if (!urlPattern.test(video.value.trim())) {
    video.classList.add("is-invalid");
    document.getElementById("lectureVideoError").innerText =
      "Enter a valid URL (http/https)";
    document.getElementById("lectureVideoError").style.display = "block";
    isValid = false;
  }

  // ── NOTES FILE ────────────────────────────────
  if (!notes.files.length) {
    notes.classList.add("is-invalid");
    document.getElementById("lectureNotesError").innerText =
      "Please upload a PDF file";
    document.getElementById("lectureNotesError").style.display = "block";
    isValid = false;
  } else {
    const file = notes.files[0];
    if (file.type !== "application/pdf") {
      notes.classList.add("is-invalid");
      document.getElementById("lectureNotesError").innerText =
        "Only PDF files are allowed";
      document.getElementById("lectureNotesError").style.display = "block";
      isValid = false;
    } else if (file.size > 2 * 1024 * 1024) {
      notes.classList.add("is-invalid");
      document.getElementById("lectureNotesError").innerText =
        "File size must be under 2MB";
      document.getElementById("lectureNotesError").style.display = "block";
      isValid = false;
    }
  }

  if (!isValid) {
    showToast("Please fill all fields correctly!", "error");
    return;
  }

  // ── API CALL ──────────────────────────────────
  const subjectIndex = subject.value;
  const selectedSubject = subjects[parseInt(subjectIndex)];

  const formData = new FormData();
  formData.append("subject_id", selectedSubject.id);
  formData.append("day_number", day.value.trim());
  formData.append("topic_name", topic.value.trim());
  formData.append("lecture_number", number.value.trim());
  formData.append("video_url", video.value.trim());
  formData.append("notes_file", notes.files[0]);

  try {
    const response = await fetch("/bridgecourse/api/lectures/add/", {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (response.ok) {
      selectedSubject.lectures.push({
        id: result.id,
        day: day.value.trim(),
        topic: topic.value.trim(),
        lectureNumber: number.value.trim(),
        videoLink: video.value.trim(),
      });

      renderSubjects();

      // Close Add Lecture modal first, then show success modal
      const addModal = bootstrap.Modal.getInstance(
        document.getElementById("addLectureModal"),
      );
      addModal.hide();

      document
        .querySelectorAll("#addLectureModal input, #addLectureModal select")
        .forEach((el) => (el.value = ""));

      // Show success modal after the add modal finishes hiding
      document
        .getElementById("addLectureModal")
        .addEventListener("hidden.bs.modal", function onHide() {
          showSuccessModal(
            `Lecture "${topic.value.trim() || result.topic_name || "Lecture"}" added successfully! 🎉`,
          );
          this.removeEventListener("hidden.bs.modal", onHide);
        });
    } else {
      showToast("Failed to add lecture", "error");
    }
  } catch (error) {
    console.error(error);
    showToast("Server error", "error");
  }
}

// ================================================
// DELETE SUBJECT
// ================================================
async function deleteSubject(index) {
  const subject = subjects[index];
  if (
    confirm(
      `Are you sure you want to delete "${subject.name}"? This will also delete all ${subject.lectures.length} lectures.`,
    )
  ) {
    try {
      if (subject.id) {
        await fetch(`/bridgecourse/api/subjects/delete/${subject.id}/`, {
          method: "DELETE",
        });
      }
      subjects.splice(index, 1);
      renderSubjects();
      populateSubjects();
      showToast(`Subject "${subject.name}" deleted successfully!`, "success");
    } catch (error) {
      console.error("Error deleting subject:", error);
      showToast("Error deleting subject", "error");
    }
  }
}

// ================================================
// EDIT LECTURE
// ================================================
function editLecture(subjectIndex, lectureIndex) {
  const lecture = subjects[subjectIndex].lectures[lectureIndex];

  document.getElementById("editSubjectIndex").value = subjectIndex;
  document.getElementById("editLectureIndex").value = lectureIndex;
  document.getElementById("editLectureId").value = lecture.id;
  document.getElementById("editLectureDay").value = lecture.day || "";
  document.getElementById("editLectureNumber").value =
    lecture.lectureNumber || "";
  document.getElementById("editLectureTopic").value = lecture.topic || "";
  document.getElementById("editLectureVideo").value = lecture.videoLink || "";
  document.getElementById("editLectureNotes").value = "";

  clearFormFields("editLectureDay", "editLectureTopic");
  new bootstrap.Modal(document.getElementById("editLectureModal")).show();
}

// ================================================
// UPDATE LECTURE
// ================================================
async function updateLecture() {
  const subjectIndex = document.getElementById("editSubjectIndex").value;
  const lectureIndex = document.getElementById("editLectureIndex").value;
  const lectureId = document.getElementById("editLectureId").value;

  const day = document.getElementById("editLectureDay").value.trim();
  const lectureNumber = document
    .getElementById("editLectureNumber")
    .value.trim();
  const topic = document.getElementById("editLectureTopic").value.trim();
  const videoLink = document.getElementById("editLectureVideo").value.trim();
  const notesFile =
    document.getElementById("editLectureNotes").files[0] || null;

  const isDayValid = validateField("editLectureDay", "editLectureDayError");
  const isTopicValid = validateField(
    "editLectureTopic",
    "editLectureTopicError",
  );

  if (!isDayValid || !isTopicValid) {
    showToast("Please fill in all required fields", "error");
    return;
  }

  if (!lectureId) {
    showToast("Lecture ID not found. Please refresh and try again.", "error");
    return;
  }

  try {
    const formData = new FormData();
    formData.append("lecture_id", lectureId);
    formData.append("day_number", day);
    formData.append("topic_name", topic);
    formData.append("lecture_number", lectureNumber);
    formData.append("video_url", videoLink);
    if (notesFile) formData.append("notes_file", notesFile);

    const response = await fetch("/bridgecourse/api/lectures/update/", {
      method: "POST",
      body: formData,
    });
    const result = await response.json();

    if (response.ok) {
      subjects[subjectIndex].lectures[lectureIndex] = {
        id: lectureId,
        day,
        lectureNumber,
        topic,
        videoLink,
        notesFile: result.notes_file || "",
      };

      renderSubjects();
      bootstrap.Modal.getInstance(
        document.getElementById("editLectureModal"),
      ).hide();
      showToast(`Lecture "${topic}" updated successfully!`, "success");
    } else {
      showToast(
        "Failed to update lecture: " + (result.error || "Unknown error"),
        "error",
      );
    }
  } catch (error) {
    console.error("Error updating lecture:", error);
    showToast("Error updating lecture: " + error.message, "error");
  }
}

// ================================================
// DELETE LECTURE
// ================================================
async function deleteLecture(subjectIndex, lectureIndex) {
  const subject = subjects[subjectIndex];
  const lecture = subject.lectures[lectureIndex];

  if (
    confirm(`Are you sure you want to delete the lecture "${lecture.topic}"?`)
  ) {
    try {
      if (lecture.id) {
        await fetch(`/bridgecourse/api/lectures/delete/${lecture.id}/`, {
          method: "DELETE",
        });
      }
      subject.lectures.splice(lectureIndex, 1);
      renderSubjects();
      populateSubjects();
      showToast(`Lecture "${lecture.topic}" deleted successfully!`, "success");
    } catch (error) {
      console.error("Error deleting lecture:", error);
      showToast("Error deleting lecture", "error");
    }
  }
}

// ================================================
// VIDEO MODAL
// ================================================
function openVideoModal(videoUrl) {
  if (!videoUrl) return;
  window.open(videoUrl, "_blank");
}

document
  .getElementById("videoModal")
  ?.addEventListener("hidden.bs.modal", function () {
    document.getElementById("videoFrame").src = "";
  });

// ================================================
// RENDER SUBJECTS
// ================================================
function renderSubjects() {
  const container = document.getElementById("subjectContainer");
  const emptyState = document.getElementById("emptyState");

  if (subjects.length === 0) {
    container.innerHTML = "";
    container.appendChild(emptyState.cloneNode(true));
    return;
  }

  container.innerHTML = "";

  subjects.forEach((s, index) => {
    let lectureHTML = "";
    s.lectures.forEach((l, lectureIndex) => {
      const videoOnclick = l.videoLink
        ? `openVideoModal('${l.videoLink.replace(/'/g, "\\'")}')`
        : "";
      lectureHTML += `
        <div class="lecture-list" style="animation-delay:${lectureIndex * 0.1}s">
          <div class="lecture-badges">
            ${l.day ? `<span class="lecture-badge">${l.day}</span>` : ""}
            ${l.lectureNumber ? `<span class="lecture-badge lecture-number">${l.lectureNumber}</span>` : ""}
          </div>
          <span class="lecture-topic">${l.topic}</span>
          ${l.videoLink ? `<i class="bi bi-play-circle video-link" onclick="${videoOnclick}" title="Watch Video" style="cursor:pointer;"></i>` : ""}
          <div class="lecture-actions">
            <i class="bi bi-pencil edit-lecture"  onclick="editLecture(${index},${lectureIndex})"  title="Edit Lecture"></i>
            <i class="bi bi-trash  delete-lecture" onclick="deleteLecture(${index},${lectureIndex})" title="Delete Lecture"></i>
          </div>
        </div>`;
    });

    const card = document.createElement("div");
    card.className = "subject-card";
    card.style.animationDelay = `${index * 0.15}s`;
    card.innerHTML = `
      <div>
        <div class="subject-header">
          <i class="bi bi-book"></i>
          <strong>${s.name}</strong>
        </div>
        <div class="mt-2">
          <span class="tag">${s.grade}</span>
          <span class="tag">${s.board}</span>
          <span class="tag tag-lectures">${s.lectures.length} ${s.lectures.length === 1 ? "Lecture" : "Lectures"}</span>
        </div>
        ${lectureHTML}
      </div>
      <i class="bi bi-trash" onclick="deleteSubject(${index})" title="Delete Subject"></i>`;

    container.appendChild(card);
  });
}

// ================================================
// DYNAMIC STYLES
// ================================================
const dynamicStyles = document.createElement("style");
dynamicStyles.textContent = `
  .subject-header { display:flex; align-items:center; gap:12px; }
  .subject-header i.bi-book { font-size:1.5rem; color:#4f46e5; background:rgba(79,70,229,.1); padding:10px; border-radius:8px; }
  .subject-header strong { font-size:1.15rem; color:#1f2937; }
  .lecture-list { display:flex; align-items:center; gap:12px; margin-top:10px; padding:12px 16px; background:#f9fafb; border-radius:8px; border-left:3px solid #10b981; font-size:14px; color:#4b5563; transition:all .3s ease; }
  .lecture-list:hover { background:#f3f4f6; border-left-color:#4f46e5; transform:translateX(4px); }
  .lecture-badge { background:linear-gradient(135deg,#4f46e5 0%,#818cf8 100%); color:white; padding:4px 10px; border-radius:6px; font-size:11px; font-weight:600; min-width:60px; text-align:center; }
  .lecture-badges { display:flex; gap:6px; }
  .lecture-number { background:linear-gradient(135deg,#10b981 0%,#34d399 100%) !important; }
  .lecture-topic { flex:1; }
  .video-link { color:#ef4444; font-size:1.1rem; transition:all .3s ease; }
  .video-link:hover { color:#dc2626; transform:scale(1.2); }
  .lecture-actions { display:flex; gap:8px; margin-left:auto; }
  .edit-lecture,.delete-lecture { font-size:1rem; padding:6px; border-radius:6px; cursor:pointer; transition:all .3s ease; }
  .edit-lecture { color:#4f46e5; }
  .edit-lecture:hover { background:rgba(79,70,229,.1); transform:scale(1.1); }
  .delete-lecture { color:#ef4444; }
  .delete-lecture:hover { background:rgba(239,68,68,.1); transform:scale(1.1); }
  .tag-lectures { background:linear-gradient(135deg,#d1fae5 0%,#a7f3d0 100%); color:#059669; }
  .is-invalid { border-color:#ef4444 !important; animation:shake .4s ease; }
  @keyframes shake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-5px)} 75%{transform:translateX(5px)} }
  .invalid-feedback { display:none; color:#ef4444; font-size:.8rem; margin-top:4px; }
`;
document.head.appendChild(dynamicStyles);

// ================================================
// INIT
// ================================================
document.addEventListener("DOMContentLoaded", function () {
  loadSubjectsFromDB();

  // Clear validation errors on input — applied to ALL form inputs
  document.querySelectorAll(".form-control, .form-select").forEach((field) => {
    field.addEventListener("input", function () {
      this.classList.remove("is-invalid");
      const error = document.getElementById(this.id + "Error");
      if (error) error.style.display = "none";
    });
  });

  // Reset forms on modal close
  document
    .getElementById("addSubjectModal")
    .addEventListener("hidden.bs.modal", () =>
      clearFormFields("subjectName", "classSelect", "boardSelect"),
    );
  document
    .getElementById("addLectureModal")
    .addEventListener("hidden.bs.modal", () =>
      clearFormFields(
        "lectureDay",
        "lectureTopic",
        "lectureNumber",
        "lectureVideo",
      ),
    );
  document
    .getElementById("editLectureModal")
    .addEventListener("hidden.bs.modal", () =>
      clearFormFields(
        "editLectureDay",
        "editLectureTopic",
        "editLectureNumber",
        "editLectureVideo",
      ),
    );
});
