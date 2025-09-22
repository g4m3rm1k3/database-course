// ==================================================================
//               Mastercam GitLab Interface Script
//                    (Final Corrected Version)
// ==================================================================

// -- Global Variables --
let currentUser = "demo_user";
let ws = null;
let groupedFiles = {};
let currentConfig = null;

// -- WebSocket Management --
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${
    window.location.host
  }/ws?user=${encodeURIComponent(currentUser)}`;
  ws = new WebSocket(wsUrl);

  ws.onopen = function () {
    console.log("WebSocket connected");
    updateConnectionStatus(true);
    ws.send(`SET_USER:${currentUser}`);
  };

  ws.onmessage = function (event) {
    console.log("WebSocket message:", event.data);
    handleWebSocketMessage(event.data);
  };

  ws.onclose = function () {
    console.log("WebSocket disconnected");
    updateConnectionStatus(false);
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = function (error) {
    console.error("WebSocket error:", error);
    updateConnectionStatus(false);
  };

  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send("PING");
  }, 30000);
}

function handleWebSocketMessage(message) {
  try {
    const data = JSON.parse(message);
    if (data.type === "FILE_LIST_UPDATED") {
      console.log("Received real-time file list update.");
      groupedFiles = data.payload;
      renderFiles();
      showNotification("File list updated automatically.", "info");
    }
  } catch (error) {
    console.log("Received non-JSON WebSocket message:", message);
  }
}

// -- Data Loading and Rendering --
async function loadFiles() {
  try {
    const response = await fetch("/files");
    if (!response.ok)
      throw new Error(`Server responded with ${response.status}`);
    const data = await response.json();

    if (typeof data === "object" && data !== null && !Array.isArray(data)) {
      groupedFiles = data;
    } else {
      groupedFiles = {};
    }
    renderFiles();
    updateRepoStatus("Ready");
  } catch (error) {
    console.error("Error loading files:", error);
    showNotification("Error loading files", "error");
    updateRepoStatus("Error");
  }
}

function renderFiles() {
  const fileListEl = document.getElementById("fileList");
  const searchTerm = document.getElementById("searchInput").value.toLowerCase();
  const expandedGroups =
    JSON.parse(localStorage.getItem("expandedGroups")) || [];
  fileListEl.innerHTML = "";
  let totalFilesFound = 0;

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
    if (!Array.isArray(filesInGroup)) return;
    const filteredFiles = filesInGroup.filter(
      (file) =>
        file.filename.toLowerCase().includes(searchTerm) ||
        file.path.toLowerCase().includes(searchTerm)
    );

    if (filteredFiles.length === 0) return;
    totalFilesFound += filteredFiles.length;

    const detailsEl = document.createElement("details");
    detailsEl.className =
      "file-group group border-t border-gray-200 dark:border-gray-600";
    detailsEl.dataset.groupName = groupName;
    if (expandedGroups.includes(groupName)) detailsEl.open = true;
    detailsEl.addEventListener("toggle", saveExpandedState);

    const summaryEl = document.createElement("summary");
    summaryEl.className =
      "list-none py-3 px-4 bg-gray-50 dark:bg-gray-800 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 flex justify-between items-center transition-colors";

    const summaryLeft = document.createElement("div");
    summaryLeft.className = "flex items-center space-x-3";
    const icon = document.createElement("i");
    icon.className =
      "fa-solid fa-chevron-right text-xs text-gray-500 dark:text-gray-400 transform transition-transform duration-200 group-open:rotate-90";
    const titleSpan = document.createElement("span");
    titleSpan.className = "font-semibold text-gray-700 dark:text-gray-200";
    titleSpan.textContent = groupName.endsWith("XXXXX")
      ? `${groupName} SERIES`
      : groupName;
    summaryLeft.append(icon, titleSpan);

    const countSpan = document.createElement("span");
    countSpan.className =
      "text-sm font-medium text-gray-500 dark:text-gray-400";
    countSpan.textContent = `(${filteredFiles.length} files)`;

    summaryEl.append(summaryLeft, countSpan);
    detailsEl.appendChild(summaryEl);

    const filesContainer = document.createElement("div");
    filteredFiles.forEach((file) => {
      const fileEl = document.createElement("div");
      let statusClass = "",
        statusBadgeText = "";
      switch (file.status) {
        case "unlocked":
          statusClass =
            "bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-100";
          statusBadgeText = "Available";
          break;
        case "locked":
          statusClass =
            "bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-100";
          statusBadgeText = `Locked by ${file.locked_by}`;
          break;
        case "checked_out_by_user":
          statusClass =
            "bg-blue-100 text-blue-800 dark:bg-gold-500 dark:text-black";
          statusBadgeText = "Checked out by you";
          break;
      }
      const actionsHtml = getActionButtons(file);
      fileEl.className =
        "py-6 px-4 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors duration-200 border-b border-gray-200 dark:border-gray-600";
      fileEl.innerHTML = `
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0">
            <div class="flex items-center space-x-4"><h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">${
              file.filename
            }</h3><span class="text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}">${statusBadgeText}</span></div>
            <div class="flex items-center space-x-2 flex-wrap">${actionsHtml}</div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4 text-gray-600 dark:text-gray-300 text-sm">
            <div class="flex items-center space-x-2"><i class="fa-solid fa-file text-gray-500 dark:text-gray-400"></i><span>Path: ${
              file.path
            }</span></div>
            <div class="flex items-center space-x-2"><i class="fa-solid fa-hard-drive text-gray-500 dark:text-gray-400"></i><span>Size: ${formatBytes(
              file.size
            )}</span></div>
            <div class="flex items-center space-x-2"><i class="fa-solid fa-clock text-gray-500 dark:text-gray-400"></i><span>Modified: ${formatDate(
              file.modified_at
            )}</span></div>
            ${
              file.locked_by && file.status !== "checked_out_by_user"
                ? `<div class="flex items-center space-x-2 sm:col-span-2 lg:col-span-1"><i class="fa-solid fa-lock text-gray-500 dark:text-gray-400"></i><span>Locked by: ${
                    file.locked_by
                  } at ${formatDate(file.locked_at)}</span></div>`
                : ""
            }
        </div>`;
      filesContainer.appendChild(fileEl);
    });
    detailsEl.appendChild(filesContainer);
    fileListEl.appendChild(detailsEl);
  });

  if (totalFilesFound === 0) {
    fileListEl.innerHTML = `<div class="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400"><i class="fa-solid fa-folder-open text-6xl mb-4"></i><h3 class="text-2xl font-semibold">No files found</h3><p class="mt-2 text-center">No Mastercam files match your search criteria.</p></div>`;
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

// -- UI Update Functions --
function updateConnectionStatus(connected) {
  const statusEl = document.getElementById("connectionStatus");
  const textEl = document.getElementById("connectionText");
  statusEl.className = `w-3 h-3 rounded-full animate-pulse ${
    connected ? "bg-green-500" : "bg-red-500"
  }`;
  textEl.textContent = connected ? "Connected" : "Disconnected";
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
  let buttons = "";
  const btnClass =
    "flex items-center space-x-2 px-4 py-2 rounded-md transition-colors text-sm font-semibold";
  if (file.status === "unlocked") {
    buttons += `<button class="${btnClass} bg-blue-500 text-white hover:bg-blue-600" onclick="checkoutFile('${file.filename}')"><i class="fa-solid fa-download"></i><span>Checkout</span></button>`;
  } else if (file.status === "checked_out_by_user") {
    buttons += `<button class="${btnClass} bg-gold-500 text-black hover:bg-gold-600" onclick="showCheckinDialog('${file.filename}')"><i class="fa-solid fa-upload"></i><span>Check In</span></button>`;
    buttons += `<a href="/files/${file.filename}/download" class="${btnClass} bg-gray-300 dark:bg-gray-600 text-gray-800 dark:text-gray-200 hover:bg-gray-400 dark:hover:bg-gray-500"><i class="fa-solid fa-file-arrow-down"></i><span>Download</span></a>`;
  } else if (file.status === "locked" && file.locked_by !== currentUser) {
    buttons += `<a href="/files/${file.filename}/download" class="${btnClass} bg-gray-300 dark:bg-gray-600 text-gray-800 dark:text-gray-200 hover:bg-gray-400 dark:hover:bg-gray-500"><i class="fa-solid fa-eye"></i><span>View</span></a>`;
    buttons += `<button class="${btnClass} bg-red-500 text-white hover:bg-red-600" onclick="adminOverride('${file.filename}')"><i class="fa-solid fa-unlock"></i><span>Admin Override</span></button>`;
  }
  buttons += `<button class="${btnClass} bg-gray-300 dark:bg-gray-600 text-gray-800 dark:text-gray-200 hover:bg-gray-400 dark:hover:bg-gray-500" onclick="viewFileHistory('${file.filename}')"><i class="fa-solid fa-history"></i><span>History</span></button>`;
  return buttons;
}

async function checkoutFile(filename) {
  try {
    const response = await fetch(`/files/${filename}/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: currentUser }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    showNotification(`File '${filename}' checked out successfully!`, "success");
  } catch (error) {
    showNotification(`Checkout Error: ${error.message}`, "error");
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
    showNotification(`Uploading ${filename}...`, "info");
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
    formData.append("commit_message", commitMessage);
    const response = await fetch(`/files/${filename}/checkin`, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    showNotification(`File '${filename}' checked in successfully!`, "success");
  } catch (error) {
    showNotification(`Check-in Error: ${error.message}`, "error");
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
    if (!response.ok) throw new Error(result.detail);
    showNotification(`File '${filename}' lock overridden!`, "success");
  } catch (error) {
    showNotification(`Override Error: ${error.message}`, "error");
  }
}

