let createTestRedirectUrl = null;
let allTests = [];
let allFolders = [];
let isInsideFolderView = false;
let pendingDeleteFolders = [];
let currentFolderId = null;

function updatePrimaryActionButton() {
  const label = document.getElementById("primary-action-label");
  if (!label) return;
  label.textContent = isInsideFolderView ? "New Test" : "New Folder";
}

function openPrimaryActionModal() {
  const modalId = isInsideFolderView ? "createTestModal" : "createFolderModal";
  const modalElement = document.getElementById(modalId);
  if (!modalElement) return;
  const modal = new bootstrap.Modal(modalElement);
  modal.show();
}

function updateFolderActions() {
  const folderActions = document.getElementById("folder-actions");
  const selectedFolders = document.querySelectorAll(".folder-checkbox:checked");
  const selectAllFolders = document.getElementById("select-all-folders");
  const visibleFolderCheckboxes = document.querySelectorAll(".folder-checkbox");

  if (folderActions) {
    folderActions.style.display =
      !isInsideFolderView && selectedFolders.length > 0 ? "flex" : "none";
  }

  if (selectAllFolders) {
    const allSelected =
      visibleFolderCheckboxes.length > 0 &&
      selectedFolders.length === visibleFolderCheckboxes.length;
    selectAllFolders.checked = allSelected;
    selectAllFolders.indeterminate =
      selectedFolders.length > 0 && !allSelected;
  }
}

function toggleFolderSelection(checkbox) {
  const card = checkbox.closest(".folder-card");
  if (card) {
    card.classList.toggle("selected", checkbox.checked);
  }
  updateFolderActions();
}

function toggleAllFolders(source) {
  const shouldSelect = source.checked;
  const checkboxes = document.querySelectorAll(".folder-checkbox");
  checkboxes.forEach((checkbox) => {
    checkbox.checked = shouldSelect;
    const card = checkbox.closest(".folder-card");
    if (card) {
      card.classList.toggle("selected", shouldSelect);
    }
  });
  updateFolderActions();
}

function deleteSelectedFolders() {
  const selectedCheckboxes = document.querySelectorAll(
    ".folder-checkbox:checked",
  );
  if (selectedCheckboxes.length === 0) return;

  pendingDeleteFolders = Array.from(selectedCheckboxes).map((checkbox) => {
    const card = checkbox.closest(".folder-card");
    return {
      id: card?.dataset?.id,
      name: card?.dataset?.name || "Folder",
    };
  });

  const folderCount = pendingDeleteFolders.length;
  const message =
    folderCount === 1
      ? `Delete folder "${pendingDeleteFolders[0].name}" and all tests inside it? This action cannot be undone.`
      : `Delete ${folderCount} selected folders and all tests inside them? This action cannot be undone.`;

  const modal = new bootstrap.Modal(
    document.getElementById("deleteFolderModal"),
  );
  document.getElementById("delete-folder-message").textContent = message;
  document.getElementById("confirm-delete-folder-btn").onclick =
    confirmDeleteSelectedFolders;
  modal.show();
}

function confirmDeleteSelectedFolders() {
  if (!pendingDeleteFolders.length) return;

  Promise.all(
    pendingDeleteFolders.map((folder) =>
      fetch(`/scholarship/api/folders/${folder.id}/delete/`, {
        method: "DELETE",
      }),
    ),
  )
    .then((responses) => Promise.all(responses.map((res) => res.json())))
    .then(() => {
      const deletedIds = new Set(pendingDeleteFolders.map((folder) => `${folder.id}`));
      allFolders = allFolders.filter((folder) => !deletedIds.has(`${folder.id}`));
      allTests = allTests.filter((test) => !deletedIds.has(`${test.folderId}`));
      pendingDeleteFolders = [];
      showAllItems();

      const modal = bootstrap.Modal.getInstance(
        document.getElementById("deleteFolderModal"),
      );
      if (modal) modal.hide();
      showToast("Selected folders deleted successfully");
    })
    .catch((err) => {
      console.error("Error deleting selected folders:", err);
      showToast("Error deleting selected folders");
    });
}

function showToast(message) {
  // Simple toast implementation
  const toast = document.createElement("div");
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #333;
    color: white;
    padding: 12px 16px;
    border-radius: 4px;
    z-index: 9999;
    font-size: 14px;
    max-width: 300px;
    word-wrap: break-word;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }, 3000);
}

