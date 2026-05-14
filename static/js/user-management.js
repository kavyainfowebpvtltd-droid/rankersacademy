const addUserModalEl = document.getElementById("addUserModal");
let addUserModal = null;
const defaultOneTimePassword = "Tra@2026";

function getAddUserForm() {
  return document.querySelector("#addUserModal form");
}

function getCommonBatchInput() {
  return document.getElementById("batchInputCommon");
}

function getCommonUsernameInput() {
  return document.getElementById("commonUsername");
}

function extractBatchPrefix(batch) {
  const normalizedBatch = String(batch || "").trim();
  if (!normalizedBatch) {
    return "";
  }

  const parts = normalizedBatch.split(/\s+/);
  const firstWord = parts[0] || "";
  const firstLetter = firstWord.charAt(0).toUpperCase() || "X";

  let batchNumber = "01";
  if (parts.length >= 2) {
    const digits = (parts[1].match(/\d+/) || [])[0];
    if (digits) {
      batchNumber = String(parseInt(digits, 10)).padStart(2, "0");
    }
  }

  return `${firstLetter}${batchNumber}`;
}

function getBatchCount(batch) {
  const normalizedBatch = String(batch || "").trim();
  if (!normalizedBatch || typeof batchCounts === "undefined" || !batchCounts) {
    return 0;
  }

  if (Object.prototype.hasOwnProperty.call(batchCounts, normalizedBatch)) {
    return batchCounts[normalizedBatch];
  }

  const matchedKey = Object.keys(batchCounts).find(
    (key) => String(key || "").trim().toLowerCase() === normalizedBatch.toLowerCase(),
  );
  return matchedKey ? batchCounts[matchedKey] : 0;
}

function buildUsernameFromBatch(batch) {
  const prefix = extractBatchPrefix(batch);
  if (!prefix) {
    return "";
  }

  const constant = "202628";
  const existingCount = getBatchCount(batch);
  const nextSequence = String(existingCount + 1).padStart(2, "0");
  return `${prefix}${constant}${nextSequence}`;
}

document.addEventListener("DOMContentLoaded", () => {
  initUserTypeTabs();

  if (addUserModalEl) {
    addUserModal = typeof bootstrap !== "undefined" ? new bootstrap.Modal(addUserModalEl) : null;
  }

  toggleFields();
  initStudentFilterSearch();
  bindStaffRoleToggles();

  document.querySelectorAll(".password-toggle").forEach((toggleBtn) => {
    toggleBtn.addEventListener("click", () => {
      const input = document.getElementById(toggleBtn.dataset.target);
      const icon = toggleBtn.querySelector("i");
      if (!input || !icon) return;

      const showPassword = input.type === "password";
      input.type = showPassword ? "text" : "password";
      icon.className = showPassword ? "bi bi-eye-slash" : "bi bi-eye";
      toggleBtn.setAttribute(
        "aria-label",
        showPassword ? "Hide password" : "Show password",
      );
    });
  });

  // Auto-generate username when batch is entered/changed
  const batchInput = getCommonBatchInput();
  if (batchInput) {
    batchInput.addEventListener("input", () => generateUsernameFromBatch());
    batchInput.addEventListener("change", () => generateUsernameFromBatch());
    batchInput.addEventListener("blur", () => generateUsernameFromBatch());
  }
});

function initUserTypeTabs() {
  const tabs = document.querySelectorAll(".user-type-tab");
  const panels = document.querySelectorAll(".user-section-panel");

  if (!tabs.length || !panels.length) {
    return;
  }

  const showSection = (section) => {
    const selectedSection = section || "students";

    tabs.forEach((tab) => {
      const isActive = tab.dataset.userSection === selectedSection;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-pressed", isActive ? "true" : "false");
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    panels.forEach((panel) => {
      const isActive = panel.dataset.userPanel === selectedSection;
      panel.classList.toggle("d-none", !isActive);
      panel.hidden = !isActive;
      panel.style.display = isActive ? "" : "none";
    });
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      showSection(tab.dataset.userSection || "students");
    });
  });

  showSection("students");
}

