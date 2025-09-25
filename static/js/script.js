// ==================================================================
//           Mastercam GitLab Interface Script
// (Corrected Version with Admin and View Fixes)
// ==================================================================

// -- Global Variables --
let currentUser = "demo_user";
let ws = null;
let groupedFiles = {};
let currentConfig = null;
let isAdminModeEnabled = false;
let reconnectAttempts = 0;
let maxReconnectAttempts = 5;
let reconnectTimeout = null;
let isManualDisconnect = false;
let lastNotification = { message: null, timestamp: 0 };

// -- Notification Debounce --
function debounceNotifications(message, type, delay = 5000) {
  const now = Date.now();
  if (
    lastNotification.message === message &&
    now - lastNotification.timestamp < delay
  ) {
    console.log(`Debounced notification: ${message}`);
    return;
  }
  lastNotification = { message, timestamp: now };
  showNotification(message, type);
}

// -- Improved WebSocket Management --
function connectWebSocket() {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${
    window.location.host
  }/ws?user=${encodeURIComponent(currentUser)}`;
  ws = new WebSocket(wsUrl);
  ws.onopen = function () {
    console.log("WebSocket connected successfully");
    updateConnectionStatus(true);
    reconnectAttempts = 0;
    ws.send(`SET_USER:${currentUser}`);
    ws.send("REFRESH_FILES");
  };
  ws.onmessage = function (event) {
    handleWebSocketMessage(event.data);
  };
  ws.onclose = function (event) {
    updateConnectionStatus(false);
    if (isManualDisconnect) {
      isManualDisconnect = false;
      return;
    }
    if (reconnectAttempts < maxReconnectAttempts) {
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      reconnectTimeout = setTimeout(() => {
        reconnectAttempts++;
        connectWebSocket();
      }, delay);
    } else {
      debounceNotifications(
        "Connection lost. Please refresh the page.",
        "error"
      );
    }
  };
  ws.onerror = function (error) {
    console.error("WebSocket error:", error);
    updateConnectionStatus(false);
  };
}

function disconnectWebSocket() {
  isManualDisconnect = true;
  if (ws) ws.close();
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
}

function handleWebSocketMessage(message) {
  try {
    const data = JSON.parse(message);
    if (data.type === "FILE_LIST_UPDATED") {
      groupedFiles = data.payload || {};
      renderFiles();
    } else if (data.type === "NEW_MESSAGES") {
      if (data.payload && data.payload.length > 0) {
        populateAndShowMessagesModal(data.payload);
      }
    }
  } catch (error) {
    console.log("Received non-JSON WebSocket message:", message);
  }
}

function manualRefresh() {
  loadFiles();
}

// -- Data Loading and Rendering --
async function loadFiles() {
  try {
    const response = await fetch("/files");
    if (!response.ok) {
      throw new Error(
        `Server responded with ${response.status}: ${response.statusText}`
      );
    }
    groupedFiles = await response.json();
    renderFiles();
    updateRepoStatus("Ready");
  } catch (error) {
    console.error("Error loading files:", error);
    debounceNotifications(`Error loading files: ${error.message}`, "error");
    updateRepoStatus("Error");
  }
}

function renderFiles() {
  const fileListEl = document.getElementById("fileList");
  const searchTerm = document.getElementById("searchInput").value.toLowerCase();
  const expandedGroups =
    JSON.parse(localStorage.getItem("expandedGroups")) || [];
  const expandedSubGroups =
    JSON.parse(localStorage.getItem("expandedSubGroups")) || [];
  fileListEl.innerHTML = "";
  let totalFilesFound = 0;

  if (!groupedFiles || Object.keys(groupedFiles).length === 0) {
    fileListEl.innerHTML = `<div class="flex flex-col items-center justify-center py-12 text-primary-600 dark:text-primary-300"><i class="fa-solid fa-exclamation-triangle text-6xl mb-4"></i><h3 class="text-2xl font-semibold">No Connection</h3><p class="mt-2 text-center">Unable to load files. Check your configuration.</p><button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-accent to-accent-hover text-white rounded-md hover:bg-opacity-80">Try Again</button></div>`;
    return;
  }

  const sortedGroupNames = Object.keys(groupedFiles).sort((a, b) => {
    const isAMisc = a === "Miscellaneous";
    const isBMisc = b === "Miscellaneous";
    if (isAMisc) return 1;
    if (isBMisc) return -1;
    return a.localeCompare(b);
  });

  sortedGroupNames.forEach((groupName) => {
    const filesInGroup = groupedFiles[groupName];
    if (!Array.isArray(filesInGroup)) return;

    // Group files by the first 7 digits of their filename
    const subGroupedFiles = {};
    filesInGroup.forEach((file) => {
      const sevenDigitPrefix =
        file.filename.match(/^\d{7}/)?.[0] || "Miscellaneous";
      if (!subGroupedFiles[sevenDigitPrefix]) {
        subGroupedFiles[sevenDigitPrefix] = [];
      }
      subGroupedFiles[sevenDigitPrefix].push(file);
    });

    // Filter and count total files after search
    let groupFileCount = 0;
    const filteredSubGroups = {};
    Object.keys(subGroupedFiles).forEach((subGroupName) => {
      const filteredFiles = subGroupedFiles[subGroupName].filter(
        (file) =>
          file.filename.toLowerCase().includes(searchTerm) ||
          file.path.toLowerCase().includes(searchTerm)
      );
      if (filteredFiles.length > 0) {
        filteredSubGroups[subGroupName] = filteredFiles.sort((a, b) =>
          a.filename.localeCompare(b.filename)
        );
        groupFileCount += filteredFiles.length;
      }
    });

    if (groupFileCount === 0) return;
    totalFilesFound += groupFileCount;

    // Create top-level group (by first two digits)
    const detailsEl = document.createElement("details");
    detailsEl.className =
      "file-group group border-t border-primary-300 dark:border-mc-dark-accent";
    detailsEl.dataset.groupName = groupName;
    if (expandedGroups.includes(groupName)) detailsEl.open = true;
    detailsEl.addEventListener("toggle", saveExpandedState);

    const summaryEl = document.createElement("summary");
    summaryEl.className =
      "list-none py-3 px-4 bg-gradient-to-r from-mc-light-accent to-white dark:from-mc-dark-accent dark:to-mc-dark-bg cursor-pointer hover:bg-opacity-80 flex justify-between items-center transition-colors";
    summaryEl.innerHTML = `<div class="flex items-center space-x-3"><i class="fa-solid fa-chevron-right text-xs text-primary-600 dark:text-primary-300 transform transition-transform duration-200 group-open:rotate-90"></i><span class="font-semibold text-primary-800 dark:text-primary-200">${
      groupName.endsWith("XXXXX") ? `${groupName} SERIES` : groupName
    }</span></div><span class="text-sm font-medium text-primary-600 dark:text-primary-300">(${groupFileCount} files)</span>`;
    detailsEl.appendChild(summaryEl);

    // Create container for subgroups
    const subGroupsContainer = document.createElement("div");
    subGroupsContainer.className = "pl-4";

    // Render subgroups (by seven-digit prefix)
    Object.keys(filteredSubGroups)
      .sort()
      .forEach((subGroupName) => {
        const filesInSubGroup = filteredSubGroups[subGroupName];

        const subDetailsEl = document.createElement("details");
        subDetailsEl.className =
          "sub-file-group group border-t border-primary-200 dark:border-primary-600";
        subDetailsEl.dataset.subGroupName = `${groupName}/${subGroupName}`;
        if (expandedSubGroups.includes(`${groupName}/${subGroupName}`)) {
          subDetailsEl.open = true;
        }
        subDetailsEl.addEventListener("toggle", saveExpandedSubState);

        const subSummaryEl = document.createElement("summary");
        subSummaryEl.className =
          "list-none py-2 px-3 bg-gradient-to-r from-primary-50 to-primary-100 dark:from-primary-700 dark:to-primary-800 cursor-pointer hover:bg-opacity-80 flex justify-between items-center transition-colors";
        subSummaryEl.innerHTML = `<div class="flex items-center space-x-3"><i class="fa-solid fa-chevron-right text-xs text-primary-600 dark:text-primary-300 transform transition-transform duration-200 group-open:rotate-90"></i><span class="font-medium text-primary-800 dark:text-primary-200">${subGroupName}</span></div><span class="text-sm font-medium text-primary-600 dark:text-primary-300">(${filesInSubGroup.length} files)</span>`;
        subDetailsEl.appendChild(subSummaryEl);

        const filesContainer = document.createElement("div");
        filesContainer.className = "pl-4";
        filesInSubGroup.forEach((file) => {
          const fileEl = document.createElement("div");
          fileEl.id = `file-${file.filename.replace(/[^a-zA-Z0-9]/g, "-")}`;
          let statusClass = "",
            statusBadgeText = "";
          switch (file.status) {
            case "unlocked":
              statusClass =
                "bg-green-100 text-green-900 dark:bg-green-900 dark:text-green-200";
              statusBadgeText = "Available";
              break;
            case "locked":
              statusClass =
                "bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-200";
              statusBadgeText = `Locked by ${file.locked_by}`;
              break;
            case "checked_out_by_user":
              statusClass =
                "bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-200";
              statusBadgeText = "Checked out by you";
              break;
            default:
              statusClass =
                "bg-primary-100 text-primary-900 dark:bg-primary-600 dark:text-primary-200";
              statusBadgeText = "Unknown";
          }
          const actionsHtml = getActionButtons(file);
          fileEl.className =
            "py-6 px-4 bg-white dark:bg-mc-dark-bg hover:bg-opacity-80 transition-colors duration-200 border-b border-primary-300 dark:border-mc-dark-accent bg-opacity-95";
          fileEl.innerHTML = `
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0">
                <div class="flex items-center space-x-4 flex-wrap">
                    <h3 class="text-lg font-semibold text-primary-900 dark:text-primary-100">${
                      file.filename
                    }</h3>
                    <span class="text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}">${statusBadgeText}</span>
                    ${
                      file.revision
                        ? `<span class="text-xs font-bold px-2.5 py-1 rounded-full bg-primary-200 text-primary-800 dark:bg-primary-700 dark:text-primary-200">REV ${file.revision}</span>`
                        : ""
                    }
                </div>
                <div class="flex items-center space-x-2 flex-wrap">${actionsHtml}</div>
            </div>
            ${
              file.description
                ? `<div class="mt-2 text-sm text-primary-700 dark:text-primary-300 italic">${file.description}</div>`
                : ""
            }
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4 text-primary-700 dark:text-primary-300 text-sm">
                <div class="flex items-center space-x-2"><i class="fa-solid fa-file text-primary-600 dark:text-primary-300"></i><span>Path: ${
                  file.path
                }</span></div>
                <div class="flex items-center space-x-2"><i class="fa-solid fa-hard-drive text-primary-600 dark:text-primary-300"></i><span>Size: ${formatBytes(
                  file.size
                )}</span></div>
                <div class="flex items-center space-x-2"><i class="fa-solid fa-clock text-primary-600 dark:text-primary-300"></i><span>Modified: ${formatDate(
                  file.modified_at
                )}</span></div>
                ${
                  file.locked_by && file.status !== "checked_out_by_user"
                    ? `<div class="flex items-center space-x-2 sm:col-span-2 lg:col-span-1"><i class="fa-solid fa-lock text-primary-600 dark:text-primary-300"></i><span>Locked by: ${
                        file.locked_by
                      } at ${formatDate(file.locked_at)}</span></div>`
                    : ""
                }
            </div>`;
          filesContainer.appendChild(fileEl);
        });
        subDetailsEl.appendChild(filesContainer);
        subGroupsContainer.appendChild(subDetailsEl);
      });

    detailsEl.appendChild(subGroupsContainer);
    fileListEl.appendChild(detailsEl);
  });

  if (totalFilesFound === 0) {
    fileListEl.innerHTML = `<div class="flex flex-col items-center justify-center py-12 text-primary-600 dark:text-primary-300"><i class="fa-solid fa-folder-open text-6xl mb-4"></i><h3 class="text-2xl font-semibold">No files found</h3><p class="mt-2 text-center">No Mastercam files match your search criteria.</p><button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-accent to-accent-hover text-white rounded-md hover:bg-opacity-80">Refresh</button></div>`;
  }
}