document.addEventListener("DOMContentLoaded", () => {
  const redirectRouteEl = document.getElementById("create-test-redirect-route");
  createTestRedirectUrl = redirectRouteEl?.dataset?.url || null;

  loadData();
  lucide.createIcons();
  updatePrimaryActionButton();

  const minuteSelect = document.getElementById("minute-select");
  for (let i = 0; i <= 59; i++) {
    if (i !== 30) {
      minuteSelect.innerHTML += `<option>${i}</option>`;
    }
  }

  document
    .getElementById("createTestModal")
    .addEventListener("show.bs.modal", updateFolderSelect);
  const copyModalEl = document.getElementById("copyTestModal");
  if (copyModalEl) {
    copyModalEl.addEventListener("hidden.bs.modal", () => {
      document.getElementById("copy-test-form").reset();
    });
  }
});

async function loadData() {
  try {
    const [testsRes, foldersRes] = await Promise.all([
      fetch("/scholarship/api/tests/"),
      fetch("/scholarship/api/folders/"),
    ]);

    if (!testsRes.ok || !foldersRes.ok) {
      console.error("Failed to load test data");
      return;
    }

    const testsData = await testsRes.json();
    const foldersData = await foldersRes.json();

    allTests = testsData.tests || [];
    allFolders = foldersData.folders || [];

    allTests.forEach((test) => renderTest(test, false));
    allFolders.forEach((folder, index) => renderFolder(folder, index));
    updateCounts();
    updateFolderSelect();
  } catch (err) {
    console.error("Error loading data:", err);
  }
}

function handleCreateTest() {
  const name = document.getElementById("test-name-input").value;
  if (!name.trim()) return;

  const hourSelect = document.getElementById("hour-select");
  const minuteSelect = document.getElementById("minute-select");
  const tagsInput = document.getElementById("test-tags-input");

  const data = {
    name: name,
    folderId: isInsideFolderView ? currentFolderId : null,
    duration_hours: parseInt(hourSelect.value) || 0,
    duration_minutes: parseInt(minuteSelect.value) || 30,
    tags: tagsInput.value.trim() || "",
  };

  fetch("/scholarship/api/tests/create/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(data),
  })
    .then((res) => {
      if (!res.ok) {
        console.error("Create test API failed:", res.status, res.statusText);
        return res.text().then((text) => {
          console.error("Response:", text.substring(0, 500));
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        });
      }
      return res.json();
    })
    .then((result) => {
      if (result.success) {
        const test = result.test;
        test.folderId = data.folderId;
        allTests.push(test);
        if (isInsideFolderView) {
          renderTest(test, true);
          const emptyState = document.getElementById("empty-state");
          emptyState.style.display = "none";
          document.getElementById("test-list-container").style.display = "block";
        } else {
          renderTest(test, false);
        }
        document.getElementById("create-test-form").reset();
        const modal = bootstrap.Modal.getInstance(
          document.getElementById("createTestModal"),
        );
        if (modal) modal.hide();
        updateCounts();
      } else {
        console.error("Create test failed:", result.error);
      }
    })
    .catch((err) => console.error("Error creating test:", err));
}