let studentSearchDebounceRef = null;
let studentFilterAbortController = null;

function initStudentFilterSearch() {
  const studentFilterForm = document.getElementById("studentFilterForm");
  const studentSearchInput = document.getElementById("studentSearchInput");
  const studentFilterSelects = document.querySelectorAll(".student-filter-select");

  if (!studentFilterForm || !studentSearchInput) {
    return;
  }

  if (studentFilterForm.dataset.ajaxBound === "true") {
    return;
  }
  studentFilterForm.dataset.ajaxBound = "true";

  studentFilterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    fetchStudentTableResults(studentFilterForm);
  });

  studentSearchInput.addEventListener("input", () => {
    if (studentSearchDebounceRef) {
      clearTimeout(studentSearchDebounceRef);
    }

    studentSearchDebounceRef = setTimeout(() => {
      fetchStudentTableResults(studentFilterForm);
    }, 700);
  });

  studentSearchInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (studentSearchDebounceRef) {
      clearTimeout(studentSearchDebounceRef);
    }
    fetchStudentTableResults(studentFilterForm);
  });

  studentFilterSelects.forEach((select) => {
    select.addEventListener("change", () => {
      if (studentSearchDebounceRef) {
        clearTimeout(studentSearchDebounceRef);
      }
      fetchStudentTableResults(studentFilterForm);
    });
  });
}

async function fetchStudentTableResults(form) {
  if (!form) return;

  const studentTableCard = document.getElementById("studentTableCard");
  if (!studentTableCard) {
    form.submit();
    return;
  }

  if (studentFilterAbortController) {
    studentFilterAbortController.abort();
  }
  studentFilterAbortController = new AbortController();

  const searchInput = document.getElementById("studentSearchInput");
  const activeElementId = document.activeElement && document.activeElement.id;
  const activeSelectionStart =
    searchInput && document.activeElement === searchInput
      ? searchInput.selectionStart
      : null;
  const activeSelectionEnd =
    searchInput && document.activeElement === searchInput
      ? searchInput.selectionEnd
      : null;

  studentTableCard.style.opacity = "0.6";
  const url = new URL(form.action || window.location.href, window.location.origin);
  const formData = new FormData(form);
  url.search = new URLSearchParams(formData).toString();

  try {
    const response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
      signal: studentFilterAbortController.signal,
    });

    if (!response.ok) {
      throw new Error("Unable to fetch filtered students.");
    }

    const html = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const nextStudentTableCard = doc.getElementById("studentTableCard");

    if (!nextStudentTableCard) {
      throw new Error("Filtered student table not found.");
    }

    studentTableCard.replaceWith(nextStudentTableCard);
    initStudentFilterSearch();

    const nextSearchInput = document.getElementById("studentSearchInput");
    if (nextSearchInput && activeElementId === "studentSearchInput") {
      nextSearchInput.focus();
      if (
        activeSelectionStart !== null &&
        activeSelectionEnd !== null &&
        typeof nextSearchInput.setSelectionRange === "function"
      ) {
        nextSearchInput.setSelectionRange(activeSelectionStart, activeSelectionEnd);
      }
    }
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    form.submit();
  } finally {
    const refreshedStudentTableCard = document.getElementById("studentTableCard");
    if (refreshedStudentTableCard) {
      refreshedStudentTableCard.style.opacity = "";
    }
  }
}

function generateUsernameFromBatch(sourceInput = null) {
  const batchInput = sourceInput || getCommonBatchInput();
  const batch = (batchInput ? batchInput.value : "").trim();
  const usernameInput = getCommonUsernameInput();
  const hint = document.getElementById("usernameHint");

  if (!batch) {
    if (usernameInput) usernameInput.value = '';
    if (hint) hint.style.display = 'none';
    return;
  }
  const generated = buildUsernameFromBatch(batch);

  if (usernameInput) {
    usernameInput.value = generated;
    if (hint) hint.style.display = 'block';
  }
}

