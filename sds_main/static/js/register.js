let currentStep = 1;
const totalSteps = 4;
const personNameRegex = /^[A-Za-z ]+$/;

// Helper function to show inline error
function showFieldError(fieldId, message) {
  const field = document.getElementById(fieldId);
  const errorDiv = document.getElementById(fieldId + "Error");

  if (field) {
    field.classList.add("is-invalid");
  }

  if (errorDiv) {
    errorDiv.textContent = message;
    errorDiv.style.display = "block";
  }
}

// Helper function to clear inline error
function clearFieldError(fieldId) {
  const field = document.getElementById(fieldId);
  const errorDiv = document.getElementById(fieldId + "Error");

  if (field) {
    field.classList.remove("is-invalid");
  }

  if (errorDiv) {
    errorDiv.textContent = "";
    errorDiv.style.display = "none";
  }
}

// Helper function to clear all inline errors
function clearAllFieldErrors() {
  const fieldIds = [
    "fullName",
    "dateOfBirth",
    "gender",
    "phone",
    "email",
    "city",
    "state",
    "pincode",
    "class",
    "board",
    "schoolName",
    "password",
    "confirmPassword",
  ];
  fieldIds.forEach((id) => clearFieldError(id));
}

document.addEventListener("DOMContentLoaded", function () {
  updateProgress();

  const today = new Date().toISOString().split("T")[0];
  const dobEl = document.getElementById("dateOfBirth");
  if (dobEl) dobEl.setAttribute("max", today);

  const phoneEl = document.getElementById("phone");
  if (phoneEl) {
    phoneEl.addEventListener("input", function () {
      // Clear any previous error when user starts typing
      clearFieldError("phone");
      this.value = this.value.replace(/\D/g, "").slice(0, 10);
    });

    // Check if phone already exists when user leaves the field
    phoneEl.addEventListener("blur", async function () {
      const phone = this.value.trim();
      if (phone.length === 10) {
        await checkPhoneExists(phone);
      }
    });
  }

  const pincodeEl = document.getElementById("pincode");
  if (pincodeEl) {
    pincodeEl.addEventListener("input", function () {
      clearFieldError("pincode");
      this.value = this.value.replace(/\D/g, "").slice(0, 6);
    });
  }

  // Full name validation - no numbers allowed
  const fullNameEl = document.getElementById("fullName");
  if (fullNameEl) {
    fullNameEl.addEventListener("input", function () {
      clearFieldError("fullName");
      this.value = this.value.replace(/[^A-Za-z ]/g, "");
    });
  }

  document.querySelectorAll(".password-toggle").forEach((toggleBtn) => {
    toggleBtn.addEventListener("click", function () {
      const input = document.getElementById(this.dataset.target);
      const icon = this.querySelector("i");
      if (!input || !icon) return;

      const showPassword = input.type === "password";
      input.type = showPassword ? "text" : "password";
      icon.className = showPassword ? "bi bi-eye-slash" : "bi bi-eye";
      this.setAttribute(
        "aria-label",
        showPassword ? "Hide password" : "Show password",
      );
    });
  });

  // Email validation - check if already exists
  const emailEl = document.getElementById("email");
  if (emailEl) {
    emailEl.addEventListener("input", function () {
      clearFieldError("email");
    });

    emailEl.addEventListener("blur", async function () {
      const email = this.value.trim();
      if (email && email.includes("@")) {
        await checkEmailExists(email);
      }
    });
  }

  // City validation - no numbers
  const cityEl = document.getElementById("city");
  if (cityEl) {
    cityEl.addEventListener("input", function () {
      clearFieldError("city");
      // Allow only letters and spaces
      this.value = this.value.replace(/[0-9]/g, "");
    });
  }

  // Date of Birth validation - no future dates
  const dobEl2 = document.getElementById("dateOfBirth");
  if (dobEl2) {
    dobEl2.addEventListener("change", function () {
      clearFieldError("dateOfBirth");
      const selectedDate = new Date(this.value);
      const today = new Date();
      today.setHours(23, 59, 59, 999); // End of today

      if (selectedDate > today) {
        showFieldError("dateOfBirth", "Date of Birth cannot be in the future");
        this.value = "";
      }
    });
  }
});

// Function to check if phone already exists
async function checkPhoneExists(phone) {
  try {
    const response = await fetch(
      `/auth/check-phone-exists/?phone=${encodeURIComponent(phone)}`,
    );
    const data = await response.json();

    if (data.exists) {
      showFieldError("phone", "Phone Number Already Registered");
      return true;
    } else {
      clearFieldError("phone");
      return false;
    }
  } catch (e) {
    console.error("Error checking phone:", e);
    return false;
  }
}

