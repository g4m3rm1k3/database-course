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
let tooltipsEnabled =
  localStorage.getItem("tooltipsEnabled") === "true" || false;
let lastFileListHash = null;

// -- DOM Cache (Updated with Modals) --
const domCache = {
  fileList: document.getElementById("fileList"),
  searchInput: document.getElementById("searchInput"),
  clearSearchBtn: document.getElementById("clearSearchBtn"),
  dashboardModal: document.getElementById("dashboardModal"),
  messagesModal: document.getElementById("messagesModal"), // Messages modal
  configModal: document.getElementById("configModal"), // Configuration modal
  mainContent: document.getElementById("mainContent"), // Replace with your main container ID
  tooltipToggle: document.getElementById("tooltip-toggle"),
  repoStatus: document.getElementById("repo-status"),
  connectionStatus: document.getElementById("connection-status"),
};

// -- Tooltip Cache --
const tooltipCache = new Map();

// -- Utility Functions --
function debounceNotifications(message, type) {
  const now = Date.now();
  if (
    lastNotification.message === message &&
    now - lastNotification.timestamp < 5000
  ) {
    return;
  }
  lastNotification = { message, timestamp: now };
  console.log(`[${type.toUpperCase()}] ${message}`);
  // Add your notification display logic here
}

// -- WebSocket Management --
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
    const heartbeatInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send("PING");
        ws.send("REFRESH_FILES");
      } else {
        clearInterval(heartbeatInterval);
      }
    }, 15000);
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
      handleOfflineStatus();
    }
  };

  ws.onerror = function (error) {
    console.error("WebSocket error:", error);
    updateConnectionStatus(false);
  };
}

function disconnectWebSocket() {
  if (ws) {
    isManualDisconnect = true;
    ws.close();
    ws = null;
    updateConnectionStatus(false);
  }
}

function handleWebSocketMessage(message) {
  try {
    const data = JSON.parse(message);
    if (data.type === "FILE_LIST_UPDATED") {
      const newHash = JSON.stringify(data.payload);
      if (newHash === lastFileListHash) {
        console.log("Skipping duplicate file list update");
        return;
      }
      lastFileListHash = newHash;
      groupedFiles = data.payload || {};
      if (
        domCache.dashboardModal &&
        domCache.dashboardModal.classList.contains("hidden")
      ) {
        renderFiles();
      }
    } else if (data.type === "NEW_MESSAGES") {
      if (data.payload && data.payload.length > 0) {
        populateAndShowMessagesModal(data.payload);
      }
    }
  } catch (error) {
    console.error("Error handling WebSocket message:", error);
    if (!navigator.onLine) {
      handleOfflineStatus();
    }
  }
}

// -- Offline Detection --
function handleOfflineStatus() {
  if (!navigator.onLine) {
    disconnectWebSocket();
    if (domCache.mainContent) {
      domCache.mainContent.innerHTML = `
        <div class="flex flex-col items-center justify-center py-12 text-gray-600 dark:text-gray-400">
          <i class="fa-solid fa-wifi text-6xl mb-4 text-red-500"></i>
          <h3 class="text-2xl font-semibold">Offline</h3>
          <p class="mt-2 text-center">You are offline. Please check your network connection and try again.</p>
          <button onclick="window.location.reload()" class="mt-4 px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 text-white rounded-md hover:bg-opacity-80">Retry</button>
        </div>`;
    }
    // Close all modals
    [
      domCache.dashboardModal,
      domCache.messagesModal,
      domCache.configModal,
    ].forEach((modal) => {
      if (modal && !modal.classList.contains("hidden")) {
        modal.classList.add("hidden");
      }
    });
    document.querySelectorAll(".tooltip").forEach((t) => t.remove());
    debounceNotifications(
      "You are offline. The application is paused.",
      "error"
    );
  }
}

function handleOnlineStatus() {
  if (navigator.onLine) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    }
    loadFiles();
    debounceNotifications("Connection restored. Reloading data...", "success");
  }
}

window.addEventListener("online", handleOnlineStatus);
window.addEventListener("offline", handleOfflineStatus);

// -- Data Loading --
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
    if (!navigator.onLine) {
      handleOfflineStatus();
    }
  }
}