function handleCreateFolder() {
  const name = document.getElementById("folder-name-input").value;
  if (!name.trim()) return;

  const tagsSelect = document.querySelector("#createFolderModal .form-select");

  const data = {
    name: name,
    tags: tagsSelect ? tagsSelect.value : "",
  };

  fetch("/scholarship/api/folders/create/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  })
    .then(async (res) => {
      const result = await res.json().catch(() => ({}));
      if (!res.ok) {
        console.error("Create folder API failed:", res.status, res.statusText);
        throw new Error(result.error || `HTTP ${res.status}: ${res.statusText}`);
      }
      return result;
    })
    .then((result) => {
      if (result.success) {
        const folder = result.folder;
        allFolders.push(folder);
        renderFolder(folder, allFolders.length - 1);
        document.getElementById("create-folder-form").reset();
        const modal = bootstrap.Modal.getInstance(
          document.getElementById("createFolderModal"),
        );
        if (modal) modal.hide();
        showToast("Folder created successfully");
      } else {
        console.error("Create folder failed:", result.error);
        showToast(result.error || "Unable to create folder");
      }
    })
    .catch((err) => {
      console.error("Error creating folder:", err);
      showToast(err.message || "Error creating folder");
    });
}

window.openEditFolderModal = function (folderId, currentName, currentTags) {
  // Set the form values
  const nameInput = document.getElementById("edit-folder-name-input");
  const idInput = document.getElementById("edit-folder-id");

  if (nameInput) nameInput.value = currentName;
  if (idInput) idInput.value = folderId;

  const tagsSelect = document.querySelector("#editFolderModal .form-select");
  if (tagsSelect) {
    tagsSelect.value = currentTags || "";
  }

  // Show the modal
  const modal = new bootstrap.Modal(document.getElementById("editFolderModal"));
  modal.show();
};

window.handleEditFolder = function () {
  const folderId = document.getElementById("edit-folder-id").value;
  const name = document.getElementById("edit-folder-name-input").value;
  if (!name.trim()) return;

  const tagsSelect = document.querySelector("#editFolderModal .form-select");

  const data = {
    name: name,
    tags: tagsSelect ? tagsSelect.value : "",
  };

  fetch(`/scholarship/api/folders/${folderId}/update/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  })
    .then((res) => {
      if (!res.ok) {
        console.error("Update folder API failed:", res.status, res.statusText);
        return res.text().then((text) => {
          console.error("Response:", text.substring(0, 500));
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        });
      }
      return res.json();
    })
    .then((result) => {
      if (result.success) {
        // Update the folder in the local array
        const folderIndex = allFolders.findIndex((f) => f.id == folderId);
        if (folderIndex !== -1) {
          allFolders[folderIndex] = result.folder;
          // Re-render all folders
          document.getElementById("folder-grid-container").innerHTML = "";
          allFolders.forEach((folder, index) => renderFolder(folder, index));
        }
        const modal = bootstrap.Modal.getInstance(
          document.getElementById("editFolderModal"),
        );
        if (modal) modal.hide();
        showToast("✓ Folder updated successfully");
      } else {
        console.error("Update folder failed:", result.error);
        showToast("❌ " + (result.error || "Update failed"));
      }
    })
    .catch((err) => {
      console.error("Error updating folder:", err);
      showToast("❌ Error updating folder");
    });
};

window.confirmDeleteFolder = function (folderId, folderName) {
  // Check if folder has tests
  const folderTests = allTests.filter((test) => test.folderId == folderId);
  const hasTests = folderTests.length > 0;

  let message = `Delete folder "${folderName}"?`;
  if (hasTests) {
    message += ` It contains ${folderTests.length} test(s) that will also be deleted.`;
  }
  message += " This action cannot be undone.";

  const modal = new bootstrap.Modal(
    document.getElementById("deleteFolderModal"),
  );
  document.getElementById("delete-folder-message").textContent = message;
  document.getElementById("confirm-delete-folder-btn").onclick = () =>
    handleDeleteFolder(folderId);
  modal.show();
};

window.handleDeleteFolder = function (folderId) {
  fetch(`/scholarship/api/folders/${folderId}/delete/`, {
    method: "DELETE",
  })
    .then((res) => {
      if (!res.ok) {
        console.error("Delete folder API failed:", res.status, res.statusText);
        return res.text().then((text) => {
          console.error("Response:", text.substring(0, 500));
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        });
      }
      return res.json();
    })
    .then((result) => {
      if (result.success) {
        // Remove from local array
        allFolders = allFolders.filter((f) => f.id != folderId);
        allTests = allTests.filter((test) => test.folderId != folderId);
        // Re-render all folders
        document.getElementById("folder-grid-container").innerHTML = "";
        allFolders.forEach((folder, index) => renderFolder(folder, index));
        updateFolderActions();

        const modal = bootstrap.Modal.getInstance(
          document.getElementById("deleteFolderModal"),
        );
        if (modal) modal.hide();
        showToast("✓ Folder deleted successfully");
      } else {
        console.error("Delete folder failed:", result.error);
        showToast("❌ " + (result.error || "Delete failed"));
      }
    })
    .catch((err) => {
      console.error("Error deleting folder:", err);
      showToast("❌ Error deleting folder");
    });
};

function renderTest(data, isFolderView = false) {
  const container = document.getElementById("test-list-container");
  const div = document.createElement("div");
  div.className = "test-item";
  div.dataset.id = data.id;
  const dateStr = data.date
    ? data.date
    : new Date().toISOString().split("T")[0];
  const status = (data.status || "draft").toLowerCase();
  const badgeClass = status === "published" ? "badge-published" : "badge-draft";
  const badgeLabel = status.charAt(0).toUpperCase() + status.slice(1);
  div.innerHTML = `<input type="checkbox" class="test-checkbox" onchange="toggleTestActions()"><div class="test-icon-box"><i data-lucide="file-text" style="width: 28px; height: 28px;"></i></div><div class="test-info"><p class="test-title">${data.name}</p><div class="hover-actions"><a href="#" class="copy-test-link">Copy Test</a> <span>|</span> <a href="#" class="move-test-link">Move to folder</a> <span>|</span> <a href="#" class="delete-test-link">Delete</a></div></div><span class="${badgeClass}">${badgeLabel}</span><span class="test-date">${dateStr}</span>`;
  const copyLink = div.querySelector(".copy-test-link");
  copyLink.addEventListener("click", (event) => {
    event.preventDefault();
    openCopyTestModal(data.id, data.name);
  });
  const moveLink = div.querySelector(".move-test-link");
  moveLink.addEventListener("click", (event) => {
    event.preventDefault();
    document.querySelectorAll(".test-checkbox").forEach((checkbox) => {
      checkbox.checked = false;
    });
    document.getElementById("test-actions").classList.remove("show");
    const checkbox = div.querySelector(".test-checkbox");
    if (checkbox) {
      checkbox.checked = true;
    }
    moveSelectedTests();
  });
  const deleteLink = div.querySelector(".delete-test-link");
  deleteLink.addEventListener("click", (event) => {
    event.preventDefault();
    document.querySelectorAll(".test-checkbox").forEach((checkbox) => {
      checkbox.checked = false;
    });
    document.getElementById("test-actions").classList.remove("show");
    const checkbox = div.querySelector(".test-checkbox");
    if (checkbox) {
      checkbox.checked = true;
    }
    deleteSelectedTests();
  });

  if (createTestRedirectUrl) {
    div.addEventListener("click", (event) => {
      const clickedInteractive = event.target.closest(
        ".test-checkbox, .hover-actions a",
      );
      if (clickedInteractive) {
        return;
      }
      window.location.href =
        createTestRedirectUrl + "?test_id=" + data.id + "&_ts=" + Date.now();
    });
  }
  container.appendChild(div);
  updateCounts();
  lucide.createIcons();
}

function toggleTestActions() {
  const checkboxes = document.querySelectorAll(".test-checkbox:checked");
  const visibleTestCheckboxes = document.querySelectorAll(".test-checkbox");
  const actions = document.getElementById("test-actions");
  const selectAllTests = document.getElementById("select-all-tests");
  if (checkboxes.length > 0) {
    actions.classList.add("show");
  } else {
    actions.classList.remove("show");
  }

  if (selectAllTests) {
    const allSelected =
      visibleTestCheckboxes.length > 0 &&
      checkboxes.length === visibleTestCheckboxes.length;
    selectAllTests.checked = allSelected;
    selectAllTests.indeterminate = checkboxes.length > 0 && !allSelected;
  }
}

function toggleAllTests(source) {
  const checkboxes = document.querySelectorAll(".test-checkbox");
  checkboxes.forEach((checkbox) => {
    checkbox.checked = source.checked;
  });
  toggleTestActions();
}

function moveSelectedTests() {
  const selectedCheckboxes = document.querySelectorAll(
    ".test-checkbox:checked",
  );
  if (selectedCheckboxes.length === 0) return;

  const folderSelect = document.getElementById("move-folder-select");
  folderSelect.innerHTML = '<option value="">Select a folder</option>';
  allFolders.forEach((folder, index) => {
    folderSelect.innerHTML += `<option value="${folder.id}">${folder.name}</option>`;
  });

  const modal = new bootstrap.Modal(document.getElementById("moveTestModal"));
  modal.show();
}

function confirmMoveTests() {
  const folderIndex = document.getElementById("move-folder-select").value;
  if (folderIndex === "") return;

  const selectedCheckboxes = document.querySelectorAll(
    ".test-checkbox:checked",
  );

  const testIds = Array.from(selectedCheckboxes).map((checkbox) => {
    return checkbox.closest(".test-item").dataset.id;
  });

  Promise.all(
    testIds.map((testId) =>
      fetch(`/scholarship/api/tests/${testId}/move/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ folderId: folderIndex }),
      }),
    ),
  )
    .then(() => {
      location.reload();
    })
    .catch((err) => console.error("Error moving tests:", err));
}

