function toggleSubject(el) {
  const card = el.closest(".subject-card");
  const container = card.querySelector(".chapters-container");
  const chevron = el.querySelector(".chevron");

  container.classList.toggle("expanded");
  chevron.classList.toggle("rotated");
}

function toggleChapter(el) {
  const card = el.closest(".chapter-card");
  const container = card.querySelector(".topics-container");
  const chevron = el.querySelector(".chevron");

  container.classList.toggle("expanded");
  chevron.classList.toggle("rotated");
}

function toggleTopic(el) {
  const card = el.closest(".topic-card");
  const container = card.querySelector(".mcqs-container");
  const chevron = el.querySelector(".chevron");

  container.classList.toggle("expanded");
  chevron.classList.toggle("rotated");
}

function openAddSubjectModal() {
  document.getElementById("addSubjectModal").classList.add("active");
}

function closeModal() {
  document
    .querySelectorAll(".modal-overlay.active")
    .forEach((m) => m.classList.remove("active"));
}

function openChapterModal(subjectId) {
  event.stopPropagation();
  document.getElementById("chapterSubjectId").value = subjectId;
  document.getElementById("addChapterModal").classList.add("active");
}

function closeChapterModal() {
  document.getElementById("addChapterModal").classList.remove("active");
  document.getElementById("chapterSubjectId").value = "";
}

function openTopicModal(chapterId) {
  event.stopPropagation();
  document.getElementById("topicChapterId").value = chapterId;
  document.getElementById("addTopicModal").classList.add("active");
}

function closeTopicModal() {
  document.getElementById("addTopicModal").classList.remove("active");
  document.getElementById("topicChapterId").value = "";
}

function openMcqModal(topicId) {
  event.stopPropagation();
  document.getElementById("mcqTopicId").value = topicId;
  resetMcqImagePreview("add");
  document.getElementById("addMcqModal").classList.add("active");
}

function closeMcqModal() {
  document.getElementById("addMcqModal").classList.remove("active");
  document.getElementById("mcqTopicId").value = "";
  const form = document.getElementById("addMcqForm");
  if (form) form.reset();
  resetMcqImagePreview("add");
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal();
  }
});

function openEditSubjectModal(id, name, grade, board) {
  document.getElementById("editSubjectName").value = name;
  document.getElementById("editSubjectGrade").value = grade;
  document.getElementById("editSubjectBoard").value = board;
  document.getElementById("editSubjectForm").action = `/edit-subject/${id}/`;
  document.getElementById("editSubjectModal").classList.add("active");
}

function closeEditSubjectModal() {
  document.getElementById("editSubjectModal").classList.remove("active");
}

function openEditChapterModal(id, name) {
  document.getElementById("editChapterName").value = name;
  document.getElementById("editChapterForm").action = `/edit-chapter/${id}/`;
  document.getElementById("editChapterModal").classList.add("active");
}

function closeEditChapterModal() {
  document.getElementById("editChapterModal").classList.remove("active");
}

function openEditTopicModal(id, name) {
  document.getElementById("editTopicName").value = name;
  document.getElementById("editTopicForm").action = `/edit-topic/${id}/`;
  document.getElementById("editTopicModal").classList.add("active");
}

function closeEditTopicModal() {
  document.getElementById("editTopicModal").classList.remove("active");
}

function openEditMcqModal(id, q, a, b, c, d, correct, imageUrl = "") {
  document.getElementById("editMcqQuestion").value = q;
  document.getElementById("editOptionA").value = a;
  document.getElementById("editOptionB").value = b;
  document.getElementById("editOptionC").value = c;
  document.getElementById("editOptionD").value = d;
  document.getElementById("editCorrectAnswer").value = correct;
  document.getElementById("editQuestionImage").value = "";
  document.getElementById("removeQuestionImage").checked = false;

  setMcqImagePreview("edit", imageUrl || "");

  document.getElementById("editMcqForm").action = `/edit-mcq/${id}/`;
  document.getElementById("editMcqModal").classList.add("active");
}

function closeEditMcqModal() {
  document.getElementById("editMcqModal").classList.remove("active");
  document.getElementById("editQuestionImage").value = "";
  document.getElementById("removeQuestionImage").checked = false;
  resetMcqImagePreview("edit");
}

function setMcqImagePreview(mode, src) {
  const previewWrap = document.getElementById(`${mode}McqImagePreview`);
  const previewImg = document.getElementById(`${mode}McqImagePreviewTag`);
  if (!previewWrap || !previewImg) return;

  if (src) {
    previewImg.src = src;
    previewImg.style.display = "block";
    previewWrap.style.display = "block";
  } else {
    previewImg.removeAttribute("src");
    previewImg.style.display = "none";
    previewWrap.style.display = "none";
  }
}

function resetMcqImagePreview(mode) {
  setMcqImagePreview(mode, "");
  if (mode === "add") {
    const input = document.getElementById("addQuestionImage");
    if (input) input.value = "";
  }
}

function bindMcqImagePreview(inputId, mode) {
  const input = document.getElementById(inputId);
  if (!input) return;

  input.addEventListener("change", function () {
    const file = this.files && this.files[0];
    if (!file) {
      if (mode === "edit" && !document.getElementById("removeQuestionImage").checked) {
        return;
      }
      resetMcqImagePreview(mode);
      return;
    }

    const reader = new FileReader();
    reader.onload = function (e) {
      setMcqImagePreview(mode, e.target?.result || "");
      if (mode === "edit") {
        document.getElementById("removeQuestionImage").checked = false;
      }
    };
    reader.readAsDataURL(file);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindMcqImagePreview("editQuestionImage", "edit");
  bindMcqImagePreview("addQuestionImage", "add");

  const removeCheckbox = document.getElementById("removeQuestionImage");
  if (removeCheckbox) {
    removeCheckbox.addEventListener("change", function () {
      if (this.checked) {
        setMcqImagePreview("edit", "");
      }
    });
  }
});
