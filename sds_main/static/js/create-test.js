var defaultS = {
  testName: "Mathematics",
  duration: "1",
  tags: "SCHOLARSHIP TEST",
  instructions: "",
  defaultPosMarks: 2,
  defaultNegMarks: 1,
  sections: [
    {
      id: 1,
      name: "mTHS",
      collapsed: false,
      allowSwitching: true,
      sectionInstructions: "",
      questions: [
        {
          id: 1,
          type: "mcq",
          text: "What is Java?",
          difficulty: "Medium",
          posMarks: 4,
          negMarks: 1,
          negUnattempted: 2,
          tags: ["SCHOLARSHIP TEST"],
          options: [
            "PROGRAMMING LANGUAGE",
            "Scripting language",
            "Its designing language",
            "Its using backend",
          ],
          correctOptions: [0, 3],
          multiSelect: true,
        },
        {
          id: 2,
          type: "tf",
          text: "Java is an object-oriented language.",
          difficulty: "Easy",
          posMarks: 2,
          negMarks: 0,
          negUnattempted: 0,
          tags: ["SCHOLARSHIP TEST"],
          correctAnswer: "True",
        },
        {
          id: 3,
          type: "fitb",
          text: "The main method signature in Java is public static .......... main.",
          difficulty: "Medium",
          posMarks: 2,
          negMarks: 1,
          negUnattempted: 0,
          tags: ["SCHOLARSHIP TEST"],
          correctAnswer: "void",
        },
      ],
    },
    {
      id: 2,
      name: "zxyz",
      collapsed: false,
      allowSwitching: false,
      sectionInstructions: "",
      questions: [
        {
          id: 4,
          type: "fitb",
          text: "javascript is ..........language",
          difficulty: "Medium",
          posMarks: 2,
          negMarks: 1,
          negUnattempted: 1,
          tags: ["SCHOLARSHIP TEST"],
          correctAnswer: "scripting",
        },
      ],
    },
  ],
  nextSecId: 3,
  nextQId: 5,
};
var S = {};
var currentTestId = null;

function getTestIdFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get("test_id");
}

function hasTestId() {
  return !!getTestIdFromUrl();
}

function formatDurationValue(hours, minutes) {
  var totalHours = Number(hours || 0) + Number(minutes || 0) / 60;
  if (!isFinite(totalHours) || totalHours < 0) {
    totalHours = 0;
  }
  return String(totalHours).replace(/\.0+$/, "");
}

function normalizeDurationValue(durationValue, fallbackHours, fallbackMinutes) {
  if (fallbackHours != null || fallbackMinutes != null) {
    return formatDurationValue(fallbackHours, fallbackMinutes);
  }

  if (durationValue == null || durationValue === "") {
    return "0";
  }

  if (typeof durationValue === "object") {
    return formatDurationValue(
      durationValue.hours || durationValue.duration_hours || 0,
      durationValue.minutes || durationValue.duration_minutes || 0,
    );
  }

  var rawValue = String(durationValue).trim();
  if (!rawValue) {
    return "0";
  }

  var colonMatch = rawValue.match(/^(\d+)\s*:\s*(\d+)$/);
  if (colonMatch) {
    return formatDurationValue(colonMatch[1], colonMatch[2]);
  }

  return formatDurationValue(rawValue, 0);
}

function getDurationParts(durationValue) {
  var totalHours = Number(normalizeDurationValue(durationValue));
  if (!isFinite(totalHours) || totalHours < 0) {
    totalHours = 0;
  }

  var hours = Math.floor(totalHours);
  var minutes = Math.round((totalHours - hours) * 60);
  if (minutes >= 60) {
    hours += Math.floor(minutes / 60);
    minutes = minutes % 60;
  }

  return {
    hours: hours,
    minutes: minutes,
    value: formatDurationValue(hours, minutes),
  };
}

function formatDurationLabel(durationValue) {
  var duration = getDurationParts(durationValue);
  var parts = [];

  if (duration.hours > 0) {
    parts.push(duration.hours + (duration.hours === 1 ? " hr" : " hrs"));
  }

  if (duration.minutes > 0) {
    parts.push(duration.minutes + " min");
  }

  if (parts.length === 0) {
    return "0 min";
  }

  return parts.join(" ");
}

function syncGradingFromInputs() {
  var posInput = document.getElementById("default-pos-marks");
  var negInput = document.getElementById("default-neg-marks");

  if (posInput) {
    S.defaultPosMarks = Number(posInput.value);
    if (isNaN(S.defaultPosMarks)) {
      S.defaultPosMarks = defaultS.defaultPosMarks;
    }
  }

  if (negInput) {
    S.defaultNegMarks = Number(negInput.value);
    if (isNaN(S.defaultNegMarks)) {
      S.defaultNegMarks = defaultS.defaultNegMarks;
    }
  }
}

function getTestDetailsPayload() {
  syncGradingFromInputs();
  var duration = getDurationParts(S.duration);

  return {
    testName: S.testName,
    duration: duration.value,
    duration_hours: duration.hours,
    duration_minutes: duration.minutes,
    tags: S.tags,
    instructions: S.instructions,
    default_pos_marks: S.defaultPosMarks,
    default_neg_marks: S.defaultNegMarks,
  };
}

function applyDefaultMarksToQuestions() {
  S.sections.forEach(function (sec) {
    sec.questions.forEach(function (q) {
      q.pos_marks = S.defaultPosMarks;
      q.posMarks = S.defaultPosMarks;
      q.neg_marks = S.defaultNegMarks;
      q.negMarks = S.defaultNegMarks;
      normalizeQuestion(q);
    });
  });
}

function loadData() {
  currentTestId = getTestIdFromUrl();

  if (currentTestId) {
    // Load existing test data
    fetch(`/scholarship/api/tests/${currentTestId}/`)
      .then((response) => response.json())
      .then((data) => {
        if (data.test) {
          S = {
            testName: data.test.name,
            duration: normalizeDurationValue(
              data.test.duration,
              data.test.duration_hours,
              data.test.duration_minutes,
            ),
            tags: data.test.tags,
            instructions: data.test.instructions,
            defaultPosMarks: data.test.default_pos_marks,
            defaultNegMarks: data.test.default_neg_marks,
            sections: (data.test.sections || []).map(function (sec) {
              return normalizeSection(sec);
            }),
            nextSecId:
              Math.max.apply(
                null,
                [0].concat(
                  (data.test.sections || []).map(function (s) {
                    return s.id;
                  }),
                ),
              ) + 1,
            nextQId:
              Math.max.apply(
                null,
                [0].concat(
                  (data.test.sections || []).reduce(function (ids, section) {
                    return ids.concat(
                      (section.questions || []).map(function (q) {
                        return q.id;
                      }),
                    );
                  }, []),
                ),
              ) + 1,
          };
          S.editSec = null;
          S.editQ = null;
          S.addToSec = null;
          S.qType = null;
          render();
          updateTopbarTitle();
        } else {
          // Test not found, load default
          S = JSON.parse(JSON.stringify(defaultS));
          S.sections = S.sections.map(function (sec) {
            return normalizeSection(sec);
          });
          S.editSec = null;
          S.editQ = null;
          S.addToSec = null;
          S.qType = null;
          render();
          updateTopbarTitle();
        }
      })
      .catch((err) => {
        console.error("Error loading test data:", err);
        S = JSON.parse(JSON.stringify(defaultS));
        S.sections = S.sections.map(function (sec) {
          return normalizeSection(sec);
        });
        S.editSec = null;
        S.editQ = null;
        S.addToSec = null;
        S.qType = null;
        render();
        updateTopbarTitle();
      });
  } else {
    // New test, load default
    S = JSON.parse(JSON.stringify(defaultS));
    S.sections = S.sections.map(function (sec) {
      return normalizeSection(sec);
    });
    S.editSec = null;
    S.editQ = null;
    S.addToSec = null;
    S.qType = null;
    render();
    updateTopbarTitle();
  }
}

