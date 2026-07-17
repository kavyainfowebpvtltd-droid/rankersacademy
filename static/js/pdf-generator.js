/**
 * PDF Report Generator for The Rankers Academy
 * Uses jsPDF + jspdf-autotable for professional PDF generation
 */

(function () {
  "use strict";

  // Color constants
  const COLORS = {
    primary: "#1E3A8A",
    primaryLight: "#1E40AF",
    white: "#FFFFFF",
    lightBg: "#F5F7FA",
    border: "#E5E7EB",
    textDark: "#1F2937",
    textLight: "#6B7280",
    headerBg: "#1E3A8A",
    rowAlt: "#F9FAFB",
  };

  // Academy information
  const ACADEMY_INFO = {
    name: "THE RANKERS ACADEMY",
    subtitle: "Student Self-Diagnostic Test Report",
    address: "123 Knowledge Road, Education City, Nagpur, India – 440001",
    email: "info@rankersacademy.com",
    phone: "+91 99999 88888",
    website: "www.rankersacademy.com",
  };

  /**
   * Generate the PDF report
   * @param {Object} studentData - Student information
   * @param {Object} performanceData - Performance summary
   * @param {Array} subjectData - Subject-wise report data
   * @param {string} logoUrl - URL to the academy logo
   */
  window.generateProfessionalPDF = function (
    studentData,
    performanceData,
    subjectData,
    logoUrl,
  ) {
    // Check if jsPDF is loaded
    if (typeof window.jspdf === "undefined") {
      console.error("jsPDF not loaded");
      alert("PDF library not loaded. Please refresh the page and try again.");
      return;
    }

    // Create new jsPDF document (A4 portrait)
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({
      orientation: "portrait",
      unit: "mm",
      format: "a4",
    });

    const pageWidth = 210; // A4 width in mm
    const pageHeight = 297; // A4 height in mm
    const margin = 15;
    const contentWidth = pageWidth - margin * 2;
    let currentY = margin;

    // Helper function to add a new page if needed
    function checkNewPage(height) {
      if (currentY + height > pageHeight - margin) {
        doc.addPage();
        currentY = margin;
        return true;
      }
      return false;
    }

    // Helper function to draw a horizontal line
    function drawLine(y, color = COLORS.border) {
      doc.setDrawColor(color);
      doc.setLineWidth(0.3);
      doc.line(margin, y, pageWidth - margin, y);
    }

    // ============================================
    // HEADER SECTION
    // ============================================

    // Blue header background
    doc.setFillColor(COLORS.primary);
    doc.rect(0, 0, pageWidth, 35, "F");

    // Add logo (if available)
    if (logoUrl) {
      try {
        doc.addImage(logoUrl, "PNG", margin + 5, 5, 20, 20);
      } catch (e) {
        console.warn("Logo not loaded, using text only");
      }
    }

    // Academy name centered
    doc.setTextColor(COLORS.white);
    doc.setFontSize(18);
    doc.setFont("helvetica", "bold");
    doc.text(ACADEMY_INFO.name, pageWidth / 2, 15, { align: "center" });

    // Subtitle
    doc.setFontSize(11);
    doc.setFont("helvetica", "normal");
    doc.text(ACADEMY_INFO.subtitle, pageWidth / 2, 22, { align: "center" });

    // Divider line below header
    currentY = 38;
    drawLine(currentY, COLORS.white);
    currentY += 5;

    // ============================================
    // STUDENT INFORMATION CARD
    // ============================================

    // Card background
    doc.setFillColor(COLORS.lightBg);
    doc.setDrawColor(COLORS.border);
    doc.setLineWidth(0.5);
    doc.roundedRect(margin, currentY, contentWidth, 32, 2, 2, "FD");

    // Student info data
    const studentInfo = [
      { label: "Student Name", value: studentData.name || "-" },
      { label: "Username", value: studentData.username || "-" },
      { label: "School", value: studentData.school || "-" },
      { label: "Class", value: studentData.class || "-" },
      { label: "Board", value: studentData.board || "-" },
      { label: "Gender", value: studentData.gender || "-" },
      { label: "Test No", value: studentData.testNo || "-" },
      { label: "Test Date", value: studentData.testDate || "-" },
    ];

    // 2 column layout for student info
    doc.setTextColor(COLORS.textDark);
    doc.setFontSize(9);

    const colWidth = contentWidth / 2;
    const rowHeight = 7;

    studentInfo.forEach((info, index) => {
      const col = index % 2;
      const row = Math.floor(index / 2);
      const x = margin + 5 + col * colWidth;
      const y = currentY + 4 + row * rowHeight;

      // Label
      doc.setFont("helvetica", "normal");
      doc.setTextColor(COLORS.textLight);
      doc.text(info.label + ":", x, y);

      // Value
      doc.setFont("helvetica", "bold");
      doc.setTextColor(COLORS.textDark);
      const labelWidth = doc.getTextWidth(info.label + ": ");
      doc.text(String(info.value), x + labelWidth, y);
    });

    currentY += 36;

    // ============================================
    // PERFORMANCE SUMMARY
    // ============================================

    doc.setTextColor(COLORS.primary);
    doc.setFontSize(11);
    doc.setFont("helvetica", "bold");
    doc.text("Performance Summary", margin, currentY);
    currentY += 6;

    // Score boxes
    const boxWidth = (contentWidth - 10) / 2;

    // Total Score box
    doc.setFillColor(COLORS.lightBg);
    doc.setDrawColor(COLORS.primary);
    doc.setLineWidth(0.5);
    doc.roundedRect(margin, currentY, boxWidth, 15, 2, 2, "FD");

    doc.setTextColor(COLORS.textLight);
    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    doc.text("Total Score", margin + 5, currentY + 5);

    doc.setTextColor(COLORS.primary);
    doc.setFontSize(14);
    doc.setFont("helvetica", "bold");
    doc.text(performanceData.totalScore || "0%", margin + 5, currentY + 12);

    // Previous Score box
    doc.setFillColor(COLORS.lightBg);
    doc.setDrawColor(COLORS.border);
    doc.roundedRect(margin + boxWidth + 10, currentY, boxWidth, 15, 2, 2, "FD");

    doc.setTextColor(COLORS.textLight);
    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    doc.text("Previous Score", margin + boxWidth + 15, currentY + 5);

    doc.setTextColor(COLORS.textDark);
    doc.setFontSize(14);
    doc.setFont("helvetica", "bold");
    doc.text(
      performanceData.previousScore || "0%",
      margin + boxWidth + 15,
      currentY + 12,
    );

    currentY += 20;

    // Horizontal divider
    drawLine(currentY);
    currentY += 5;

    // ============================================
    // SUBJECT WISE REPORT TABLES
    // ============================================

    doc.setTextColor(COLORS.primary);
    doc.setFontSize(11);
    doc.setFont("helvetica", "bold");
    doc.text("Subject Wise Report", margin, currentY);
    currentY += 5;

    // Process each subject
    subjectData.forEach((subject, subjectIndex) => {
      checkNewPage(60);

      // Subject title
      doc.setTextColor(COLORS.primary);
      doc.setFontSize(10);
      doc.setFont("helvetica", "bold");
      doc.text(
        subject.name || "Subject " + (subjectIndex + 1),
        margin,
        currentY,
      );
      currentY += 3;

      // Table data
      const tableBody = subject.chapters.map((chapter, idx) => [
        String(idx + 1).padStart(2, "0"),
        chapter.name,
        String(chapter.total),
        String(chapter.correct),
        String(chapter.unknown),
        chapter.coverage,
      ]);

      // Generate table using autoTable
      doc.autoTable({
        startY: currentY,
        head: [["Sr No", "Chapter", "Total", "Correct", "Unknown", "Coverage"]],
        body: tableBody,
        margin: { left: margin, right: margin },
        headStyles: {
          fillColor: COLORS.primary,
          textColor: COLORS.white,
          fontStyle: "bold",
          fontSize: 8,
          halign: "center",
        },
        bodyStyles: {
          fontSize: 8,
          textColor: COLORS.textDark,
        },
        alternateRowStyles: {
          fillColor: COLORS.rowAlt,
        },
        columnStyles: {
          0: { cellWidth: 12, halign: "center" },
          1: { cellWidth: 65 },
          2: { cellWidth: 18, halign: "center" },
          3: { cellWidth: 20, halign: "center" },
          4: { cellWidth: 22, halign: "center" },
          5: { cellWidth: 22, halign: "center" },
        },
        theme: "grid",
        styles: {
          lineColor: COLORS.border,
          lineWidth: 0.1,
          cellPadding: 2,
        },
      });

      currentY = doc.lastAutoTable.finalY + 5;

      // Weak Topics section
      if (subject.weakTopics && subject.weakTopics.length > 0) {
        checkNewPage(20);

        doc.setTextColor(COLORS.textDark);
        doc.setFontSize(9);
        doc.setFont("helvetica", "bold");
        doc.text("Weak Topics:", margin, currentY);
        currentY += 4;

        doc.setFont("helvetica", "normal");
        doc.setFontSize(8);
        doc.setTextColor(COLORS.textLight);

        const weakTopicsText = subject.weakTopics.slice(0, 5).join(", ");
        doc.text(weakTopicsText, margin, currentY);
        currentY += 8;
      }
    });

    // ============================================
    // FOOTER SECTION
    // ============================================

    checkNewPage(40);

    // Footer background
    currentY = pageHeight - 35;

    // Left side - logo
    if (logoUrl) {
      try {
        doc.addImage(logoUrl, "PNG", margin, currentY, 15, 15);
      } catch (e) {
        console.warn("Footer logo not loaded");
      }
    }

    // Right side - contact info
    doc.setTextColor(COLORS.textDark);
    doc.setFontSize(8);

    const contactX = pageWidth - margin - 60;
    doc.setFont("helvetica", "bold");
    doc.text("Contact Information:", contactX, currentY + 3);

    doc.setFont("helvetica", "normal");
    doc.text(ACADEMY_INFO.address, contactX, currentY + 8);
    doc.text(ACADEMY_INFO.email, contactX, currentY + 13);
    doc.text(ACADEMY_INFO.phone, contactX, currentY + 18);

    // Bottom center text
    currentY = pageHeight - 12;
    drawLine(currentY - 3, COLORS.border);

    doc.setTextColor(COLORS.textLight);
    doc.setFontSize(7);
    doc.setFont("helvetica", "normal");
    doc.text(
      "© 2026 The Rankers Academy | Student Self Diagnostic Report",
      pageWidth / 2,
      currentY + 5,
      { align: "center" },
    );

    // Save the PDF
    const filename = `Student_Diagnostic_Report_${studentData.name || "Student"}_${new Date().toISOString().split("T")[0]}.pdf`;
    doc.save(filename);
  };

  /**
   * Generate PDF from existing page data
   * This function extracts data from the page and generates the PDF
   */
  window.generatePDFFromPage = function () {
    // Gather data from the page
    const studentMetaEl = document.getElementById("student-meta");
    const chartPayloadEl = document.getElementById("chart-payload");

    if (!studentMetaEl) {
      console.error("Student meta not found");
      return;
    }

    const studentMeta = JSON.parse(studentMetaEl.textContent);
    const studentId = studentMeta.student_id;

    // Fetch the report data from API
    fetch(`/dashboard/students/${studentId}/pdf-report/?download=0`)
      .then((response) => response.text())
      .then((html) => {
        // Parse the HTML to extract data
        // For now, we'll use sample data structure
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, "text/html");

        // Extract data from the page
        const studentData = {
          name:
            document.querySelector(".fw-bold")?.textContent?.trim() ||
            "Student",
          username: studentMeta.username || "N/A",
          school: "School Name", // Get from actual data
          class:
            document.querySelector('[class*="grade"]')?.textContent || "10th",
          board: "CBSE",
          gender: "Male",
          testNo: "1",
          testDate: new Date().toLocaleDateString("en-GB"),
        };

        const performanceData = {
          totalScore:
            document.querySelector(".circular-progress .inner-circle")
              ?.textContent || "0%",
          previousScore: "0%",
        };

        // Sample subject data (in real implementation, extract from page)
        const subjectData = [
          {
            name: "MATHS 1",
            chapters: [
              {
                name: "Linear equation in two variables",
                total: 4,
                correct: 2,
                unknown: 2,
                coverage: "50%",
              },
              {
                name: "Quadratic Equations",
                total: 2,
                correct: 2,
                unknown: 0,
                coverage: "100%",
              },
            ],
            weakTopics: [],
          },
          {
            name: "MATHS 2",
            chapters: [
              {
                name: "Similarity",
                total: 2,
                correct: 1,
                unknown: 1,
                coverage: "50%",
              },
              {
                name: "Pythagoras theorem",
                total: 2,
                correct: 1,
                unknown: 1,
                coverage: "50%",
              },
            ],
            weakTopics: ["Similarity", "Pythagoras theorem"],
          },
        ];

        // Get logo URL
        const logoUrl = document.querySelector("nav img")?.src || "";

        // Generate PDF
        window.generateProfessionalPDF(
          studentData,
          performanceData,
          subjectData,
          logoUrl,
        );
      })
      .catch((error) => {
        console.error("Error fetching report data:", error);

        // Fallback: generate with sample data
        const studentData = {
          name: "Student Name",
          username: "username",
          school: "School Name",
          class: "10th",
          board: "CBSE",
          gender: "Male",
          testNo: "1",
          testDate: new Date().toLocaleDateString("en-GB"),
        };

        const performanceData = {
          totalScore: "50%",
          previousScore: "45%",
        };

        const subjectData = [
          {
            name: "MATHS 1",
            chapters: [
              {
                name: "Linear equation in two variables",
                total: 4,
                correct: 2,
                unknown: 2,
                coverage: "50%",
              },
              {
                name: "Quadratic Equations",
                total: 2,
                correct: 2,
                unknown: 0,
                coverage: "100%",
              },
            ],
            weakTopics: ["Linear equation in two variables"],
          },
          {
            name: "MATHS 2",
            chapters: [
              {
                name: "Similarity",
                total: 2,
                correct: 1,
                unknown: 1,
                coverage: "50%",
              },
              {
                name: "Pythagoras theorem",
                total: 2,
                correct: 1,
                unknown: 1,
                coverage: "50%",
              },
            ],
            weakTopics: ["Similarity", "Pythagoras theorem"],
          },
        ];

        const logoUrl = document.querySelector("nav img")?.src || "";
        window.generateProfessionalPDF(
          studentData,
          performanceData,
          subjectData,
          logoUrl,
        );
      });
  };

  // Export for use
  window.PDFGenerator = {
    generate: window.generateProfessionalPDF,
    generateFromPage: window.generatePDFFromPage,
  };
})();