// Function to check if email already exists
async function checkEmailExists(email) {
  try {
    const response = await fetch(
      `/auth/check-email-exists/?email=${encodeURIComponent(email)}`,
    );
    const data = await response.json();

    if (data.exists) {
      showFieldError("email", "Email Id Already Registered");
      return true;
    } else {
      clearFieldError("email");
      return false;
    }
  } catch (e) {
    console.error("Error checking email:", e);
    return false;
  }
}

function updateProgress() {
  const progressPercentage = ((currentStep - 1) / (totalSteps - 1)) * 100;
  document.getElementById("progressFill").style.width =
    progressPercentage + "%";

  for (let i = 1; i <= totalSteps; i++) {
    const stepIndicator = document.getElementById("stepIndicator" + i);
    const stepContent = document.getElementById("step" + i);

    stepIndicator.classList.remove("active", "completed");
    stepContent.classList.remove("active");

    if (i < currentStep) {
      stepIndicator.classList.add("completed");
      const circle = stepIndicator.querySelector(".step-circle");
      circle.innerHTML = '<i class="bi bi-check"></i>';
    } else if (i === currentStep) {
      stepIndicator.classList.add("active");
      stepContent.classList.add("active");
      const circle = stepIndicator.querySelector(".step-circle");
      circle.textContent = i;
    } else {
      const circle = stepIndicator.querySelector(".step-circle");
      circle.textContent = i;
    }
  }

  const backLoginBtn = document.getElementById("backLoginBtn");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const submitBtn = document.getElementById("submitBtn");

  if (currentStep === 1) {
    backLoginBtn.classList.remove("d-none");
    prevBtn.classList.add("d-none");
  } else {
    backLoginBtn.classList.add("d-none");
    prevBtn.classList.remove("d-none");
  }

  if (currentStep === totalSteps) {
    nextBtn.classList.add("d-none");
    submitBtn.classList.remove("d-none");
  } else {
    nextBtn.classList.remove("d-none");
    submitBtn.classList.add("d-none");
  }
}

function validateStep1() {
  const fullName = (document.getElementById("fullName")?.value || "").trim();
  const dateOfBirth = document.getElementById("dateOfBirth")?.value || "";
  const gender = document.getElementById("gender")?.value || "";
  let isValid = true;

  if (!fullName) {
    showFieldError("fullName", "Please enter your full name");
    isValid = false;
  } else if (!personNameRegex.test(fullName)) {
    showFieldError("fullName", "Full name should contain only letters and spaces");
    isValid = false;
  } else {
    clearFieldError("fullName");
  }

  if (!dateOfBirth) {
    showFieldError("dateOfBirth", "Please select your date of birth");
    isValid = false;
  } else {
    const selectedDate = new Date(dateOfBirth);
    const today = new Date();
    if (selectedDate > today) {
      showFieldError("dateOfBirth", "Date of Birth cannot be in the future");
      isValid = false;
    } else {
      clearFieldError("dateOfBirth");
    }
  }

  if (!gender) {
    showFieldError("gender", "Please select your gender");
    isValid = false;
  } else {
    clearFieldError("gender");
  }

  return isValid;
}

async function validateStep2() {
  const phone = (document.getElementById("phone")?.value || "").trim();
  const email = (document.getElementById("email")?.value || "").trim();
  const city = (document.getElementById("city")?.value || "").trim();
  const state = document.getElementById("state")?.value || "";
  const pincode = (document.getElementById("pincode")?.value || "").trim();
  let isValid = true;

  // Phone validation
  if (!phone) {
    showFieldError("phone", "Please enter your phone number");
    isValid = false;
  } else if (phone.length !== 10) {
    showFieldError("phone", "Please enter a valid 10-digit phone number");
    isValid = false;
  } else {
    // Check if phone already exists
    const phoneExists = await checkPhoneExists(phone);
    if (phoneExists) {
      isValid = false;
    }
  }

  // Email validation
  if (!email) {
    showFieldError("email", "Please enter your email address");
    isValid = false;
  } else if (!email.includes("@") || !email.includes(".")) {
    showFieldError("email", "Please enter a valid email address");
    isValid = false;
  } else {
    // Check if email already exists
    const emailExists = await checkEmailExists(email);
    if (emailExists) {
      isValid = false;
    }
  }

  // City validation
  if (!city) {
    showFieldError("city", "Please enter your city");
    isValid = false;
  } else if (/\d/.test(city)) {
    showFieldError("city", "City should not contain numbers");
    isValid = false;
  } else {
    clearFieldError("city");
  }

  // State validation
  if (!state) {
    showFieldError("state", "Please select your state");
    isValid = false;
  } else {
    clearFieldError("state");
  }

  // Pincode validation
  if (!pincode) {
    showFieldError("pincode", "Please enter your pincode");
    isValid = false;
  } else if (pincode.length !== 6) {
    showFieldError("pincode", "Please enter a valid 6-digit pincode");
    isValid = false;
  } else {
    clearFieldError("pincode");
  }

  return isValid;
}