function saveData(extraData) {
  if (!currentTestId) return Promise.resolve();
  var payload = getTestDetailsPayload();
  if (extraData && typeof extraData === "object") {
    Object.keys(extraData).forEach(function (key) {
      payload[key] = extraData[key];
    });
  }

  return fetch(`/scholarship/api/tests/${currentTestId}/save-details/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }).then(function (response) {
    if (!response.ok) {
      return response.json().then(function (data) {
        throw new Error(data.error || "Failed to save test details");
      });
    }
    return response.json();
  });
}

var TL = {
  mcq: "Multiple Choice",
  tf: "True/False",
  comp: "Comprehension",
  fitb: "Fill In The Blanks",
  int: "Integer Type",
};
var pendingRte = null;

function getQPosMarks(q) {
  var val = q && q.pos_marks != null ? q.pos_marks : q && q.posMarks;
  val = Number(val);
  return isNaN(val) ? 0 : val;
}

function getQuestionOptions(q) {
  if (!q || q.options == null) return [];
  var options = Array.isArray(q.options)
    ? q.options
    : typeof q.options === "object"
      ? Object.keys(q.options)
          .sort()
          .map(function (key) {
            return q.options[key];
          })
      : [];
  return options.map(function (opt) {
    if (opt && typeof opt === "object") {
      return opt.text != null
        ? opt.text
        : opt.option_text != null
          ? opt.option_text
          : "";
    }
    return opt == null ? "" : String(opt);
  });
}

function getCorrectOptionIndexes(q) {
  if (!q) return [];
  if (Array.isArray(q.correct_options)) {
    return q.correct_options
      .map(function (idx) {
        return Number(idx);
      })
      .filter(function (idx) {
        return !isNaN(idx);
      });
  }
  if (Array.isArray(q.correctOptions)) {
    return q.correctOptions
      .map(function (idx) {
        return Number(idx);
      })
      .filter(function (idx) {
        return !isNaN(idx);
      });
  }
  var options = Array.isArray(q.options)
    ? q.options
    : q && q.options && typeof q.options === "object"
      ? Object.keys(q.options)
          .sort()
          .map(function (key) {
            return q.options[key];
          })
      : [];
  if (options.length > 0) {
    var derived = [];
    options.forEach(function (opt, idx) {
      if (opt && typeof opt === "object" && opt.is_correct) {
        derived.push(idx);
      }
    });
    if (derived.length > 0) return derived;
  }
  return [];
}

function normalizeQuestion(q) {
  if (!q) return q;
  q.pos_marks = getQPosMarks(q);
  q.neg_marks = Number(
    q && q.neg_marks != null ? q.neg_marks : q && q.negMarks,
  );
  q.neg_marks = isNaN(q.neg_marks) ? 0 : q.neg_marks;
  q.neg_unattempted = Number(
    q && q.neg_unattempted != null ? q.neg_unattempted : q && q.negUnattempted,
  );
  q.neg_unattempted = isNaN(q.neg_unattempted) ? 0 : q.neg_unattempted;
  q.multi_select = !!(q.multi_select || q.multiSelect);
  q.options = getQuestionOptions(q);
  q.correct_options = getCorrectOptionIndexes(q);
  if (!Array.isArray(q.tags)) {
    q.tags = q.tags
      ? String(q.tags)
          .split(",")
          .map(function (t) {
            return t.trim();
          })
          .filter(Boolean)
      : [];
  }
  q.passage = q.passage || "";
  q.sub_questions = Array.isArray(q.sub_questions) ? q.sub_questions : [];
  q._persisted = q._persisted !== false;
  return q;
}

function normalizeSection(sec) {
  if (!sec) return sec;
  sec.allow_switching = !!(sec.allow_switching || sec.allowSwitching);
  sec.instructions = sec.instructions || sec.sectionInstructions || "";
  sec.questions = Array.isArray(sec.questions)
    ? sec.questions.map(function (q) {
        return normalizeQuestion(q);
      })
    : [];
  sec._persisted = sec._persisted !== false;
  return sec;
}

function buildQuestionPayload(q, sectionId) {
  var data = {
    section_id: sectionId,
    type: q.type,
    text: q.text || "",
    difficulty: q.difficulty || "Medium",
    pos_marks: getQPosMarks(q),
    neg_marks: Number(q.neg_marks != null ? q.neg_marks : q.negMarks) || 0,
    neg_unattempted:
      Number(
        q.neg_unattempted != null ? q.neg_unattempted : q.negUnattempted,
      ) || 0,
    tags: Array.isArray(q.tags)
      ? q.tags
      : q.tags
        ? String(q.tags)
            .split(",")
            .map(function (t) {
              return t.trim();
            })
            .filter(Boolean)
        : [],
  };

  if (q && q._persisted) {
    data.id = q.id;
  }

  if (q.type === "mcq") {
    data.options = getQuestionOptions(q);
    data.correct_options = getCorrectOptionIndexes(q);
    data.multi_select = !!(q.multi_select || q.multiSelect);
  } else if (q.type === "tf" || q.type === "fitb" || q.type === "int") {
    data.correct_answer = q.correct_answer || q.correctAnswer || "";
  } else if (q.type === "comp") {
    data.passage = q.passage || "";
    data.sub_questions = Array.isArray(q.sub_questions) ? q.sub_questions : [];
  }

  return data;
}

function syncQuestionIntoSection(sectionId, q) {
  var sec = S.sections.find(function (s) {
    return s.id === sectionId;
  });
  if (!sec) return;
  sec.questions = sec.questions.filter(function (x) {
    return x.id !== q.id;
  });
  sec.questions.push(normalizeQuestion(q));
}

window.toggleSb = function (id) {
  var b = document.getElementById(id + "-body"),
    a = document.getElementById(id + "-arrow");
  if (!b) return;
  var o = b.classList.contains("open");
  b.classList.toggle("open", !o);
  if (a) a.classList.toggle("open", !o);
};

function render() {
  S.sections = (S.sections || []).map(function (sec) {
    return normalizeSection(sec);
  });
  var defaultPosInput = document.getElementById("default-pos-marks");
  var defaultNegInput = document.getElementById("default-neg-marks");
  if (defaultPosInput) defaultPosInput.value = S.defaultPosMarks;
  if (defaultNegInput) defaultNegInput.value = S.defaultNegMarks;
  document.getElementById("meta-duration").textContent = formatDurationLabel(
    S.duration,
  );
  document.getElementById("meta-tags").textContent = S.tags;
  document.getElementById("instructions-text").textContent = S.instructions
    ? "Instructions: " + S.instructions
    : "Test Instructions: Click here to add";
  var c = document.getElementById("sections-container");
  if (S.sections.length === 0) {
    c.innerHTML =
      '<div class="empty-state"><div class="empty-state-icon">📋</div><div class="empty-state-title">No sections yet</div><div>Click "Add New Section" to get started</div></div>';
    return;
  }
  c.innerHTML = S.sections.map(renderSec).join("");
  syncSectionBodyHeights();
}

function syncSectionBodyHeights() {
  var wrappers = document.querySelectorAll(".section-body-wrapper");
  wrappers.forEach(function (wrapper) {
    var sectionId = Number(wrapper.getAttribute("data-section-id"));
    var section = S.sections.find(function (sec) {
      return sec.id === sectionId;
    });

    if (!section || section.collapsed) {
      wrapper.style.maxHeight = "0px";
      return;
    }

    wrapper.style.maxHeight = wrapper.scrollHeight + "px";
  });
}

window.applyGradingToAll = function () {
  syncGradingFromInputs();

  if (isNaN(S.defaultPosMarks) || isNaN(S.defaultNegMarks)) {
    showToast("Please enter valid grading values");
    return;
  }

  applyDefaultMarksToQuestions();
  render();

  if (!currentTestId) {
    showToast("Grading applied to all questions");
    return;
  }

  saveData()
    .then(function () {
      return saveAllSectionsFixed();
    })
    .then(function () {
      return persistAllQuestionsFixed();
    })
    .then(function () {
      showToast("Grading applied to all questions");
    })
    .catch(function (err) {
      console.error("Error applying grading:", err);
      showToast("❌ " + err.message);
    });
};

function renderSec(sec) {
  var tm = sec.questions.reduce(function (s, q) {
    return s + getQPosMarks(q);
  }, 0);
  var qh =
    sec.questions.length === 0
      ? '<div class="empty-state" style="padding:24px"><div class="empty-state-icon" style="font-size:28px">❓</div><div>No questions yet.</div></div>'
      : sec.questions
          .map(function (q, i) {
            return renderQ(q, i + 1, sec.id);
          })
          .join("");
  return (
    '<div class="section-card" id="sec-' +
    sec.id +
    '">' +
    '<div class="section-header">' +
    '<div class="section-header-left">' +
    '<button class="section-star" onclick="showToast(\'Added to favourites\')">☆</button>' +
    '<span class="section-name">' +
    e(sec.name) +
    "</span>" +
    '<span class="section-qcount">— ' +
    sec.questions.length +
    " Question" +
    (sec.questions.length !== 1 ? "s" : "") +
    "</span>" +
    "</div>" +
    '<div class="section-actions">' +
    '<button class="sec-action-btn danger" onclick="confirmDelSec(' +
    sec.id +
    ')">' +
    ico("trash") +
    " Delete</button>" +
    '<button class="sec-action-btn" onclick="reordSec(' +
    sec.id +
    ')">' +
    ico("reorder") +
    " Reorder</button>" +
    '<button class="sec-action-btn" onclick="openEditSec(' +
    sec.id +
    ')">' +
    ico("edit") +
    " Edit Details</button>" +
    '<button class="collapse-btn ' +
    (sec.collapsed ? "collapsed" : "") +
    '" onclick="togSec(' +
    sec.id +
    ')">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"/></svg>' +
    "</button>" +
    "</div>" +
    "</div>" +
    '<div class="section-meta"><span>Max. Section Marks: <strong>' +
    tm.toFixed(2) +
    "</strong></span>" +
    (sec.allow_switching || sec.allowSwitching
      ? '<span style="color:var(--blue);font-size:11px">Section Switching: ON</span>'
      : "") +
    "</div>" +
    '<div class="section-body-wrapper" data-section-id="' +
    sec.id +
    '" style="max-height:' +
    (sec.collapsed ? "0px" : "none") +
    '">' +
    "<div>" +
    qh +
    "</div>" +
    '<div class="section-add-q" onclick="openAddQ(\'mcq\',' +
    sec.id +
    ')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Add Question to this section</div>' +
    "</div>" +
    "</div>"
  );
}

function renderQ(q, idx, secId) {
  var opts = getQuestionOptions(q);
  var correctIndexes = getCorrectOptionIndexes(q);
  var dc =
    q.difficulty === "Easy"
      ? "badge-diff-easy"
      : q.difficulty === "Hard"
        ? "badge-diff-hard"
        : "badge-diff-med";
  var ah = "";
  if (q.type === "mcq") {
    ah =
      '<div class="mcq-options">' +
      opts
        .map(function (o, i) {
          var ok = correctIndexes.indexOf(i) !== -1;
          return (
            '<div class="mcq-opt">' +
            (q.multi_select || q.multiSelect
              ? '<div class="mcq-opt-check' +
                (ok ? " correct" : "") +
                '"></div>'
              : '<div class="mcq-opt-radio' +
                (ok ? " correct" : "") +
                '"></div>') +
            "<span" +
            (ok ? ' style="color:var(--green);font-weight:500"' : "") +
            ">" +
            renderQuestionHtml(o) +
            "</span></div>"
          );
        })
        .join("") +
      "</div>";
  } else if (q.type === "tf") {
    ah =
      '<div class="q-answer-box">Answer: ' +
      e(q.correct_answer || q.correctAnswer) +
      "</div>";
  } else if (q.type === "fitb" || q.type === "int") {
    ah =
      '<div class="q-answer-box">Answer: ' +
      e(String(q.correct_answer || q.correctAnswer)) +
      "</div>";
  } else if (q.type === "comp") {
    var passagePreview = q.passage
      ? '<div class="q-answer-box" style="white-space:normal"><strong>Passage:</strong> ' +
        e(String(q.passage).replace(/<br\s*\/?>/gi, " ")) +
        "</div>"
      : "";
    var subQuestionsPreview =
      q.sub_questions && q.sub_questions.length > 0
        ? '<div class="mcq-options">' +
          q.sub_questions
            .map(function (sq) {
              return (
                '<div class="mcq-opt" style="align-items:flex-start"><span>' +
                e(String(sq)) +
                "</span></div>"
              );
            })
            .join("") +
          "</div>"
        : "";
    ah =
      '<div style="margin-left:30px;margin-bottom:8px;font-size:12px;color:var(--gray-500);font-style:italic">Passage-based question</div>' +
      passagePreview +
      subQuestionsPreview;
  }
  var dt =
    q.type === "fitb"
      ? e(q.text).replace(/\.{5,}|_+/g, '<span class="fill-blank"></span>')
      : q.text;
  return (
    '<div class="question-item" id="q-' +
    q.id +
    '">' +
    '<div class="q-row"><span class="q-num">' +
    idx +
    '.</span><span class="q-text">' +
    dt +
    "</span></div>" +
    ah +
    '<div class="q-badges">' +
    '<span class="badge ' +
    dc +
    '">' +
    q.difficulty +
    "</span>" +
    '<span class="badge badge-pos">+' +
    q.pos_marks +
    "</span>" +
    (q.neg_marks > 0
      ? '<span class="badge badge-neg">-' + q.neg_marks + "</span>"
      : "") +
    (q.neg_unattempted > 0
      ? '<span class="badge badge-neg">-' +
        q.neg_unattempted +
        " if unatt.</span>"
      : "") +
    '<span class="badge badge-type">' +
    TL[q.type] +
    "</span>" +
    ((q.tags || []).length > 0
      ? (Array.isArray(q.tags) ? q.tags : String(q.tags).split(","))
          .map(function (t) {
            return (
              '<span class="badge badge-tag">🏷 ' + e(t.trim()) + "</span>"
            );
          })
          .join("")
      : "") +
    "</div>" +
    '<div class="q-actions">' +
    '<button class="q-act-btn" onclick="openEditQ(' +
    q.id +
    "," +
    secId +
    ')">' +
    ico("edit") +
    " Edit</button>" +
    '<button class="q-act-btn" onclick="copyQ(' +
    q.id +
    "," +
    secId +
    ')">' +
    ico("copy") +
    " Copy</button>" +
    '<button class="q-act-btn" onclick="openEditMarks(' +
    q.id +
    "," +
    secId +
    ')">' +
    ico("marks") +
    " Edit Marks</button>" +
    '<button class="q-act-btn danger" onclick="confirmDelQ(' +
    q.id +
    "," +
    secId +
    ')">' +
    ico("trash") +
    " Delete</button>" +
    "</div>" +
    "</div>"
  );
}

function ico(n) {
  var m = {
    edit: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    trash:
      '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>',
    copy: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    reorder:
      '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/></svg>',
    marks:
      '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>',
  };
  return m[n] || "";
}
function e(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function renderQuestionHtml(v) {
  var raw = v == null ? "" : String(v);
  return /<[^>]+>/.test(raw) ? raw : e(raw);
}
window.togSec = function (id) {
  var s = S.sections.find(function (x) {
    return x.id === id;
  });
  if (s) {
    s.collapsed = !s.collapsed;
    render();
  }
};

window.openWordUpload = function () {
  var input = document.createElement("input");
  input.type = "file";
  input.accept = ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  input.onchange = function () {
    var file = input.files && input.files[0];
    if (file) {
      uploadWordQuestionFile(file);
    }
  };
  input.click();
};

function createImportedSectionName(baseName) {
  var cleanedBase = (baseName || "Imported Questions").trim();
  if (!cleanedBase) cleanedBase = "Imported Questions";

  var existingNames = (S.sections || []).map(function (section) {
    return String(section.name || "").toLowerCase();
  });

  if (existingNames.indexOf(cleanedBase.toLowerCase()) === -1) {
    return cleanedBase;
  }

  var counter = 2;
  while (
    existingNames.indexOf((cleanedBase + " " + counter).toLowerCase()) !== -1
  ) {
    counter += 1;
  }
  return cleanedBase + " " + counter;
}

function prepareImportedQuestion(question) {
  question = question || {};
  question.id = S.nextQId++;
  question._persisted = false;

  if (question.pos_marks == null && question.posMarks == null) {
    question.pos_marks = S.defaultPosMarks;
    question.posMarks = S.defaultPosMarks;
  }

  if (question.neg_marks == null && question.negMarks == null) {
    question.neg_marks = S.defaultNegMarks;
    question.negMarks = S.defaultNegMarks;
  }

  if (question.neg_unattempted == null && question.negUnattempted == null) {
    question.neg_unattempted = 0;
    question.negUnattempted = 0;
  }

  return normalizeQuestion(question);
}

function applyImportedTestMetadata(imported) {
  if (!imported || typeof imported !== "object") return;

  if (imported.test_name) {
    S.testName = String(imported.test_name).trim() || S.testName;
  }

  if (
    imported.duration_hours != null ||
    imported.duration_minutes != null
  ) {
    S.duration = normalizeDurationValue(
      null,
      imported.duration_hours || 0,
      imported.duration_minutes || 0,
    );
  }

  updateTopbarTitle();
}

function createImportedSections(imported) {
  var importedSections = Array.isArray(imported.sections) ? imported.sections : [];

  if (importedSections.length > 0) {
    return importedSections.map(function (sectionData) {
      return normalizeSection({
        id: S.nextSecId++,
        name: createImportedSectionName(sectionData.name || imported.section_name),
        collapsed: false,
        allowSwitching:
          sectionData.allow_switching != null
            ? sectionData.allow_switching
            : sectionData.allowSwitching != null
              ? sectionData.allowSwitching
              : true,
        sectionInstructions:
          sectionData.instructions || sectionData.sectionInstructions || "",
        _persisted: false,
        questions: (Array.isArray(sectionData.questions)
          ? sectionData.questions
          : []
        ).map(function (question) {
          return prepareImportedQuestion(question);
        }),
      });
    });
  }

  var questions = Array.isArray(imported.questions) ? imported.questions : [];
  if (questions.length === 0) {
    return [];
  }

  return [
    normalizeSection({
      id: S.nextSecId++,
      name: createImportedSectionName(imported.section_name),
      collapsed: false,
      allowSwitching: true,
      sectionInstructions: "",
      _persisted: false,
      questions: questions.map(function (question) {
        return prepareImportedQuestion(question);
      }),
    }),
  ];
}

function attachImportedQuestions(imported) {
  applyImportedTestMetadata(imported);

  var sections = createImportedSections(imported);
  if (sections.length === 0) {
    showToast("No questions found in the Word file");
    return;
  }

  var questionCount = sections.reduce(function (total, section) {
    return total + (Array.isArray(section.questions) ? section.questions.length : 0);
  }, 0);

  sections.forEach(function (section) {
    S.sections.push(section);
  });
  render();

  var warnings = Array.isArray(imported.warnings) ? imported.warnings : [];
  if (warnings.length > 0) {
    showToast(
      "Imported " +
        questionCount +
        " question(s) into " +
        sections.length +
        " section(s). Review the imported test and click Save Test.",
    );
    console.warn("Word import warnings:", warnings);
    return;
  }

  showToast(
    "Imported " +
      questionCount +
      " question(s) into " +
      sections.length +
      " section(s). Click Save Test to persist them.",
  );
}

window.uploadWordQuestionFile = function (file) {
  if (!file.name || !/\.docx$/i.test(file.name)) {
    showToast("Please choose a .docx Word file");
    return;
  }

  var formData = new FormData();
  formData.append("word_file", file);

  fetch("/scholarship/api/tests/import-word/", {
    method: "POST",
    body: formData,
  })
    .then(function (response) {
      if (!response.ok) {
        return response.json().then(function (data) {
          throw new Error(data.error || "Failed to import Word file");
        });
      }
      return response.json();
    })
    .then(function (result) {
      if (!result.success || !result.imported) {
        throw new Error(result.error || "Failed to import Word file");
      }
      attachImportedQuestions(result.imported);
    })
    .catch(function (error) {
      console.error("Word import failed:", error);
      showToast("❌ " + error.message);
    });
};

window.openAddSection = function () {
  S.editSec = null;
  showModal(secModalHtml("Add New Section", "", true, ""));
};

window.openEditSec = function (id) {
  var s = S.sections.find(function (x) {
    return x.id === id;
  });
  if (!s) return;
  S.editSec = id;
  showModal(
    secModalHtml(
      "Edit Section",
      s.name,
      s.allow_switching || s.allowSwitching,
      s.instructions || s.sectionInstructions,
    ),
  );
};

function secModalHtml(title, name, sw, instr) {
  return (
    '<div class="modal-header"><span class="modal-title">' +
    e(title) +
    '</span><button class="modal-close" onclick="closeModal()">×</button></div>' +
    '<div class="modal-body">' +
    '<div class="form-group"><div class="form-label">Section Name</div><input class="form-input" id="sec-name" value="' +
    e(name) +
    '" placeholder="e.g. Mathematics A"></div>' +
    '<div class="toggle-row"><div class="toggle-info"><div class="toggle-info-title">Allow Section Switching</div><div class="toggle-info-sub">Students can switch between sections during the test.</div></div><label class="toggle-switch"><input type="checkbox" id="sec-sw" ' +
    (sw ? "checked" : "") +
    ' ><span class="toggle-slider"></span></label></div>' +
    '<div class="form-group" style="margin-top:14px"><div class="form-label">Section Instructions</div><textarea class="form-input" id="sec-instr" placeholder="Optional...">' +
    e(instr) +
    "</textarea></div>" +
    "</div>" +
    '<div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="saveSec()">Save</button></div>'
  );
}

window.saveSec = function () {
  var name = document.getElementById("sec-name").value.trim();
  if (!name) {
    alert("Enter section name");
    return;
  }
  var sw = document.getElementById("sec-sw").checked;
  var instr = document.getElementById("sec-instr").value.trim();

  if (currentTestId) {
    const data = {
      id: S.editSec,
      name: name,
      allowSwitching: sw,
      instructions: instr,
    };

    fetch(`/scholarship/api/tests/${currentTestId}/save-section/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "Request failed");
          });
        }
        return response.json();
      })
      .then(function (result) {
        if (result.success) {
          if (S.editSec) {
            var s = S.sections.find(function (x) {
              return x.id === S.editSec;
            });
            if (s) {
              s.name = name;
              s.allow_switching = sw;
              s.instructions = instr;
            }
            showToast('✓ Section "' + name + '" updated');
          } else {
            S.sections.push({
              id: result.section.id,
              name: name,
              collapsed: false,
              allow_switching: sw,
              instructions: instr,
              _persisted: true,
              questions: [],
            });
            S.nextSecId = Math.max(S.nextSecId, result.section.id + 1);
            showToast('✓ Section "' + name + '" added');
          }
          closeModal();
          render();
        } else {
          showToast("❌ " + (result.error || "Unknown error"));
        }
      })
      .catch(function (err) {
        console.error("Error saving section:", err);
        showToast("❌ " + err.message);
      });
  } else {
    // Fallback for new tests without ID
    if (S.editSec) {
      var s = S.sections.find(function (x) {
        return x.id === S.editSec;
      });
      if (s) {
        s.name = name;
        s.allowSwitching = sw;
        s.sectionInstructions = instr;
      }
      showToast("✓ Section updated");
    } else {
      S.sections.push({
        id: S.nextSecId++,
        name: name,
        collapsed: false,
        allowSwitching: sw,
        sectionInstructions: instr,
        _persisted: false,
        questions: [],
      });
      showToast('✓ Section "' + name + '" added');
    }
    saveData();
    closeModal();
    render();
  }
};

