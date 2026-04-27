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
  const teacherFields = document.getElementById("teacherFields");
  const studentInputs = studentFields.querySelectorAll("input, select, textarea");
  const teacherInputs = teacherFields.querySelectorAll("input, select, textarea");

  // Handle username field readonly state and hint
  const usernameInput = document.getElementById('commonUsername');
  const usernameCol = document.querySelector('.field-username-col');
  const usernameHint = document.getElementById('usernameHint');

  if (type === "student") {
    studentFields.style.display = "flex";
    teacherFields.style.display = "none";
    studentInputs.forEach((input) => {
      input.disabled = false;
    });
    teacherInputs.forEach((input) => {
      input.disabled = true;
    });
    // Make username readonly for students
    if (usernameInput) {
      usernameInput.readOnly = true;
      usernameInput.classList.add('readonly-bg');
      if (usernameCol) usernameCol.style.display = ''; // show
    }
    // Clear and regenerate based on batch
    if (usernameInput) usernameInput.value = '';
    if (usernameHint) usernameHint.style.display = 'none';
    const batchInput = getCommonBatchInput();
    if (batchInput && batchInput.value.trim()) {
      generateUsernameFromBatch(batchInput);
    }
  } else {
    studentFields.style.display = "none";
    teacherFields.style.display = "flex";
    studentInputs.forEach((input) => {
      input.disabled = true;
    });
    teacherInputs.forEach((input) => {
      input.disabled = false;
    });
    // Make username editable for teachers
    if (usernameInput) {
      usernameInput.readOnly = false;
      usernameInput.classList.remove('readonly-bg');
      if (usernameHint) usernameHint.style.display = 'none';
    }
  }

  // Toggle common batch field visibility and disabled state
  const commonBatchCol = document.getElementById("commonBatchCol");
  if (commonBatchCol) {
    const batchInput = commonBatchCol.querySelector('input[name="batch"]');
    if (batchInput) {
      // When student: enabled; when teacher: disabled/hide
      batchInput.disabled = (type !== "student");
    }
    commonBatchCol.style.display = (type === "student") ? "" : "none";
  }

  // Reorder common fields and adjust password column width
  const commonRow = document.getElementById("commonFieldsRow");
  if (!commonRow) return;

  const nameCol = commonRow.querySelector('.field-name-col');
  const batchCol = commonRow.querySelector('.field-batch-col');
  const contactCol = commonRow.querySelector('.field-contact-col');
  const emailCol = commonRow.querySelector('.field-email-col');
  const genderCol = commonRow.querySelector('.field-gender-col');
  const passwordCol = commonRow.querySelector('.field-password-col');

  if (type === "student") {
    // Student mode: natural DOM order (name, batch, username, contact, email, gender, password)
    [nameCol, batchCol, usernameCol, contactCol, emailCol, genderCol, passwordCol].forEach(col => {
      if (col) col.style.order = '';
    });
    // Ensure password full width
    if (passwordCol) {
      passwordCol.classList.remove('col-md-6');
      passwordCol.classList.add('col-12');
    }
  } else {
    // Teacher mode: order: name, username, email, contact, password, gender
    if (nameCol) nameCol.style.order = '0';
    if (usernameCol) usernameCol.style.order = '1';
    if (emailCol) emailCol.style.order = '2';
    if (contactCol) contactCol.style.order = '3';
    if (passwordCol) {
      passwordCol.style.order = '4';
      passwordCol.classList.remove('col-12');
      passwordCol.classList.add('col-md-6');
    }
    if (genderCol) genderCol.style.order = '5';
    if (batchCol) batchCol.style.order = '-1';
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
  const fields = ["name", "username", "email", "contact"];
  fields.forEach((fieldId) => {
    const input = document.querySelector(`#addUserModal [name="${fieldId}"]`);
    if (input) {
      input.classList.remove("is-invalid");
    }
    const errorDiv = document.getElementById(fieldId + "Error");
    if (errorDiv) {
      errorDiv.textContent = "";
    }
  });
}

function validateAndSubmitAddUser() {
  const form = getAddUserForm();
  const nameInput = form.querySelector('[name="name"]');
  const usernameInput = getCommonUsernameInput();
  const emailInput = form.querySelector('[name="email"]');
  const contactInput = form.querySelector('[name="contact"]');
  const batchInput = getCommonBatchInput();

  // Get the user type to determine which fields to validate
  const userType = document.getElementById("userTypeSelect").value;

   // Clear previous errors
   clearAllAddUserErrors();
   // Clear batch error manually (since not in clearAll)
   if (batchInput) {
     batchInput.classList.remove("is-invalid");
     const batchErrorDiv = document.getElementById("batchError");
     if (batchErrorDiv) batchErrorDiv.textContent = "";
   }

   let isValid = true;

  // Validate name - only alphabets and spaces
  const nameValue = nameInput.value.trim();
  const nameRegex = /^[a-zA-Z\s]+$/;
  if (!nameValue) {
    nameInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("nameError");
    if (errorDiv) errorDiv.textContent = "Name is required";
    isValid = false;
  } else if (!nameRegex.test(nameValue)) {
    nameInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("nameError");
    if (errorDiv) errorDiv.textContent = "Name should contain only letters and spaces";
    isValid = false;
  }

  // Validate batch for students (required)
  if (userType === "student") {
    if (!batchInput || !batchInput.value.trim()) {
      if (batchInput) batchInput.classList.add("is-invalid");
      const errorDiv = document.getElementById("batchError");
      if (errorDiv) errorDiv.textContent = "Batch is required for students";
      isValid = false;
    }
  }

  // Validate contact - only 10 digits
  const contactValue = contactInput.value.trim();
  const contactRegex = /^\d{10}$/;
  if (!contactValue) {
    contactInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("contactError");
    if (errorDiv) errorDiv.textContent = "Contact number is required";
    isValid = false;
  } else if (!contactRegex.test(contactValue)) {
    contactInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("contactError");
    if (errorDiv) errorDiv.textContent = "Contact must be exactly 10 digits";
    isValid = false;
  }

  // Validate email
  const emailValue = emailInput.value.trim();
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (!emailValue) {
    emailInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("emailError");
    if (errorDiv) errorDiv.textContent = "Email is required";
    isValid = false;
  } else if (!emailRegex.test(emailValue)) {
    emailInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("emailError");
    if (errorDiv) errorDiv.textContent = "Please enter a valid email address";
    isValid = false;
  }

  // For students, ensure username is auto-generated if batch provided
  if (userType === "student") {
    // Auto-generate username from batch if empty
    if (!usernameInput.value.trim() && batchInput && batchInput.value.trim()) {
      generateUsernameFromBatch(batchInput);
    }
  }

  // Validate username (required for both types)
  const usernameValue = usernameInput.value.trim();
  if (!usernameValue) {
    usernameInput.classList.add("is-invalid");
    const errorDiv = document.getElementById("usernameError");
    if (errorDiv) errorDiv.textContent = "Username is required";
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
