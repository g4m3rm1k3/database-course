// ==================================================================
//               Mastercam GitLab Interface Script
//             (Updated with Confirmed Checkout Logic)
// ==================================================================

// -- Global Variables --
let currentUser = "demo_user";
let ws = null;
let groupedFiles = {};
let currentConfig = null;
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

  console.log(
    `Attempting WebSocket connection (attempt ${
      reconnectAttempts + 1
    }/${maxReconnectAttempts})`
  );
  ws = new WebSocket(wsUrl);

  ws.onopen = function () {
    console.log("WebSocket connected successfully");
    updateConnectionStatus(true);
    reconnectAttempts = 0;
    ws.send(`SET_USER:${currentUser}`);
    ws.send("REFRESH_FILES");
  };

  ws.onmessage = function (event) {
    console.log("WebSocket message received:", event.data);
    handleWebSocketMessage(event.data);
  };

  ws.onclose = function (event) {
    console.log(
      "WebSocket disconnected. Code:",
      event.code,
      "Reason:",
      event.reason
    );
    updateConnectionStatus(false);

    if (isManualDisconnect) {
      isManualDisconnect = false;
      return;
    }

    if (reconnectAttempts < maxReconnectAttempts) {
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      console.log(`Attempting to reconnect in ${delay}ms...`);
      reconnectTimeout = setTimeout(() => {
        reconnectAttempts++;
        connectWebSocket();
      }, delay);
    } else {
      console.error(
        "Max reconnection attempts reached. Please refresh the page."
      );
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
      console.log("Received real-time file list update");
      groupedFiles = data.payload || {};
      renderFiles();
      debounceNotifications("File list updated", "info");
    } else {
      console.log("Received unknown message type:", data.type);
    }
  } catch (error) {
    console.log("Received non-JSON WebSocket message:", message);
  }
}

function manualRefresh() {
  console.log("Manual refresh requested");
  loadFiles();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send("REFRESH_FILES");
  }
}

// -- Updated Data Loading and Rendering --
async function loadFiles() {
  try {
    console.log("Loading files from API...");
    const response = await fetch("/files");
    if (!response.ok) {
      throw new Error(
        `Server responded with ${response.status}: ${response.statusText}`
      );
    }

    const data = await response.json();
    if (typeof data === "object" && data !== null && !Array.isArray(data)) {
      groupedFiles = data;
      console.log(
        "Files loaded successfully:",
        Object.keys(groupedFiles).length,
        "groups"
      );
    } else {
      console.warn("Unexpected data format received:", typeof data);
      groupedFiles = {};
    }

    renderFiles();
    updateRepoStatus("Ready");
  } catch (error) {
    console.error("Error loading files:", error);
    debounceNotifications(`Error loading files: ${error.message}`, "error");
    updateRepoStatus("Error");

    groupedFiles = {
      Miscellaneous: [
        {
          filename: "demo_connection_error.mcam",
          path: "demo_connection_error.mcam",
          status: "unlocked",
          size: 0,
          modified_at: new Date().toISOString(),
        },
      ],
    };
    renderFiles();
  }
}