window.confirmDelSec = function (id) {
  var s = S.sections.find(function (x) {
    return x.id === id;
  });
  if (!s) return;
  showModal(
    '<div class="modal-header"><span class="modal-title">Delete Section</span><button class="modal-close" onclick="closeModal()">×</button></div>' +
      '<div class="modal-body"><div class="confirm-icon">🗑️</div><div class="confirm-msg">Delete <strong>"' +
      e(s.name) +
      '"</strong> and all <strong>' +
      s.questions.length +
      " questions</strong>? Cannot be undone.</div></div>" +
      '<div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-danger" onclick="delSec(' +
      id +
      ')">Delete</button></div>',
  );
};

window.delSec = function (id) {
  if (currentTestId) {
    fetch(`/scholarship/api/tests/${currentTestId}/sections/${id}/delete/`, {
      method: "DELETE",
    })
      .then((response) => response.json())
      .then((result) => {
        if (result.success) {
          S.sections = S.sections.filter(function (s) {
            return s.id !== id;
          });
          closeModal();
          render();
          showToast("Section deleted");
        } else {
          alert("Error deleting section: " + (result.error || "Unknown error"));
        }
      })
      .catch((err) => {
        console.error("Error deleting section:", err);
        alert("Error deleting section");
      });
  } else {
    S.sections = S.sections.filter(function (s) {
      return s.id !== id;
    });
    saveData();
    closeModal();
    render();
    showToast("Section deleted");
  }
};