function openAddUserModal() {
  if (addUserModal) {
    addUserModal.show();
  } else if (addUserModalEl) {
    addUserModalEl.classList.add("show");
    addUserModalEl.style.display = "block";
    addUserModalEl.removeAttribute("aria-hidden");
  }
  // Reset form when opening modal
  const form = document.querySelector("#addUserModal form");
  if (form) {
    form.reset();
    // Reset user type to student
    document.getElementById("userTypeSelect").value = "student";
    document.getElementById("userTypeHidden").value = "student";
    const passwordInput = document.getElementById("addUserPassword");
    if (passwordInput) {
      passwordInput.value = defaultOneTimePassword;
    }
    toggleFields();
    // Clear any error styling
    clearAllAddUserErrors();
    // Remove dynamically created error divs for board/grade/batch
    const boardError = document.getElementById("boardError");
    if (boardError && boardError.parentNode) {
      boardError.parentNode.removeChild(boardError);
    }
    const gradeError = document.getElementById("gradeError");
    if (gradeError && gradeError.parentNode) {
      gradeError.parentNode.removeChild(gradeError);
    }
    const batchError = document.getElementById("batchError");
    if (batchError && batchError.parentNode) {
      batchError.parentNode.removeChild(batchError);
    }
    // Remove is-invalid class from board, grade, batch selects
    const boardSelect = form.querySelector('[name="board"]');
    const gradeSelect = form.querySelector('[name="grade"]');
    const batchSelect = form.querySelector('[name="batch"]');
    if (boardSelect) boardSelect.classList.remove("is-invalid");
    if (gradeSelect) gradeSelect.classList.remove("is-invalid");
    if (batchSelect) batchSelect.classList.remove("is-invalid");
    // Hide username hint
    const usernameHint = document.getElementById('usernameHint');
    if (usernameHint) usernameHint.style.display = 'none';
  }
}

function toggleFields() {
  const type = document.getElementById("userTypeSelect").value;

  document.getElementById("userTypeHidden").value = type;

  const studentFields = document.getElementById("studentFields");
  const teacherCommonFieldsRow = document.getElementById("teacherCommonFieldsRow");
  const teacherFields = document.getElementById("teacherFields");
  const studentInputs = studentFields.querySelectorAll("input, select, textarea");
  const teacherInputs = document.querySelectorAll(
    "#teacherCommonFieldsRow input, #teacherCommonFieldsRow select, #teacherCommonFieldsRow textarea, #teacherFields input, #teacherFields select, #teacherFields textarea",
  );
  const usernameInput = document.getElementById("commonUsername");
  const usernameHint = document.getElementById("usernameHint");

  if (type === "student") {
    studentFields.style.display = "flex";
    if (teacherCommonFieldsRow) teacherCommonFieldsRow.style.display = "none";
    teacherFields.style.display = "none";
    studentInputs.forEach((input) => {
      input.disabled = false;
    });
    teacherInputs.forEach((input) => {
      input.disabled = true;
    });
    if (usernameInput) {
      usernameInput.readOnly = true;
      usernameInput.classList.add("readonly-bg");
      usernameInput.value = "";
    }
    if (usernameHint) usernameHint.style.display = "none";
    const batchInput = getCommonBatchInput();
    if (batchInput && batchInput.value.trim()) {
      generateUsernameFromBatch(batchInput);
    }
  } else {
    studentFields.style.display = "none";
    if (teacherCommonFieldsRow) teacherCommonFieldsRow.style.display = "flex";
    teacherFields.style.display = "block";
    studentInputs.forEach((input) => {
      input.disabled = true;
    });
    teacherInputs.forEach((input) => {
      input.disabled = false;
    });
    if (usernameHint) usernameHint.style.display = "none";
    toggleTeacherRoleFields();
  }

  const commonBatchCol = document.getElementById("commonBatchCol");
  if (commonBatchCol) {
    const batchInput = commonBatchCol.querySelector('input[name="batch"]');
    if (batchInput) {
      batchInput.disabled = type !== "student";
    }
    commonBatchCol.style.display = type === "student" ? "" : "none";
  }
}