// -- Tooltip Management --
function showTooltip(event) {
  if (!tooltipsEnabled || !navigator.onLine) return;

  const tooltipKey = event.currentTarget.dataset.tooltip;
  const tooltipData = tooltips[tooltipKey];
  if (!tooltipData) return;

  let tooltip = tooltipCache.get(tooltipKey);
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.className = `tooltip position-${tooltipData.position || "top"}`;
    const titleHtml = tooltipData.title
      ? `<div class="tooltip-title">${tooltipData.title}</div>`
      : "";
    const contentHtml = tooltipData.multiline
      ? tooltipData.content.replace(/\n/g, "<br>")
      : tooltipData.content;
    tooltip.innerHTML = `${titleHtml}<div class="tooltip-content">${contentHtml}</div>`;
    tooltipCache.set(tooltipKey, tooltip);
  }

  document.querySelectorAll(".tooltip").forEach((t) => t.remove());
  document.body.appendChild(tooltip);
  tooltip.targetElement = event.currentTarget;
  tooltip.preferredPosition = tooltipData.position || "top";

  positionTooltip(tooltip, event.currentTarget, tooltipData.position || "top");
  setTimeout(() => tooltip.classList.add("show"), 10);

  const repositionOnScroll = () => {
    if (tooltip.parentNode && tooltip.targetElement) {
      positionTooltip(
        tooltip,
        tooltip.targetElement,
        tooltip.preferredPosition
      );
    }
  };
  window.addEventListener("scroll", repositionOnScroll, { passive: true });
  window.addEventListener("resize", repositionOnScroll);
  tooltip.cleanup = () => {
    window.removeEventListener("scroll", repositionOnScroll);
    window.removeEventListener("resize", repositionOnScroll);
  };
}

// -- Updated Functions Using domCache --
function renderFiles() {
  const fileListEl = domCache.fileList;
  const searchTerm = domCache.searchInput
    ? domCache.searchInput.value.toLowerCase()
    : "";
  fileListEl.innerHTML = "";
  const expandedGroups =
    JSON.parse(localStorage.getItem("expandedGroups")) || [];
  const expandedSubGroups =
    JSON.parse(localStorage.getItem("expandedSubGroups")) || [];
  let totalFilesFound = 0;
  // ... your existing renderFiles logic ...
  setTimeout(() => {
    addDynamicTooltips();
    addDataElementTooltips();
  }, 100);
}

function updateTooltipVisibility() {
  tooltipsEnabled = domCache.tooltipToggle
    ? domCache.tooltipToggle.checked
    : false;
  localStorage.setItem("tooltipsEnabled", tooltipsEnabled);
  document.querySelectorAll(".tooltip").forEach((tooltip) => {
    if (!tooltipsEnabled) {
      if (tooltip.cleanup) tooltip.cleanup();
      tooltip.remove();
    }
  });
}

function updateRepoStatus(status) {
  if (domCache.repoStatus) {
    domCache.repoStatus.textContent = status;
    domCache.repoStatus.className = `status ${status.toLowerCase()}`;
  }
}

function updateConnectionStatus(isConnected) {
  if (domCache.connectionStatus) {
    domCache.connectionStatus.textContent = isConnected
      ? "Connected"
      : "Disconnected";
    domCache.connectionStatus.className = `status ${
      isConnected ? "connected" : "disconnected"
    }`;
  }
}

function populateAndShowMessagesModal(messages) {
  if (domCache.messagesModal) {
    // Example: Populate messages modal
    const messagesContainer =
      domCache.messagesModal.querySelector(".messages-content"); // Adjust selector as needed
    if (messagesContainer) {
      messagesContainer.innerHTML = messages
        .map((msg) => `<div>${msg}</div>`)
        .join(""); // Adjust rendering logic
    }
    domCache.messagesModal.classList.remove("hidden");
  }
}

// -- Placeholder Functions --
function addDynamicTooltips() {
  // Add dynamic tooltips to elements
}

function addDataElementTooltips() {
  // Add tooltips to data elements
}

function positionTooltip(tooltip, target, position) {
  // Position tooltip relative to target
}

// -- Initialize --
document.addEventListener("DOMContentLoaded", function () {
  if (!navigator.onLine) {
    handleOfflineStatus();
  } else {
    connectWebSocket();
    loadFiles();
  }
  if (domCache.tooltipToggle) {
    domCache.tooltipToggle.addEventListener("change", updateTooltipVisibility);
  }
});
