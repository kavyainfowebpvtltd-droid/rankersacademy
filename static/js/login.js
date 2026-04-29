const left = document.getElementById("leftCard");
const right = document.getElementById("rightCard");

window.addEventListener("DOMContentLoaded", () => {
  left?.classList.add("enter-left");
  right?.classList.add("enter-right");
});

let selectedRole = "Student";
const roleInput = document.getElementById("roleInput");
const loginBtn = document.getElementById("loginBtn");

document.querySelectorAll(".role").forEach((r) => {
  r.onclick = () => {
    document
      .querySelectorAll(".role")
      .forEach((x) => x.classList.remove("active"));
    r.classList.add("active");

    selectedRole = r.dataset.role;
    roleInput.value = selectedRole;

    loginBtn.innerText = "Sign In as " + selectedRole;
  };
});

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
}

const csrfToken = getCookie("csrftoken");

const otpToggleBtn = document.getElementById("otpToggleBtn");
const otpLoginSection = document.getElementById("otpLoginSection");
const otpResetSection = document.getElementById("otpResetSection");

const usernameInput = document.getElementById("usernameField");
const passwordInput = document.getElementById("passwordField");
const loginBtnSubmit = document.getElementById("loginBtn");

const sendOtpBtn = document.getElementById("sendOtpBtn");
const verifyOtpBtn = document.getElementById("verifyOtpBtn");
const otpPhone = document.getElementById("otpPhone");
const otpInput = document.getElementById("otpInput");
const backToPasswordBtn = document.getElementById("backToPasswordBtn");

const forgotPasswordLink = document.getElementById("forgotPasswordLink");
const resetPhone = document.getElementById("resetPhone");
const sendResetOtpBtn = document.getElementById("sendResetOtpBtn");
const resetOtpInput = document.getElementById("resetOtpInput");
const verifyResetOtpBtn = document.getElementById("verifyResetOtpBtn");
const newPass = document.getElementById("newPass");
const confirmPass = document.getElementById("confirmPass");
const newPassGroup = document.getElementById("newPassGroup");
const confirmPassGroup = document.getElementById("confirmPassGroup");
const setNewPassBtn = document.getElementById("setNewPassBtn");
const resetBackBtn = document.getElementById("resetBackBtn");
const attemptTestsTrigger = document.getElementById("attemptTestsTrigger");
const attemptTestsModalEl = document.getElementById("attemptTestsModal");
const scholarshipTestSelect = document.getElementById("scholarshipTestSelect");
const scholarshipTestSummary = document.getElementById(
  "scholarshipTestSummary",
);
const scholarshipTestContinueBtn = document.getElementById(
  "scholarshipTestContinueBtn",
);

function showPasswordLogin() {
  otpLoginSection.style.display = "none";
  otpResetSection.style.display = "none";

  usernameInput.style.display = "";
  passwordInput.style.display = "";
  loginBtnSubmit.style.display = "";

  otpInput.style.display = "none";
  verifyOtpBtn.style.display = "none";
  otpInput.value = "";

  resetOtpInput.style.display = "none";
  verifyResetOtpBtn.style.display = "none";
  newPassGroup.style.display = "none";
  confirmPassGroup.style.display = "none";
  setNewPassBtn.style.display = "none";

  usernameInput.required = true;
  passwordInput.required = true;
}

function showOtpLogin() {
  otpResetSection.style.display = "none";
  otpLoginSection.style.display = "";

  usernameInput.style.display = "none";
  passwordInput.style.display = "none";
  loginBtnSubmit.style.display = "none";

  usernameInput.required = false;
  passwordInput.required = false;
}

function showReset() {
  otpLoginSection.style.display = "none";
  otpResetSection.style.display = "";

  usernameInput.style.display = "none";
  passwordInput.style.display = "none";
  loginBtnSubmit.style.display = "none";

  usernameInput.required = false;
  passwordInput.required = false;
}

otpToggleBtn?.addEventListener("click", () => showOtpLogin());
backToPasswordBtn?.addEventListener("click", () => showPasswordLogin());

forgotPasswordLink?.addEventListener("click", (e) => {
  e.preventDefault();
  showReset();
});

resetBackBtn?.addEventListener("click", () => showPasswordLogin());

sendOtpBtn?.addEventListener("click", async () => {
  const phone = (otpPhone.value || "").trim();
  const role = roleInput.value;

  const form = new URLSearchParams();
  form.append("phone", phone);
  form.append("role", role);

  const res = await fetch("/auth/send-login-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: form.toString(),
  });

  const data = await res.json();
  if (!data.ok) {
    Swal.fire({ icon: "error", title: data.msg || "Failed to send OTP" });
    return;
  }

  Swal.fire({ icon: "success", title: data.msg || "OTP sent" });
  otpInput.style.display = "";
  verifyOtpBtn.style.display = "";
});

