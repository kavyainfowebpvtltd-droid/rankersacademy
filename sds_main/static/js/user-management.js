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

function getTeacherUsernameInput() {
  return document.getElementById("teacherUsernameInput");
}

function getCurrentUserType() {
  const userTypeSelect = document.getElementById("userTypeSelect");
  return userTypeSelect ? userTypeSelect.value : "student";
}

function setValidationError(input, errorId, message) {
  if (input) {
    input.classList.add("is-invalid");
  }
  const errorDiv = document.getElementById(errorId);
  if (errorDiv) {
    errorDiv.textContent = message;
  }
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
  if (addUserModalEl) {
    addUserModal = new bootstrap.Modal(addUserModalEl);
  }

  toggleFields();

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
  if (addUserModal) addUserModal.show();
  const form = getAddUserForm();
  if (form) {
    form.reset();
    document.getElementById("userTypeSelect").value = "student";
    document.getElementById("userTypeHidden").value = "student";
    const studentPasswordInput = document.getElementById("addUserPassword");
    const teacherPasswordInput = document.getElementById("teacherAddUserPassword");
    if (studentPasswordInput) studentPasswordInput.value = defaultOneTimePassword;
    if (teacherPasswordInput) teacherPasswordInput.value = defaultOneTimePassword;
    toggleFields();
    clearAllAddUserErrors();
    const usernameHint = document.getElementById("usernameHint");
    if (usernameHint) usernameHint.style.display = "none";
  }
}

function toggleFields() {
  const type = getCurrentUserType();
  document.getElementById("userTypeHidden").value = type;

  const studentFields = document.getElementById("studentFields");
  const teacherCommonFields = document.getElementById("teacherCommonFieldsRow");
  const teacherFields = document.getElementById("teacherFields");
  const studentInputs = studentFields ? studentFields.querySelectorAll("input, select, textarea") : [];
  const teacherCommonInputs = teacherCommonFields ? teacherCommonFields.querySelectorAll("input, select, textarea") : [];
  const teacherInputs = teacherFields ? teacherFields.querySelectorAll("input, select, textarea") : [];
  const usernameInput = getCommonUsernameInput();
  const usernameHint = document.getElementById("usernameHint");

  if (type === "student") {
    if (studentFields) studentFields.style.display = "flex";
    if (teacherCommonFields) teacherCommonFields.style.display = "none";
    if (teacherFields) teacherFields.style.display = "none";
    studentInputs.forEach((input) => {
      input.disabled = false;
    });
    teacherCommonInputs.forEach((input) => {
      input.disabled = true;
    });
    teacherInputs.forEach((input) => {
      input.disabled = true;
    });
    if (usernameInput) {
      usernameInput.readOnly = true;
      usernameInput.classList.add("readonly-bg");
    }
    if (usernameInput) usernameInput.value = '';
    if (usernameHint) usernameHint.style.display = 'none';
    const batchInput = getCommonBatchInput();
    if (batchInput && batchInput.value.trim()) {
      generateUsernameFromBatch(batchInput);
    }
  } else {
    if (studentFields) studentFields.style.display = "none";
    if (teacherCommonFields) teacherCommonFields.style.display = "flex";
    if (teacherFields) teacherFields.style.display = "flex";
    studentInputs.forEach((input) => {
      input.disabled = true;
    });
    teacherCommonInputs.forEach((input) => {
      input.disabled = false;
    });
    teacherInputs.forEach((input) => {
      input.disabled = false;
    });
    if (usernameInput) {
      usernameInput.classList.remove("readonly-bg");
      if (usernameHint) usernameHint.style.display = 'none';
    }
  }
}

function clearAllAddUserErrors() {
  const form = getAddUserForm();
  if (!form) return;

  form.querySelectorAll(".is-invalid").forEach((input) => {
    input.classList.remove("is-invalid");
  });

  [
    "studentNameError",
    "teacherNameError",
    "studentUsernameError",
    "teacherUsernameError",
    "studentEmailError",
    "teacherEmailError",
    "studentContactError",
    "teacherContactError",
    "studentEmergencyContactError",
    "studentStreamError",
    "studentBoardError",
    "batchError",
  ].forEach((errorId) => {
    const errorDiv = document.getElementById(errorId);
    if (errorDiv) {
      errorDiv.textContent = "";
    }
  });
}