function bindStaffRoleToggles() {
  const addTeacherRoleInput = document.getElementById("teacherRoleInput");
  if (addTeacherRoleInput && addTeacherRoleInput.dataset.toggleBound !== "true") {
    addTeacherRoleInput.addEventListener("input", toggleTeacherRoleFields);
    addTeacherRoleInput.addEventListener("change", toggleTeacherRoleFields);
    addTeacherRoleInput.addEventListener("keyup", toggleTeacherRoleFields);
    addTeacherRoleInput.dataset.toggleBound = "true";
  }

  const editTeacherRoleInput = document.getElementById("editTeacherRole");
  if (editTeacherRoleInput && editTeacherRoleInput.dataset.toggleBound !== "true") {
    editTeacherRoleInput.addEventListener("input", toggleEditTeacherRoleFields);
    editTeacherRoleInput.addEventListener("change", toggleEditTeacherRoleFields);
    editTeacherRoleInput.addEventListener("keyup", toggleEditTeacherRoleFields);
    editTeacherRoleInput.dataset.toggleBound = "true";
  }
}

function isTeacherDesignationValue(value) {
  return String(value || "").trim().toLowerCase() === "teacher";
}

function setElementVisibility(element, isVisible, displayValue = "") {
  if (!element) return;
  element.hidden = !isVisible;
  element.classList.toggle("d-none", !isVisible);
  element.style.display = isVisible ? displayValue : "none";
}

function toggleTeacherRoleFields() {
  const roleInput = document.getElementById("teacherRoleInput");
  const teacherFields = document.getElementById("teacherFields");
  const teacherOnlyRow = document.getElementById("teacherTeacherFieldsRow");
  const teacherOnlyInputs = teacherOnlyRow
    ? teacherOnlyRow.querySelectorAll("input, select, textarea")
    : [];
  const isTeacher = isTeacherDesignationValue(roleInput ? roleInput.value : "");

  setElementVisibility(teacherFields, true, "block");
  setElementVisibility(teacherOnlyRow, isTeacher, "flex");

  teacherOnlyInputs.forEach((input) => {
    input.disabled = !isTeacher;
  });
}

function toggleEditTeacherRoleFields() {
  const roleInput = document.getElementById("editTeacherRole");
  const subjectsCol = document.getElementById("editTeacherSubjectsCol");
  const batchCol = document.getElementById("editTeacherBatchCol");
  const subjectsInput = document.getElementById("editTeacherSubjects");
  const batchInput = document.getElementById("editTeacherBatch");
  const isTeacher = isTeacherDesignationValue(roleInput ? roleInput.value : "");

  setElementVisibility(subjectsCol, isTeacher, "");
  setElementVisibility(batchCol, isTeacher, "");
  if (subjectsInput) {
    subjectsInput.disabled = !isTeacher;
  }
  if (batchInput) {
    batchInput.disabled = !isTeacher;
  }
}

function showFieldError(inputId, message) {
  const input = document.getElementById(inputId);
  if (input) {
    input.classList.add("is-invalid");
    const errorDiv = document.getElementById(inputId + "Error");
    if (errorDiv) {
      errorDiv.textContent = message;
    }
  }
}

function clearFieldError(inputId) {
  const input = document.getElementById(inputId);
  if (input) {
    input.classList.remove("is-invalid");
    const errorDiv = document.getElementById(inputId + "Error");
    if (errorDiv) {
      errorDiv.textContent = "";
    }
  }
}

function clearAllAddUserErrors() {
  const fields = [
    "studentNameInput",
    "teacherNameInput",
    "commonUsername",
    "teacherUsernameInput",
    "studentEmailInput",
    "teacherEmailInput",
    "studentContactInput",
    "teacherContactInput",
    "teacherRoleInput",
  ];
  fields.forEach((fieldId) => {
    const input = document.getElementById(fieldId);
    if (input) {
      input.classList.remove("is-invalid");
    }
  });

  const errorIds = [
    "studentNameError",
    "teacherNameError",
    "studentUsernameError",
    "teacherUsernameError",
    "studentEmailError",
    "teacherEmailError",
    "studentContactError",
    "teacherContactError",
    "teacherRoleError",
  ];
  errorIds.forEach((errorId) => {
    const errorDiv = document.getElementById(errorId);
    if (errorDiv) {
      errorDiv.textContent = "";
    }
  });
}