async function loadConfig() {
  try {
    const response = await fetch("/config");
    currentConfig = await response.json();
    console.log("Loaded config:", currentConfig); // Added for debugging admin status
    updateConfigDisplay();
    setupAdminUI();
  } catch (error) {
    console.error("Error loading config:", error);
  }
}

function updateConnectionStatus(connected) {
  const statusEl = document.getElementById("connectionStatus");
  const textEl = document.getElementById("connectionText");
  if (statusEl && textEl) {
    statusEl.className = `w-3 h-3 rounded-full ${
      connected
        ? "bg-green-600 dark:bg-green-400"
        : "bg-red-600 dark:bg-red-400 animate-pulse"
    }`;
    textEl.textContent = connected
      ? "Connected"
      : reconnectAttempts > 0
      ? `Reconnecting... (${reconnectAttempts}/${maxReconnectAttempts})`
      : "Disconnected";
  }
}
function updateRepoStatus(status) {
  document.getElementById("repoStatus").textContent = status;
}
function updateConfigDisplay() {
  if (currentConfig) {
    document.getElementById("configStatusText").textContent =
      currentConfig.has_token ? "Configured" : "Not configured";
    document.getElementById("configRepoText").textContent =
      currentConfig.repo_path || "Not available";
    document.getElementById("gitlabUrl").value = currentConfig.gitlab_url || "";
    document.getElementById("projectId").value = currentConfig.project_id || "";
    document.getElementById("username").value = currentConfig.username || "";
    if (currentConfig.username) {
      currentUser = currentConfig.username;
      document.getElementById("currentUser").textContent = currentUser;
    }
  }
}
function setupAdminUI() {
  const adminToggle = document.getElementById("globalAdminToggle");
  const sendMsgBtn = document.getElementById("sendMessageBtn");
  if (!adminToggle || !sendMsgBtn) return;

  if (currentConfig && currentConfig.is_admin) {
    adminToggle.classList.remove("hidden");
    sendMsgBtn.classList.remove("hidden");

    if (!adminToggle.dataset.listenerAttached) {
      adminToggle.addEventListener("click", () => {
        isAdminModeEnabled = !isAdminModeEnabled;
        adminToggle.classList.toggle("from-gray-200", !isAdminModeEnabled);
        adminToggle.classList.toggle("to-gray-300", !isAdminModeEnabled);
        adminToggle.classList.toggle("text-gray-800", !isAdminModeEnabled);
        adminToggle.classList.toggle("dark:from-gray-600", !isAdminModeEnabled);
        adminToggle.classList.toggle("dark:to-gray-700", !isAdminModeEnabled);
        adminToggle.classList.toggle("dark:text-gray-100", !isAdminModeEnabled);
        adminToggle.classList.toggle("from-accent", isAdminModeEnabled);
        adminToggle.classList.toggle("to-accent-hover", isAdminModeEnabled);
        adminToggle.classList.toggle("text-white", isAdminModeEnabled);
        adminToggle.classList.toggle("dark:text-white", isAdminModeEnabled);
        document.querySelectorAll(".admin-action-btn").forEach((btn) => {
          btn.classList.toggle("hidden", !isAdminModeEnabled);
        });
      });
      adminToggle.dataset.listenerAttached = "true";
    }
    if (!sendMsgBtn.dataset.listenerAttached) {
      sendMsgBtn.addEventListener("click", openSendMessageModal);
      sendMsgBtn.dataset.listenerAttached = "true";
    }
  } else {
    adminToggle.classList.add("hidden");
    sendMsgBtn.classList.add("hidden");
  }
}