function renderFiles() {
  const fileListEl = document.getElementById("fileList");
  const searchTerm = document.getElementById("searchInput").value.toLowerCase();
  const expandedGroups =
    JSON.parse(localStorage.getItem("expandedGroups")) || [];

  fileListEl.innerHTML = "";
  let totalFilesFound = 0;

  if (!groupedFiles || Object.keys(groupedFiles).length === 0) {
    fileListEl.innerHTML = `
      <div class="flex flex-col items-center justify-center py-12 text-primary-600 dark:text-primary-300">
        <i class="fa-solid fa-exclamation-triangle text-6xl mb-4"></i>
        <h3 class="text-2xl font-semibold">No Connection</h3>
        <p class="mt-2 text-center">Unable to load files. Check your configuration.</p>
        <button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-accent to-accent-hover text-white rounded-md hover:bg-opacity-80">
          Try Again
        </button>
      </div>`;
    return;
  }

  const groupOrder = [
    "12XXXXX",
    "48XXXXX",
    "49XXXXX",
    "74XXXXX",
    "Miscellaneous",
  ];
  const sortedGroupNames = Object.keys(groupedFiles).sort((a, b) => {
    const indexA =
      groupOrder.indexOf(a) === -1 ? Infinity : groupOrder.indexOf(a);
    const indexB =
      groupOrder.indexOf(b) === -1 ? Infinity : groupOrder.indexOf(b);
    return indexA - indexB;
  });

  sortedGroupNames.forEach((groupName) => {
    const filesInGroup = groupedFiles[groupName];
    if (!Array.isArray(filesInGroup)) {
      console.warn(`Invalid files data for group ${groupName}:`, filesInGroup);
      return;
    }

    const filteredFiles = filesInGroup.filter(
      (file) =>
        file.filename.toLowerCase().includes(searchTerm) ||
        file.path.toLowerCase().includes(searchTerm)
    );

    if (filteredFiles.length === 0) return;
    totalFilesFound += filteredFiles.length;

    const detailsEl = document.createElement("details");
    detailsEl.className =
      "file-group group border-t border-primary-300 dark:border-mc-dark-accent";
    detailsEl.dataset.groupName = groupName;
    if (expandedGroups.includes(groupName)) detailsEl.open = true;
    detailsEl.addEventListener("toggle", saveExpandedState);

    const summaryEl = document.createElement("summary");
    summaryEl.className =
      "list-none py-3 px-4 bg-gradient-to-r from-mc-light-accent to-white dark:from-mc-dark-accent dark:to-mc-dark-bg cursor-pointer hover:bg-opacity-80 flex justify-between items-center transition-colors";

    const summaryLeft = document.createElement("div");
    summaryLeft.className = "flex items-center space-x-3";
    const icon = document.createElement("i");
    icon.className =
      "fa-solid fa-chevron-right text-xs text-primary-600 dark:text-primary-300 transform transition-transform duration-200 group-open:rotate-90";
    const titleSpan = document.createElement("span");
    titleSpan.className =
      "font-semibold text-primary-800 dark:text-primary-200";
    titleSpan.textContent = groupName.endsWith("XXXXX")
      ? `${groupName} SERIES`
      : groupName;
    summaryLeft.append(icon, titleSpan);

    const countSpan = document.createElement("span");
    countSpan.className =
      "text-sm font-medium text-primary-600 dark:text-primary-300";
    countSpan.textContent = `(${filteredFiles.length} files)`;

    summaryEl.append(summaryLeft, countSpan);
    detailsEl.appendChild(summaryEl);

    const filesContainer = document.createElement("div");
    filteredFiles.forEach((file) => {
      const fileEl = document.createElement("div");
      fileEl.id = `file-${file.filename.replace(/[^a-zA-Z0-9]/g, "-")}`;
      let statusClass = "",
        statusBadgeText = "";

      switch (file.status) {
        case "unlocked":
          statusClass =
            "bg-gradient-to-r from-green-100 to-green-200 text-green-900 dark:from-green-900 dark:to-green-800 dark:text-green-200";
          statusBadgeText = "Available";
          break;
        case "locked":
          statusClass =
            "bg-gradient-to-r from-red-100 to-red-200 text-red-900 dark:from-red-900 dark:to-red-800 dark:text-red-200";
          statusBadgeText = `Locked by ${file.locked_by}`;
          break;
        case "checked_out_by_user":
          statusClass =
            "bg-gradient-to-r from-blue-100 to-blue-200 text-blue-900 dark:from-blue-900 dark:to-blue-800 dark:text-blue-200";
          statusBadgeText = "Checked out by you";
          break;
        default:
          statusClass =
            "bg-gradient-to-r from-primary-100 to-primary-200 text-primary-900 dark:from-primary-600 dark:to-primary-700 dark:text-primary-200";
          statusBadgeText = "Unknown";
      }

      const actionsHtml = getActionButtons(file);
      fileEl.className =
        "py-6 px-4 bg-white dark:bg-mc-dark-bg hover:bg-opacity-80 transition-colors duration-200 border-b border-primary-300 dark:border-mc-dark-accent bg-opacity-95";
      fileEl.innerHTML = `
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0">
            <div class="flex items-center space-x-4">
                <h3 class="text-lg font-semibold text-primary-900 dark:text-primary-100">${
                  file.filename
                }</h3>
                <span class="text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}">${statusBadgeText}</span>
            </div>
            <div class="flex items-center space-x-2 flex-wrap">${actionsHtml}</div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4 text-primary-700 dark:text-primary-300 text-sm">
            <div class="flex items-center space-x-2">
                <i class="fa-solid fa-file text-primary-600 dark:text-primary-300"></i>
                <span>Path: ${file.path}</span>
            </div>
            <div class="flex items-center space-x-2">
                <i class="fa-solid fa-hard-drive text-primary-600 dark:text-primary-300"></i>
                <span>Size: ${formatBytes(file.size)}</span>
            </div>
            <div class="flex items-center space-x-2">
                <i class="fa-solid fa-clock text-primary-600 dark:text-primary-300"></i>
                <span>Modified: ${formatDate(file.modified_at)}</span>
            </div>
            ${
              file.locked_by && file.status !== "checked_out_by_user"
                ? `<div class="flex items-center space-x-2 sm:col-span-2 lg:col-span-1">
                <i class="fa-solid fa-lock text-primary-600 dark:text-primary-300"></i>
                <span>Locked by: ${file.locked_by} at ${formatDate(
                    file.locked_at
                  )}</span>
              </div>`
                : ""
            }
        </div>`;
      filesContainer.appendChild(fileEl);
    });
    detailsEl.appendChild(filesContainer);
    fileListEl.appendChild(detailsEl);
  });

  if (totalFilesFound === 0) {
    fileListEl.innerHTML = `
      <div class="flex flex-col items-center justify-center py-12 text-primary-600 dark:text-primary-300">
        <i class="fa-solid fa-folder-open text-6xl mb-4"></i>
        <h3 class="text-2xl font-semibold">No files found</h3>
        <p class="mt-2 text-center">No Mastercam files match your search criteria.</p>
        <button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-accent to-accent-hover text-white rounded-md hover:bg-opacity-80">
          Refresh
        </button>
      </div>`;
  }
}