window.reordSec = function (id) {
  var i = S.sections.findIndex(function (s) {
    return s.id === id;
  });
  if (i > 0) {
    var t = S.sections[i];
    S.sections[i] = S.sections[i - 1];
    S.sections[i - 1] = t;
    saveData();
    render();
    showToast("Section moved up");
  } else showToast("Already at top");
};

window.openAddQ = function (type, secId) {
  S.editQ = null;
  S.addToSec = secId || (S.sections.length > 0 ? S.sections[0].id : null);
  S.qType = type;
  syncGradingFromInputs();
  if (!S.addToSec && S.sections.length === 0) {
    showToast("Please add a section first!");
    return;
  }
  var q = {
    type: type,
    text: "",
    difficulty: "Medium",
    pos_marks: S.defaultPosMarks,
    neg_marks: S.defaultNegMarks,
    neg_unattempted: 0,
    tags: [S.tags],
    options: type === "mcq" ? ["", "", "", ""] : [],
    correct_options: [],
    correct_answer: "",
    multi_select: false,
    passage: "",
    sub_questions: [""],
  };
  showModal(qModalHtml(q, false), true);
};

window.openEditQ = function (qId, secId) {
  var sec = S.sections.find(function (s) {
    return s.id === secId;
  });
  if (!sec) return;
  var q = sec.questions.find(function (x) {
    return x.id === qId;
  });
  if (!q) return;
  S.editQ = qId;
  S.addToSec = secId;
  S.qType = q.type;
  showModal(qModalHtml(q, true), true);
};

function qModalHtml(q, isEdit) {
  var type = q.type || S.qType;
  var secOpts = S.sections
    .map(function (s) {
      return (
        '<option value="' +
        s.id +
        '"' +
        (s.id === S.addToSec ? " selected" : "") +
        ">" +
        e(s.name) +
        "</option>"
      );
    })
    .join("");
  return (
    '<div class="modal-header">' +
    "<div>" +
    '<div style="font-size:11px;color:var(--blue);font-weight:600;margin-bottom:2px">' +
    TL[type] +
    "</div>" +
    '<div class="modal-title">' +
    (isEdit ? "Edit" : "Add") +
    " Question</div>" +
    "</div>" +
    '<div style="display:flex;align-items:center;gap:8px">' +
    '<span class="q-marks-chip badge-pos">+' +
    q.pos_marks +
    "</span>" +
    '<span class="q-marks-chip badge-neg">-' +
    q.neg_marks +
    "</span>" +
    (q.neg_unattempted > 0
      ? '<span class="q-marks-chip badge-neg">-' +
        q.neg_unattempted +
        " unatt.</span>"
      : "") +
    '<button class="modal-close" onclick="closeModal()">×</button>' +
    "</div>" +
    "</div>" +
    '<div class="modal-body">' +
    '<div class="form-row" style="margin-bottom:14px;align-items:flex-start">' +
    '<div style="flex:1">' +
    '<div class="form-label">Question' +
    (type === "fitb"
      ? ' <span style="font-size:10px;color:var(--gray-500)">(use .......... for blanks)</span>'
      : "") +
    "</div>" +
    buildRte("qmain", "Type your question here...", q.text || "") +
    "</div>" +
    '<div style="width:136px;flex-shrink:0">' +
    '<div class="form-group">' +
    '<div class="form-label">Difficulty</div>' +
    '<select class="form-input form-select" id="q-diff"><option' +
    (q.difficulty === "Easy" ? " selected" : "") +
    ">Easy</option><option" +
    (q.difficulty === "Medium" ? " selected" : "") +
    ">Medium</option><option" +
    (q.difficulty === "Hard" ? " selected" : "") +
    ">Hard</option></select>" +
    "</div>" +
    (type === "mcq"
      ? '<div class="form-group"><div class="form-label">Answers</div><select class="form-input form-select" id="q-ans-type" onchange="updateAnsMode()"><option value="single"' +
        (!q.multi_select && !q.multiSelect ? " selected" : "") +
        '>Single</option><option value="multiple"' +
        (q.multi_select || q.multiSelect ? " selected" : "") +
        ">Multiple</option></select></div>"
      : "") +
    "" +
    "</div>" +
    "</div>" +
    buildAnsSection(type, q) +
    '<div class="section-divider"><div class="section-divider-line"></div><div class="section-divider-text">Marks & Settings</div><div class="section-divider-line"></div></div>' +
    '<div class="form-row">' +
    '<div class="form-group"><div class="form-label">Marks per Question</div><input class="form-input" type="number" id="q-pos" value="' +
    q.pos_marks +
    '" min="0"></div>' +
    '<div class="form-group"><div style="display:flex;align-items:center;gap:6px;margin-bottom:5px"><input type="checkbox" id="neg-en"' +
    (q.neg_marks > 0 ? " checked" : "") +
    ' onchange="toggleNegField()"><label for="neg-en" class="form-label" style="margin:0">Negative Marks</label></div><input class="form-input" type="number" id="q-neg" value="' +
    q.neg_marks +
    '" min="0"></div>' +
    "</div>" +
    '<div class="form-group"' +
    (q.neg_marks > 0 ? "" : ' style="display:none"') +
    ' id="neg-un-group"><div style="display:flex;align-items:center;gap:6px;margin-bottom:5px"><input type="checkbox" id="neg-un"' +
    (q.neg_unattempted > 0 ? " checked" : "") +
    ' ><label for="neg-un" class="form-label" style="margin:0">Neg. if Unattempted</label></div><input class="form-input" type="number" id="q-negUn" value="' +
    q.neg_unattempted +
    '" min="0"></div>' +
    '<div class="form-group" style="margin-top:14px"><div class="form-label">Add to Section</div><select class="form-input form-select" id="q-section">' +
    secOpts +
    "</select></div>" +
    '<div class="form-group"><div class="form-label">Tags</div><input class="form-input" id="q-tags" value="' +
    e((q.tags || []).join(", ")) +
    '" placeholder="e.g. SCHOLARSHIP TEST"></div>' +
    "</div>" +
    '<div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="saveQ(' +
    (isEdit ? q.id : "null") +
    ')">Save Question</button></div>'
  );
}

