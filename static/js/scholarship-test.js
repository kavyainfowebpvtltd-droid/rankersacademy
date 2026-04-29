// Questions from backend
const questions = {{ questions|safe }};
const totalQuestions = {{ total_questions }};
const timeLimit = {{ time_limit }};
let timeRemaining = {{ time_remaining_seconds }};
const attemptId = {{ attempt.id }};

let currentQuestionIndex = 0;
let answers = {};
let timerInterval;
let isSubmitted = false;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
  if (questions && questions.length > 0) {
    loadQuestion(0);
    buildQuestionNavigator();
    startTimer();
  } else {
    // Handle case when no questions are available
    document.querySelector('.question-body').innerHTML = '<div class="alert alert-warning">No questions available. Please contact admin.</div>';
  }
});

function loadQuestion(index) {
  if (index < 0 || index >= questions.length) return;
  
  currentQuestionIndex = index;
  const q = questions[index];
  
  document.getElementById('questionText').textContent = q.question;
  
  const optionsGrid = document.getElementById('optionsGrid');
  optionsGrid.innerHTML = '';
  
  const options = ['A', 'B', 'C', 'D'];
  options.forEach(opt => {
    const optionText = q.options[opt];
    if (optionText) {
      const div = document.createElement('label');
      div.className = 'option-label';
      div.innerHTML = `
        <input type="radio" name="exam" class="option-input" value="${opt}" 
          ${answers[q.id] === opt ? 'checked' : ''} onchange="selectOption('${opt}')">
        <div class="option-card ${answers[q.id] === opt ? 'selected' : ''}">
          <span class="option-bullet">${opt}</span>
          <span class="option-text">${optionText}</span>
        </div>
      `;
      optionsGrid.appendChild(div);
    }
  });
  
  // Update question number
  const questionLabel = document.querySelector('.question-label');
  if (questionLabel) {
    questionLabel.textContent = `Question ${String(index + 1).padStart(2, '0')} of ${totalQuestions}`;
  }
  
  // Update navigator
  updateNavigator();
}

function selectOption(option) {
  const q = questions[currentQuestionIndex];
  answers[q.id] = option;
  loadQuestion(currentQuestionIndex);
}

function buildQuestionNavigator() {
  const grid = document.getElementById('questionGrid');
  if (!grid) return;
  
  grid.innerHTML = '';
  
  for (let i = 0; i < totalQuestions; i++) {
    const btn = document.createElement('div');
    btn.className = 'question-dot';
    btn.id = 'qdot-' + i;
    btn.textContent = i + 1;
    btn.onclick = () => loadQuestion(i);
    grid.appendChild(btn);
  }
}

function updateNavigator() {
  for (let i = 0; i < totalQuestions; i++) {
    const dot = document.getElementById('qdot-' + i);
    if (!dot) continue;
    
    const q = questions[i];
    
    dot.classList.remove('answered', 'current');
    
    if (answers[q.id]) {
      dot.classList.add('answered');
    }
    
    if (i === currentQuestionIndex) {
      dot.classList.add('current');
    }
  }
  
  // Update progress
  const answered = Object.keys(answers).length;
  const answeredCountEl = document.getElementById('answeredCount');
  if (answeredCountEl) {
    answeredCountEl.textContent = answered;
  }
  const progressFill = document.querySelector('.progress-fill');
  if (progressFill) {
    progressFill.style.width = (answered / totalQuestions * 100) + '%';
  }
}

function startTimer() {
  timerInterval = setInterval(() => {
    timeRemaining--;
    
    const minutes = Math.floor(timeRemaining / 60);
    const seconds = timeRemaining % 60;
    const timerDisplay = document.getElementById('timerDisplay');
    if (timerDisplay) {
      timerDisplay.textContent = 
        'Timer: ' + String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
    }
    
    if (timeRemaining <= 0) {
      clearInterval(timerInterval);
      autoSubmit();
    }
  }, 1000);
}

function autoSubmit() {
  if (!isSubmitted) {
    isSubmitted = true;
    const answeredCount = Object.keys(answers).length;
    const finalCountEl = document.getElementById('finalCount');
    if (finalCountEl) {
      finalCountEl.textContent = answeredCount;
    }
    const timeUpModal = document.getElementById('timeUpModal');
    if (timeUpModal) {
      timeUpModal.classList.add('active');
    }
  }
}

// Navigation
const prevBtn = document.querySelector('.btn-prev');
if (prevBtn) {
  prevBtn.onclick = () => loadQuestion(currentQuestionIndex - 1);
}

const nextBtn = document.querySelector('.btn-next');
if (nextBtn) {
  nextBtn.onclick = () => loadQuestion(currentQuestionIndex + 1);
}

// Submit
const submitBtn = document.querySelector('.submit-btn');
if (submitBtn) {
  submitBtn.onclick = () => {
    const answered = Object.keys(answers).length;
    if (answered < totalQuestions) {
      showWarningModal();
    } else {
      submitTest();
    }
  };
}

function showWarningModal() {
  const answered = Object.keys(answers).length;
  const answeredCountEl = document.getElementById('answeredCount');
  const totalCountEl = document.getElementById('totalCount');
  const warningModal = document.getElementById('warningModal');
  
  if (answeredCountEl) {
    answeredCountEl.textContent = answered;
  }
  if (totalCountEl) {
    totalCountEl.textContent = totalQuestions;
  }
  if (warningModal) {
    warningModal.classList.add('active');
  }
}

function closeWarningModal() {
  const warningModal = document.getElementById('warningModal');
  if (warningModal) {
    warningModal.classList.remove('active');
  }
}

window.submitExam = function() {
  closeWarningModal();
  submitTest();
};

async function submitTest() {
  if (isSubmitted) return;
  isSubmitted = true;
  
  if (timerInterval) {
    clearInterval(timerInterval);
  }
  
  try {
    const response = await fetch('/scholarship/test/' + attemptId + '/submit/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      },
      body: JSON.stringify({ answers: answers })
    });
    
    const data = await response.json();
    
    if (data.success) {
      window.location.href = data.redirect;
    } else {
      alert('Error: ' + data.error);
      isSubmitted = false;
    }
  } catch (err) {
    console.error(err);
    alert('Error submitting test');
    isSubmitted = false;
  }
}

function goToSuccess() {
  window.location.href = '/scholarship/success/' + attemptId + '/';
}

function getCSRFToken() {
  const name = 'csrftoken';
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