let pendingDeleteTests = [];

function deleteSelectedTests() {
  const selectedCheckboxes = document.querySelectorAll(
    ".test-checkbox:checked",
  );
  if (selectedCheckboxes.length === 0) return;

  pendingDeleteTests = Array.from(selectedCheckboxes).map((checkbox) => {
    return checkbox.closest(".test-item").dataset.id;
  });

  const modal = new bootstrap.Modal(document.getElementById("deleteTestModal"));
  modal.show();
}

function confirmDeleteTests() {
  if (!pendingDeleteTests.length) return;

  Promise.all(
    pendingDeleteTests.map((testId) =>
      fetch(`/scholarship/api/tests/${testId}/delete/`, {
        method: "DELETE",
      }),
    ),
  )
    .then(() => {
      location.reload();
    })
    .catch((err) => console.error("Error deleting tests:", err));
}

function renderFolder(data, index) {
  const container = document.getElementById("folder-grid-container");
  if (!container) {
    console.error("Folder grid container not found!");
    return;
  }
  const div = document.createElement("div");
  div.className = "folder-card";
  div.dataset.id = data.id;

  // Create elements individually to avoid onclick issues
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "folder-checkbox";
  checkbox.addEventListener("click", (e) => e.stopPropagation());
  checkbox.addEventListener("change", function () {
    toggleFolderSelection(this);
  });
  div.dataset.name = data.name;

  const folderContent = document.createElement("div");
  folderContent.className = "folder-content";
  folderContent.onclick = () => showFolderTests(index, data.id, data.name);

  const iconArea = document.createElement("div");
  iconArea.className = "folder-icon-area";

  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", "folder");
  icon.className = "folder-icon";
  icon.style.fill = "currentColor";

  const folderName = document.createElement("div");
  folderName.className = "folder-name";
  folderName.textContent = data.name;

  iconArea.appendChild(icon);
  folderContent.appendChild(iconArea);
  folderContent.appendChild(folderName);

  const actions = document.createElement("div");
  actions.className = "folder-actions";

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "folder-action-btn edit-btn";
  editBtn.title = "Edit Folder";
  editBtn.setAttribute("aria-label", "Edit Folder");
  editBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    window.openEditFolderModal(data.id, data.name, data.tags || "");
  });

  const editIcon = document.createElement("i");
  editIcon.setAttribute("data-lucide", "edit");
  editIcon.style.width = "14px";
  editIcon.style.height = "14px";
  editBtn.appendChild(editIcon);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "folder-action-btn delete-btn";
  deleteBtn.title = "Delete Folder";
  deleteBtn.setAttribute("aria-label", "Delete Folder");
  deleteBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    window.confirmDeleteFolder(data.id, data.name);
  });

  const deleteIcon = document.createElement("i");
  deleteIcon.setAttribute("data-lucide", "trash");
  deleteIcon.style.width = "14px";
  deleteIcon.style.height = "14px";
  deleteBtn.appendChild(deleteIcon);

  actions.appendChild(editBtn);
  actions.appendChild(deleteBtn);

  div.appendChild(checkbox);
  div.appendChild(folderContent);
  div.appendChild(actions);

  container.appendChild(div);
  updateCounts();
  lucide.createIcons();
}

