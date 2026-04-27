// Store form data across steps
let bridgeCourseData = {
  board: "",
  grade: "",
  name: "",
  mobile: "",
};
const bridgeCourseNamePattern = /^[A-Za-z ]+$/;

function nextStep() {
  let board = document.getElementById("board").value;
  let grade = document.getElementById("class").value;

  if (board == "" || grade == "") {
    alert("Please select Board and Class");
    return;
  }

  // Store data for later use
  bridgeCourseData.board = board;
  bridgeCourseData.grade = grade;

  document.getElementById("step1").style.display = "none";
  document.getElementById("step2").style.display = "block";
}

function sendOTP() {
  let name = document.getElementById("name").value.trim();
  let mobile = document.getElementById("mobile").value.trim();

  let mobilePattern = /^[0-9]{10}$/;

  if (!bridgeCourseNamePattern.test(name)) {
    alert("Enter a valid name using letters and spaces only");
    return;
  }

  if (!mobilePattern.test(mobile)) {
    alert("Enter valid 10 digit mobile number");
    return;
  }

  // Store data for later use
  bridgeCourseData.name = name;
  bridgeCourseData.mobile = mobile;

  // Disable button to prevent double clicks
  const btn = document.querySelector("#step2 .btn-main");
  btn.disabled = true;
  btn.textContent = "Sending OTP...";

  // Call server-side OTP endpoint
  fetch("/bridgecourse/api/bridge-course/send-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
    },
    body: JSON.stringify({
      board: bridgeCourseData.board,
      grade: bridgeCourseData.grade,
      name: bridgeCourseData.name,
      mobile: bridgeCourseData.mobile,
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      btn.disabled = false;
      btn.textContent = "Send OTP";

      if (data.success) {
        // Show message - for testing, the OTP will be shown in the message
        alert(data.message);
        document.getElementById("step2").style.display = "none";
        document.getElementById("step3").style.display = "block";
      } else {
        alert(data.error || "Failed to send OTP. Please try again.");
      }
    })
    .catch((error) => {
      console.error("Error:", error);
      btn.disabled = false;
      btn.textContent = "Send OTP";
      alert("An error occurred. Please check your connection and try again.");
    });
}

function verifyOTP() {
  let otp = document.getElementById("otp").value.trim();

  if (otp.length !== 4) {
    alert("Please enter a valid 4-digit OTP");
    return;
  }

  // Disable button to prevent double clicks
  const btn = document.querySelector("#step3 .btn-main");
  btn.disabled = true;
  btn.textContent = "Verifying...";

  // Call server-side OTP verification endpoint
  fetch("/bridgecourse/api/bridge-course/verify-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
    },
    body: JSON.stringify({
      mobile: bridgeCourseData.mobile,
      otp: otp,
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        alert("Login Successful");
        // Redirect to bridge course
        window.location.href = data.redirect_url || "/bridge-course/";
      } else {
        btn.disabled = false;
        btn.textContent = "Verify OTP";
        alert(data.error || "Invalid OTP. Please try again.");
      }
    })
    .catch((error) => {
      console.error("Error:", error);
      btn.disabled = false;
      btn.textContent = "Verify OTP";
      alert("An error occurred. Please check your connection and try again.");
    });
}

// Helper function to get CSRF token
function getCSRFToken() {
  // Try to get CSRF token from cookie
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

document.addEventListener("DOMContentLoaded", function () {
  const nameInput = document.getElementById("name");
  if (nameInput) {
    nameInput.addEventListener("input", function () {
      this.value = this.value.replace(/[^A-Za-z ]/g, "");
    });
  }
});
