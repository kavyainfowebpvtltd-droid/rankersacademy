// Store form data for login
let bridgeCourseLoginData = {
  mobile: "",
};

// Store registered user data from the database
let registeredUserData = null;

function sendOTP() {
  let mobile = document.getElementById("mobile").value.trim();
  let mobilePattern = /^[0-9]{10}$/;

  if (!mobilePattern.test(mobile)) {
    alert("Please enter a valid 10-digit mobile number");
    return;
  }

  // Store mobile number
  bridgeCourseLoginData.mobile = mobile;

  // Disable button to prevent double clicks
  const btn = document.querySelector("#step1 .btn-main");
  btn.disabled = true;
  btn.textContent = "Sending OTP...";

  // First check if user exists, then send OTP
  fetch("/bridgecourse/api/bridge-course/check-user/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
    },
    body: JSON.stringify({
      mobile: bridgeCourseLoginData.mobile,
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        // User exists, now send OTP
        fetch("/bridgecourse/api/bridge-course/login-send-otp/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken(),
          },
          body: JSON.stringify({
            mobile: bridgeCourseLoginData.mobile,
          }),
        })
          .then((response) => response.json())
          .then((otpData) => {
            btn.disabled = false;
            btn.textContent = "Send OTP";

            if (otpData.success) {
              // Store user data for after OTP verification
              registeredUserData = data.user_data;
              alert(otpData.message);
              document.getElementById("step1").style.display = "none";
              document.getElementById("step2").style.display = "block";
            } else {
              alert(otpData.error || "Failed to send OTP. Please try again.");
            }
          })
          .catch((error) => {
            console.error("Error:", error);
            btn.disabled = false;
            btn.textContent = "Send OTP";
            alert(
              "An error occurred. Please check your connection and try again.",
            );
          });
      } else {
        btn.disabled = false;
        btn.textContent = "Send OTP";
        alert(data.error || "User not found. Please register first.");
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
  const btn = document.querySelector("#step2 .btn-main");
  btn.disabled = true;
  btn.textContent = "Verifying...";

  // Call server-side OTP verification endpoint
  fetch("/bridgecourse/api/bridge-course/login-verify-otp/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCSRFToken(),
    },
    body: JSON.stringify({
      mobile: bridgeCourseLoginData.mobile,
      otp: otp,
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        alert("Login Successful");
        // Redirect to bridge course
        window.location.href =
          data.redirect_url || "/bridgecourse/bridge-course/";
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

function goBack() {
  document.getElementById("step2").style.display = "none";
  document.getElementById("step1").style.display = "block";
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