function setAddUserFieldError(input, errorId, message) {
  if (input) {
    input.classList.add("is-invalid");
  }
  const errorDiv = document.getElementById(errorId);
  if (errorDiv) {
    errorDiv.textContent = message;
  }
}

function setEditTeacherFieldError(input, errorId, message) {
  if (input) {
    input.classList.add("is-invalid");
  }
  const errorDiv = document.getElementById(errorId);
  if (errorDiv) {
    errorDiv.textContent = message;
  }
}

function clearEditTeacherNameError() {
  const nameInput = document.getElementById("editTeacherName");
  const errorDiv = document.getElementById("editTeacherNameError");
  if (nameInput) {
    nameInput.classList.remove("is-invalid");
  }
  if (errorDiv) {
    errorDiv.textContent = "";
  }
}

function validateAndSubmitAddUser() {
  const form = getAddUserForm();
  if (!form) return;

  const userType = document.getElementById("userTypeSelect").value;
  const isTeacherUser = userType === "teacher";
  const nameInput = document.getElementById(
    isTeacherUser ? "teacherNameInput" : "studentNameInput",
  );
  const usernameInput = document.getElementById(
    isTeacherUser ? "teacherUsernameInput" : "commonUsername",
  );
  const emailInput = document.getElementById(
    isTeacherUser ? "teacherEmailInput" : "studentEmailInput",
  );
  const contactInput = document.getElementById(
    isTeacherUser ? "teacherContactInput" : "studentContactInput",
  );
  const batchInput = getCommonBatchInput();
  const teacherRoleInput = document.getElementById("teacherRoleInput");
  const nameErrorId = isTeacherUser ? "teacherNameError" : "studentNameError";
  const usernameErrorId = isTeacherUser
    ? "teacherUsernameError"
    : "studentUsernameError";
  const emailErrorId = isTeacherUser ? "teacherEmailError" : "studentEmailError";
  const contactErrorId = isTeacherUser
    ? "teacherContactError"
    : "studentContactError";

  clearAllAddUserErrors();
  if (batchInput) {
    batchInput.classList.remove("is-invalid");
    const batchErrorDiv = document.getElementById("batchError");
    if (batchErrorDiv) batchErrorDiv.textContent = "";
  }

  let isValid = true;

  const nameValue = nameInput.value.trim();
  const nameRegex = /^[a-zA-Z\s.]+$/;
  if (!nameValue) {
    setAddUserFieldError(nameInput, nameErrorId, "Name is required");
    isValid = false;
  } else if (!nameRegex.test(nameValue)) {
    setAddUserFieldError(
      nameInput,
      nameErrorId,
      "Name should contain only letters, spaces, and dots",
    );
    isValid = false;
  }

  if (userType === "student") {
    if (!batchInput || !batchInput.value.trim()) {
      if (batchInput) batchInput.classList.add("is-invalid");
      const errorDiv = document.getElementById("batchError");
      if (errorDiv) errorDiv.textContent = "Batch is required for students";
      isValid = false;
    }
  } else if (!teacherRoleInput || !teacherRoleInput.value.trim()) {
    setAddUserFieldError(
      teacherRoleInput,
      "teacherRoleError",
      "Designation is required",
    );
    isValid = false;
  }

  const contactValue = contactInput.value.trim();
  const contactRegex = /^\d{10}$/;
  if (!contactValue) {
    setAddUserFieldError(
      contactInput,
      contactErrorId,
      "Contact number is required",
    );
    isValid = false;
  } else if (!contactRegex.test(contactValue)) {
    setAddUserFieldError(
      contactInput,
      contactErrorId,
      "Contact must be exactly 10 digits",
    );
    isValid = false;
  }

  const emailValue = emailInput.value.trim();
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (!emailValue) {
    setAddUserFieldError(emailInput, emailErrorId, "Email is required");
    isValid = false;
  } else if (!emailRegex.test(emailValue)) {
    setAddUserFieldError(
      emailInput,
      emailErrorId,
      "Please enter a valid email address",
    );
    isValid = false;
  }

  if (userType === "student") {
    if (!usernameInput.value.trim() && batchInput && batchInput.value.trim()) {
      generateUsernameFromBatch(batchInput);
    }
  }

  const usernameValue = usernameInput.value.trim();
  if (!usernameValue) {
    setAddUserFieldError(usernameInput, usernameErrorId, "Username is required");
    isValid = false;
  }

   // For students, validate board (grade optional)
   if (userType === "student") {
     const boardSelect = form.querySelector('[name="board"]');
     const gradeSelect = form.querySelector('[name="grade"]');
     const boardErrorId = "boardError";

     // Create error div for board if it doesn't exist
     if (boardSelect && !document.getElementById(boardErrorId)) {
       const errorDiv = document.createElement("div");
       errorDiv.id = boardErrorId;
       errorDiv.className = "invalid-feedback";
       errorDiv.style.display = "block";
       boardSelect.parentNode.appendChild(errorDiv);
     }

     if (boardSelect && !boardSelect.value) {
       boardSelect.classList.add("is-invalid");
       const errorDiv = document.getElementById(boardErrorId);
       if (errorDiv) errorDiv.textContent = "Board is required";
       isValid = false;
     } else if (boardSelect) {
       boardSelect.classList.remove("is-invalid");
       const errorDiv = document.getElementById(boardErrorId);
       if (errorDiv) errorDiv.textContent = "";
     }

     // Grade is optional - just clear any previous error if present
     if (gradeSelect) {
       gradeSelect.classList.remove("is-invalid");
       const gradeErrorDiv = document.getElementById("gradeError");
       if (gradeErrorDiv) gradeErrorDiv.textContent = "";
     }
   }

  if (!isValid) {
    return;
  }

  // All validations passed, submit the form
  // Hide modal before submitting to prevent any timing issues
  if (addUserModal) {
    addUserModal.hide();
  }

  // All validations passed, submit the form
  form.submit();
}