function buildAnsSection(type, q) {
  if (type === "mcq") {
    var opts = getQuestionOptions(q);
    var correctIndexes = getCorrectOptionIndexes(q);
    opts = opts.length > 0 ? opts : ["", "", "", ""];
    return (
      '<div class="form-group"><div class="form-label">Answer Options <span style="font-size:11px;color:var(--gray-500)">(click to mark correct)</span></div>' +
      '<div class="options-list" id="opts-list">' +
      opts
        .map(function (o, i) {
          var ok = correctIndexes.indexOf(i) !== -1;
          return (
            '<div class="option-row" id="orow-' +
            i +
            '"><div class="option-check' +
            (ok ? " checked" : "") +
            '" onclick="togOpt(' +
            i +
            ')" id="ochk-' +
            i +
            '">' +
            (ok ? "✓" : "") +
            '</div><input class="option-input" placeholder="Option ' +
            (i + 1) +
            '" value="' +
            e(o) +
            '" id="oinp-' +
            i +
            '"><button class="option-delete" onclick="this.parentElement.remove()">✕</button></div>'
          );
        })
        .join("") +
      "</div>" +
      '<button class="add-option-btn" onclick="addOpt()">+ Add new option</button>' +
      "</div>"
    );
  } else if (type === "tf") {
    return (
      '<div class="form-group"><div class="form-label">Correct Answer</div><div style="display:flex;gap:20px;margin-top:6px"><label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer"><input type="radio" name="tf-ans" value="True"' +
      ((q.correct_answer || q.correctAnswer) === "True" ? " checked" : "") +
      ' > True</label><label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer"><input type="radio" name="tf-ans" value="False"' +
      ((q.correct_answer || q.correctAnswer) === "False" ? " checked" : "") +
      " > False</label></div></div>"
    );
  } else if (type === "fitb") {
    return (
      '<div class="form-group"><div class="form-label">Correct Answer</div><input class="form-input" id="q-ans" value="' +
      e(q.correct_answer || q.correctAnswer || "") +
      '" placeholder="Type correct fill-in answer..."></div>'
    );
  } else if (type === "int") {
    return (
      '<div class="form-group"><div class="form-label">Correct Integer Answer</div><input class="form-input" type="number" id="q-ans" value="' +
      e(q.correct_answer || q.correctAnswer || "") +
      '" placeholder="Enter integer..."></div>'
    );
  } else if (type === "comp") {
    var sqs =
      q.sub_questions && q.sub_questions.length > 0 ? q.sub_questions : [""];
    return (
      '<div class="form-group"><div class="form-label">Passage</div><textarea class="form-input" id="q-passage" rows="3" placeholder="Enter comprehension passage...">' +
      e(q.passage || "") +
      "</textarea></div>" +
      '<div class="form-group"><div class="form-label">Sub-questions</div><div class="options-list" id="subq-list">' +
      sqs
        .map(function (sq, i) {
          return (
            '<div class="option-row" style="align-items:flex-start" id="subq-row-' +
            i +
            '"><span style="color:var(--gray-500);font-size:12px;min-width:20px;padding-top:8px">' +
            (i + 1) +
            '.</span><textarea class="option-input" rows="2" placeholder="Sub-question ' +
            (i + 1) +
            '" id="subq-' +
            i +
            '">' +
            e(sq) +
            '</textarea><button class="option-delete" onclick="this.parentElement.remove()" style="margin-top:6px">✕</button></div>'
          );
        })
        .join("") +
      '</div><button class="add-option-btn" onclick="addSubQ()">+ Add sub-question</button></div>'
    );
  }
  return "";
}

window.togOpt = function (i) {
  var ansType = document.getElementById("q-ans-type");
  var isMulti = ansType && ansType.value === "multiple";
  var el = document.getElementById("ochk-" + i);
  if (!el) return;
  if (!isMulti) {
    var allChk = document.querySelectorAll(".option-check");
    allChk.forEach(function (c) {
      c.classList.remove("checked");
      c.textContent = "";
    });
    el.classList.add("checked");
    el.textContent = "✓";
  } else {
    el.classList.toggle("checked");
    el.textContent = el.classList.contains("checked") ? "✓" : "";
  }
};

window.updateAnsMode = function () {
  var ansType = document.getElementById("q-ans-type");
  var isMulti = ansType && ansType.value === "multiple";
  var allChk = document.querySelectorAll(".option-check");
  if (!isMulti) {
    var checkedCount = 0;
    allChk.forEach(function (c) {
      if (c.classList.contains("checked")) checkedCount++;
    });
    if (checkedCount > 1) {
      allChk.forEach(function (c) {
        c.classList.remove("checked");
        c.textContent = "";
      });
    }
  }
};

window.toggleNegField = function () {
  var negEn = document.getElementById("neg-en");
  var negUnGroup = document.getElementById("neg-un-group");
  if (negEn && negUnGroup) {
    negUnGroup.style.display = negEn.checked ? "block" : "none";
    if (!negEn.checked) {
      document.getElementById("neg-un").checked = false;
      document.getElementById("q-negUn").value = 0;
    }
  }
};

window.addOpt = function () {
  var l = document.getElementById("opts-list");
  if (!l) return;
  var c = l.querySelectorAll(".option-row").length;
  var d = document.createElement("div");
  d.className = "option-row";
  d.id = "orow-" + c;
  d.innerHTML =
    '<div class="option-check" onclick="togOpt(' +
    c +
    ')" id="ochk-' +
    c +
    '"></div><input class="option-input" placeholder="Option ' +
    (c + 1) +
    '" id="oinp-' +
    c +
    '"><button class="option-delete" onclick="this.parentElement.remove()">✕</button>';
  l.appendChild(d);
};

window.addSubQ = function () {
  var l = document.getElementById("subq-list");
  if (!l) return;
  var c = l.querySelectorAll(".option-row").length;
  var d = document.createElement("div");
  d.className = "option-row";
  d.style.alignItems = "flex-start";
  d.id = "subq-row-" + c;
  d.innerHTML =
    '<span style="color:var(--gray-500);font-size:12px;min-width:20px;padding-top:8px">' +
    (c + 1) +
    '.</span><textarea class="option-input" rows="2" placeholder="Sub-question ' +
    (c + 1) +
    '" id="subq-' +
    c +
    '"></textarea><button class="option-delete" onclick="this.parentElement.remove()" style="margin-top:6px">✕</button>';
  l.appendChild(d);
};