async function loadConfig() {
  try {
    const response = await fetch("/config");
    currentConfig = await response.json();
    updateConfigDisplay();
  } catch (error) {
    console.error("Error loading config:", error);
  }
}

// -- Updated UI Functions --
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

// -- Action Button and Event Handlers --
function getActionButtons(file) {
  const btnClass =
    "flex items-center space-x-2 px-4 py-2 rounded-md transition-colors text-sm font-semibold";
  let buttons = "";
  if (file.status === "unlocked") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-green-600 to-green-700 text-white hover:bg-opacity-80 js-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-download"></i><span>Checkout</span></button>`;
  } else if (file.status === "checked_out_by_user") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-blue-600 to-blue-700 text-white hover:bg-opacity-80 js-checkin-btn" data-filename="${file.filename}"><i class="fa-solid fa-upload"></i><span>Check In</span></button>`;
    buttons += `<a href="/files/${file.filename}/download" class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80"><i class="fa-solid fa-file-arrow-down"></i><span>Download</span></a>`;
  } else if (file.status === "locked" && file.locked_by !== currentUser) {
    buttons += `<a href="/files/${file.filename}/download" class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80"><i class="fa-solid fa-eye"></i><span>View</span></a>`;
    buttons += `<button class="${btnClass} bg-gradient-to-r from-red-600 to-red-700 text-white hover:bg-opacity-80 js-override-btn" data-filename="${file.filename}"><i class="fa-solid fa-unlock"></i><span>Admin Override</span></button>`;
  }
  buttons += `<button class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80 js-history-btn" data-filename="${file.filename}"><i class="fa-solid fa-history"></i><span>History</span></button>`;
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
    } else if (response.status === 409) {
      const errorData = await response.json();
      debounceNotifications(`Checkout Failed: ${errorData.detail}`, "error");
      revertFileStateFromLoading(filename);
    } else {
      const errorData = await response.json();
      throw new Error(errorData.detail || "An unknown server error occurred.");
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
      checkoutBtn.innerHTML = `
        <i class="fa-solid fa-spinner fa-spin"></i>
        <span>Locking...</span>
      `;
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
      checkoutBtn.innerHTML = `
        <i class="fa-solid fa-download"></i>
        <span>Checkout</span>
      `;
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

async function checkinFile(filename, file, commitMessage) {
  try {
    debounceNotifications(`Uploading ${filename}...`, "info");
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
    formData.append("commit_message", commitMessage);
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

async function viewFileHistory(filename) {
  try {
    const response = await fetch(`/files/${filename}/history`);
    const result = await response.json();
    if (response.ok) showFileHistoryModal(result);
    else debounceNotifications("Error loading file history", "error");
  } catch (error) {
    debounceNotifications("Error loading file history", "error");
  }
}

function showFileHistoryModal(historyData) {
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100]";

  let historyHtml = `
      <div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-opacity-95 border border-transparent bg-gradient-to-br from-white to-mc-light-accent dark:from-mc-dark-bg dark:to-mc-dark-accent">
        <div class="flex justify-between items-center mb-4 pb-2 border-b border-primary-300 dark:border-mc-dark-accent">
          <h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100">Version History - ${historyData.filename}</h3>
          <button class="text-primary-600 hover:text-primary-900 dark:text-primary-300 dark:hover:text-accent" onclick="this.closest('.fixed').remove()">
            <i class="fa-solid fa-xmark text-2xl"></i>
          </button>
        </div>`;

  if (historyData.history && historyData.history.length > 0) {
    historyHtml += '<div class="space-y-4">';
    historyData.history.forEach((commit) => {
      historyHtml += `
              <div class="p-4 bg-gradient-to-r from-primary-100 to-primary-200 dark:from-mc-dark-accent dark:to-primary-700 rounded-lg border border-primary-300 dark:border-mc-dark-accent bg-opacity-95">
                  <div class="flex justify-between items-start">
                      <div>
                          <div class="flex items-center space-x-3 text-sm mb-1">
                              <span class="font-mono font-bold text-accent dark:text-accent">${commit.commit_hash.substring(
                                0,
                                8
                              )}</span>
                              <span class="text-primary-600 dark:text-primary-300">${formatDate(
                                commit.date
                              )}</span>
                          </div>
                          <div class="text-primary-900 dark:text-primary-200 text-sm mb-1">${
                            commit.message
                          }</div>
                          <div class="text-xs text-primary-600 dark:text-primary-300">Author: ${
                            commit.author_name
                          }</div>
                      </div>
                      <div class="flex-shrink-0 ml-4">
                          <a href="/files/${historyData.filename}/versions/${
        commit.commit_hash
      }" class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 rounded-md hover:bg-opacity-80 transition-colors text-sm font-semibold">
                              <i class="fa-solid fa-file-arrow-down"></i>
                              <span>Download</span>
                          </a>
                      </div>
                  </div>
              </div>`;
    });
    historyHtml += "</div>";
  } else {
    historyHtml +=
      '<p class="text-center text-primary-600 dark:text-primary-300">No version history available.</p>';
  }

  historyHtml += `</div>`;
  modal.innerHTML = historyHtml;
  document.body.appendChild(modal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.remove();
  });
}

function showNewFileDialog() {
  const input = document.getElementById("newFileUpload");
  input.onchange = () => {
    if (input.files[0]) uploadNewFile(input.files[0]);
  };
  input.click();
}

async function uploadNewFile(file) {
  try {
    debounceNotifications(`Adding new file '${file.name}'...`, "info");
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
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

// -- UI Toggles and Theme --
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

// -- Utility Functions --
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

function formatDate(dateString) {
  if (!dateString) return "Unknown";
  return new Date(dateString).toLocaleString();
}

function saveExpandedState() {
  const openGroups = [];
  document.querySelectorAll(".file-group[open]").forEach((detailsEl) => {
    if (detailsEl.dataset.groupName)
      openGroups.push(detailsEl.dataset.groupName);
  });
  localStorage.setItem("expandedGroups", JSON.stringify(openGroups));
}

// -- Initial Setup --
document.addEventListener("DOMContentLoaded", function () {
  applyThemePreference();
  loadConfig();
  loadFiles();
  setTimeout(() => connectWebSocket(), 1000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && ws && ws.readyState !== WebSocket.OPEN) {
      console.log("Tab became visible, checking WebSocket connection...");
      if (reconnectAttempts < maxReconnectAttempts) connectWebSocket();
    }
  });
  window.addEventListener("beforeunload", () => disconnectWebSocket());
  window.manualRefresh = manualRefresh;
  setInterval(async () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log("WebSocket disconnected, doing fallback refresh...");
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
  document.getElementById("fileList").addEventListener("click", (e) => {
    const button = e.target.closest("button, a");
    if (!button) return;
    const filename = button.dataset.filename;
    if (button.classList.contains("js-checkout-btn")) checkoutFile(filename);
    else if (button.classList.contains("js-checkin-btn"))
      showCheckinDialog(filename);
    else if (button.classList.contains("js-override-btn"))
      adminOverride(filename);
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
    if (
      filename &&
      fileInput.files.length > 0 &&
      messageInput.value.trim() !== ""
    ) {
      checkinFile(filename, fileInput.files[0], messageInput.value.trim());
      checkinModal.classList.add("hidden");
    } else {
      debounceNotifications(
        "Please provide a file and a commit message.",
        "error"
      );
    }
  });
  cancelCheckinBtn.addEventListener("click", () =>
    checkinModal.classList.add("hidden")
  );
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