// Add direct input filtering for contact field to prevent alphabets
document.addEventListener("DOMContentLoaded", function () {
  const contactInputs = document.querySelectorAll(".number-only");
  contactInputs.forEach((input) => {
    input.addEventListener("input", function () {
      // Remove any non-digit characters
      this.value = this.value.replace(/\D/g, "");
      // Limit to 10 digits
      if (this.value.length > 10) {
        this.value = this.value.slice(0, 10);
      }
    });

    // Also handle paste event
    input.addEventListener("paste", function (e) {
      e.preventDefault();
      const pastedText = (e.clipboardData || window.clipboardData).getData(
        "text",
      );
      const filtered = pastedText.replace(/\D/g, "").slice(0, 10);
      this.value = filtered;
    });
  });
});

document.addEventListener("input", (e) => {
  if (e.target.classList.contains("alpha-only")) {
    e.target.value = e.target.value.replace(/[^a-zA-Z\s.]/g, "");
  }

  if (e.target.classList.contains("number-only")) {
    e.target.value = e.target.value.replace(/\D/g, "");
  }

  if (e.target && e.target.id === "batchInputCommon") {
    generateUsernameFromBatch(e.target);
  }

  if (e.target && e.target.id === "teacherRoleInput") {
    toggleTeacherRoleFields();
  }

  if (e.target && e.target.id === "editTeacherRole") {
    toggleEditTeacherRoleFields();
  }
});

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "batchInputCommon") {
    generateUsernameFromBatch(e.target);
  }

  if (e.target && e.target.id === "teacherRoleInput") {
    toggleTeacherRoleFields();
  }

  if (e.target && e.target.id === "editTeacherRole") {
    toggleEditTeacherRoleFields();
  }
});