window.saveQ = function (editId) {
  var rteEl = document.getElementById("rte-qmain");
  var html = rteEl ? rteEl.innerHTML.trim() : "";
  var plain = rteEl ? rteEl.innerText.trim() : "";
  if (!plain && !html) {
    showToast("Please enter question text!");
    return;
  }
  var type = S.qType;
  var diff = document.getElementById("q-diff").value;
  var pos = parseFloat(document.getElementById("q-pos").value);
  if (isNaN(pos)) {
    pos = S.defaultPosMarks;
  }
  var neg = document.getElementById("neg-en").checked
    ? parseFloat(document.getElementById("q-neg").value)
    : 0;
  if (isNaN(neg)) {
    neg = document.getElementById("neg-en").checked ? S.defaultNegMarks : 0;
  }
  var negUn = document.getElementById("neg-un").checked
    ? parseFloat(document.getElementById("q-negUn").value) || 0
    : 0;
  var secId = parseInt(document.getElementById("q-section").value);
  var tags = document
    .getElementById("q-tags")
    .value.split(",")
    .map(function (t) {
      return t.trim();
    })
    .filter(Boolean);
  var ansTypeEl = document.getElementById("q-ans-type");
  var multi = ansTypeEl && ansTypeEl.value === "multiple";
  var q = {
    id: editId || S.nextQId++,
    type: type,
    text: html,
    difficulty: diff,
    pos_marks: pos,
    neg_marks: neg,
    neg_unattempted: negUn,
    tags: tags,
  };
  if (type === "mcq") {
    var opts = [],
      corr = [];
    var l = document.getElementById("opts-list");
    if (l) {
      l.querySelectorAll(".option-row").forEach(function (row) {
        var inp = row.querySelector(".option-input"),
          chk = row.querySelector(".option-check");
        if (inp) opts.push(inp.value);
        if (chk && chk.classList.contains("checked"))
          corr.push(opts.length - 1);
      });
    }
    q.options = opts;
    q.correct_options = corr;
    q.multi_select = multi;
  } else if (type === "tf") {
    var r = document.querySelector('input[name="tf-ans"]:checked');
    q.correct_answer = r ? r.value : "True";
  } else if (type === "fitb" || type === "int") {
    q.correct_answer = (document.getElementById("q-ans") || {}).value || "";
  } else if (type === "comp") {
    q.passage = (document.getElementById("q-passage") || {}).value || "";
    var sl = document.getElementById("subq-list"),
      sqs = [];
    if (sl) {
      sl.querySelectorAll("textarea").forEach(function (t) {
        sqs.push(t.value.trim());
      });
    }
    q.sub_questions = sqs;
  }
  q._persisted = !!editId;

  if (currentTestId) {
    const data = buildQuestionPayload(q, secId);

    fetch(`/scholarship/api/tests/${currentTestId}/save-question/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    })
      .then((response) => {
        if (!response.ok) {
          return response.text().then((text) => {
            try {
              const data = JSON.parse(text);
              throw new Error(data.error || `HTTP ${response.status}`);
            } catch (e) {
              throw new Error(
                text.substring(0, 200) || `HTTP ${response.status}`,
              );
            }
          });
        }
        return response.json();
      })
      .then((result) => {
        if (result.success) {
          var tSec = S.sections.find(function (s) {
            return s.id === secId;
          });
          if (!tSec) {
            showToast("Section not found!");
            return;
          }
          if (editId) {
            var os = S.sections.find(function (s) {
              return s.questions.some(function (x) {
                return x.id === editId;
              });
            });
            if (os)
              os.questions = os.questions.filter(function (x) {
                return x.id !== editId;
              });
            q.id =
              result.question && result.question.id ? result.question.id : q.id;
            q._persisted = true;
            tSec.questions.push(normalizeQuestion(q));
            showToast("✓ Question updated");
          } else {
            q.id =
              result.question && result.question.id ? result.question.id : q.id;
            q._persisted = true;
            tSec.questions.push(normalizeQuestion(q));
            showToast('✓ Question added to "' + tSec.name + '"');
          }
          closeModal();
          render();
        } else {
          showToast("❌ " + (result.error || "Unknown error"));
        }
      })
      .catch((err) => {
        console.error("Error saving question:", err);
        showToast("❌ " + err.message);
      });
  } else {
    // Fallback for new tests
    var tSec = S.sections.find(function (s) {
      return s.id === secId;
    });
    if (!tSec) {
      showToast("Section not found!");
      return;
    }
    if (editId) {
      var os = S.sections.find(function (s) {
        return s.questions.some(function (x) {
          return x.id === editId;
        });
      });
      if (os)
        os.questions = os.questions.filter(function (x) {
          return x.id !== editId;
        });
      tSec.questions.push(q);
      showToast("✓ Question updated");
    } else {
      tSec.questions.push(q);
      showToast('✓ Question added to "' + tSec.name + '"');
    }
    saveData();
    closeModal();
    render();
  }
};

window.openEditMarks = function (qId, secId) {
  var sec = S.sections.find(function (s) {
    return s.id === secId;
  });
  if (!sec) return;
  var q = sec.questions.find(function (x) {
    return x.id === qId;
  });
  if (!q) return;
  showModal(
    '<div class="modal-header"><span class="modal-title">Edit Marks — Question #' +
      qId +
      '</span><button class="modal-close" onclick="closeModal()">×</button></div>' +
      '<div class="modal-body">' +
      '<div class="form-row">' +
      '<div class="form-group"><div class="form-label">Marks per Question</div><input class="form-input" type="number" id="em-pos" value="' +
      q.pos_marks +
      '" min="0"></div>' +
      '<div class="form-group"><div class="form-label">Negative Marks</div><input class="form-input" type="number" id="em-neg" value="' +
      q.neg_marks +
      '" min="0"></div>' +
      "</div>" +
      '<div class="form-group"><div class="form-label">Negative if Unattempted</div><input class="form-input" type="number" id="em-negUn" value="' +
      q.neg_unattempted +
      '" min="0"></div>' +
      '<div class="partial-info"><span>Partial Marking <span class="new-badge">New</span></span><span class="partial-link">View Example</span></div>' +
      "</div>" +
      '<div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="saveMarks(' +
      qId +
      "," +
      secId +
      ')">Save Marks</button></div>',
  );
};

window.saveMarks = function (qId, secId) {
  var sec = S.sections.find(function (s) {
    return s.id === secId;
  });
  if (!sec) return;
  var q = sec.questions.find(function (x) {
    return x.id === qId;
  });
  if (!q) return;
  q.pos_marks = parseFloat(document.getElementById("em-pos").value) || 0;
  q.neg_marks = parseFloat(document.getElementById("em-neg").value) || 0;
  q.neg_unattempted =
    parseFloat(document.getElementById("em-negUn").value) || 0;
  closeModal();
  render();
  showToast("✓ Marks updated");
};

window.copyQ = function (qId, secId) {
  var sec = S.sections.find(function (s) {
    return s.id === secId;
  });
  if (!sec) return;
  var q = sec.questions.find(function (x) {
    return x.id === qId;
  });
  if (!q) return;
  var cp = JSON.parse(JSON.stringify(q));
  cp.id = S.nextQId++;
  cp.text = cp.text + " (Copy)";
  sec.questions.push(cp);
  render();
  showToast("✓ Question copied");
};

function confirmDelQ(qId, secId) {
  showModal(
    '<div class="modal-header"><span class="modal-title">Delete Question</span><button class="modal-close" onclick="closeModal()">×</button></div>' +
      '<div class="modal-body"><div class="confirm-icon">🗑️</div><div class="confirm-msg">Delete this question? Cannot be undone.</div></div>' +
      '<div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-danger" onclick="delQ(' +
      qId +
      "," +
      secId +
      ')">Delete</button></div>',
  );
}

window.delQ = function (qId, secId) {
  if (currentTestId) {
    fetch(`/scholarship/api/tests/${currentTestId}/questions/${qId}/delete/`, {
      method: "DELETE",
    })
      .then((response) => response.json())
      .then((result) => {
        if (result.success) {
          var sec = S.sections.find(function (s) {
            return s.id === secId;
          });
          if (sec)
            sec.questions = sec.questions.filter(function (q) {
              return q.id !== qId;
            });
          closeModal();
          render();
          showToast("Question deleted");
        } else {
          alert(
            "Error deleting question: " + (result.error || "Unknown error"),
          );
        }
      })
      .catch((err) => {
        console.error("Error deleting question:", err);
        alert("Error deleting question");
      });
  } else {
    var sec = S.sections.find(function (s) {
      return s.id === secId;
    });
    if (sec)
      sec.questions = sec.questions.filter(function (q) {
        return q.id !== qId;
      });
    saveData();
    closeModal();
    render();
    showToast("Question deleted");
  }
};

window.openTestDetails = function () {
  var duration = getDurationParts(S.duration);
  showModal(
    '<div class="modal-header"><span class="modal-title">Test Details</span><button class="modal-close" onclick="closeModal()">×</button></div>' +
      '<div class="modal-body">' +
      '<div class="form-group"><div class="form-label">Test Name</div><input class="form-input" id="td-name" value="' +
      e(S.testName) +
      '"></div>' +
      '<div class="form-row">' +
      '<div class="form-group"><div class="form-label">Duration (hours)</div><input class="form-input" type="number" id="td-dur-hours" value="' +
      e(duration.hours) +
      '" min="0" step="1"></div>' +
      '<div class="form-group"><div class="form-label">Duration (minutes)</div><input class="form-input" type="number" id="td-dur-minutes" value="' +
      e(duration.minutes) +
      '" min="0" max="59" step="1"></div>' +
      "</div>" +
      '<div class="form-row">' +
      '<div class="form-group"><div class="form-label">Tags</div><input class="form-input" id="td-tags" value="' +
      e(S.tags) +
      '"></div>' +
      "</div>" +
      '<div class="form-group"><div class="form-label">Instructions</div><textarea class="form-input" id="td-instr" placeholder="Enter instructions...">' +
      e(S.instructions) +
      "</textarea></div>" +
      "</div>" +
      '<div class="modal-footer"><button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="saveTestDetails()">Save</button></div>',
  );
};

window.saveTestDetails = function () {
  var durationHours = document.getElementById("td-dur-hours").value;
  var durationMinutes = document.getElementById("td-dur-minutes").value;

  S.testName = document.getElementById("td-name").value.trim() || S.testName;
  S.duration = normalizeDurationValue(null, durationHours, durationMinutes);
  S.tags = document.getElementById("td-tags").value.trim();
  S.instructions = document.getElementById("td-instr").value.trim();
  saveData();
  closeModal();
  render();
  showToast("✓ Test details updated");
  updateTopbarTitle();
};

window._legacySaveTest = function () {
  // For new tests (no test ID), first create the test
  if (!currentTestId) {
    // Get test details from the form
    var testName = S.testName || "Untitled Test";
    var duration = getDurationParts(S.duration || "1");
    var tags = S.tags || "";

    // Create the test via API
    var data = {
      name: testName,
      duration_hours: duration.hours,
      duration_minutes: duration.minutes,
      tags: tags,
      status: "published",
    };

    fetch("/scholarship/api/tests/create/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "Failed to create test");
          });
        }
        return response.json();
      })
      .then(function (result) {
        if (result.success) {
          currentTestId = result.test.id;
          // Update URL without reload
          var newUrl = window.location.pathname + "?test_id=" + currentTestId;
          window.history.pushState({ path: newUrl }, "", newUrl);
          // Now save sections
          saveAllSectionsFixed();
        } else {
          showToast("❌ " + (result.error || "Failed to create test"));
        }
      })
      .catch(function (err) {
        console.error("Error creating test:", err);
        showToast("❌ " + err.message);
      });
  } else {
    // Test already exists, just save everything
    saveData();
    saveAllSectionsFixed();
    showToast("✓ Test saved successfully");
  }
};

function saveAllSections() {
  if (!currentTestId) return;

  var promises = S.sections.map(function (sec) {
    var data = {
      id: sec.id,
      name: sec.name,
      allowSwitching: sec.allow_switching || sec.allowSwitching,
      instructions: sec.instructions || sec.sectionInstructions || "",
    };

    return fetch(`/scholarship/api/tests/${currentTestId}/save-section/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (data) {
          throw new Error(data.error || "Failed to save section");
        });
      }
      return response.json();
    });
  });

  Promise.all(promises)
    .then(function (results) {
      updateTopbarTitle();
      showToast("✓ Test saved with all sections");
    })
    .catch(function (err) {
      console.error("Error saving sections:", err);
    });
}