// FIXED: Action buttons now show View for all files
function getActionButtons(file) {
  const btnClass =
    "flex items-center space-x-2 px-4 py-2 rounded-md transition-colors text-sm font-semibold";
  let buttons = "";

  // Always show View/Download button first
  let viewBtnHtml = `<a href="/files/${file.filename}/download" class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80"><i class="fa-solid fa-eye"></i><span>View</span></a>`;

  if (file.status === "unlocked") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-green-600 to-green-700 text-white hover:bg-opacity-80 js-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-download"></i><span>Checkout</span></button>`;
  } else if (file.status === "checked_out_by_user") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-blue-600 to-blue-700 text-white hover:bg-opacity-80 js-checkin-btn" data-filename="${file.filename}"><i class="fa-solid fa-upload"></i><span>Check In</span></button>`;
    buttons += `<button class="${btnClass} bg-gradient-to-r from-yellow-600 to-yellow-700 text-white dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80 js-cancel-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-times"></i><span>Cancel Checkout</span></button>`;
    // Change View to Download for checked out files
    viewBtnHtml = viewBtnHtml.replace(
      '<i class="fa-solid fa-eye"></i><span>View</span>',
      '<i class="fa-solid fa-file-arrow-down"></i><span>Download</span>'
    );
  }

  // Add View/Download button
  buttons = viewBtnHtml + buttons;

  // Always add History button
  buttons += `<button class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80 js-history-btn" data-filename="${file.filename}"><i class="fa-solid fa-history"></i><span>History</span></button>`;

  // Admin buttons (only show if user is admin and admin mode is enabled)
  if (currentConfig && currentConfig.is_admin) {
    const adminBtnVisibility = isAdminModeEnabled ? "" : "hidden";

    if (file.status === "locked" && file.locked_by !== currentUser) {
      const overrideBtnClasses =
        "bg-gradient-to-r from-yellow-400 to-yellow-500 text-yellow-900 dark:from-yellow-600 dark:to-yellow-700 dark:text-yellow-100";
      buttons += `<button class="${btnClass} ${adminBtnVisibility} admin-action-btn ${overrideBtnClasses} hover:bg-opacity-80 js-override-btn" data-filename="${file.filename}"><i class="fa-solid fa-unlock"></i><span>Override</span></button>`;
    }

    const deleteBtnClasses =
      "bg-gradient-to-r from-red-600 to-red-700 text-white dark:from-red-700 dark:to-red-800 dark:text-red-100";
    buttons += `<button class="${btnClass} ${adminBtnVisibility} admin-action-btn ${deleteBtnClasses} hover:bg-opacity-80 js-delete-btn" data-filename="${file.filename}"><i class="fa-solid fa-trash-can"></i><span>Delete</span></button>`;
  }

  return buttons;
}