function confirmDelete(message = "Are you sure you want to delete this user?") {
  return confirm(message);
}

const editStudentModal = document.getElementById("editStudentModal");

if (editStudentModal) {
  editStudentModal.addEventListener("show.bs.modal", function (event) {
    const button = event.relatedTarget;

    const id = button.dataset.id;

    const form = document.getElementById("editStudentForm");
    form.action = `/edit-student/${id}/`;

    document.getElementById("editStudentName").value =
      button.dataset.name || "";
    document.getElementById("editStudentEmail").value =
      button.dataset.email || "";

    document.getElementById("editStudentContact").value =
      button.dataset.contact || "";

    document.getElementById("editStudentBoard").value =
      button.dataset.board || "";

    document.getElementById("editStudentGrade").value =
      button.dataset.grade || "";

    document.getElementById("editStudentGender").value =
      button.dataset.gender || "";

    document.getElementById("editStudentBatch").value =
      button.dataset.batch || "";
  });
}

const editTeacherModal = document.getElementById("editTeacherModal");
const editTeacherForm = document.getElementById("editTeacherForm");

if (editTeacherForm && editTeacherForm.dataset.validationBound !== "true") {
  editTeacherForm.addEventListener("submit", (event) => {
    const nameInput = document.getElementById("editTeacherName");
    if (!nameInput) {
      return;
    }

    clearEditTeacherNameError();

    const nameValue = nameInput.value.trim();
    const nameRegex = /^[a-zA-Z\s.]+$/;
    if (!nameValue) {
      setEditTeacherFieldError(nameInput, "editTeacherNameError", "Name is required");
      event.preventDefault();
      return;
    }

    if (!nameRegex.test(nameValue)) {
      setEditTeacherFieldError(
        nameInput,
        "editTeacherNameError",
        "Name should contain only letters, spaces, and dots",
      );
      event.preventDefault();
    }
  });
  editTeacherForm.dataset.validationBound = "true";
}

if (editTeacherModal) {
  editTeacherModal.addEventListener("show.bs.modal", function (event) {
    const button = event.relatedTarget;

    const id = button.dataset.id;

    const form = document.getElementById("editTeacherForm");
    form.action = `/edit-teacher/${id}/`;

    document.getElementById("editTeacherName").value =
      button.dataset.name || "";

    document.getElementById("editTeacherUsername").value =
      button.dataset.username || "";

    document.getElementById("editTeacherEmail").value =
      button.dataset.email || "";

    document.getElementById("editTeacherContact").value =
      button.dataset.contact || "";

    document.getElementById("editTeacherGender").value =
      button.dataset.gender || "";

    document.getElementById("editTeacherRole").value =
      button.dataset.role || "";

    document.getElementById("editTeacherBloodGroup").value =
      button.dataset.bloodGroup || "";

    document.getElementById("editTeacherSubjects").value =
      button.dataset.subjects || "";

    document.getElementById("editTeacherGrade").value =
      button.dataset.grade || "";

    document.getElementById("editTeacherBoard").value =
      button.dataset.board || "";

    document.getElementById("editTeacherBatch").value =
      button.dataset.batch || "";
    document.getElementById("editTeacherPassword").value = "";

    clearEditTeacherNameError();

    toggleEditTeacherRoleFields();

    // Set current profile picture preview
    const currentPicDiv = document.getElementById("currentProfilePicture");
    const profilePicUrl = button.dataset.profilePicture;
    if (currentPicDiv) {
      if (profilePicUrl) {
        currentPicDiv.innerHTML = `<img src="${profilePicUrl}" alt="Current Profile" width="60" height="60" style="border-radius: 50%; object-fit: cover; border: 2px solid #ddd;" />`;
      } else {
        currentPicDiv.innerHTML = `<span class="text-muted"><i class="bi bi-person-circle" style="font-size: 2rem;"></i></span>`;
      }
    }
  });
}