function legacySaveAllSectionsFixed() {
  if (!currentTestId) return;

  var promises = S.sections.map(function (sec) {
    var data = {
      name: sec.name,
      allowSwitching: sec.allow_switching || sec.allowSwitching,
      instructions: sec.instructions || sec.sectionInstructions || "",
      preferExistingByName: true,
    };
    if (sec._persisted) {
      data.id = sec.id;
    }

    return fetch(`/scholarship/api/tests/${currentTestId}/save-section/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (data) {
          throw new Error(data.error || "Failed to save section");
        });
      }
      return response.json();
    });
  });

  Promise.all(promises)
    .then(function (results) {
      results.forEach(function (result, idx) {
        if (!result || !result.success || !result.section) return;
        S.sections[idx].id = result.section.id;
        S.sections[idx].allow_switching = result.section.allow_switching;
        S.sections[idx].instructions = result.section.instructions;
        S.sections[idx]._persisted = true;
      });
      return persistAllQuestionsFixed();
    })
    .then(function () {
      updateTopbarTitle();
      showToast("âœ“ Test saved with all sections");
    })
    .catch(function (err) {
      console.error("Error saving sections:", err);
      showToast("âŒ " + err.message);
    });
}

function persistAllQuestionsFixed() {
  if (!currentTestId) return Promise.resolve();

  var allQuestions = [];
  S.sections.forEach(function (sec) {
    sec.questions.forEach(function (q) {
      allQuestions.push({ question: q, sectionId: sec.id });
    });
  });

  if (allQuestions.length === 0) {
    return Promise.resolve();
  }

  var requests = allQuestions.map(function (item) {
    return fetch(`/scholarship/api/tests/${currentTestId}/save-question/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildQuestionPayload(item.question, item.sectionId)),
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "Failed to save question");
          });
        }
        return response.json();
      })
      .then(function (result) {
        if (result && result.question && result.question.id) {
          item.question.id = result.question.id;
        }
        item.question._persisted = true;
        normalizeQuestion(item.question);
      });
  });

  return Promise.all(requests);
}

function redirectToManagementPage() {
  window.location.href = "/scholarship/scholarshiptest-management/";
}