function showFolderTests(index, folderId, folderName) {
  isInsideFolderView = true;
  currentFolderId = folderId;
  updatePrimaryActionButton();
  updateFolderActions();
  document.getElementById("test-section").style.display = "block";
  document.getElementById("folder-grid-container").style.display = "none";
  document.getElementById("folder-section").style.display = "none";
  document.querySelector(".view-all-btn").style.display = "none";
  document.getElementById("back-btn").style.display = "block";

  const testContainer = document.getElementById("test-list-container");
  testContainer.innerHTML = "";

  const folderTests = allTests.filter((t) => t.folderId == folderId);

  if (folderTests.length === 0) {
    document.getElementById("empty-state").style.display = "block";
    document.getElementById("empty-state").querySelector("h4").textContent =
      "No tests in this folder";
    document.getElementById("empty-state").querySelector("p").textContent =
      "Add tests to this folder from the test creation or move option";
    testContainer.style.display = "none";
  } else {
    document.getElementById("empty-state").style.display = "none";
    testContainer.style.display = "block";
    folderTests.forEach((test) => renderTest(test, true));
  }
  const selectAllTests = document.getElementById("select-all-tests");
  if (selectAllTests) {
    selectAllTests.checked = false;
    selectAllTests.indeterminate = false;
  }
  document.getElementById("test-count").parentElement.style.display = "flex";
}

