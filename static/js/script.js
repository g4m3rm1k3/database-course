// ==================================================================
//               Mastercam GitLab Interface Script
//               (Complete and Corrected Version)
// ==================================================================

// -- Global Variables --
let currentUser = "demo_user";
let ws = null;
let groupedFiles = {}; // Use one variable to store the grouped file object
let currentConfig = null;

// -- WebSocket Management --
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${
    window.location.host
  }/ws?user=${encodeURIComponent(currentUser)}`;
  ws = new WebSocket(wsUrl);

  ws.onopen = function (event) {
    console.log("WebSocket connected");
    updateConnectionStatus(true);
    ws.send(`SET_USER:${currentUser}`);
  };

  ws.onmessage = function (event) {
    console.log("WebSocket message:", event.data);
    handleWebSocketMessage(event.data);
  };

  ws.onclose = function (event) {
    console.log("WebSocket disconnected");
    updateConnectionStatus(false);
    setTimeout(connectWebSocket, 3000); // Attempt to reconnect
  };

  ws.onerror = function (error) {
    console.error("WebSocket error:", error);
    updateConnectionStatus(false);
  };

  // Keep-alive ping
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("PING");
    }
  }, 30000);
}

function handleWebSocketMessage(message) {
  const actions = {
    FILE_STATUS_CHANGED: () => showNotification(`File status updated.`, "info"),
    FILE_COMMITTED: (parts) =>
      showNotification(`File ${parts[1]} committed successfully.`, "success"),
    FILE_ADD_FAILED: (parts) =>
      showNotification(`Failed to add new file ${parts[1]}.`, "error"),
    FILE_COMMIT_FAILED: (parts) =>
      showNotification(`Failed to commit file ${parts[1]}.`, "error"),
    FILE_ADDED: (parts) =>
      showNotification(`New file ${parts[1]} added successfully.`, "success"),
  };

  const [command, ...parts] = message.split(":");
  if (actions[command]) {
    actions[command](parts);
    loadFiles(); // Refresh the file list for most actions
  }
}

// -- Data Loading and Rendering --
async function loadFiles() {
  try {
    const response = await fetch("/files");
    const data = await response.json();

    if (typeof data === "object" && data !== null && !Array.isArray(data)) {
      groupedFiles = data;
    } else {
      console.error("API did not return a grouped object:", data);
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
    if (!Array.isArray(filesInGroup)) {
      console.warn(`Data for group "${groupName}" is not an array, skipping.`);
      return;
    }
    const filteredFiles = filesInGroup.filter(
      (file) =>
        file.filename.toLowerCase().includes(searchTerm) ||
        file.path.toLowerCase().includes(searchTerm)
    );

    if (filteredFiles.length === 0) {
      return;
    }

    totalFilesFound += filteredFiles.length;

    const detailsEl = document.createElement("details");
    detailsEl.className =
      "file-group group border-t border-gray-200 dark:border-gray-600";

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

    summaryLeft.appendChild(icon);
    summaryLeft.appendChild(titleSpan);

    const countSpan = document.createElement("span");
    countSpan.className =
      "text-sm font-medium text-gray-500 dark:text-gray-400";
    countSpan.textContent = `(${filteredFiles.length} files)`;

    summaryEl.appendChild(summaryLeft);
    summaryEl.appendChild(countSpan);
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
            <div class="flex items-center space-x-4">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">${
                  file.filename
                }</h3>
                <span class="text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}">${statusBadgeText}</span>
            </div>
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
              file.version_info
                ? `<div class="flex items-center space-x-2"><i class="fa-solid fa-code-commit text-gray-500 dark:text-gray-400"></i><span>Version: ${file.version_info.latest_commit} (${file.version_info.commit_count} commits)</span></div>`
                : ""
            }
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
    fileListEl.innerHTML = `
      <div class="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
        <i class="fa-solid fa-folder-open text-6xl mb-4"></i>
        <h3 class="text-2xl font-semibold">No files found</h3>
        <p class="mt-2 text-center">No Mastercam files match your search criteria.</p>
      </div>
    `;
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
  if (file.status === "unlocked") {
    buttons += `<button class="flex items-center space-x-2 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors text-sm" onclick="checkoutFile('${file.filename}')"><i class="fa-solid fa-download"></i><span>Checkout</span></button>`;
  } else if (
    file.status === "checked_out_by_user" ||
    (file.status === "locked" && file.locked_by === currentUser)
  ) {
    buttons += `<button class="flex items-center space-x-2 px-4 py-2 bg-gold-500 text-black rounded-md hover:bg-gold-600 transition-colors text-sm" onclick="showCheckinDialog('${file.filename}')"><i class="fa-solid fa-upload"></i><span>Check In</span></button>`;
  } else if (file.status === "locked" && file.locked_by !== currentUser) {
    buttons += `<button class="flex items-center space-x-2 px-4 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors text-sm" onclick="adminOverride('${file.filename}')"><i class="fa-solid fa-unlock"></i><span>Admin Override</span></button>`;
  }
  buttons += `<button class="flex items-center space-x-2 px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-md hover:bg-gray-400 dark:hover:bg-gray-500 transition-colors text-sm" onclick="viewFileHistory('${file.filename}')"><i class="fa-solid fa-history"></i><span>History</span></button>`;
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
    if (response.ok) {
      showNotification(
        `File '${filename}' checked out successfully!`,
        "success"
      );
      loadFiles();
      if (confirm("Would you like to download the file now?")) {
        window.location.href = `/files/${filename}/download`;
      }
    } else {
      showNotification(`Error: ${result.detail}`, "error");
    }
  } catch (error) {
    console.error("Error checking out file:", error);
    showNotification("Error checking out file", "error");
  }
}

function showCheckinDialog(filename) {
  const input = document.getElementById("fileUpload");
  input.onchange = function (event) {
    const file = event.target.files[0];
    if (file) {
      checkinFile(filename, file);
    }
  };
  input.click();
}

async function checkinFile(filename, file) {
  try {
    showNotification(`Uploading ${filename}...`, "info");
    const formData = new FormData();
    formData.append("user", currentUser);
    formData.append("file", file);
    const response = await fetch(`/files/${filename}/checkin`, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (response.ok) {
      showNotification(`File '${filename}' is being processed`, "success");
      loadFiles();
    } else {
      showNotification(`Error: ${result.detail}`, "error");
    }
  } catch (error) {
    console.error("Error checking in file:", error);
    showNotification("Error checking in file", "error");
  }
}

async function adminOverride(filename) {
  if (
    !confirm(`Are you sure you want to override the lock on '${filename}'?`)
  ) {
    return;
  }
  try {
    const response = await fetch(`/files/${filename}/override`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });
    const result = await response.json();
    if (response.ok) {
      showNotification(`File '${filename}' unlocked successfully!`, "success");
      loadFiles();
    } else {
      showNotification(`Error: ${result.detail}`, "error");
    }
  } catch (error) {
    console.error("Error overriding file lock:", error);
    showNotification("Error overriding file lock", "error");
  }
}

async function viewFileHistory(filename) {
  try {
    const response = await fetch(`/files/${filename}/history`);
    const result = await response.json();
    if (response.ok) {
      showFileHistoryModal(result);
    } else {
      showNotification("Error loading file history", "error");
    }
  } catch (error) {
    console.error("Error loading file history:", error);
    showNotification("Error loading file history", "error");
  }
}

function showFileHistoryModal(historyData) {
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-gray-900 bg-opacity-75 flex items-center justify-center p-4 z-[100]";
  let historyHtml = `
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto text-gray-900 dark:text-gray-100">
        <div class="flex justify-between items-center mb-4 pb-2 border-b border-gray-200 dark:border-gray-700">
            <h3 class="text-xl font-semibold text-gray-800 dark:text-gold-500">Version History - ${historyData.filename}</h3>
            <button class="text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gold-500" onclick="this.closest('.fixed').remove()"><i class="fa-solid fa-xmark text-2xl"></i></button>
        </div>`;
  if (historyData.history && historyData.history.length > 0) {
    historyHtml += '<div class="space-y-4">';
    historyData.history.forEach((commit) => {
      historyHtml += `
            <div class="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                <div class="flex justify-between items-center text-sm mb-1">
                    <span class="font-bold text-gray-800 dark:text-gold-500">${commit.commit_hash.substring(
                      0,
                      8
                    )}</span>
                    <span class="text-gray-500 dark:text-gray-400">${formatDate(
                      commit.date
                    )}</span>
                </div>
                <div class="text-gray-700 dark:text-gray-300 text-sm mb-1">${
                  commit.message
                }</div>
                <div class="text-xs text-gray-500 dark:text-gray-400">Author: ${
                  commit.author_name
                }</div>
            </div>`;
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
    if (e.target === modal) {
      modal.remove();
    }
  });
}

function showNewFileDialog() {
  const input = document.getElementById("newFileUpload");
  input.onchange = function (event) {
    const file = event.target.files[0];
    if (file) {
      uploadNewFile(file);
    }
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
    if (response.ok) {
      showNotification(`New file '${file.name}' is being processed`, "success");
      loadFiles();
    } else {
      showNotification(`Error: ${result.detail}`, "error");
    }
  } catch (error) {
    console.error("Error uploading new file:", error);
    showNotification("Error uploading new file", "error");
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

// -- Initial Setup --
document.getElementById("searchInput").addEventListener("input", renderFiles);

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
      if (response.ok) {
        showNotification("Configuration saved successfully!", "success");
        loadConfig();
        loadFiles();
        toggleConfigPanel();
      } else {
        showNotification(`Error: ${result.detail}`, "error");
      }
    } catch (error) {
      console.error("Error saving configuration:", error);
      showNotification("Error saving configuration", "error");
    }
  });

document.addEventListener("DOMContentLoaded", function () {
  applyThemePreference();
  connectWebSocket();
  loadConfig();
  loadFiles();
  setInterval(loadFiles, 60000); // Auto-refresh every 60 seconds
});