verifyOtpBtn?.addEventListener("click", async () => {
  const phone = (otpPhone.value || "").trim();
  const otp = (otpInput.value || "").trim();
  const role = roleInput.value;

  const form = new URLSearchParams();
  form.append("phone", phone);
  form.append("otp", otp);
  form.append("role", role);

  const res = await fetch("/auth/verify-login-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: form.toString(),
  });

  const data = await res.json();
  if (!data.ok) {
    Swal.fire({ icon: "error", title: data.msg || "OTP verification failed" });
    return;
  }

  window.location.href = data.redirect;
});

sendResetOtpBtn?.addEventListener("click", async () => {
  const phone = (resetPhone.value || "").trim();

  const form = new URLSearchParams();
  form.append("phone", phone);

  const res = await fetch("/auth/send-reset-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: form.toString(),
  });

  const data = await res.json();
  if (!data.ok) {
    Swal.fire({ icon: "error", title: data.msg || "Failed to send reset OTP" });
    return;
  }

  Swal.fire({ icon: "success", title: data.msg || "Reset OTP sent" });
  resetOtpInput.style.display = "";
  verifyResetOtpBtn.style.display = "";
});

verifyResetOtpBtn?.addEventListener("click", async () => {
  const phone = (resetPhone.value || "").trim();
  const otp = (resetOtpInput.value || "").trim();

  const form = new URLSearchParams();
  form.append("phone", phone);
  form.append("otp", otp);

  const res = await fetch("/auth/verify-reset-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: form.toString(),
  });

  const data = await res.json();
  if (!data.ok) {
    Swal.fire({ icon: "error", title: data.msg || "OTP verification failed" });
    return;
  }

  Swal.fire({ icon: "success", title: data.msg || "OTP verified" });
  newPassGroup.style.display = "";
  confirmPassGroup.style.display = "";
  setNewPassBtn.style.display = "";
});

document.querySelectorAll(".password-toggle").forEach((toggleBtn) => {
  toggleBtn.addEventListener("click", () => {
    const targetId = toggleBtn.dataset.target;
    const input = document.getElementById(targetId);
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

setNewPassBtn?.addEventListener("click", async () => {
  const phone = (resetPhone.value || "").trim();
  const p1 = (newPass.value || "").trim();
  const p2 = (confirmPass.value || "").trim();

  const form = new URLSearchParams();
  form.append("phone", phone);
  form.append("new_password", p1);
  form.append("confirm_password", p2);

  const res = await fetch("/auth/set-new-password/", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: form.toString(),
  });

  const data = await res.json();
  if (!data.ok) {
    Swal.fire({ icon: "error", title: data.msg || "Password update failed" });
    return;
  }

  Swal.fire({ icon: "success", title: data.msg || "Password updated" });
  showPasswordLogin();
});

if (attemptTestsTrigger && attemptTestsModalEl) {
  const attemptTestsModal = new bootstrap.Modal(attemptTestsModalEl);

  const updateScholarshipTestSummary = () => {
    if (!scholarshipTestSelect || !scholarshipTestSummary) return;

    const selectedOption =
      scholarshipTestSelect.options[scholarshipTestSelect.selectedIndex];

    if (!selectedOption || !selectedOption.value) {
      scholarshipTestSummary.textContent =
        "Select a test to view its details.";
      return;
    }

    const testType = selectedOption.dataset.testType || "scholarship";
    const loginMode = selectedOption.dataset.loginMode || "otp";
    
    if (testType === "regular") {
      // Regular diagnostic test summary
      scholarshipTestSummary.textContent = 
        "Standard diagnostic test covering multiple subjects based on your grade and board. Login with your username and password to begin.";
    } else {
      // Scholarship test summary
      const duration = selectedOption.dataset.duration || "Custom duration";
      const questions = selectedOption.dataset.questions || "0";
      const entryMode =
        selectedOption.dataset.entryMode === "landing"
          ? "Opens the scholarship landing flow first."
          : "Opens the selected test flow directly.";
      const loginText =
        loginMode === "password"
          ? "Login with your username and password to continue."
          : "Continue with the current OTP-based scholarship login flow.";
      const summaryText = `${questions} questions - ${duration}. ${entryMode} ${loginText}`;

      scholarshipTestSummary.textContent = `${questions} questions • ${duration}. ${entryMode}`;
      scholarshipTestSummary.textContent = summaryText;
    }
  };

  attemptTestsTrigger.addEventListener("click", () => {
    if (scholarshipTestSelect) {
      scholarshipTestSelect.selectedIndex = 0;
    }
    updateScholarshipTestSummary();
    attemptTestsModal.show();
  });

  scholarshipTestSelect?.addEventListener("change", updateScholarshipTestSummary);

  scholarshipTestContinueBtn?.addEventListener("click", () => {
    const launchUrl = scholarshipTestSelect?.value;

    if (!launchUrl) {
      Swal.fire({
        icon: "info",
        title: "Select a Test",
        text: "Please choose a test to continue.",
      });
      return;
    }

    window.location.href = launchUrl;
  });
}