function validateStep3() {
  const classGrade = document.getElementById("class")?.value || "";
  const board = document.getElementById("board")?.value || "";
  const schoolName = (
    document.getElementById("schoolName")?.value || ""
  ).trim();
  let isValid = true;

  const selectedExams = [];
  if (document.getElementById("examJee")?.checked) selectedExams.push("JEE");
  if (document.getElementById("examMhcet")?.checked)
    selectedExams.push("MHTCET");
  if (document.getElementById("examNeet")?.checked) selectedExams.push("NEET");

  if (!classGrade) {
    showFieldError("class", "Please select your class");
    isValid = false;
  } else {
    clearFieldError("class");
  }

  if (!board) {
    showFieldError("board", "Please select your board");
    isValid = false;
  } else {
    clearFieldError("board");
  }

  if (!schoolName) {
    showFieldError("schoolName", "Please enter your school name");
    isValid = false;
  } else {
    clearFieldError("schoolName");
  }

  if (selectedExams.length === 0) {
    Swal.fire({
      icon: "warning",
      title: "Validation Error",
      text: "Please select at least one interested exam",
    });
    isValid = false;
  }
  return isValid;
}

function validateStep4() {
  const password = document.getElementById("password")?.value || "";
  const confirmPassword =
    document.getElementById("confirmPassword")?.value || "";
  let isValid = true;

  if (!password) {
    showFieldError("password", "Please enter a password");
    isValid = false;
  } else if (password.length < 6) {
    showFieldError("password", "Password must be at least 6 characters");
    isValid = false;
  } else {
    clearFieldError("password");
  }

  if (!confirmPassword) {
    showFieldError("confirmPassword", "Please confirm your password");
    isValid = false;
  } else if (password !== confirmPassword) {
    showFieldError("confirmPassword", "Passwords do not match");
    isValid = false;
  } else {
    clearFieldError("confirmPassword");
  }

  return isValid;
}

function nextStep() {
  let isValid = false;

  if (currentStep === 1) isValid = validateStep1();
  else if (currentStep === 2) isValid = validateStep2();
  else if (currentStep === 3) isValid = validateStep3();

  if (isValid && currentStep < totalSteps) {
    currentStep++;
    updateProgress();
  }
}

function previousStep() {
  if (currentStep > 1) {
    currentStep--;
    updateProgress();
  }
}

