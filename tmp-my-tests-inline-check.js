  (() => {
    const BADGE_DEFS = [
      ["first_test", "T1", "Mock Test Starter", "Completed the first academy test", "bronze"],
      ["top_25", "R25", "Rank Booster", "Entered the top 25 merit band", "silver"],
      ["top_10", "T10", "JEE Main Sprinter", "Cracked the top 10 in class", "gold"],
      ["top_3", "T3", "NEET Podium Performer", "Reached the top 3 merit list", "gold"],
      ["rank_1", "R1", "AIR Mindset Champion", "Held rank #1 on a test", "platinum"],
      ["climb_5", "UP5", "Comeback Climber", "Climbed 5+ ranks in one test", "silver"],
      ["streak_3", "S3", "Consistency Streak", "Improved across 3 tests in a row", "gold"],
      ["subject_90", "90+", "Subject Mastery Badge", "Scored 90+ in any subject", "gold"],
      ["attend_perfect", "ATT", "Revision Warrior", "Attended every assigned booster session", "silver"],
      ["no_cluster", "CLR", "Concept Clear Badge", "Stayed out of coaching clusters this test", "bronze"],
    ].map(([id, icon, name, desc, tier]) => ({ id, icon, name, desc, tier }));

    const THEME_SEQUENCE = [
      { key: "Physics", from: "#0ea5e9", to: "#06b6d4", accent: "#22d3ee", icon: "P" },
      { key: "Chemistry", from: "#d946ef", to: "#ec4899", accent: "#f472b6", icon: "C" },
      { key: "Biology", from: "#22c55e", to: "#16a34a", accent: "#4ade80", icon: "B" },
      { key: "Maths", from: "#f59e0b", to: "#f97316", accent: "#fb923c", icon: "M" },
    ];

    const MEDALS = {
      1: { icon: "🥇", label: "Gold medal" },
      2: { icon: "🥈", label: "Silver medal" },
      3: { icon: "🥉", label: "Bronze medal" },
    };

    const payload = JSON.parse(document.getElementById("my-tests-payload").textContent || "{}");
    let liveSignature = (document.getElementById("my-tests-live-signature")?.textContent || "").trim();
    const currentStudent = payload.student || {};
    const completedTests = (payload.completedTests || [])
      .map((test) => ({ ...test, kind: "completed" }))
      .sort((left, right) => new Date(left.sortAt) - new Date(right.sortAt));
    const visibleCompleted = completedTests.slice(-2);
    const upcomingSlot = payload.upcomingTest
      ? { ...payload.upcomingTest, kind: "upcoming" }
      : {
          id: "upcoming-placeholder",
          kind: "placeholder",
          name: "Upcoming Test",
          date: "Awaiting schedule",
          shortDate: "Soon",
          launchUrl: "",
          canLaunchNow: false,
        };
    const selectorSlots = [
      visibleCompleted[0] || completedTests[completedTests.length - 1] || null,
      visibleCompleted[1] || visibleCompleted[0] || completedTests[completedTests.length - 1] || null,
      upcomingSlot,
    ];
    const currentStudentId = currentStudent.id || "";
    const studentMap = new Map();

    (completedTests || []).forEach((test) => {
      (test.leaderboard || []).forEach((entry) => {
        studentMap.set(entry.studentId, {
          id: entry.studentId,
          name: entry.studentName || entry.studentId,
          studentRef: entry.studentRef || entry.studentId,
          profilePhotoUrl: entry.profilePhotoUrl || "",
        });
      });
    });

    studentMap.set(currentStudentId, {
      id: currentStudentId,
      name: currentStudent.name || "Student",
      studentRef: currentStudent.username || currentStudentId,
      profilePhotoUrl: currentStudent.profilePhotoUrl || "",
    });

    const rewardsPayload = normalizeRewards(payload.rewards || {});
    const lockedTabs = new Set(["analytics", "rewards"]);

    const state = {
      studentTab: "home",
      studentLeaderboardOpen: false,
      testId:
        (visibleCompleted[1] && visibleCompleted[1].id) ||
        (visibleCompleted[0] && visibleCompleted[0].id) ||
        (completedTests[completedTests.length - 1] && completedTests[completedTests.length - 1].id) ||
        null,
      online: navigator.onLine,
    };

    function isLockedTab(tab) {
      return lockedTabs.has(tab);
    }

    const refs = {
      tabButtons: [...document.querySelectorAll("#studentTabs [data-tab]")],
      testButtons: [...document.querySelectorAll("#testSelector [data-slot-index]")],
      homeSection: document.getElementById("homeSection"),
      analyticsSection: document.getElementById("analyticsSection"),
      rewardsSection: document.getElementById("rewardsSection"),
      rankTierBadge: document.getElementById("rankTierBadge"),
      testStreakBadge: document.getElementById("testStreakBadge"),
      rankShiftBadge: document.getElementById("rankShiftBadge"),
      rankValue: document.getElementById("rankValue"),
      rankSummary: document.getElementById("rankSummary"),
      resultTestTitle: document.getElementById("resultTestTitle"),
      resultTestDateTime: document.getElementById("resultTestDateTime"),
      homeKpiRow: document.getElementById("homeKpiRow"),
      homeActionRow: document.getElementById("homeActionRow"),
      topPerformers: document.getElementById("topPerformers"),
      leaderboardCountBadge: document.getElementById("leaderboardCountBadge"),
      leaderboardBody: document.getElementById("leaderboardBody"),
      leaderboardHeadRow: document.getElementById("leaderboardHeadRow"),
      leaderboardFooterText: document.getElementById("leaderboardFooterText"),
      leaderboardToggleBtn: document.getElementById("leaderboardToggleBtn"),
      rankJourneyRow: document.getElementById("rankJourneyRow"),
      analyticsBreakdownTitle: document.getElementById("analyticsBreakdownTitle"),
      topicAnalyticsContainer: document.getElementById("topicAnalyticsContainer"),
      rewardLevelTitle: document.getElementById("rewardLevelTitle"),
      rewardXpText: document.getElementById("rewardXpText"),
      rewardStreakBadge: document.getElementById("rewardStreakBadge"),
      rewardProgressBar: document.getElementById("rewardProgressBar"),
      rewardsGrid: document.getElementById("rewardsGrid"),
    };

    const clientBootstrapMs = Date.now();
    const serverBootstrapNow = parseIsoDate(payload.serverNow);

    function normalizeRewards(rawRewards) {
      const rewardMap = new Map(BADGE_DEFS.map((badge) => [badge.id, { ...badge, earned: false }]));
      (rawRewards.badges || []).forEach((badge) => {
        const base = rewardMap.get(badge.id) || {};
        rewardMap.set(badge.id, { ...base, ...badge });
      });
      return {
        xp: Number(rawRewards.xp || 0),
        level: Number(rawRewards.level || 1),
        progress: Number(rawRewards.progress || 0),
        streak: Number(rawRewards.streak || 0),
        badges: [...rewardMap.values()],
      };
    }

    function parseIsoDate(value) {
      if (!value) return null;
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? null : date;
    }

    function getServerSynchronizedNow() {
      if (!serverBootstrapNow) {
        return new Date();
      }
      return new Date(serverBootstrapNow.getTime() + (Date.now() - clientBootstrapMs));
    }

    function currentTest() {
      return completedTests.find((test) => test.id === state.testId) || null;
    }

    function currentLeaderboard() {
      return currentTest()?.leaderboard || [];
    }

    function currentStudentEntry(test = currentTest()) {
      const leaderboard = test?.leaderboard || [];
      return leaderboard.find((entry) => entry.studentId === currentStudentId || entry.isCurrentStudent) || null;
    }

    function sectionIdentity(section, index = 0) {
      const normalized = normalizeSectionKey(section?.name || section?.sectionName || "");
      if (normalized) {
        return normalized;
      }

      const rawName = String(section?.name || section?.sectionName || "").trim().toLowerCase();
      return rawName || `section-${index + 1}`;
    }

    function normalizeSectionBreakdownItems(rawSections) {
      if (!Array.isArray(rawSections) || !rawSections.length) {
        return [];
      }

      return rawSections.map((section, index) => {
        const sectionName = String(section?.name || section?.sectionName || `Section ${index + 1}`).trim();
        const score = Number(section?.score || 0);
        const total = Number(section?.total || 0);
        const parsedPercentage = Number(section?.percentage);
        const percentage = Number.isFinite(parsedPercentage)
          ? parsedPercentage
          : (total > 0 ? Math.round((score / total) * 1000) / 10 : 0);

        return {
          ...section,
          name: sectionName || `Section ${index + 1}`,
          sectionName: sectionName || `Section ${index + 1}`,
          shortLabel:
            section?.shortLabel ||
            sectionDisplayLabel(
              { name: sectionName || `Section ${index + 1}` },
              index,
            ),
          score,
          total,
          percentage,
        };
      });
    }

    function currentStudentSectionBreakdown(test) {
      const currentEntry = currentStudentEntry(test);
      const configuredSections = normalizeSectionBreakdownItems(
        test?.studentSectionBreakdown || test?.sectionBreakdown,
      );
      const currentEntrySections = normalizeSectionBreakdownItems(currentEntry?.sectionScores);
      const leaderboardSections = normalizeSectionBreakdownItems(
        (test?.leaderboard || []).find(
          (entry) => Array.isArray(entry.sectionScores) && entry.sectionScores.length,
        )?.sectionScores,
      );
      const legacyEntrySections = normalizeSectionBreakdownItems(
        sectionHeaderItems(test).map((section, index) => {
          const sectionName = String(section?.name || section?.sectionName || `Section ${index + 1}`).trim();
          const normalizedKey = normalizeSectionKey(sectionName);
          const legacyScoreCandidates = [
            currentEntry?.[sectionName],
            normalizedKey ? currentEntry?.[normalizedKey] : undefined,
            currentEntry?.[section?.sectionName],
          ];
          const legacyScore = legacyScoreCandidates.find(
            (value) => value !== undefined && value !== null && value !== "",
          );

          return {
            name: sectionName,
            sectionName: sectionName,
            shortLabel:
              section?.shortLabel ||
              sectionDisplayLabel({ name: sectionName }, index),
            score: Number(legacyScore || 0),
            total: Number(section?.total || 0),
          };
        }),
      );

      const seedSections = configuredSections.length
        ? configuredSections
        : currentEntrySections.length
          ? currentEntrySections
          : leaderboardSections.length
            ? leaderboardSections
            : legacyEntrySections;

      if (!seedSections.length) {
        return [];
      }

      const currentEntrySectionsByKey = new Map(
        currentEntrySections.map((section, index) => [sectionIdentity(section, index), section]),
      );
      const legacyEntrySectionsByKey = new Map(
        legacyEntrySections.map((section, index) => [sectionIdentity(section, index), section]),
      );

      return seedSections.map((section, index) => {
        const sectionKey = sectionIdentity(section, index);
        const currentSection = currentEntrySectionsByKey.get(sectionKey);
        const legacySection = legacyEntrySectionsByKey.get(sectionKey);
        const resolvedSection = currentSection || legacySection || section;
        const sectionName = String(
          resolvedSection?.name ||
          resolvedSection?.sectionName ||
          section?.name ||
          section?.sectionName ||
          `Section ${index + 1}`,
        ).trim();
        const score = Number(resolvedSection?.score || 0);
        const total = Number(resolvedSection?.total || section?.total || 0);
        const parsedPercentage = Number(resolvedSection?.percentage);
        const percentage = Number.isFinite(parsedPercentage)
          ? parsedPercentage
          : (total > 0 ? Math.round((score / total) * 1000) / 10 : 0);

        return {
          ...section,
          ...resolvedSection,
          name: sectionName || `Section ${index + 1}`,
          sectionName: sectionName || `Section ${index + 1}`,
          shortLabel:
            resolvedSection?.shortLabel ||
            section?.shortLabel ||
            sectionDisplayLabel(
              { name: sectionName || `Section ${index + 1}` },
              index,
            ),
          score,
          total,
          percentage,
        };
      });
    }

    function clearNode(node) {
      while (node.firstChild) {
        node.removeChild(node.firstChild);
      }
    }

    function cloneTemplate(id) {
      return document.getElementById(id).content.firstElementChild.cloneNode(true);
    }

    function createAvatar(name, size = 38, photoUrl = "") {
      if (photoUrl) {
        const img = document.createElement("img");
        img.src = photoUrl;
        img.alt = name;
        img.className = "rounded-circle flex-shrink-0";
        img.style.width = `${size}px`;
        img.style.height = `${size}px`;
        img.style.objectFit = "cover";
        img.addEventListener("error", () => {
          if (img.parentNode) {
            img.replaceWith(createAvatar(name, size, ""));
          }
        });
        return img;
      }

      const span = document.createElement("span");
      const initials = String(name || "S")
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();
      span.className = "d-inline-flex align-items-center justify-content-center rounded-circle text-white fw-bold brand-gradient flex-shrink-0";
      span.style.width = `${size}px`;
      span.style.height = `${size}px`;
      span.style.fontSize = `${Math.max(10, size * 0.32)}px`;
      span.textContent = initials || "S";
      return span;
    }

    function createBadge(text, className) {
      const span = document.createElement("span");
      span.className = `badge rounded-pill ${className}`;
      span.textContent = text;
      return span;
    }

    function createRankMedal(rank) {
      const medal = MEDALS[rank];
      if (!medal) return null;
      const span = document.createElement("span");
      span.className = "rank-medal";
      span.setAttribute("role", "img");
      span.setAttribute("aria-label", medal.label);
      span.title = medal.label;
      span.textContent = medal.icon;
      return span;
    }

    function setProgressBar(bar, value, background) {
      bar.style.width = `${Math.max(0, Math.min(100, Number(value || 0)))}%`;
      bar.style.background = background;
    }

    function normalizeSectionKey(name) {
      const value = String(name || "").toLowerCase();
      if (value.includes("physics") || value === "phy") return "Physics";
      if (value.includes("chemistry") || value === "chem") return "Chemistry";
      if (value.includes("biology") || value === "bio" || value.includes("botany") || value.includes("zoology")) return "Biology";
      if (value.includes("math")) return "Maths";
      return "";
    }

    function getThemeForSection(name, index = 0) {
      const normalized = normalizeSectionKey(name);
      if (normalized) {
        return THEME_SEQUENCE.find((item) => item.key === normalized) || THEME_SEQUENCE[0];
      }
      return THEME_SEQUENCE[index % THEME_SEQUENCE.length];
    }

    function createSubjectIcon(name, index = 0) {
      const theme = getThemeForSection(name, index);
      const span = document.createElement("span");
      span.className = "d-inline-flex align-items-center justify-content-center rounded-3 text-white fw-bold flex-shrink-0";
      span.style.width = "36px";
      span.style.height = "36px";
      span.style.background = `linear-gradient(135deg, ${theme.from}, ${theme.to})`;
      span.textContent = theme.icon || String(name || "S").slice(0, 1).toUpperCase();
      return span;
    }

    function getUpcomingSlotRuntimeState(slot) {
      if (!slot || slot.kind !== "upcoming") {
        return slot;
      }

      const startAt = parseIsoDate(slot.scheduledStartAt);
      const endAt = parseIsoDate(slot.scheduledEndAt);
      const launchWindowOpensAt =
        parseIsoDate(slot.launchWindowOpensAt) ||
        (startAt ? new Date(startAt.getTime() - 10 * 60 * 1000) : null);

      if (!startAt || !endAt) {
        return {
          ...slot,
          canLaunchNow: false,
          isLive: false,
          hasEnded: false,
        };
      }

      const now = getServerSynchronizedNow();
      return {
        ...slot,
        canLaunchNow: !!launchWindowOpensAt && now >= launchWindowOpensAt && now < endAt,
        isLive: now >= startAt && now < endAt,
        hasEnded: now >= endAt,
      };
    }

    function sectionHeaderItems(test) {
      const configuredSections = test?.sectionBreakdown || [];
      if (configuredSections.length) {
        return configuredSections;
      }

      const leaderboardSections = (test?.leaderboard || []).find(
        (entry) => Array.isArray(entry.sectionScores) && entry.sectionScores.length,
      )?.sectionScores || [];

      return leaderboardSections.map((section, index) => ({
        name: section.name || section.sectionName || `Section ${index + 1}`,
        shortLabel:
          section.shortLabel ||
          sectionDisplayLabel(
            { name: section.name || section.sectionName || `Section ${index + 1}` },
            index,
          ),
      }));
    }

    function leaderboardRowTotal(row) {
      if (row?.score !== undefined && row?.score !== null && row?.score !== "") {
        return Number(row.score) || 0;
      }
      if (row?.total !== undefined && row?.total !== null && row?.total !== "") {
        return Number(row.total) || 0;
      }
      return (row?.sectionScores || []).reduce((sum, section) => sum + (Number(section?.score) || 0), 0);
    }

    function leaderboardRowTotalMarks(row, test) {
      if (row?.totalMarks !== undefined && row?.totalMarks !== null && row?.totalMarks !== "") {
        return Number(row.totalMarks) || 0;
      }
      if (test?.totalMarks !== undefined && test?.totalMarks !== null && test?.totalMarks !== "") {
        return Number(test.totalMarks) || 0;
      }
      return (row?.sectionScores || []).reduce((sum, section) => sum + (Number(section?.total) || 0), 0);
    }

    function leaderboardSectionCellData(row, section, index = 0) {
      const normalizedRowSections = normalizeSectionBreakdownItems(row?.sectionScores);
      const targetKey = sectionIdentity(section, index);
      const fallbackName = String(section?.name || section?.sectionName || `Section ${index + 1}`).trim();

      const matchedSection = normalizedRowSections.find(
        (item, itemIndex) => sectionIdentity(item, itemIndex) === targetKey,
      );
      if (matchedSection) {
        return matchedSection;
      }

      const indexedSection = normalizedRowSections[index];
      if (indexedSection) {
        return indexedSection;
      }

      const normalizedKey = normalizeSectionKey(fallbackName);
      const legacyScoreCandidates = [
        row?.[fallbackName],
        row?.[section?.sectionName],
        normalizedKey ? row?.[normalizedKey] : undefined,
      ];
      const legacyScore = legacyScoreCandidates.find(
        (value) => value !== undefined && value !== null && value !== "",
      );

      if (legacyScore !== undefined) {
        return {
          name: fallbackName || `Section ${index + 1}`,
          sectionName: fallbackName || `Section ${index + 1}`,
          shortLabel:
            section?.shortLabel ||
            sectionDisplayLabel({ name: fallbackName || `Section ${index + 1}` }, index),
          score: Number(legacyScore || 0),
          total: Number(section?.total || 0),
        };
      }

      return null;
    }

    function sectionDisplayLabel(section, index = 0) {
      if (section?.shortLabel) {
        return section.shortLabel;
      }

      const rawName = String(section?.name || `SEC ${index + 1}`).trim();
      if (!rawName) {
        return `SEC ${index + 1}`;
      }

      const compactName = rawName.replace(/\s+/g, " ");
      if (compactName.length <= 8) {
        return compactName.toUpperCase();
      }

      const parts = compactName.split(" ").filter(Boolean);
      if (parts.length === 1) {
        return compactName.slice(0, 8).toUpperCase();
      }

      return parts
        .slice(0, 3)
        .map((part) => part[0])
        .join("")
        .toUpperCase();
    }

    function renderTestSlotSections(layout, slot) {
      const sections = sectionHeaderItems(slot);
      if (!sections.length) {
        return;
      }

      const sectionRow = document.createElement("span");
      sectionRow.className = "test-slot-sections";

      sections.forEach((section, index) => {
        const chip = document.createElement("span");
        chip.className = "test-slot-section-chip";
        chip.textContent = sectionDisplayLabel(section, index);
        chip.title = section.name || `Section ${index + 1}`;
        sectionRow.appendChild(chip);
      });

      layout.appendChild(sectionRow);
    }

    function renderLeaderboardHeaders(test) {
      if (!refs.leaderboardHeadRow) {
        return test;
      }

      clearNode(refs.leaderboardHeadRow);
      const headers = [
        { label: "#", className: "" },
        { label: "Student", className: "" },
        ...sectionHeaderItems(test).map((section, index) => ({
          label: sectionDisplayLabel(section, index),
          title: section.name || section.sectionName || `Section ${index + 1}`,
          className: "leaderboard-section-head",
        })),
        { label: "TOTAL SCORE", className: "text-end leaderboard-total-head" },
        { label: "BATCH RANK", className: "leaderboard-section-head" },
        { label: "INSTITUTE RANK", className: "leaderboard-section-head" },
      ];

      headers.forEach((header) => {
        const th = document.createElement("th");
        th.textContent = header.label;
        if (header.className) {
          th.className = header.className;
        }
        if (header.title) {
          th.title = header.title;
        }
        refs.leaderboardHeadRow.appendChild(th);
      });
      return test;
    }

    function leaderboardRows(rows, highlightId, collapsed) {
      if (!collapsed) return rows;
      const topFive = rows.slice(0, 5);
      const mine = rows.find(
        (row) => String(row.studentId || "") === String(highlightId || "") || row.isCurrentStudent,
      );
      return mine && !topFive.some(
        (row) => String(row.studentId || "") === String(highlightId || "") || row.isCurrentStudent,
      )
        ? [...topFive, mine]
        : topFive;
    }

    function renderKpiCards(items) {
      clearNode(refs.homeKpiRow);
      items.forEach((item) => {
        const node = cloneTemplate("kpiTemplate");
        node.querySelector(".summary-card-title").textContent = item.label;
        node.querySelector(".summary-card-value").textContent = item.value;
        node.querySelector(".summary-card-extra").textContent = item.extra || "";
        refs.homeKpiRow.appendChild(node);
      });
    }

    function renderHomeActions(test) {
      clearNode(refs.homeActionRow);
      return test;
    }

    function applyTestSlotButtonState(button, slot, slotIndex) {
      button.classList.remove("btn-brand", "btn-outline-light", "test-slot-selected", "test-slot-upcoming");
      button.disabled = false;
      button.title = "";
      button.replaceChildren();

      if (!slot) {
        button.textContent = "Unavailable";
        button.disabled = true;
        button.classList.add("btn-outline-light");
        return;
      }

      const slotLabel = slotIndex === 0 ? "Previous" : slotIndex === 1 ? "Recent" : "Upcoming";

      if (slot.kind === "completed") {
        const layout = document.createElement("span");
        layout.className = "test-slot-layout";
        const titleRow = document.createElement("span");
        titleRow.className = "test-slot-title-row";
        const nameSpan = document.createElement("span");
        nameSpan.className = "test-slot-name";
        nameSpan.textContent = slot.name;
        titleRow.appendChild(nameSpan);
        titleRow.appendChild(createBadge(slotLabel, "text-bg-dark test-slot-badge"));
        const meta = document.createElement("span");
        meta.className = "test-slot-meta";
        const subjectLabel = slot.subject ? `${slot.subject} • ` : "";
        const attemptedCountLabel =
          Number(slot.attemptedCount || slot.totalStudents || 0) > 0
            ? ` • ${slot.attemptedCount || slot.totalStudents} attempted`
            : "";
        meta.textContent = `${slot.date} • ${subjectLabel}${slot.attempted ? "Completed" : "Not Attempted"}${attemptedCountLabel}`;
        layout.appendChild(titleRow);
        layout.appendChild(meta);
        renderTestSlotSections(layout, slot);
        button.appendChild(layout);
        button.classList.add("btn-outline-light");
        if (slot.id === state.testId) {
          button.classList.add("test-slot-selected");
        }
        return;
      }

      if (slot.kind === "placeholder") {
        const layout = document.createElement("span");
        layout.className = "test-slot-layout";
        const titleRow = document.createElement("span");
        titleRow.className = "test-slot-title-row";
        const nameSpan = document.createElement("span");
        nameSpan.className = "test-slot-name";
        nameSpan.textContent = slot.name;
        titleRow.appendChild(nameSpan);
        const meta = document.createElement("span");
        meta.className = "test-slot-meta";
        meta.textContent = slot.date;
        layout.appendChild(titleRow);
        layout.appendChild(meta);
        button.appendChild(layout);
        button.disabled = true;
        button.title = "No upcoming test has been scheduled yet.";
        button.classList.add("btn-outline-light", "test-slot-upcoming");
        return;
      }

      const runtimeSlot = getUpcomingSlotRuntimeState(slot);
      const layout = document.createElement("span");
      layout.className = "test-slot-layout";

      const titleRow = document.createElement("span");
      titleRow.className = "test-slot-title-row";
      const nameSpan = document.createElement("span");
      nameSpan.className = "test-slot-name";
      nameSpan.textContent = runtimeSlot.name;
      titleRow.appendChild(nameSpan);
      titleRow.appendChild(
        createBadge(
          runtimeSlot.isLive ? "Live" : slotLabel,
          runtimeSlot.isLive ? "text-bg-danger test-slot-badge" : "text-bg-warning text-dark test-slot-badge",
        ),
      );

      const meta = document.createElement("span");
      meta.className = "test-slot-meta";
      if (runtimeSlot.hasEnded) {
        meta.textContent = "This test window has closed.";
      } else if (runtimeSlot.canLaunchNow) {
        meta.textContent = `${runtimeSlot.date} • ${runtimeSlot.time || ""} • Opens now`;
      } else {
        meta.textContent = `${runtimeSlot.date} • ${runtimeSlot.time || ""}`;
      }

      layout.appendChild(titleRow);
      layout.appendChild(meta);
      button.appendChild(layout);
      button.classList.add("btn-outline-light", "test-slot-upcoming");

      const launchable = runtimeSlot.canLaunchNow && !!runtimeSlot.launchUrl;
      if (launchable) {
        button.classList.add("test-slot-live", "test-slot-selected");
      }
      button.disabled = !launchable;
      if (!launchable) {
        button.title = runtimeSlot.hasEnded
          ? "This test window has closed."
          : "This test opens 10 minutes before the scheduled start time.";
      }
    }

    function renderHeader() {
      if (isLockedTab(state.studentTab)) {
        state.studentTab = "home";
      }

      refs.tabButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === state.studentTab);
      });

      refs.testButtons.forEach((button) => {
        const slot = selectorSlots[Number(button.dataset.slotIndex)];
        applyTestSlotButtonState(button, slot, Number(button.dataset.slotIndex));
      });

      refs.homeSection.classList.toggle("active", state.studentTab === "home");
      refs.analyticsSection.classList.toggle("active", state.studentTab === "analytics");
      refs.rewardsSection.classList.toggle("active", state.studentTab === "rewards");
    }

    function renderHome() {
      const test = currentTest();
      if (!test) {
        refs.rankTierBadge.className = "badge rounded-pill text-bg-secondary";
        refs.rankTierBadge.textContent = "NO TESTS YET";
        refs.rankValue.textContent = "--";
        refs.rankSummary.textContent = "No completed tests available yet.";
        refs.resultTestTitle.textContent = "";
        refs.resultTestDateTime.textContent = "";
        refs.testStreakBadge.classList.add("d-none");
        refs.rankShiftBadge.classList.add("d-none");
        renderKpiCards([
          { label: "Status", value: "Awaiting", extra: "First completed test" },
          { label: "Window", value: "Soon", extra: "Use the upcoming tab to launch" },
        ]);
        clearNode(refs.homeActionRow);
        clearNode(refs.topPerformers);
        clearNode(refs.leaderboardBody);
        refs.leaderboardCountBadge.textContent = "0 students";
        refs.leaderboardFooterText.textContent = "";
        return;
      }

      const attempted = !!test.attempted;
      const leaderboardEntry = currentStudentEntry();
      const parsedLeaderboardRank = Number.isInteger(leaderboardEntry?.rank)
        ? leaderboardEntry.rank
        : null;
      const rank = attempted
        ? (Number.isInteger(test.rank) ? test.rank : parsedLeaderboardRank)
        : null;
      const rankDelta = attempted ? test.rankDelta : null;
      const scoreValue = Number(test.score || 0);
      const totalMarks = Number(test.totalMarks || 0);
      const previousRank = rank !== null && rankDelta !== null ? rank + rankDelta : null;
      const currentSections = currentStudentSectionBreakdown(test);

      if (attempted) {
        refs.rankTierBadge.className = `badge rounded-pill ${
          Number.isInteger(rank) && rank <= 10
            ? "text-bg-info"
            : Number.isInteger(rank) && rank <= 25
              ? "text-bg-primary"
              : "text-bg-secondary"
        }`;
        refs.rankTierBadge.textContent = Number.isInteger(rank)
          ? (rank <= 10 ? "ELITE" : rank <= 25 ? "RISING STAR" : "BOOST SQUAD")
          : "ATTEMPTED";
        refs.rankValue.textContent = Number.isInteger(rank) ? `#${rank}` : "NA";
      } else {
        refs.rankTierBadge.className = "badge rounded-pill text-bg-secondary";
        refs.rankTierBadge.textContent = "NOT ATTEMPTED";
        refs.rankValue.textContent = "--";
      }

      refs.rankSummary.textContent = `of ${test.totalStudents || currentLeaderboard().length} students`;
      refs.resultTestTitle.textContent = test.name || "--";
      refs.resultTestDateTime.textContent = [test.shortDate || test.date || "--", test.time || ""]
        .filter(Boolean)
        .join(", ");

      if (test.testStreak > 0) {
        refs.testStreakBadge.className = "badge rounded-pill text-bg-warning text-dark";
        refs.testStreakBadge.textContent = `${test.testStreak}-TEST STREAK`;
        refs.testStreakBadge.classList.remove("d-none");
      } else {
        refs.testStreakBadge.classList.add("d-none");
      }

      refs.rankShiftBadge.classList.remove("d-none", "text-bg-success", "text-bg-danger", "text-bg-secondary");
      if (!attempted) {
        refs.rankShiftBadge.classList.add("text-bg-secondary");
        refs.rankShiftBadge.textContent = "NA";
      } else if (rankDelta === null) {
        refs.rankShiftBadge.classList.add("text-bg-secondary");
        refs.rankShiftBadge.textContent = "0";
      } else if (rankDelta > 0) {
        refs.rankShiftBadge.classList.add("text-bg-success");
        refs.rankShiftBadge.textContent = `↑ ${rankDelta}`;
      } else if (rankDelta < 0) {
        refs.rankShiftBadge.classList.add("text-bg-danger");
        refs.rankShiftBadge.textContent = `↓ ${Math.abs(rankDelta)}`;
      } else {
        refs.rankShiftBadge.classList.add("text-bg-secondary");
        refs.rankShiftBadge.textContent = "0";
      }

      const kpiItems = [
        {
          label: "Total",
          value: `${scoreValue}/${totalMarks}`,
          extra: attempted
            ? previousRank === null
              ? "First recorded test"
              : rank < previousRank
                ? `Up ${previousRank - rank} ranks`
                : rank > previousRank
                  ? `Down ${rank - previousRank} ranks`
                  : "No rank change"
            : "Missed this test",
        },
      ];

      currentSections.forEach((section) => {
        const sectionName = String(section.name || section.sectionName || "Section").trim();
        const sectionScore = Number(section.score || 0);
        const sectionTotal = Number(section.total || 0);
        const sectionPercentage = Number.isFinite(Number(section.percentage))
          ? Number(section.percentage)
          : 0;

        kpiItems.push({
          label: sectionName || "Section",
          value: `${sectionScore}/${sectionTotal}`,
          extra: attempted ? `${sectionPercentage}% scored` : "Section score",
        });
      });

      renderKpiCards(kpiItems);
      renderHomeActions(test);

      renderTopPerformers(test);
      renderLeaderboard(test);
    }
    function renderTopPerformers(test) {
      clearNode(refs.topPerformers);
      const entries = (test?.topPerformers && test.topPerformers.length)
        ? test.topPerformers
        : currentLeaderboard().slice(0, 5);

      if (!entries.length) {
        const empty = document.createElement("div");
        empty.className = "card app-card p-3 text-center soft";
        empty.textContent = "Top performers will appear once this test has attempts.";
        refs.topPerformers.appendChild(empty);
        return;
      }

      entries.forEach((entry) => {
        const student = studentMap.get(entry.studentId) || {};
        const node = cloneTemplate("topPerformerTemplate");
        const medal = createRankMedal(entry.rank);
        node.querySelector(".top-performer-rank").textContent = `#${entry.rank}`;
        if (medal) {
          node.querySelector(".top-performer-rank").appendChild(medal);
        }
        node.querySelector(".top-performer-avatar").appendChild(
          createAvatar(
            entry.studentName || student.name || entry.studentId,
            112,
            entry.profilePhotoUrl || student.profilePhotoUrl || "",
          ),
        );
        node.querySelector(".top-performer-name").textContent = entry.studentName || student.name || entry.studentId;
        node.querySelector(".top-performer-meta").textContent =
          `Score ${leaderboardRowTotal(entry)}/${leaderboardRowTotalMarks(entry, test)}`;
        refs.topPerformers.appendChild(node);
      });
    }

    function renderLeaderboard(test) {
      const ranked = currentLeaderboard();
      refs.leaderboardCountBadge.textContent = `${ranked.length} students`;
      clearNode(refs.leaderboardBody);
      renderLeaderboardHeaders(test);

      function setSubjectScoreCell(cell, value) {
        if (!cell) return;
        const hasScore = value !== null && value !== undefined;
        cell.classList.toggle("score-na", !hasScore);
        cell.textContent = hasScore ? value : "-";
      }

      const rows = leaderboardRows(ranked, currentStudentId, !state.studentLeaderboardOpen);
      const subjectDefs = sectionHeaderItems(test);
      rows.forEach((row) => {
        const student = studentMap.get(row.studentId) || {};
        const node = document.createElement("tr");
        const mine =
          String(row.studentId || "") === String(currentStudentId || "") || !!row.isCurrentStudent;
        const medal = createRankMedal(row.rank);

        if (mine) {
          node.classList.add("student-highlight");
        }

        const rankCell = document.createElement("td");
        rankCell.className = "mono leaderboard-rank";
        const rankText = document.createElement("span");
        rankText.className = "leaderboard-rank-text";
        rankText.textContent = Number.isInteger(Number(row.rank)) ? `#${row.rank}` : "NA";
        rankCell.appendChild(rankText);
        if (medal) {
          const medalWrap = document.createElement("span");
          medalWrap.className = "leaderboard-rank-medal";
          medalWrap.appendChild(medal);
          rankCell.appendChild(medalWrap);
        }
        node.appendChild(rankCell);

        const studentCell = document.createElement("td");
        studentCell.className = "leaderboard-student";
        const studentWrap = document.createElement("div");
        studentWrap.className = "leaderboard-student-wrap";
        const avatarWrap = document.createElement("div");
        avatarWrap.className = "leaderboard-avatar";
        avatarWrap.appendChild(
          createAvatar(
            row.studentName || student.name || row.studentId,
            28,
            row.profilePhotoUrl || student.profilePhotoUrl || "",
          ),
        );
        studentWrap.appendChild(avatarWrap);

        const textWrap = document.createElement("div");
        const nameRow = document.createElement("div");
        const nameNode = document.createElement("span");
        nameNode.className = "leaderboard-name";
        nameNode.textContent = row.studentName || student.name || row.studentId;
        nameRow.appendChild(nameNode);
        if (mine) {
          nameNode.classList.add("is-current");
          const badgeWrap = document.createElement("span");
          badgeWrap.className = "leaderboard-you";
          badgeWrap.appendChild(createBadge("You", "text-bg-info"));
          nameRow.appendChild(document.createTextNode(" "));
          nameRow.appendChild(badgeWrap);
        }
        textWrap.appendChild(nameRow);

        const idNode = document.createElement("div");
        idNode.className = "small mono leaderboard-id";
        idNode.textContent = row.studentRef || student.studentRef || row.studentId;
        textWrap.appendChild(idNode);

        studentWrap.appendChild(textWrap);
        studentCell.appendChild(studentWrap);
        node.appendChild(studentCell);

        subjectDefs.forEach((section, index) => {
          const scoreCell = document.createElement("td");
          scoreCell.className = "leaderboard-section-score mono";
          const sectionData = leaderboardSectionCellData(row, section, index);
          setSubjectScoreCell(scoreCell, sectionData?.score);
          node.appendChild(scoreCell);
        });

        const totalCell = document.createElement("td");
        totalCell.className = "leaderboard-total-cell";
        const totalNode = document.createElement("b");
        totalNode.className = "leaderboard-total mono";
        totalNode.textContent = `${leaderboardRowTotal(row)}`;
        totalCell.appendChild(totalNode);
        node.appendChild(totalCell);

        const batchRankCell = document.createElement("td");
        batchRankCell.className = "leaderboard-section-score mono";
        batchRankCell.textContent = Number.isInteger(row.batchRank) ? `#${row.batchRank}` : "NA";
        node.appendChild(batchRankCell);

        const instituteRankCell = document.createElement("td");
        instituteRankCell.className = "leaderboard-section-score mono";
        instituteRankCell.textContent = Number.isInteger(row.instituteRank) ? `#${row.instituteRank}` : "NA";
        node.appendChild(instituteRankCell);
        refs.leaderboardBody.appendChild(node);
      });

      refs.leaderboardFooterText.textContent = state.studentLeaderboardOpen
        ? `Showing all ${ranked.length} students`
        : `Showing top 5${rows.length > 5 ? " + your rank" : ""}`;
      refs.leaderboardToggleBtn.textContent = state.studentLeaderboardOpen ? "Show Less" : "View All";
      refs.leaderboardToggleBtn.disabled = ranked.length <= 5;
    }

    function renderRankJourney() {
      clearNode(refs.rankJourneyRow);
      completedTests.forEach((test, index) => {
        const wrapper = document.createElement("div");
        wrapper.className = "col-6 col-lg-3";
        const node = cloneTemplate("kpiTemplate");
        node.querySelector(".summary-card-title").textContent = test.shortDate || test.date || `Test ${index + 1}`;
        node.querySelector(".summary-card-value").textContent =
          test.rank === null || test.rank === undefined ? "#-" : `#${test.rank}`;
        node.querySelector(".summary-card-extra").textContent =
          index === 0 || test.rankDelta === null || test.rankDelta === undefined
            ? "Baseline"
            : `${test.rankDelta >= 0 ? "Up" : "Down"} ${Math.abs(test.rankDelta)}`;
        wrapper.appendChild(node);
        refs.rankJourneyRow.appendChild(wrapper);
      });
    }

    function renderAnalytics() {
      const test = currentTest();
      renderRankJourney();
      clearNode(refs.topicAnalyticsContainer);

      const sections = test?.sectionBreakdown || [];
      refs.analyticsBreakdownTitle.textContent = sections.length <= 1 ? "Topic Analytics" : "Section Analytics";

      sections.forEach((section, index) => {
        const theme = getThemeForSection(section.name, index);
        const node = cloneTemplate("topicCardTemplate");
        const rowsContainer = node.querySelector(".topic-rows");
        node.querySelector(".topic-subject-icon").appendChild(createSubjectIcon(section.shortLabel || section.name, index));
        node.querySelector(".topic-subject-name").textContent = section.name;
        node.querySelector(".topic-subject-name").style.color = theme.accent;
        node.querySelector(".topic-subject-score").textContent = `${section.score}/${section.total}`;

        completedTests.forEach((item) => {
          const sectionItem = (item.sectionBreakdown || []).find((entry) => entry.name === section.name);
          if (!sectionItem) {
            return;
          }
          const row = cloneTemplate("topicRowTemplate");
          row.querySelector(".topic-name").textContent = `${item.shortDate || item.date} - ${item.name}`;
          row.querySelector(".topic-score").textContent = `${sectionItem.score}/${sectionItem.total}`;
          setProgressBar(
            row.querySelector(".topic-progress-fill"),
            sectionItem.percentage,
            `linear-gradient(135deg, ${theme.from}, ${theme.to})`,
          );
          rowsContainer.appendChild(row);
        });

        refs.topicAnalyticsContainer.appendChild(node);
      });
    }

    function renderRewards() {
      refs.rewardLevelTitle.textContent = `Level ${rewardsPayload.level}`;
      refs.rewardXpText.textContent = `${rewardsPayload.xp} XP earned`;
      refs.rewardStreakBadge.textContent = `${rewardsPayload.streak} TEST STREAK`;
      setProgressBar(
        refs.rewardProgressBar,
        Math.round((rewardsPayload.progress || 0) * 100),
        "linear-gradient(135deg, #ff8a00, #e52e71 52%, #7c3aed)",
      );

      clearNode(refs.rewardsGrid);
      rewardsPayload.badges.forEach((badgeItem) => {
        const node = cloneTemplate("rewardCardTemplate");
        const shell = node.querySelector(".reward-card-shell");
        node.querySelector(".reward-icon-text").textContent = badgeItem.icon || badgeItem.name?.slice(0, 2) || "RG";
        node.querySelector(".reward-name").textContent = badgeItem.name;
        node.querySelector(".reward-desc").textContent = badgeItem.desc;
        node.querySelector(".reward-meta").textContent = `${badgeItem.earned ? "earned" : "locked"} - ${badgeItem.tier}`;
        if (!badgeItem.earned) {
          shell.classList.add("opacity-50");
        }
        refs.rewardsGrid.appendChild(node);
      });
    }

    function render() {
      renderHeader();
      renderHome();
      renderAnalytics();
      renderRewards();
    }

    refs.tabButtons.forEach((button) => {
      button.addEventListener("click", () => {
        if (isLockedTab(button.dataset.tab)) {
          state.studentTab = "home";
          renderHeader();
          return;
        }
        state.studentTab = button.dataset.tab;
        renderHeader();
      });
    });

    refs.testButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const slot = selectorSlots[Number(button.dataset.slotIndex)];
        if (!slot) return;

        if (slot.kind === "completed") {
          state.testId = slot.id;
          state.studentLeaderboardOpen = false;
          render();
          return;
        }

        const runtimeSlot = getUpcomingSlotRuntimeState(slot);
        if (runtimeSlot.kind === "upcoming" && runtimeSlot.canLaunchNow && runtimeSlot.launchUrl) {
          window.location.href = runtimeSlot.launchUrl;
        }
      });
    });

    refs.leaderboardToggleBtn.addEventListener("click", () => {
      state.studentLeaderboardOpen = !state.studentLeaderboardOpen;
      renderLeaderboard(currentTest());
    });

    window.addEventListener("online", () => {
      state.online = true;
      renderHeader();
    });

    window.addEventListener("offline", () => {
      state.online = false;
      renderHeader();
    });

    document.addEventListener("keydown", (event) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
      if (["1", "2", "3"].includes(event.key)) {
        const nextTab = ["home", "analytics", "rewards"][Number(event.key) - 1];
        state.studentTab = isLockedTab(nextTab) ? "home" : nextTab;
        renderHeader();
      }
    });

    setInterval(() => {
      renderHeader();
    }, 5000);

    async function pollRealtimeLeaderboardState() {
      if (!state.online) return;
      try {
        const qs = new URLSearchParams({ since: liveSignature || "" });
        const response = await fetch(`/my-tests/live-state/?${qs.toString()}`, {
          method: "GET",
          cache: "no-store",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!response.ok) return;
        const data = await response.json();
        if (!data?.success || !data?.signature) return;
        if (liveSignature && data.signature !== liveSignature) {
          window.location.reload();
          return;
        }
        liveSignature = data.signature;
      } catch (_error) {
      }
    }

    setInterval(pollRealtimeLeaderboardState, 3000);

    render();
  })();