function showAllItems() {
  isInsideFolderView = false;
  currentFolderId = null;
  updatePrimaryActionButton();
  pendingDeleteFolders = [];
  document.getElementById("test-section").style.display = "none";
  document.getElementById("folder-grid-container").style.display = "grid";
  document.getElementById("folder-section").style.display = "block";
  document.querySelector(".view-all-btn").style.display = "inline-block";
  document.getElementById("back-btn").style.display = "none";

  const testContainer = document.getElementById("test-list-container");
  testContainer.innerHTML = "";
  testContainer.style.display = "block";

  allTests.forEach((test) => renderTest(test, false));
  document.querySelectorAll(".folder-card").forEach((card) => card.remove());
  allFolders.forEach((folder, index) => renderFolder(folder, index));
  const selectAllFolders = document.getElementById("select-all-folders");
  if (selectAllFolders) {
    selectAllFolders.checked = false;
    selectAllFolders.indeterminate = false;
  }
  const selectAllTests = document.getElementById("select-all-tests");
  if (selectAllTests) {
    selectAllTests.checked = false;
    selectAllTests.indeterminate = false;
  }
  updateFolderActions();

  document.getElementById("empty-state").querySelector("h4").textContent =
    "No tests here";
  document.getElementById("empty-state").querySelector("p").textContent =
    "Try searching with a different keyword or filters";
  updateCounts();
}

function openCopyTestModal(testId, testName) {
  const input = document.getElementById("copy-test-name-input");
  input.value = testName || "";
  input.dataset.testId = testId;
  const modalEl = document.getElementById("copyTestModal");
  const modal = new bootstrap.Modal(modalEl);
  modal.show();
}

function submitCopyTest() {
  const input = document.getElementById("copy-test-name-input");
  if (!input || !input.value.trim()) return;

  const testId = input.dataset.testId;

  fetch(`/scholarship/api/tests/${testId}/copy/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: input.value.trim() }),
  })
    .then((res) => res.json())
    .then((result) => {
      if (result.success) {
        const modalEl = document.getElementById("copyTestModal");
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) {
          modal.hide();
        }
        location.reload();
      }
    })
    .catch((err) => console.error("Error copying test:", err));
}

function updateFolderSelect() {
  const select = document.getElementById("test-folder-select");
  if (!select) return;
  select.innerHTML = '<option value="">No Folder</option>';
  allFolders.forEach((folder) => {
    select.innerHTML += `<option value="${folder.id}">${folder.name}</option>`;
  });
}

function updateCounts() {
  const testCount = document.querySelectorAll(".test-item").length;
  const folderCount = document.querySelectorAll(".folder-card").length;

  document.getElementById("test-count").innerText = testCount;
  document.getElementById("folder-count").innerText = folderCount;

  const emptyState = document.getElementById("empty-state");
  const testList = document.getElementById("test-list-container");

  if (testCount === 0) {
    emptyState.style.display = "block";
    testList.style.display = "none";
  } else {
    emptyState.style.display = "none";
    testList.style.display = "block";
  }
}

function saveItem(key, item) {
  let items = JSON.parse(localStorage.getItem(key)) || [];
  items.push(item);
  localStorage.setItem(key, JSON.stringify(items));
}

function loadDataLegacy() {
  (JSON.parse(localStorage.getItem("myTests")) || []).forEach((t) =>
    renderTest(t, false),
  );
  (JSON.parse(localStorage.getItem("myFolders")) || []).forEach(
    (folder, index) => renderFolder(folder, index),
  );
  updateCounts();
  updateFolderSelect();
}