async function viewFileHistory(filename) {
  try {
    const response = await fetch(`/files/${filename}/history`);
    const result = await response.json();
    if (response.ok) showFileHistoryModal(result);
    else showNotification("Error loading file history", "error");
  } catch (error) {
    showNotification("Error loading file history", "error");
  }
}

function showFileHistoryModal(historyData) {
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-gray-900 bg-opacity-75 flex items-center justify-center p-4 z-[100]";
  let historyHtml = `<div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto text-gray-900 dark:text-gray-100"><div class="flex justify-between items-center mb-4 pb-2 border-b border-gray-200 dark:border-gray-700"><h3 class="text-xl font-semibold text-gray-800 dark:text-gold-500">Version History - ${historyData.filename}</h3><button class="text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gold-500" onclick="this.closest('.fixed').remove()"><i class="fa-solid fa-xmark text-2xl"></i></button></div>`;
  if (historyData.history && historyData.history.length > 0) {
    historyHtml += '<div class="space-y-4">';
    historyData.history.forEach((commit) => {
      historyHtml += `<div class="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600"><div class="flex justify-between items-center text-sm mb-1"><span class="font-bold text-gray-800 dark:text-gold-500">${commit.commit_hash.substring(
        0,
        8
      )}</span><span class="text-gray-500 dark:text-gray-400">${formatDate(
        commit.date
      )}</span></div><div class="text-gray-700 dark:text-gray-300 text-sm mb-1">${
        commit.message
      }</div><div class="text-xs text-gray-500 dark:text-gray-400">Author: ${
        commit.author_name
      }</div></div>`;
    });
    historyHtml += "</div>";
  } else {
    historyHtml +=
      '<p class="text-center text-gray-500 dark:text-gray-400">No version history available.</p>';
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
    showNotification(`Adding new file '${file.name}'...`, "info");
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
    const response = await fetch(`/files/new_upload`, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail);
    showNotification(`New file '${file.name}' added!`, "success");
  } catch (error) {
    showNotification(`Upload Error: ${error.message}`, "error");
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
      bgColor = isDarkMode ? "bg-green-700" : "bg-green-500";
      break;
    case "error":
      bgColor = isDarkMode ? "bg-red-700" : "bg-red-500";
      break;
    default:
      bgColor = isDarkMode ? "bg-blue-700" : "bg-blue-500";
      break;
  }
  notification.className = `fixed top-4 right-4 z-[1000] p-4 rounded-lg shadow-lg text-white transform transition-transform duration-300 translate-x-full ${bgColor}`;
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
  connectWebSocket();
  loadConfig();
  loadFiles(); // Load files on initial page load

  document.getElementById("searchInput").addEventListener("input", renderFiles);

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
      showNotification("Please provide a file and a commit message.", "error");
    }
  });

  cancelCheckinBtn.addEventListener("click", () => {
    checkinModal.classList.add("hidden");
  });

  document
    .getElementById("configForm")
    .addEventListener("submit", async function (e) {
      e.preventDefault();
      const formData = {
        gitlab_url: document.getElementById("gitlabUrl").value,
        project_id: document.getElementById("projectId").value,
        username: document.getElementById("username").value,
        token: document.getElementById("token").value,
      };
      try {
        showNotification("Saving configuration...", "info");
        const response = await fetch("/config/gitlab", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail);
        showNotification("Configuration saved! Re-initializing...", "success");
        toggleConfigPanel();
      } catch (error) {
        showNotification(`Config Error: ${error.message}`, "error");
      }
    });
});