function validateAndSubmitAddUser() {
  const form = getAddUserForm();
  const batchInput = getCommonBatchInput();
  const userType = getCurrentUserType();
  const nameInput = document.getElementById(
    userType === "student" ? "studentNameInput" : "teacherNameInput",
  );
  const usernameInput =
    userType === "student" ? getCommonUsernameInput() : getTeacherUsernameInput();
  const emailInput = document.getElementById(
    userType === "student" ? "studentEmailInput" : "teacherEmailInput",
  );
  const contactInput = document.getElementById(
    userType === "student" ? "studentContactInput" : "teacherContactInput",
  );

  clearAllAddUserErrors();

  let isValid = true;
  const nameRegex = /^[a-zA-Z\s]+$/;
  const nameValue = nameInput ? nameInput.value.trim() : "";
  if (!nameValue) {
    setValidationError(
      nameInput,
      userType === "student" ? "studentNameError" : "teacherNameError",
      "Name is required",
    );
    isValid = false;
  } else if (!nameRegex.test(nameValue)) {
    setValidationError(
      nameInput,
      userType === "student" ? "studentNameError" : "teacherNameError",
      "Name should contain only letters and spaces",
    );
    isValid = false;
  }

  if (userType === "student") {
    if (!batchInput || !batchInput.value.trim()) {
      setValidationError(batchInput, "batchError", "Batch is required for students");
      isValid = false;
    }
  }

  const contactRegex = /^\d{10}$/;
  const contactValue = contactInput ? contactInput.value.trim() : "";
  if (!contactValue) {
    setValidationError(
      contactInput,
      userType === "student" ? "studentContactError" : "teacherContactError",
      "Contact number is required",
    );
    isValid = false;
  } else if (!contactRegex.test(contactValue)) {
    setValidationError(
      contactInput,
      userType === "student" ? "studentContactError" : "teacherContactError",
      "Contact must be exactly 10 digits",
    );
    isValid = false;
  }

  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  const emailValue = emailInput ? emailInput.value.trim() : "";
  if (!emailValue) {
    setValidationError(
      emailInput,
      userType === "student" ? "studentEmailError" : "teacherEmailError",
      "Email is required",
    );
    isValid = false;
  } else if (!emailRegex.test(emailValue)) {
    setValidationError(
      emailInput,
      userType === "student" ? "studentEmailError" : "teacherEmailError",
      "Please enter a valid email address",
    );
    isValid = false;
  }

  if (userType === "student") {
    if (usernameInput && !usernameInput.value.trim() && batchInput && batchInput.value.trim()) {
      generateUsernameFromBatch(batchInput);
    }
  }

  const usernameValue = usernameInput ? usernameInput.value.trim() : "";
  if (!usernameValue) {
    setValidationError(
      usernameInput,
      userType === "student" ? "studentUsernameError" : "teacherUsernameError",
      "Username is required",
    );
    isValid = false;
  }

  if (userType === "student") {
    const emergencyContactInput = document.getElementById("studentEmergencyContactInput");
    const emergencyContactValue = emergencyContactInput
      ? emergencyContactInput.value.trim()
      : "";
    const streamSelect = document.getElementById("studentStreamInput");
    const boardSelect = document.getElementById("studentBoardInput");

    if (emergencyContactValue && !contactRegex.test(emergencyContactValue)) {
      setValidationError(
        emergencyContactInput,
        "studentEmergencyContactError",
        "Emergency contact must be exactly 10 digits",
      );
      isValid = false;
    }

    if (streamSelect && !streamSelect.value) {
      setValidationError(streamSelect, "studentStreamError", "Stream is required");
      isValid = false;
    }

    if (boardSelect && !boardSelect.value) {
      setValidationError(boardSelect, "studentBoardError", "Board is required");
      isValid = false;
    }
  }

  if (!isValid) {
    return;
  }

  if (addUserModal) {
    addUserModal.hide();
  }

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
    e.target.value = e.target.value.replace(/[^a-zA-Z\s]/g, "");
  }

  if (e.target.classList.contains("number-only")) {
    e.target.value = e.target.value.replace(/\D/g, "");
  }

  if (e.target && e.target.id === "batchInputCommon") {
    generateUsernameFromBatch(e.target);
  }
});

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "batchInputCommon") {
    generateUsernameFromBatch(e.target);
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

    document.getElementById("editTeacherSubjects").value =
      button.dataset.subjects || "";

    document.getElementById("editTeacherGrade").value =
      button.dataset.grade || "";

    document.getElementById("editTeacherBoard").value =
      button.dataset.board || "";

    document.getElementById("editTeacherBatch").value =
      button.dataset.batch || "";

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