function saveAllSectionsFixed() {
  if (!currentTestId) return Promise.resolve();

  if (S.sections.length === 0) {
    return Promise.resolve();
  }

  var promises = S.sections.map(function (sec) {
    var data = {
      name: sec.name,
      allowSwitching: sec.allow_switching || sec.allowSwitching,
      instructions: sec.instructions || sec.sectionInstructions || "",
    };
    if (sec._persisted) {
      data.id = sec.id;
    }

    return fetch(`/scholarship/api/tests/${currentTestId}/save-section/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    }).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (data) {
          throw new Error(data.error || "Failed to save section");
        });
      }
      return response.json();
    });
  });

  return Promise.all(promises).then(function (results) {
    results.forEach(function (result, idx) {
      if (!result || !result.success || !result.section) return;
      S.sections[idx].id = result.section.id;
      S.sections[idx].allow_switching = result.section.allow_switching;
      S.sections[idx].instructions = result.section.instructions;
      S.sections[idx]._persisted = true;
    });
    return persistAllQuestionsFixed();
  });
}

window.saveTest = function () {
  syncGradingFromInputs();
  var duration = getDurationParts(S.duration);

  function persistEverything() {
    return saveData({ status: "published" })
      .then(function () {
        return saveAllSectionsFixed();
      })
      .then(function () {
        updateTopbarTitle();
        render();
        showToast("Test saved successfully");
        setTimeout(function () {
          redirectToManagementPage();
        }, 300);
      });
  }

  if (!currentTestId) {
    var data = {
      name: S.testName || "Untitled Test",
      duration_hours: duration.hours,
      duration_minutes: duration.minutes,
      tags: S.tags || "",
      status: "published",
    };

    return fetch("/scholarship/api/tests/create/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "Failed to create test");
          });
        }
        return response.json();
      })
      .then(function (result) {
        if (!result.success) {
          throw new Error(result.error || "Failed to create test");
        }

        currentTestId = result.test.id;
        var newUrl = window.location.pathname + "?test_id=" + currentTestId;
        window.history.pushState({ path: newUrl }, "", newUrl);
        return persistEverything();
      })
      .catch(function (err) {
        console.error("Error creating test:", err);
        showToast("âŒ " + err.message);
      });
  }

  return persistEverything().catch(function (err) {
    console.error("Error saving test:", err);
    showToast("âŒ " + err.message);
  });
};

function updateTopbarTitle() {
  var titleEl = document.getElementById("back-btn-text");
  if (titleEl && S.testName) {
    titleEl.textContent = S.testName;
  }
}

window.goBack = function () {
  // If there are unsaved changes, warn the user
  if (S.sections && S.sections.length > 0) {
    if (
      !confirm("You have unsaved changes. Are you sure you want to go back?")
    ) {
      return;
    }
  }
  redirectToManagementPage();
};

window.showModal = function (html, isLarge) {
  document.getElementById("modal-root").innerHTML =
    '<div class="modal-overlay" onclick="handleMOvl(event)"><div class="modal' +
    (isLarge ? " modal-lg" : "") +
    '" onclick="event.stopPropagation()">' +
    html +
    "</div></div>";
};

window.handleMOvl = function (e) {
  if (e.target.classList.contains("modal-overlay")) closeModal();
};

window.closeModal = function () {
  document.getElementById("modal-root").innerHTML = "";
};

window.showToast = function (msg) {
  var x = document.querySelector(".toast");
  if (x) x.remove();
  var t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function () {
    if (t.parentNode) {
      t.style.opacity = "0";
      t.style.transition = "opacity 0.3s";
      setTimeout(function () {
        if (t.parentNode) t.remove();
      }, 300);
    }
  }, 2500);
};

document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") {
    closeModal();
    closeImg();
  }
});

window.addEventListener("resize", function () {
  syncSectionBodyHeights();
});

/* ========== RICH TEXT EDITOR ========== */
function buildRte(id, placeholder, initHtml) {
  return (
    '<div class="rte-wrapper">' +
    '<div class="rte-toolbar">' +
    '<div class="rte-group">' +
    '<select class="tb-sel" id="fs-' +
    id +
    "\" onchange=\"rteCmd('fontSize',this.value,'" +
    id +
    "');updateFsDropdown('" +
    id +
    '\',this.value)" title="Font Size">' +
    '<option value="1">8pt</option><option value="2">10pt</option><option value="3" selected>12pt</option><option value="4">14pt</option><option value="5">18pt</option><option value="6">24pt</option>' +
    "</select>" +
    '<select class="tb-sel" id="font-' +
    id +
    '" style="width:88px" onchange="rteCmd(\'fontName\',this.value,\'' +
    id +
    '\');syncFontDropdown(this)" title="Font">' +
    '<option value="Noto Sans">Noto Sans</option><option value="Arial">Arial</option><option value="Times New Roman">Times New Roman</option><option value="Courier New">Courier New</option><option value="Georgia">Georgia</option>' +
    "</select>" +
    "</div>" +
    '<div class="rte-group">' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('undo',null,'" +
    id +
    '\')" title="Undo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/></svg></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('redo',null,'" +
    id +
    '\')" title="Redo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 14 20 9 15 4"/><path d="M4 20v-7a4 4 0 0 1 4-4h12"/></svg></button>' +
    "</div>" +
    '<div class="rte-group">' +
    '<select class="tb-sel" style="width:76px" onchange="rteFormat(this.value,\'' +
    id +
    '\')" title="Format">' +
    '<option value="">Formats</option><option value="p">Paragraph</option><option value="h1">Heading 1</option><option value="h2">Heading 2</option><option value="h3">Heading 3</option><option value="pre">Code</option>' +
    "</select>" +
    "</div>" +
    '<div class="rte-group">' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('bold',null,'" +
    id +
    '\')" title="Bold"><b>B</b></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('italic',null,'" +
    id +
    "')\" title=\"Italic\"><i style='font-family:serif'>I</i></button>" +
    "<button class=\"tb-btn\" onclick=\"rteCmd('underline',null,'" +
    id +
    '\')" title="Underline"><u>U</u></button>' +
    "</div>" +
    '<div class="rte-group">' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('justifyLeft',null,'" +
    id +
    '\')" title="Left"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('justifyCenter',null,'" +
    id +
    '\')" title="Center"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="10" x2="6" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="18" y1="18" x2="6" y2="18"/></svg></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('justifyRight',null,'" +
    id +
    '\')" title="Right"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="21" y1="10" x2="7" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="7" y2="18"/></svg></button>' +
    "</div>" +
    '<div class="rte-group">' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('insertUnorderedList',null,'" +
    id +
    '\')" title="Bullet"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/></svg></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('insertOrderedList',null,'" +
    id +
    '\')" title="Numbered"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/></svg></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('outdent',null,'" +
    id +
    '\')" title="Outdent"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="7 8 3 12 7 16"/><line x1="21" y1="12" x2="3" y2="12"/><line x1="21" y1="6" x2="11" y2="6"/><line x1="21" y1="18" x2="11" y2="18"/></svg></button>' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('indent',null,'" +
    id +
    '\')" title="Indent"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 8 21 12 17 16"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="13" y2="6"/><line x1="3" y1="18" x2="13" y2="18"/></svg></button>' +
    "</div>" +
    /* IMAGE BUTTON */
    '<div class="rte-group">' +
    '<button class="tb-btn" onclick="openImgModal(\'' +
    id +
    '\')" title="Insert Image" style="width:auto;padding:0 6px;font-size:11px;gap:3px">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>' +
    "Image" +
    "</button>" +
    "</div>" +
    '<div class="rte-group">' +
    "<button class=\"tb-btn\" onclick=\"rteCmd('removeFormat',null,'" +
    id +
    '\')" title="Clear Formatting" style="font-size:10px">Tx</button>' +
    "</div>" +
    "</div>" +
    '<div class="rte-body" id="rte-' +
    id +
    '" contenteditable="true" data-placeholder="' +
    placeholder +
    '" onmouseup="syncFsDropdown(\'' +
    id +
    "')\" onkeyup=\"syncFsDelayed('" +
    id +
    "')\">" +
    (initHtml || "") +
    "</div>" +
    "</div>"
  );
}

var _fsTimeout = {};
function syncFsDelayed(id) {
  clearTimeout(_fsTimeout[id]);
  _fsTimeout[id] = setTimeout(function () {
    syncFsDropdown(id);
  }, 500);
}

function syncFsDropdown(id) {
  var sel = window.getSelection();
  if (sel.rangeCount > 0 && sel.rangeCount) {
    var node = sel.anchorNode;
    if (node && node.nodeType === 3) node = node.parentNode;
    if (node) {
      var sz = window.getComputedStyle(node).fontSize;
      var num = parseInt(sz) || 12;
      var val =
        num <= 8
          ? "1"
          : num <= 10
            ? "2"
            : num <= 12
              ? "3"
              : num <= 14
                ? "4"
                : num <= 18
                  ? "5"
                  : "6";
      var dropdown = document.getElementById("fs-" + id);
      if (dropdown) {
        for (var i = 0; i < dropdown.options.length; i++) {
          if (dropdown.options[i].value === val) {
            dropdown.selectedIndex = i;
            break;
          }
        }
      }
    }
  }
}

function rteCmd(cmd, val, id) {
  var el = document.getElementById("rte-" + id);
  if (!el) return;
  el.focus();
  document.execCommand(cmd, false, val);
  if (cmd === "fontSize") {
    updateFsDropdown(id, val);
  }
}

function updateFsDropdown(id, val) {
  var sel = document.getElementById("fs-" + id);
  if (sel) {
    for (var i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value === val) {
        sel.selectedIndex = i;
        break;
      }
    }
  }
}

function syncFontDropdown(sel) {
  if (!sel) return;
  var rteId = sel.id.replace("font-", "");
  var rteEl = document.getElementById("rte-" + rteId);
  if (!rteEl) return;
  var computedFont = window.getComputedStyle(rteEl).fontFamily;
  if (computedFont) {
    computedFont = computedFont.replace(/['"]/g, "").split(",")[0].trim();
    for (var i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value.toLowerCase() === computedFont.toLowerCase()) {
        sel.selectedIndex = i;
        return;
      }
    }
  }
}

function rteFormat(val, id) {
  if (!val) return;
  var el = document.getElementById("rte-" + id);
  if (!el) return;
  el.focus();
  document.execCommand("formatBlock", false, val);
}

function getRte(id) {
  var el = document.getElementById("rte-" + id);
  return el ? el.innerHTML : "";
}

/* ========== IMAGE MODAL ========== */
function openImgModal(rteId) {
  pendingRte = rteId;
  window._uploadedImgUrl = null;

  // Check if test is saved
  if (!hasTestId()) {
    showToast("⚠️ Please save the test first before adding images.");
    return;
  }

  document.getElementById("img-root").innerHTML =
    '<div class="img-overlay" onclick="handleImgOvl(event)">' +
    '<div class="img-modal-box">' +
    '<div class="img-modal-hdr"><span class="img-modal-ttl">Insert / Edit Image</span><button class="img-x" onclick="closeImg()">×</button></div>' +
    '<div class="img-tab-body active" id="itb-upload" style="display:block;padding:18px 20px">' +
    '<div class="drop-zone" id="img-dropzone" onclick="document.getElementById(\'img-file\').click()" ondragover="imgDragOver(event)" ondragleave="imgDragLeave(event)" ondrop="imgDrop(event)">' +
    '<div class="drop-zone-icon">🖼️</div>' +
    '<div class="drop-zone-text">Click to browse or drag & drop</div>' +
    '<div class="drop-zone-sub">Supports: JPG, PNG, GIF, SVG, WebP (Max 5MB)</div>' +
    "</div>" +
    '<input type="file" id="img-file" accept="image/*" style="display:none" onchange="imgFileChg(this)">' +
    '<div class="img-preview-box" id="img-up-prev" style="display:none;margin-top:10px"><img id="img-up-prev-img" src="" alt="Preview"></div>' +
    "</div>" +
    '<div class="img-modal-ftr">' +
    '<button class="btn btn-secondary btn-sm" onclick="closeImg()">Cancel</button>' +
    '<button class="btn btn-primary btn-sm" onclick="insertImg()">Insert Image</button>' +
    "</div>" +
    "</div></div>";
}

window.switchImgTab = function (btn, id) {
  document.querySelectorAll(".img-tab").forEach(function (t) {
    t.classList.remove("active");
  });
  document.querySelectorAll(".img-tab-body").forEach(function (t) {
    t.classList.remove("active");
  });
  btn.classList.add("active");
  document.getElementById("itb-" + id).classList.add("active");
};

window.prevImgUrl = function () {
  var src = (document.getElementById("img-src") || {}).value || "";
  var p = document.getElementById("img-url-prev");
  if (!p) return;
  p.innerHTML = src
    ? '<img src="' +
      src +
      '" onerror="this.parentElement.innerHTML=\'<span style=color:red>Cannot load image</span>\'" alt="preview">'
    : "<span>Image preview</span>";
};

window.imgDragOver = function (e) {
  e.preventDefault();
  document.getElementById("img-dropzone").classList.add("drag-over");
};

window.imgDragLeave = function () {
  document.getElementById("img-dropzone").classList.remove("drag-over");
};

window.imgDrop = function (e) {
  e.preventDefault();
  document.getElementById("img-dropzone").classList.remove("drag-over");
  var f = e.dataTransfer.files[0];
  if (f && f.type.startsWith("image/")) uploadImgFile(f);
};

window.imgFileChg = function (inp) {
  if (inp.files[0]) uploadImgFile(inp.files[0]);
};

window.uploadImgFile = function (file) {
  // Validate file size (5MB limit)
  if (file.size > 5 * 1024 * 1024) {
    showToast("File too large. Maximum size is 5MB.");
    return;
  }

  // Validate file type
  const allowedTypes = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
  ];
  if (!allowedTypes.includes(file.type)) {
    showToast("Invalid file type. Only images are allowed.");
    return;
  }

  // Show preview
  var prev = document.getElementById("img-up-prev");
  var img = document.getElementById("img-up-prev-img");
  if (prev && img) {
    var reader = new FileReader();
    reader.onload = function (e) {
      img.src = e.target.result;
      prev.style.display = "flex";
    };
    reader.readAsDataURL(file);
  }

  // Upload to server
  var formData = new FormData();
  formData.append("image", file);

  const testId = getTestIdFromUrl();
  if (!testId) {
    showToast("⚠️ Please save the test first before uploading images.");
    return;
  }

  fetch(`/scholarship/api/tests/${testId}/upload-image/`, {
    method: "POST",
    body: formData,
  })
    .then((response) => {
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "Upload failed");
        });
      }
      return response.json();
    })
    .then((data) => {
      if (data.success) {
        window._uploadedImgUrl = data.image.url;
        showToast("✓ Image uploaded successfully");
      } else {
        throw new Error(data.error || "Upload failed");
      }
    })
    .catch((error) => {
      console.error("Upload error:", error);
      showToast("❌ Image upload failed: " + error.message);
    });
};

function prevImgUrl(f) {
  var r = new FileReader();
  r.onload = function (ev) {
    window._uploadedImg = ev.target.result;
    var prev = document.getElementById("img-up-prev");
    var img = document.getElementById("img-up-prev-img");
    if (prev && img) {
      img.src = ev.target.result;
      prev.style.display = "flex";
    }
  };
  r.readAsDataURL(f);
}

window.insertImg = function () {
  var src = window._uploadedImgUrl || "";
  if (!src) {
    showToast("Please upload an image first");
    return;
  }
  var rteEl = document.getElementById("rte-" + pendingRte);
  if (!rteEl) {
    closeImg();
    return;
  }
  rteEl.focus();
  var attrs = 'src="' + src + '" alt="image"';
  var baseStyle =
    "max-width:100%;max-height:200px;border-radius:4px;margin:4px 2px;vertical-align:middle";
  attrs += ' style="' + baseStyle + '"';
  document.execCommand("insertHTML", false, "<img " + attrs + ">");
  window._uploadedImgUrl = null;
  closeImg();
  showToast("✓ Image inserted");
};

window.handleImgOvl = function (e) {
  if (e.target.classList.contains("img-overlay")) closeImg();
};

window.closeImg = function () {
  document.getElementById("img-root").innerHTML = "";
};

loadData();