async function checkoutFile(filename) {
  setFileStateToLoading(filename);
  try {
    const response = await fetch(`/files/${filename}/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: currentUser }),
    });
    if (response.ok) {
      debounceNotifications(
        `File '${filename}' checked out successfully!`,
        "success"
      );
    } else {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Checkout failed");
    }
  } catch (error) {
    debounceNotifications(`Checkout Error: ${error.message}`, "error");
    revertFileStateFromLoading(filename);
  }
}
function setFileStateToLoading(filename) {
  const safeId = `file-${filename.replace(/[^a-zA-Z0-9]/g, "-")}`;
  const fileEl = document.getElementById(safeId);
  if (fileEl) {
    const checkoutBtn = fileEl.querySelector(".js-checkout-btn");
    if (checkoutBtn) {
      checkoutBtn.disabled = true;
      checkoutBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>Locking...</span>`;
    }
  }
}
function revertFileStateFromLoading(filename) {
  const safeId = `file-${filename.replace(/[^a-zA-Z0-9]/g, "-")}`;
  const fileEl = document.getElementById(safeId);
  if (fileEl) {
    const checkoutBtn = fileEl.querySelector(".js-checkout-btn");
    if (checkoutBtn) {
      checkoutBtn.disabled = false;
      checkoutBtn.innerHTML = `<i class="fa-solid fa-download"></i><span>Checkout</span>`;
    }
  }
}
function showCheckinDialog(filename) {
  const modal = document.getElementById("checkinModal");
  const form = document.getElementById("checkinForm");
  const title = document.getElementById("checkinModalTitle");
  title.textContent = `Check In: ${filename}`;
  form.dataset.filename = filename;
  form.reset();
  modal.classList.remove("hidden");
}