function getCookie(name) {
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

async function postForm(url, payloadObj) {
  const fd = new FormData();
  Object.keys(payloadObj).forEach((k) => fd.append(k, payloadObj[k]));

  const res = await fetch(url, {
    method: "POST",
    headers: { "X-CSRFToken": getCookie("csrftoken") },
    body: fd,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.msg || "Something went wrong");
  }
  return data;
}

document.addEventListener("DOMContentLoaded", function () {
  const sendPhoneOtpBtn = document.getElementById("sendPhoneOtpBtn");
  const phoneOtpSection = document.getElementById("phoneOtpSection");

  const phoneInput = document.getElementById("phone");
  const phoneOtp = document.getElementById("phoneOtp");

  let phoneOtpSent = false;
  let phoneVerified = false;

  if (phoneOtp) {
    phoneOtp.addEventListener("input", function () {
      this.value = this.value.replace(/\D/g, "").slice(0, 4);
    });
  }

  function resetPhoneVerificationUI() {
    phoneOtpSent = false;
    phoneVerified = false;
    if (phoneOtpSection) phoneOtpSection.style.display = "none";

    if (sendPhoneOtpBtn) {
      sendPhoneOtpBtn.disabled = false;
      sendPhoneOtpBtn.innerHTML =
        '<i class="bi bi-phone me-2"></i>Send Phone OTP';
      sendPhoneOtpBtn.classList.remove("btn-success-custom");
      sendPhoneOtpBtn.classList.add("btn-primary-custom");
    }

    if (phoneOtp) phoneOtp.value = "";
    if (phoneInput) phoneInput.readOnly = false;
    if (phoneOtp) phoneOtp.readOnly = false;
  }

  if (phoneInput) {
    phoneInput.addEventListener("input", function () {
      if (phoneOtpSent || phoneVerified) resetPhoneVerificationUI();
    });
  }

  if (sendPhoneOtpBtn) {
    sendPhoneOtpBtn.addEventListener("click", async function () {
      const phone = (phoneInput?.value || "").trim();

      try {
        if (!phoneOtpSent) {
          if (phone.length !== 10) {
            showFieldError(
              "phone",
              "Please enter a valid 10-digit phone number",
            );
            return;
          }

          // Check if phone already exists before sending OTP
          const phoneExists = await checkPhoneExists(phone);
          if (phoneExists) {
            return;
          }

          await postForm("/auth/send-register-phone-otp/", { phone });

          if (phoneOtpSection) phoneOtpSection.style.display = "block";
          phoneOtpSent = true;

          sendPhoneOtpBtn.innerHTML =
            '<i class="bi bi-shield-check me-2"></i>Verify Phone OTP';
          sendPhoneOtpBtn.classList.remove("btn-primary-custom");
          sendPhoneOtpBtn.classList.add("btn-success-custom");
        } else {
          const otp = (phoneOtp?.value || "").trim();

          if (otp.length !== 4) {
            Swal.fire({
              icon: "warning",
              title: "Validation Error",
              text: "Please enter 4-digit phone OTP",
            });
            return;
          }

          await postForm("/auth/verify-register-phone-otp/", { phone, otp });

          phoneVerified = true;
          sendPhoneOtpBtn.innerHTML =
            '<i class="bi bi-check-circle me-2"></i>Phone Verified';
          sendPhoneOtpBtn.disabled = true;

          if (phoneInput) phoneInput.readOnly = true;
          if (phoneOtp) phoneOtp.readOnly = true;
        }
      } catch (e) {
        Swal.fire({
          icon: "error",
          title: "Error",
          text: e.message || "Something went wrong",
        });
      }
    });
  }

  const regForm = document.getElementById("registrationForm");
  if (regForm) {
    regForm.addEventListener("submit", async function (e) {
      // Prevent default form submission (page refresh)
      e.preventDefault();

      // First validate step 4
      if (!validateStep4()) {
        return;
      }

      // Validate all steps
      const step1Valid = validateStep1();
      const step2Valid = await validateStep2();
      const step3Valid = validateStep3();

      if (!step1Valid || !step2Valid || !step3Valid) {
        // Navigate to the step with error
        if (!step1Valid) {
          currentStep = 1;
          updateProgress();
        } else if (!step2Valid) {
          currentStep = 2;
          updateProgress();
        } else if (!step3Valid) {
          currentStep = 3;
          updateProgress();
        }
        return;
      }

      if (!phoneVerified) {
        Swal.fire({
          icon: "warning",
          title: "Verification Required",
          text: "Please verify your phone number using OTP before registration.",
        });
        return;
      }

      // All validations passed - submit form via AJAX
      const formData = new FormData(regForm);

      try {
        const response = await fetch("/register/", {
          method: "POST",
          body: formData,
          headers: {
            "X-CSRFToken": getCookie("csrftoken"),
          },
        });

        const data = await response.json().catch(() => ({}));

        if (response.ok) {
          // Success - redirect to login
          Swal.fire({
            icon: "success",
            title: "Registration Successful",
            text: "Your account has been created. Please login.",
            timer: 2000,
            showConfirmButton: false,
          }).then(() => {
            window.location.href="/accounts/login/";
          });
        } else {
          // Server returned error
          const errorMsg = data.msg || "Registration failed. Please try again.";

          // Check if it's a duplicate error and show inline
          if (errorMsg.toLowerCase().includes("phone")) {
            showFieldError("phone", "Phone Number Already Registered");
            currentStep = 2;
            updateProgress();
          } else if (errorMsg.toLowerCase().includes("email")) {
            showFieldError("email", "Email Id Already Registered");
            currentStep = 2;
            updateProgress();
          } else {
            Swal.fire({ icon: "error", title: "Error", text: errorMsg });
          }
        }
      } catch (err) {
        Swal.fire({
          icon: "error",
          title: "Error",
          text: "Something went wrong. Please try again.",
        });
      }
    });
  }
});