async function checkinFile(
  filename,
  file,
  commitMessage,
  rev_type,
  new_major_rev
) {
  try {
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
    formData.append("commit_message", commitMessage);
    formData.append("rev_type", rev_type);
    // Only add the new major rev number if it's provided
    if (new_major_rev) {
      formData.append("new_major_rev", new_major_rev);
    }
    const response = await fetch(`/files/${filename}/checkin`, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Unknown error");
    debounceNotifications(
      `File '${filename}' checked in successfully!`,
      "success"
    );
  } catch (error) {
    debounceNotifications(`Check-in Error: ${error.message}`, "error");
  }
}

async function adminOverride(filename) {
  if (!confirm(`Are you sure you want to override the lock on '${filename}'?`))
    return;
  try {
    const response = await fetch(`/files/${filename}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Unknown error");
    debounceNotifications(`File '${filename}' lock overridden!`, "success");
  } catch (error) {
    debounceNotifications(`Override Error: ${error.message}`, "error");
  }
}
async function adminDeleteFile(filename) {
  if (
    !confirm(
      `DANGER!\n\nAre you sure you want to permanently delete '${filename}'?\n\nThis action cannot be undone.`
    )
  )
    return;
  try {
    const response = await fetch(`/files/${filename}/delete`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(result.detail || "An unknown error occurred.");
    debounceNotifications(
      result.message || `File '${filename}' deleted successfully!`,
      "success"
    );
  } catch (error) {
    debounceNotifications(`Delete Error: ${error.message}`, "error");
  }
}
async function viewFileHistory(filename) {
  try {
    const response = await fetch(`/files/${filename}/history`);
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Failed to load history");
    }
    const result = await response.json();
    showFileHistoryModal(result);
  } catch (error) {
    debounceNotifications(`History Error: ${error.message}`, "error");
  }
}

function showFileHistoryModal(historyData) {
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100]";
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.remove();
  });
  let historyListHtml = "";
  if (historyData.history && historyData.history.length > 0) {
    historyData.history.forEach((commit) => {
      const revisionBadge = commit.revision
        ? `<span class="font-bold text-xs bg-primary-200 text-primary-800 dark:bg-primary-700 dark:text-primary-200 px-2 py-1 rounded-full">REV ${commit.revision}</span>`
        : "";
      historyListHtml += `<div class="p-4 bg-gradient-to-r from-primary-100 to-primary-200 dark:from-mc-dark-accent dark:to-primary-700 rounded-lg border border-primary-300 dark:border-mc-dark-accent bg-opacity-95"><div class="flex justify-between items-start"><div><div class="flex items-center space-x-3 text-sm mb-2 flex-wrap gap-y-1"><span class="font-mono font-bold text-accent dark:text-accent">${commit.commit_hash.substring(
        0,
        8
      )}</span>${revisionBadge}<span class="text-primary-600 dark:text-primary-300">${formatDate(
        commit.date
      )}</span></div><div class="text-primary-900 dark:text-primary-200 text-sm mb-1">${
        commit.message
      }</div><div class="text-xs text-primary-600 dark:text-primary-300">Author: ${
        commit.author_name
      }</div></div><div class="flex-shrink-0 ml-4"><a href="/files/${
        historyData.filename
      }/versions/${
        commit.commit_hash
      }" class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 rounded-md hover:bg-opacity-80 transition-colors text-sm font-semibold"><i class="fa-solid fa-file-arrow-down"></i><span>Download</span></a></div></div></div>`;
    });
  } else {
    historyListHtml = `<p class="text-center text-primary-600 dark:text-primary-300">No version history available.</p>`;
  }
  modal.innerHTML = `<div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg w-full max-w-2xl flex flex-col max-h-[90vh] bg-opacity-95 border border-transparent bg-gradient-to-br from-white to-mc-light-accent dark:from-mc-dark-bg dark:to-mc-dark-accent"><div class="flex-shrink-0 flex justify-between items-center p-6 pb-4 border-b border-primary-300 dark:border-mc-dark-accent"><h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100">Version History - ${historyData.filename}</h3><button class="text-primary-600 hover:text-primary-900 dark:text-primary-300 dark:hover:text-accent" onclick="this.closest('.fixed').remove()"><i class="fa-solid fa-xmark text-2xl"></i></button></div><div class="overflow-y-auto p-6 space-y-4">${historyListHtml}</div></div>`;
  document.body.appendChild(modal);
}

function showNewFileDialog() {
  const modal = document.getElementById("newUploadModal");
  const form = document.getElementById("newUploadForm");
  form.reset();
  modal.classList.remove("hidden");
}
async function uploadNewFile(file, description, rev) {
  try {
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
    formData.append("description", description);
    formData.append("rev", rev);
    const response = await fetch(`/files/new_upload`, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    debounceNotifications(`New file '${file.name}' added!`, "success");
  } catch (error) {
    debounceNotifications(`Upload Error: ${error.message}`, "error");
  }
}

async function openSendMessageModal() {
  const modal = document.getElementById("sendMessageModal");
  const userSelect = document.getElementById("recipientUserSelect");
  try {
    const response = await fetch("/users");
    const data = await response.json();
    if (response.ok && data.users) {
      userSelect.innerHTML = '<option value="">Select a user...</option>';
      data.users.forEach((user) => {
        if (user !== currentUser) {
          const option = document.createElement("option");
          option.value = user;
          option.textContent = user;
          userSelect.appendChild(option);
        }
      });
    }
  } catch (error) {
    debounceNotifications("Could not load user list.", "error");
  }
  modal.classList.remove("hidden");
}
async function sendMessage(recipient, message) {
  try {
    const response = await fetch("/messages/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipient: recipient,
        message: message,
        sender: currentUser,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    debounceNotifications("Message sent successfully!", "success");
  } catch (error) {
    debounceNotifications(`Send Error: ${error.message}`, "error");
  }
}
function populateAndShowMessagesModal(messages) {
  const modal = document.getElementById("viewMessagesModal");
  const container = document.getElementById("messageListContainer");
  container.innerHTML = "";
  messages.forEach((msg) => {
    const msgEl = document.createElement("div");
    msgEl.className = "p-4 bg-primary-100 dark:bg-mc-dark-accent rounded-lg";
    msgEl.dataset.messageId = msg.id;
    msgEl.innerHTML = `<div class="flex justify-between items-start"><div><p class="text-sm text-primary-700 dark:text-primary-300">${
      msg.message
    }</p><p class="text-xs text-primary-500 dark:text-primary-400 mt-2">From: <strong>${
      msg.sender
    }</strong> at ${formatDate(
      msg.timestamp
    )}</p></div><button class="ml-4 px-3 py-1 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 js-ack-btn" data-message-id="${
      msg.id
    }">Acknowledge</button></div>`;
    container.appendChild(msgEl);
  });
  modal.classList.remove("hidden");
}
async function acknowledgeMessage(messageId) {
  try {
    const response = await fetch("/messages/acknowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, user: currentUser }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    const msgEl = document.querySelector(`div[data-message-id="${messageId}"]`);
    if (msgEl) msgEl.remove();
    const container = document.getElementById("messageListContainer");
    if (!container.hasChildNodes()) {
      document.getElementById("viewMessagesModal").classList.add("hidden");
    }
  } catch (error) {
    debounceNotifications(`Acknowledgement Error: ${error.message}`, "error");
  }
}

async function cancelCheckout(filename) {
  if (
    !confirm(
      `Are you sure you want to cancel checkout for '${filename}'? Any local changes will be lost.`
    )
  )
    return;
  try {
    const response = await fetch(`/files/${filename}/cancel_checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: currentUser }),
    });
    if (response.ok) {
      debounceNotifications(
        `Checkout for '${filename}' canceled successfully!`,
        "success"
      );
    } else {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Cancel failed");
    }
  } catch (error) {
    debounceNotifications(`Cancel Error: ${error.message}`, "error");
  }
}

function toggleConfigPanel() {
  document.getElementById("configPanel").classList.toggle("translate-x-full");
}
function toggleDarkMode() {
  const htmlEl = document.documentElement;
  if (htmlEl.classList.contains("dark")) {
    htmlEl.classList.remove("dark");
    localStorage.setItem("theme", "light");
  } else {
    htmlEl.classList.add("dark");
    localStorage.setItem("theme", "dark");
  }
}
function applyThemePreference() {
  const savedTheme = localStorage.getItem("theme");
  if (
    savedTheme === "dark" ||
    (!savedTheme && window.matchMedia("(prefers-color-scheme: dark)").matches)
  ) {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}
function showNotification(message, type = "info") {
  const notification = document.createElement("div");
  let bgColor;
  const isDarkMode = document.documentElement.classList.contains("dark");
  switch (type) {
    case "success":
      bgColor = isDarkMode
        ? "bg-gradient-to-r from-green-900 to-green-800"
        : "bg-gradient-to-r from-green-600 to-green-700";
      break;
    case "error":
      bgColor = isDarkMode
        ? "bg-gradient-to-r from-red-900 to-red-800"
        : "bg-gradient-to-r from-red-600 to-red-700";
      break;
    default:
      bgColor = isDarkMode
        ? "bg-gradient-to-r from-accent-hover to-accent"
        : "bg-gradient-to-r from-accent to-accent-hover";
      break;
  }
  notification.className = `fixed top-4 right-4 z-[1000] p-4 rounded-lg shadow-lg text-white transform transition-transform duration-300 translate-x-full ${bgColor} bg-opacity-90`;
  notification.textContent = message;
  document.body.appendChild(notification);
  setTimeout(() => notification.classList.remove("translate-x-full"), 100);
  setTimeout(() => {
    notification.classList.add("translate-x-full");
    setTimeout(() => notification.remove(), 300);
  }, 4000);
}
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

// FIXED: Better date formatting with proper timezone handling
function formatDate(dateString) {
  if (!dateString) return "Unknown";
  try {
    let date;

    // Handle different date string formats
    if (dateString.includes("T") && !dateString.endsWith("Z")) {
      // If it's ISO format without Z, assume it's UTC
      date = new Date(dateString + "Z");
    } else if (dateString.includes("T") && dateString.endsWith("Z")) {
      // Already has Z, it's UTC
      date = new Date(dateString);
    } else {
      // Try to parse as-is first
      date = new Date(dateString);
    }

    if (isNaN(date.getTime())) return "Invalid Date";

    const options = {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    };
    return date.toLocaleString(undefined, options);
  } catch (error) {
    console.error("Error formatting date:", dateString, error);
    return "Date Error";
  }
}

function saveExpandedSubState() {
  const openSubGroups = [];
  document.querySelectorAll(".sub-file-group[open]").forEach((subDetailsEl) => {
    if (subDetailsEl.dataset.subGroupName) {
      openSubGroups.push(subDetailsEl.dataset.subGroupName);
    }
  });
  localStorage.setItem("expandedSubGroups", JSON.stringify(openSubGroups));
}

function saveExpandedState() {
  const openGroups = [];
  document.querySelectorAll(".file-group[open]").forEach((detailsEl) => {
    if (detailsEl.dataset.groupName)
      openGroups.push(detailsEl.dataset.groupName);
  });
  localStorage.setItem("expandedGroups", JSON.stringify(openGroups));
}

document.addEventListener("DOMContentLoaded", function () {
  applyThemePreference();
  loadConfig();
  loadFiles();
  setTimeout(() => connectWebSocket(), 1000);
  document.querySelectorAll('input[name="rev_type"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      const majorRevField = document.getElementById("newMajorRevInput");
      const majorRevLabel = document.querySelector(
        'label[for="newMajorRevInput"]'
      ); // Find the associated label

      if (e.target.value === "major") {
        majorRevField.disabled = false;
        majorRevField.classList.remove("opacity-50", "cursor-not-allowed");
        if (majorRevLabel) majorRevLabel.classList.remove("opacity-50");
      } else {
        majorRevField.disabled = true;
        majorRevField.value = "";
        majorRevField.classList.add("opacity-50", "cursor-not-allowed");
        if (majorRevLabel) majorRevLabel.classList.add("opacity-50");
      }
    });
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && ws && ws.readyState !== WebSocket.OPEN) {
      if (reconnectAttempts < maxReconnectAttempts) connectWebSocket();
    }
  });
  window.addEventListener("beforeunload", () => disconnectWebSocket());
  window.manualRefresh = manualRefresh;
  setInterval(async () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      try {
        const response = await fetch("/refresh");
        if (response.ok) {
          const result = await response.json();
          if (result.message && result.message !== "No changes detected")
            loadFiles();
        }
      } catch (error) {
        console.error("Fallback refresh failed:", error);
      }
    }
  }, 30000);
  document.getElementById("searchInput").addEventListener("input", renderFiles);
  const collapseAllBtn = document.getElementById("collapseAllBtn");
  if (collapseAllBtn) {
    collapseAllBtn.addEventListener("click", () => {
      document
        .querySelectorAll("#fileList details[open]")
        .forEach((detailsEl) => {
          detailsEl.open = false;
        });
      saveExpandedState();
    });
  }
  document.getElementById("fileList").addEventListener("click", (e) => {
    const button = e.target.closest("button, a");
    if (!button || !button.dataset.filename) return;
    const filename = button.dataset.filename;
    if (button.classList.contains("js-checkout-btn")) checkoutFile(filename);
    else if (button.classList.contains("js-checkin-btn"))
      showCheckinDialog(filename);
    else if (button.classList.contains("js-cancel-checkout-btn"))
      cancelCheckout(filename);
    else if (button.classList.contains("js-override-btn"))
      adminOverride(filename);
    else if (button.classList.contains("js-delete-btn"))
      adminDeleteFile(filename);
    else if (button.classList.contains("js-history-btn"))
      viewFileHistory(filename);
  });

  const checkinModal = document.getElementById("checkinModal");
  const checkinForm = document.getElementById("checkinForm");
  const cancelCheckinBtn = document.getElementById("cancelCheckin");
  checkinForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const filename = e.target.dataset.filename;
    const fileInput = document.getElementById("checkinFileUpload");
    const messageInput = document.getElementById("commitMessage");
    const revTypeInput = document.querySelector(
      'input[name="rev_type"]:checked'
    );
    const newMajorRevInput = document.getElementById("newMajorRevInput");
    if (
      filename &&
      fileInput.files.length > 0 &&
      messageInput.value.trim() !== ""
    ) {
      checkinFile(
        filename,
        fileInput.files[0],
        messageInput.value.trim(),
        revTypeInput.value,
        // Pass the value from the input field if rev type is 'major'
        revTypeInput.value === "major" ? newMajorRevInput.value : null
      );
      checkinModal.classList.add("hidden");
    } else {
      debounceNotifications("Please complete all required fields.", "error");
    }
  });
  cancelCheckinBtn.addEventListener("click", () =>
    checkinModal.classList.add("hidden")
  );

  const newUploadModal = document.getElementById("newUploadModal");
  const newUploadForm = document.getElementById("newUploadForm");
  const cancelNewUploadBtn = document.getElementById("cancelNewUpload");
  newUploadForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const fileInput = document.getElementById("newFileUpload");
    const descriptionInput = document.getElementById("newFileDescription");
    const revInput = document.getElementById("newFileRev");
    if (
      fileInput.files.length > 0 &&
      descriptionInput.value.trim() !== "" &&
      revInput.value.trim() !== ""
    ) {
      uploadNewFile(
        fileInput.files[0],
        descriptionInput.value.trim(),
        revInput.value.trim()
      );
      newUploadModal.classList.add("hidden");
    } else {
      debounceNotifications("Please complete all fields.", "error");
    }
  });
  cancelNewUploadBtn.addEventListener("click", () =>
    newUploadModal.classList.add("hidden")
  );

  const sendMessageModal = document.getElementById("sendMessageModal");
  const sendMessageForm = document.getElementById("sendMessageForm");
  document
    .getElementById("cancelSendMessage")
    .addEventListener("click", () => sendMessageModal.classList.add("hidden"));
  sendMessageForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const recipient = document.getElementById("recipientUserSelect").value;
    const message = document.getElementById("messageText").value;
    if (recipient && message) {
      sendMessage(recipient, message);
      sendMessageForm.reset();
      sendMessageModal.classList.add("hidden");
    } else {
      debounceNotifications(
        "Please select a recipient and write a message.",
        "error"
      );
    }
  });

  const messageListContainer = document.getElementById("messageListContainer");
  messageListContainer.addEventListener("click", (e) => {
    const ackButton = e.target.closest(".js-ack-btn");
    if (ackButton) {
      const messageId = ackButton.dataset.messageId;
      acknowledgeMessage(messageId);
    }
  });

  document
    .getElementById("configForm")
    .addEventListener("submit", async function (e) {
      e.preventDefault();
      const tokenInput = document.getElementById("token");
      const formData = {
        gitlab_url: document.getElementById("gitlabUrl").value,
        project_id: document.getElementById("projectId").value,
        username: document.getElementById("username").value,
      };
      if (tokenInput.value) formData.token = tokenInput.value;
      try {
        debounceNotifications("Saving configuration...", "info");
        const response = await fetch("/config/gitlab", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail);
        debounceNotifications("Configuration saved! Refreshing...", "success");
        toggleConfigPanel();
        await loadConfig();
        await loadFiles();
        disconnectWebSocket();
        connectWebSocket();
        tokenInput.value = "";
      } catch (error) {
        debounceNotifications(`Config Error: ${error.message}`, "error");
      }
    });
});
