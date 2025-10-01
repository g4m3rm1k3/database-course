// ==================================================================
//			Mastercam GitLab Interface Script with Tooltips
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
let tooltipsEnabled =
  localStorage.getItem("tooltipsEnabled") === "true" || false;
let lastFileListHash = null;
let currentNotification = null; // Add this line
let currentActivityOffset = 0;
const ACTIVITY_LIMIT = 50;
let isLoadingMoreActivity = false;
let currentConfigTab = "config";

const domCache = {
  fileList: document.getElementById("fileList"),
  searchInput: document.getElementById("searchInput"),
  clearSearchBtn: document.getElementById("clearSearchBtn"),
  dashboardModal: document.getElementById("dashboardModal"),
  tooltipToggle: document.getElementById("tooltip-toggle"),
  repoStatus: document.getElementById("repo-status"),
  connectionStatus: document.getElementById("connection-status"),
};

const tooltips = {
  // Main interface tooltips
  searchInput: {
    title: "Search Files",
    content:
      "Type to filter files by name or path. Results update as you type.",
    position: "bottom",
  },
  clearSearchBtn: {
    title: "Clear Search",
    content: "Click to clear the search field and show all files.",
    position: "bottom",
  },
  dashboardBtn: {
    title: "Dashboard",
    content: "View active checkouts and recent activity across all users.",
    position: "bottom",
  },
  collapseAllBtn: {
    title: "Collapse All Groups",
    content: "Collapse all file groups to get a cleaner view.",
    position: "bottom",
  },
  globalAdminToggle: {
    title: "Admin Mode Toggle",
    content:
      "Enable admin functions like overriding locks and deleting files. Use with caution.",
    position: "bottom",
  },
  sendMessageBtn: {
    title: "Send Message",
    content:
      "Send notifications to other users about file changes or important updates.",
    position: "bottom",
  },

  // Header elements
  currentUser: {
    title: "Current User",
    content:
      "The username you're logged in as. This will be used for all file operations and commits.",
    position: "bottom",
  },
  connectionStatus: {
    title: "Connection Status",
    content:
      "Shows if WebSocket connection to server is active. Green = connected, Red = disconnected.",
    position: "bottom",
  },

  // Settings and configuration
  gitlabUrl: {
    title: "GitLab URL",
    content:
      "Enter your GitLab project URL (e.g., https://gitlab.com/project.git)",
    position: "top",
  },
  projectId: {
    title: "Project ID",
    content:
      "Find this number in your GitLab project settings. Usually displayed prominently on the project page.",
    position: "top",
  },
  username: {
    title: "GitLab Username",
    content:
      "Your GitLab username (not email). This will be used for commits and file locking.",
    position: "top",
  },
  token: {
    title: "Access Token",
    content:
      'Generate a personal access token in GitLab with "api" scope. Keep this secure!',
    position: "top",
  },
  allowInsecureSsl: {
    title: "Allow Insecure SSL",
    content:
      "Disables SSL certificate verification. Only use this for internal/development GitLab servers. Never use with public internet.",
    position: "top",
  },
  configStatusText: {
    title: "Configuration Status",
    content: "Shows whether GitLab credentials have been configured.",
    position: "top",
  },
  configRepoText: {
    title: "Repository Location",
    content: "Local file system path where the repository is stored.",
    position: "top",
  },

  // Config tabs
  configTab: {
    title: "GitLab Configuration",
    content: "Configure your GitLab connection and repository settings.",
    position: "bottom",
  },
  adminTab: {
    title: "Admin Settings",
    content:
      "Administrative functions for backup, cleanup, and repository management.",
    position: "bottom",
  },
  healthTab: {
    title: "System Health",
    content:
      "View system status including repository, network, and LFS health.",
    position: "bottom",
  },

  // Form elements
  commitMessage: {
    title: "Commit Message",
    content:
      'Describe what changes you made. Be specific - others will see this in the history. Good example: "Updated tool paths for better surface finish"',
    position: "top",
  },
  checkinFileUpload: {
    title: "Select Updated File",
    content:
      "Choose the modified file from your computer. Filename must match exactly.",
    position: "top",
  },
  newMajorRevInput: {
    title: "New Major Revision",
    content:
      "Enter the new major revision number (e.g., 2, 3, 4). Leave blank for auto-increment.",
    position: "right",
  },
  newFileDescription: {
    title: "File Description",
    content: "Part name per title block",
    position: "top",
  },
  newFileRev: {
    title: "Initial Revision",
    content:
      'Starting revision number. Use format like "1.0" for the first version.',
    position: "top",
  },
  newFileUpload: {
    title: "Select File to Upload",
    content:
      "Choose your Mastercam file. Follow naming convention: 1234567_MACHINE.mcx",
    position: "top",
  },
  newLinkFilename: {
    title: "Link Filename",
    content:
      "Enter the name for this link (e.g., 1234567_M80). Do not include a file extension.",
    position: "top",
  },
  linkToMaster: {
    title: "Master File",
    content:
      "Select which existing file this link should point to. Start typing to see available files.",
    position: "top",
  },
  recipientUserSelect: {
    title: "Message Recipient",
    content:
      "Choose who will receive your message. They will see it as a notification.",
    position: "top",
  },
  messageText: {
    title: "Message Content",
    content:
      'Type your message. Keep it clear and actionable (e.g., "Please review rev 2.1 before production")',
    position: "top",
  },

  // Floating action buttons
  newFileBtn: {
    title: "Upload New File",
    content:
      "Add a new Mastercam file to the repository with initial revision.",
    position: "left",
  },
  refreshBtn: {
    title: "Manual Refresh",
    content: "Force refresh the file list if automatic updates aren't working.",
    position: "left",
  },
  darkModeBtn: {
    title: "Toggle Dark Mode",
    content: "Switch between light and dark themes.",
    position: "left",
  },
  configBtn: {
    title: "Settings Panel",
    content: "Configure GitLab connection and user preferences.",
    position: "left",
  },

  // Modal buttons
  cancelCheckin: {
    title: "Cancel Check-in",
    content:
      "Close this dialog without checking in the file. Your lock will remain active.",
    position: "top",
  },
  cancelNewUpload: {
    title: "Cancel Upload",
    content: "Close this dialog without uploading. No changes will be made.",
    position: "top",
  },
  cancelSendMessage: {
    title: "Cancel",
    content: "Close this dialog without sending the message.",
    position: "top",
  },
  closeDashboardBtn: {
    title: "Close Dashboard",
    content: "Return to the main file list view.",
    position: "left",
  },

  // File action tooltips
  checkout: {
    title: "Checkout File",
    content:
      "Lock this file for editing. Others cannot modify it while checked out.",
    position: "top",
  },
  checkin: {
    title: "Check In File",
    content: "Upload your changes and unlock the file for others to use.",
    position: "top",
  },
  "cancel-checkout": {
    title: "Cancel Checkout",
    content:
      "Release the lock without saving changes. Local modifications will be lost.",
    position: "top",
  },
  download: {
    title: "Download File",
    content:
      "Download this file. If not checked out, you'll get a view-only copy with a warning about saving changes.",
    position: "top",
  },
  history: {
    title: "Version History",
    content:
      "View all revisions, download previous versions, or revert changes.",
    position: "top",
  },
  override: {
    title: "Admin Override",
    content: "Force unlock a file locked by another user (admin only).",
    position: "top",
  },
  delete: {
    title: "Delete File",
    content: "Permanently remove this file from the repository (admin only).",
    position: "top",
  },
  "view-master": {
    title: "View Master File",
    content:
      "Scroll to and highlight the master file that this link points to.",
    position: "top",
  },
  "remove-link": {
    title: "Remove Link",
    content:
      "Delete this link file without affecting the master file it points to (admin only).",
    position: "top",
  },

  // File data element tooltips
  fileSize: {
    title: "File Size",
    content:
      "The size of this file on disk. Larger files take longer to download.",
    position: "top",
  },
  filePath: {
    title: "File Path",
    content: "The location of this file in the GitLab repository structure.",
    position: "top",
  },
  fileModified: {
    title: "Last Modified",
    content: "When this file was last changed. Updated with each check-in.",
    position: "top",
  },
  fileLocked: {
    title: "Lock Information",
    content: "Shows who has this file checked out and when they locked it.",
    position: "top",
  },
  fileRevision: {
    title: "Current Revision",
    content: "The version number of this file. Increments with each check-in.",
    position: "top",
  },
  fileDescription: {
    title: "File Description",
    content: "Part description as entered when the file was first uploaded.",
    position: "top",
  },
  linkTarget: {
    title: "Link Target",
    content:
      "Shows which master file this link points to. Links share the same content but have separate revision histories.",
    position: "top",
  },

  // Dashboard tooltips
  dashboardFileColumn: {
    title: "File Column",
    content:
      "Shows which files are currently locked by users. Click to view details.",
    position: "bottom",
  },
  dashboardUserColumn: {
    title: "User Column",
    content:
      "Shows who has each file checked out. Helps identify who to contact about file access.",
    position: "bottom",
  },
  dashboardDurationColumn: {
    title: "Duration Column",
    content:
      "How long each file has been checked out. Long durations might indicate forgotten checkouts.",
    position: "bottom",
  },
  activityUserFilter: {
    title: "Filter by User",
    content:
      "Show activity for a specific user or all users. Useful for tracking individual contributions.",
    position: "bottom",
  },

  // Form validation tooltips
  revisionType: {
    title: "Revision Type",
    content:
      "Minor: Small changes (1.1→1.2). Major: Significant changes (1.2→2.0).",
    position: "right",
  },
  revisionMinor: {
    title: "Minor Revision",
    content: "Small changes like tool path adjustments (e.g., 1.1 → 1.2)",
    position: "right",
  },
  revisionMajor: {
    title: "Major Revision",
    content: "Significant changes like complete redesign (e.g., 1.2 → 2.0)",
    position: "right",
  },
  uploadTypeFile: {
    title: "Upload File",
    content: "Upload a new physical Mastercam file to the repository.",
    position: "bottom",
  },
  uploadTypeLink: {
    title: "Create Link",
    content:
      "Create a virtual link that points to an existing file. Links share content but have separate revision histories.",
    position: "bottom",
  },

  // Submit button tooltips
  checkinSubmit: {
    title: "Submit Check-in",
    content:
      "Upload your changes and create a new revision. Make sure your commit message is clear!",
    position: "top",
  },
  uploadSubmit: {
    title: "Upload New File",
    content:
      "Add this file to the repository. Double-check the filename follows the naming convention.",
    position: "top",
  },
  configSubmit: {
    title: "Save Configuration",
    content:
      "Save GitLab settings. The system will test the connection automatically.",
    position: "top",
  },
  messageSubmit: {
    title: "Send Message",
    content:
      "Send notification to the selected user. They'll see it immediately if online.",
    position: "top",
  },
  cancelBtn: {
    title: "Cancel",
    content: "Close this dialog without saving changes.",
    position: "top",
  },
  closeBtn: {
    title: "Close",
    content: "Close this dialog or panel.",
    position: "top",
  },
};

// ===== LAZY-LOADED TOOLTIP SYSTEM =====
const MAX_CACHED_TOOLTIPS = 50;
let activeTooltip = null;
const tooltipCache = new Map();
let tooltipObserver = null;

function initLazyTooltipSystem() {
  // Create stylesheet only once
  if (!document.getElementById("tooltip-styles")) {
    const style = document.createElement("style");
    style.id = "tooltip-styles";
    style.textContent = `
  .tooltip {
    position: absolute;
    background: linear-gradient(135deg, #1f2937, #374151);
    color: white;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.4;
    z-index: 9999;
    opacity: 0;
    visibility: hidden;
    transform: scale(0.8);
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    max-width: 280px;
    word-wrap: break-word;
    pointer-events: none;
  }
  
  .tooltip.show {
    opacity: 1;
    visibility: visible;
    transform: scale(1);
  }
  
  .tooltip .tooltip-title {
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 4px;
    color: #fbbf24;
  }
  
  /* Only show question mark on input fields and static elements */
  input.tooltip-enabled::before,
  textarea.tooltip-enabled::before,
  select.tooltip-enabled::before,
  div.tooltip-enabled:not([class*="flex"])::before {
    content: '?';
    position: absolute;
    top: -2px;
    right: -2px;
    background: #fbbf24;
    color: #1f2937;
    border-radius: 50%;
    width: 16px;
    height: 16px;
    font-size: 10px;
    font-weight: bold;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    pointer-events: none;
    opacity: 0.8;
  }
`;
    document.head.appendChild(style);
  }

  // Create or ensure toggle button exists
  ensureTooltipToggleExists();

  // Set up Intersection Observer for lazy loading
  if (!tooltipObserver && tooltipsEnabled) {
    tooltipObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.target.dataset.tooltipKey) {
            attachTooltipHandlers(entry.target);
          }
        });
      },
      { rootMargin: "50px" }
    );
  }

  updateTooltipVisibility();
}

function toggleTooltips() {
  tooltipsEnabled = !tooltipsEnabled;
  localStorage.setItem("tooltipsEnabled", tooltipsEnabled);

  const toggleBtn = document.getElementById("tooltip-toggle");
  if (toggleBtn) {
    toggleBtn.style.background = tooltipsEnabled ? "#f59e0b" : "#9ca3af";
    toggleBtn.style.borderColor = tooltipsEnabled ? "#d97706" : "#6b7280";
    toggleBtn.style.opacity = tooltipsEnabled ? "1" : "0.7";
  }

  updateTooltipVisibility();

  showNotification(
    tooltipsEnabled ? "Help tooltips enabled" : "Help tooltips disabled",
    tooltipsEnabled ? "success" : "info"
  );
}

function attachTooltipHandlers(element) {
  if (element.dataset.tooltipAttached === "true") return;

  const tooltipKey = element.dataset.tooltipKey || element.id;

  // Don't attach if no valid key or tooltip data
  if (!tooltipKey || !tooltipKey.trim() || !tooltips[tooltipKey]) {
    return;
  }

  element.dataset.tooltipKey = tooltipKey;
  element.addEventListener("mouseenter", showTooltip);
  element.addEventListener("mouseleave", hideTooltip);
  element.classList.add("tooltip-enabled");
  element.dataset.tooltipAttached = "true";
}
function updateTooltipVisibility() {
  if (tooltipObserver) {
    tooltipObserver.disconnect();
  }

  document.querySelectorAll(".tooltip-enabled").forEach((el) => {
    el.classList.remove("tooltip-enabled");
    el.removeAttribute("data-tooltip-attached");
  });

  if (!tooltipsEnabled) return;

  // Add tooltips to all defined elements by ID
  Object.keys(tooltips).forEach((elementId) => {
    const element = document.getElementById(elementId);
    if (element) {
      element.dataset.tooltipKey = elementId;
      if (tooltipObserver) {
        tooltipObserver.observe(element);
      } else {
        attachTooltipHandlers(element);
      }
    }
  });

  // Add tooltips to radio buttons by name attribute
  document.querySelectorAll('input[type="radio"]').forEach((radio) => {
    if (radio.name === "rev_type" && radio.value === "minor") {
      radio.dataset.tooltipKey = "revisionMinor";
      attachTooltipHandlers(radio);
    } else if (radio.name === "rev_type" && radio.value === "major") {
      radio.dataset.tooltipKey = "revisionMajor";
      attachTooltipHandlers(radio);
    } else if (radio.name === "uploadType" && radio.value === "file") {
      radio.dataset.tooltipKey = "uploadTypeFile";
      attachTooltipHandlers(radio);
    } else if (radio.name === "uploadType" && radio.value === "link") {
      radio.dataset.tooltipKey = "uploadTypeLink";
      attachTooltipHandlers(radio);
    }
  });

  // Add tooltips to labels for radio buttons
  document
    .querySelectorAll(
      'label[for="uploadTypeFile"], label[for="uploadTypeLink"]'
    )
    .forEach((label) => {
      const forAttr = label.getAttribute("for");
      if (forAttr === "uploadTypeFile") {
        label.dataset.tooltipKey = "uploadTypeFile";
        attachTooltipHandlers(label);
      } else if (forAttr === "uploadTypeLink") {
        label.dataset.tooltipKey = "uploadTypeLink";
        attachTooltipHandlers(label);
      }
    });

  addDynamicTooltips();
}
function debugTooltips() {
  console.log("Tooltips enabled:", tooltipsEnabled);
  console.log(
    "Elements with tooltips:",
    document.querySelectorAll("[data-tooltip-key]").length
  );
  console.log("Tooltip cache size:", tooltipCache.size);
}

// Replace tooltip management with this

function showTooltip(event) {
  if (!tooltipsEnabled) return;

  const element = event.currentTarget;
  const tooltipKey = element.dataset.tooltipKey || element.id;

  // Ignore if no valid key
  if (!tooltipKey || tooltipKey.trim() === "") {
    return;
  }

  const tooltipData = tooltips[tooltipKey];

  if (!tooltipData) {
    return; // Silently ignore missing tooltips
  }

  // Hide current tooltip
  if (activeTooltip) {
    hideTooltip();
  }

  // Get or create tooltip
  let tooltip = tooltipCache.get(tooltipKey);

  if (!tooltip) {
    // Manage cache size
    if (tooltipCache.size >= MAX_CACHED_TOOLTIPS) {
      const firstKey = tooltipCache.keys().next().value;
      const oldTooltip = tooltipCache.get(firstKey);
      if (oldTooltip && oldTooltip !== activeTooltip) {
        oldTooltip.remove();
        tooltipCache.delete(firstKey);
      }
    }

    tooltip = document.createElement("div");
    tooltip.className = `tooltip position-${tooltipData.position || "top"}`;

    const titleHtml = tooltipData.title
      ? `<div class="tooltip-title">${tooltipData.title}</div>`
      : "";
    const contentHtml = tooltipData.content;
    tooltip.innerHTML = `${titleHtml}<div class="tooltip-content">${contentHtml}</div>`;

    document.body.appendChild(tooltip);
    tooltipCache.set(tooltipKey, tooltip);
  }

  activeTooltip = tooltip;
  tooltip.targetElement = element;
  tooltip.preferredPosition = tooltipData.position || "top";
  positionTooltip(tooltip, element, tooltip.preferredPosition);

  setTimeout(() => tooltip.classList.add("show"), 10);

  // Throttled scroll handler
  let scrollTimeout;
  const repositionOnScroll = () => {
    if (scrollTimeout) return;
    scrollTimeout = setTimeout(() => {
      if (tooltip.classList.contains("show") && tooltip.targetElement) {
        positionTooltip(
          tooltip,
          tooltip.targetElement,
          tooltip.preferredPosition
        );
      }
      scrollTimeout = null;
    }, 16); // ~60fps
  };

  window.addEventListener("scroll", repositionOnScroll, { passive: true });
  window.addEventListener("resize", repositionOnScroll);

  tooltip.cleanup = () => {
    window.removeEventListener("scroll", repositionOnScroll);
    window.removeEventListener("resize", repositionOnScroll);
    if (scrollTimeout) {
      clearTimeout(scrollTimeout);
    }
  };
}
function hideTooltip() {
  if (activeTooltip) {
    activeTooltip.classList.remove("show");
    if (activeTooltip.cleanup) {
      activeTooltip.cleanup();
    }
    activeTooltip = null;
  }
}

function hideTooltip() {
  const tooltip = document.querySelector(".tooltip.show");
  if (tooltip) {
    tooltip.classList.remove("show");
    if (tooltip.cleanup) {
      tooltip.cleanup();
    }
  }
}

function addDataElementTooltips() {
  if (!tooltipsEnabled) return;

  // Add tooltips to file data elements using CSS selectors and data attributes
  document
    .querySelectorAll('[class*="fa-file"], [class*="fa-hard-drive"]')
    .forEach((icon) => {
      const parent = icon.parentElement;
      if (parent && parent.textContent.includes("Size:")) {
        addTooltipToElement(parent, "fileSize");
      } else if (parent && parent.textContent.includes("Path:")) {
        addTooltipToElement(parent, "filePath");
      }
    });

  document.querySelectorAll('[class*="fa-clock"]').forEach((icon) => {
    const parent = icon.parentElement;
    if (parent && parent.textContent.includes("Modified:")) {
      addTooltipToElement(parent, "fileModified");
    }
  });

  document.querySelectorAll('[class*="fa-lock"]').forEach((icon) => {
    const parent = icon.parentElement;
    if (parent && parent.textContent.includes("Locked by:")) {
      addTooltipToElement(parent, "fileLocked");
    }
  });

  document.querySelectorAll('[class*="fa-link"]').forEach((icon) => {
    const parent = icon.parentElement;
    if (parent && parent.textContent.includes("Points to:")) {
      addTooltipToElement(parent, "linkTarget");
    }
  });

  // Add tooltips to revision badges
  document.querySelectorAll("span").forEach((span) => {
    if (span.textContent.match(/REV \d+\.\d+/)) {
      addTooltipToElement(span, "fileRevision");
    }
  });

  // Add tooltips to file descriptions (italic text under filenames)
  document.querySelectorAll(".italic").forEach((desc) => {
    if (
      desc.classList.contains("text-gray-700") ||
      desc.classList.contains("dark:text-gray-300")
    ) {
      addTooltipToElement(desc, "fileDescription");
    }
  });
}

function addTooltipToElement(element, tooltipKey) {
  if (!tooltipsEnabled) return;
  if (!element || !tooltipKey) return;

  element.dataset.tooltipKey = tooltipKey; // Changed from dataset.tooltip
  element.classList.add("tooltip-enabled");

  if (element.dataset.tooltipAttached !== "true") {
    element.addEventListener("mouseenter", showTooltip);
    element.addEventListener("mouseleave", hideTooltip);
    element.dataset.tooltipAttached = "true";
  }
}

function addDynamicTooltips() {
  if (!tooltipsEnabled) return;

  // Map of CSS selectors to tooltip keys
  const buttonMappings = [
    { selector: ".js-checkout-btn", key: "checkout" },
    { selector: ".js-checkin-btn", key: "checkin" },
    { selector: ".js-cancel-checkout-btn", key: "cancel-checkout" },
    { selector: ".js-download-btn", key: "download" },
    { selector: 'a[href*="/download"]', key: "download" },
    { selector: ".js-history-btn", key: "history" },
    { selector: ".js-override-btn", key: "override" },
    { selector: ".js-view-master-btn", key: "view-master" },
    { selector: ".js-delete-btn", key: "delete" },
  ];

  buttonMappings.forEach(({ selector, key }) => {
    document.querySelectorAll(selector).forEach((btn) => {
      if (btn.dataset.tooltipAttached !== "true") {
        btn.dataset.tooltipKey = key;
        attachTooltipHandlers(btn);
      }
    });
  });
}

function positionTooltip(tooltip, targetElement, position) {
  const rect = targetElement.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
  const scrollY = window.pageYOffset || document.documentElement.scrollTop;

  let left, top;

  // Calculate initial position relative to the document
  switch (position) {
    case "top":
      left = rect.left + scrollX + rect.width / 2 - tooltipRect.width / 2;
      top = rect.top + scrollY - tooltipRect.height - 10;
      break;
    case "bottom":
      left = rect.left + scrollX + rect.width / 2 - tooltipRect.width / 2;
      top = rect.bottom + scrollY + 10;
      break;
    case "left":
      left = rect.left + scrollX - tooltipRect.width - 10;
      top = rect.top + scrollY + rect.height / 2 - tooltipRect.height / 2;
      break;
    case "right":
      left = rect.right + scrollX + 10;
      top = rect.top + scrollY + rect.height / 2 - tooltipRect.height / 2;
      break;
  }

  // Get viewport dimensions
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  // Adjust for viewport boundaries
  const minLeft = scrollX + 10;
  const maxLeft = scrollX + viewportWidth - tooltipRect.width - 10;
  const minTop = scrollY + 10;
  const maxTop = scrollY + viewportHeight - tooltipRect.height - 10;

  // Final boundary check - clamp to viewport
  left = Math.max(minLeft, Math.min(left, maxLeft));
  top = Math.max(minTop, Math.min(top, maxTop));

  tooltip.style.left = left + "px";
  tooltip.style.top = top + "px";
}

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
  console.log(`[${type.toUpperCase()}] ${message}`);
  showNotification(message, type);
}

async function checkForMessages() {
  try {
    const response = await fetch(
      `/messages/check?user=${encodeURIComponent(currentUser)}`
    );
    if (response.ok) {
      const data = await response.json();
      if (data.messages && data.messages.length > 0) {
        populateAndShowMessagesModal(data.messages);
      }
    }
  } catch (error) {
    console.error("Failed to check messages:", error);
    // Don't show notification for this - it's a background check
  }
}
// Update the WebSocket connection handler
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

    // Check for messages on connect
    checkForMessages();
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

handleWebSocketMessage;
function disconnectWebSocket() {
  if (ws) {
    isManualDisconnect = true;
    ws.close();
    ws = null;
    updateConnectionStatus(false);
  }
}

function manualRefresh() {
  loadFiles();
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
    document
      .querySelectorAll(".modal:not(.hidden)")
      .forEach((modal) => modal.classList.add("hidden"));
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
    if (!navigator.onLine) {
      handleOfflineStatus();
    }
  }
}

// Function to scroll to and highlight the master file
function viewMasterFile(masterFilename) {
  const safeId = `file-${masterFilename.replace(/[^a-zA-Z0-9]/g, "-")}`;
  const masterFileElement = document.getElementById(safeId);

  if (masterFileElement) {
    // Expand any parent groups that might contain the master file
    let parentDetails = masterFileElement.closest("details");
    while (parentDetails) {
      parentDetails.open = true;
      parentDetails = parentDetails.parentElement.closest("details");
    }

    // Smooth scroll to the master file
    masterFileElement.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });

    // Add a temporary highlight effect
    masterFileElement.classList.add(
      "bg-yellow-100",
      "dark:bg-yellow-900",
      "ring-2",
      "ring-yellow-400",
      "ring-opacity-75"
    );

    // Remove highlight after 3 seconds
    setTimeout(() => {
      masterFileElement.classList.remove(
        "bg-yellow-100",
        "dark:bg-yellow-900",
        "ring-2",
        "ring-yellow-400",
        "ring-opacity-75"
      );
    }, 3000);

    debounceNotifications(`Located master file: ${masterFilename}`, "success");
  } else {
    debounceNotifications(
      `Master file "${masterFilename}" not found in current view. Try refreshing or clearing search filters.`,
      "error"
    );
  }
}

function renderFiles() {
  const fileListEl = document.getElementById("fileList");
  const searchTerm = document.getElementById("searchInput").value.toLowerCase();

  if (!groupedFiles || Object.keys(groupedFiles).length === 0) {
    fileListEl.innerHTML = `<div class="flex flex-col items-center justify-center py-12 text-gray-600 dark:text-gray-400"><i class="fa-solid fa-exclamation-triangle text-6xl mb-4"></i><h3 class="text-2xl font-semibold">No Connection</h3><p class="mt-2 text-center">Unable to load files. Check your configuration.</p><button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 text-white rounded-md hover:bg-opacity-80">Try Again</button></div>`;
    return;
  }

  const expandedGroups =
    JSON.parse(localStorage.getItem("expandedGroups")) || [];
  const expandedSubGroups =
    JSON.parse(localStorage.getItem("expandedSubGroups")) || [];

  let totalFilesFound = 0;
  let htmlContent = "";

  const sortedGroups = Object.keys(groupedFiles).sort();

  for (const groupName of sortedGroups) {
    const groupFiles = groupedFiles[groupName];

    // Filter files based on search
    let filteredFiles = groupFiles;
    if (searchTerm) {
      filteredFiles = groupFiles.filter(
        (file) =>
          file.filename.toLowerCase().includes(searchTerm) ||
          (file.description &&
            file.description.toLowerCase().includes(searchTerm))
      );
    }

    if (filteredFiles.length === 0) continue;

    totalFilesFound += filteredFiles.length;
    const isGroupOpen = expandedGroups.includes(groupName) || searchTerm;

    // Create machine-based sub-groups
    const subGroups = {};
    filteredFiles.forEach((file) => {
      const match = file.filename.match(/^(\d{7})/);
      const subGroupKey = match ? match[1] : "Other";
      if (!subGroups[subGroupKey]) subGroups[subGroupKey] = [];
      subGroups[subGroupKey].push(file);
    });

    const sortedSubGroupKeys = Object.keys(subGroups).sort();

    htmlContent += `
      <details class="bg-white dark:bg-gray-800 rounded-lg shadow-md file-group" 
               data-group-name="${groupName}" ${isGroupOpen ? "open" : ""}>
        <summary class="cursor-pointer p-4 font-semibold text-lg text-gray-900 dark:text-white hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center justify-between">
          <span><i class="fa-solid fa-folder mr-2 text-amber-500"></i>${groupName}</span>
          <span class="text-sm font-normal text-gray-500 dark:text-gray-400">${
            filteredFiles.length
          } file(s)</span>
        </summary>
        <div class="p-4 space-y-4">`;

    for (const subGroupKey of sortedSubGroupKeys) {
      const subGroupFiles = subGroups[subGroupKey];
      const subGroupName = `${groupName}-${subGroupKey}`;
      const isSubGroupOpen =
        expandedSubGroups.includes(subGroupName) || searchTerm;

      // Determine if this sub-group contains links
      const hasLinks = subGroupFiles.some((f) => f.is_link);
      const iconClass = hasLinks
        ? "fa-link text-purple-500"
        : "fa-file text-blue-500";

      htmlContent += `
    <details class="bg-gray-50 dark:bg-gray-700 rounded-lg sub-file-group" 
             data-sub-group-name="${subGroupName}" ${
        isSubGroupOpen ? "open" : ""
      }>
      <summary class="cursor-pointer p-3 font-medium text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors flex items-center justify-between">
        <span><i class="fa-solid ${iconClass} mr-2"></i>${subGroupKey}</span>
        <span class="text-xs text-gray-500 dark:text-gray-400">${
          subGroupFiles.length
        } file(s)</span>
      </summary>
      <div class="p-3 space-y-3">`;

      subGroupFiles.forEach((file) => {
        htmlContent += buildFileCard(file);
      });

      htmlContent += `</div></details>`;
    }

    htmlContent += `</div></details>`;
  }

  if (searchTerm && totalFilesFound === 0) {
    htmlContent = `<div class="text-center py-12 text-gray-600 dark:text-gray-400">
      <i class="fa-solid fa-search text-6xl mb-4"></i>
      <h3 class="text-2xl font-semibold">No Results Found</h3>
      <p class="mt-2">No files match "${searchTerm}"</p>
    </div>`;
  }

  fileListEl.innerHTML = htmlContent;

  // Save state on toggle
  fileListEl.addEventListener(
    "toggle",
    (e) => {
      if (e.target.classList.contains("file-group")) {
        saveExpandedState();
      } else if (e.target.classList.contains("sub-file-group")) {
        saveExpandedSubState();
      }
    },
    true
  );

  // Re-add tooltips after render
  requestAnimationFrame(() => {
    addDynamicTooltips();
    addDataElementTooltips();
  });
}

function buildFileCard(file) {
  const safeId = `file-${file.filename.replace(/[^a-zA-Z0-9]/g, "-")}`;

  let statusClass = "";
  let statusBadgeText = "";

  if (file.is_link) {
    statusClass =
      "bg-purple-100 text-purple-900 dark:bg-purple-900 dark:text-purple-200";
    statusBadgeText = `<i class="fa-solid fa-link mr-1"></i>Links to ${file.master_file}`;
  } else {
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
          "bg-gray-100 text-gray-900 dark:bg-gray-600 dark:text-gray-200";
        statusBadgeText = "Unknown";
    }
  }

  let lockInfo = "";
  if (file.locked_by && !file.is_link) {
    lockInfo = `<div class="flex items-center space-x-2 text-sm text-gray-700 dark:text-gray-300">
      <i class="fa-solid fa-lock text-red-500"></i>
      <span>Locked by: <strong>${file.locked_by}</strong> at ${formatDate(
      file.locked_at
    )}</span>
    </div>`;
  }

  return `
    <div id="${safeId}" class="py-6 px-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-300 dark:border-gray-600 hover:shadow-lg transition-shadow" 
         data-file-status="${file.status}" data-file-revision="${
    file.revision || ""
  }">
      <div class="flex flex-col md:flex-row md:items-start md:justify-between space-y-4 md:space-y-0">
        <div class="flex-grow">
          <div class="flex items-center space-x-3 mb-2 flex-wrap">
            <h4 class="text-lg font-semibold text-gray-900 dark:text-white">${
              file.filename
            }</h4>
            ${
              file.revision
                ? `<span class="text-xs font-semibold px-2.5 py-1 rounded-full bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-100">REV ${file.revision}</span>`
                : ""
            }
            <span class="text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}">${statusBadgeText}</span>
          </div>
          ${
            file.description
              ? `<p class="italic text-gray-700 dark:text-gray-300 text-sm mb-3">${file.description}</p>`
              : ""
          }
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
            ${
              !file.is_link
                ? `<div class="flex items-center space-x-2">
              <i class="fa-solid fa-hard-drive"></i><span>Size: ${formatBytes(
                file.size
              )}</span>
            </div>`
                : ""
            }
            <div class="flex items-center space-x-2">
              <i class="fa-solid fa-clock"></i><span>Modified: ${formatDate(
                file.modified_at
              )}</span>
            </div>
          </div>
          ${lockInfo}
        </div>
        <div class="flex items-center space-x-2 flex-wrap">
          ${getActionButtons(file)}
        </div>
      </div>
    </div>
  `;
}

function updateFileElement(fileEl, file) {
  console.log(`Updating element for: ${file.filename}`);

  // --- Update Status Badge ---
  const statusBadge = fileEl.querySelector("span[class*='rounded-full']");
  if (statusBadge) {
    let statusClass = "";
    let statusBadgeText = "";
    // Your existing switch/case logic to determine statusClass and statusBadgeText
    // ...
    statusBadge.className = `text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}`;
    statusBadge.textContent = statusBadgeText;
  }

  // --- Update Revision Badge ---
  const revisionBadge = fileEl.querySelector("span.text-gray-800"); // Use a more specific selector
  if (revisionBadge) {
    revisionBadge.textContent = `REV ${file.revision}`;
  }

  // --- Update Action Buttons ---
  const actionsContainer = fileEl.querySelector(
    ".flex.items-center.space-x-2.flex-wrap"
  );
  if (actionsContainer) {
    // This is the simplest way to update buttons: just replace them all.
    // It's a good middle-ground.
    actionsContainer.innerHTML = getActionButtons(file);
  }

  // --- Update Modified Date ---
  const modifiedSpan = Array.from(fileEl.querySelectorAll("span")).find(
    (span) => span.textContent.includes("Modified:")
  );
  if (modifiedSpan) {
    modifiedSpan.innerHTML = `<i class="fa-solid fa-clock text-gray-600 dark:text-gray-400"></i>
                                  <span>Modified: ${formatDate(
                                    file.modified_at
                                  )}</span>`;
  }

  // --- Update Lock Info ---
  const lockInfoDiv = Array.from(
    fileEl.querySelectorAll("div.flex.items-center")
  ).find((div) => div.textContent.includes("Locked by:"));
  if (file.locked_by && !lockInfoDiv) {
    // Add lock info if it's newly locked
    const grid = fileEl.querySelector(".grid");
    const newLockInfo = document.createElement("div");
    // ... create and append new lock info element
  } else if (!file.locked_by && lockInfoDiv) {
    // Remove lock info if it's now unlocked
    lockInfoDiv.remove();
  } else if (file.locked_by && lockInfoDiv) {
    // Update existing lock info
    lockInfoDiv.innerHTML = `<i class="fa-solid fa-lock ..."></i> <span>Locked by: ${
      file.locked_by
    } at ${formatDate(file.locked_at)}</span>`;
  }
}

function getActionButtons(file) {
  const btnClass =
    "flex items-center space-x-2 px-4 py-2 rounded-md transition-all duration-200 text-sm font-semibold border-2 transform active:scale-95";
  let buttons = "";

  // Handle linked files differently - they should only have limited actions
  if (file.is_link) {
    // Linked files only get "View Master" and "History" buttons
    buttons += `<button class="${btnClass} bg-gradient-to-r from-purple-600 to-purple-700 border-purple-800 text-white hover:from-purple-700 hover:to-purple-800 hover:shadow-lg js-view-master-btn" data-filename="${file.filename}" data-master-file="${file.master_file}"><i class="fa-solid fa-link"></i><span>View Master</span></button>`;

    buttons += `<button class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 border-primary-500 dark:from-mc-dark-accent dark:to-primary-700 dark:border-primary-600 text-primary-900 dark:text-primary-200 hover:shadow-lg js-history-btn" data-filename="${file.filename}"><i class="fa-solid fa-history"></i><span>History</span></button>`;

    // Admin delete button for links (removes the link, not the master file)
    if (currentConfig && currentConfig.is_admin && isAdminModeEnabled) {
      buttons += `<button class="${btnClass} bg-gradient-to-r from-red-600 to-red-700 border-red-800 text-white hover:from-red-700 hover:to-red-800 hover:shadow-lg js-delete-btn" data-filename="${file.filename}"><i class="fa-solid fa-trash-can"></i><span>Remove Link</span></button>`;
    }

    return buttons;
  }

  let viewBtnHtml;

  if (file.status === "checked_out_by_user") {
    // Direct download for checked out files
    viewBtnHtml = `<a href="/files/${file.filename}/download" class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 border-primary-500 dark:from-mc-dark-accent dark:to-primary-700 dark:border-primary-600 text-primary-900 dark:text-primary-200 hover:shadow-lg"><i class="fa-solid fa-file-arrow-down"></i><span>Download</span></a>`;
  } else {
    // Show modal for view-only files
    viewBtnHtml = `<button class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 border-primary-500 dark:from-mc-dark-accent dark:to-primary-700 dark:border-primary-600 text-primary-900 dark:text-primary-200 hover:shadow-lg js-download-btn" data-filename="${file.filename}"><i class="fa-solid fa-file-arrow-down"></i><span>Download</span></button>`;
  }

  if (file.status === "unlocked") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-green-600 to-green-700 border-green-800 text-white hover:from-green-700 hover:to-green-800 hover:shadow-lg js-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-download"></i><span>Checkout</span></button>`;
  } else if (file.status === "checked_out_by_user") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-blue-600 to-blue-700 border-blue-800 text-white hover:from-blue-700 hover:to-blue-800 hover:shadow-lg js-checkin-btn" data-filename="${file.filename}"><i class="fa-solid fa-upload"></i><span>Check In</span></button>`;
    buttons += `<button class="${btnClass} bg-gradient-to-r from-yellow-600 to-yellow-700 border-yellow-800 text-white hover:from-yellow-700 hover:to-yellow-800 hover:shadow-lg js-cancel-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-times"></i><span>Cancel Checkout</span></button>`;
  }

  buttons = viewBtnHtml + buttons;
  buttons += `<button class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 border-primary-500 dark:from-mc-dark-accent dark:to-primary-700 dark:border-primary-600 text-primary-900 dark:text-primary-200 hover:shadow-lg js-history-btn" data-filename="${file.filename}"><i class="fa-solid fa-history"></i><span>History</span></button>`;

  if (currentConfig && currentConfig.is_admin) {
    const adminBtnVisibility = isAdminModeEnabled ? "" : "hidden";

    if (file.status === "locked" && file.locked_by !== currentUser) {
      buttons += `<button class="${btnClass} ${adminBtnVisibility} admin-action-btn bg-gradient-to-r from-yellow-400 to-yellow-500 border-yellow-600 text-yellow-900 hover:from-yellow-500 hover:to-yellow-600 hover:shadow-lg js-override-btn" data-filename="${file.filename}"><i class="fa-solid fa-unlock"></i><span>Override</span></button>`;
    }

    buttons += `<button class="${btnClass} ${adminBtnVisibility} admin-action-btn bg-gradient-to-r from-red-600 to-red-700 border-red-800 text-white hover:from-red-700 hover:to-red-800 hover:shadow-lg js-delete-btn" data-filename="${file.filename}"><i class="fa-solid fa-trash-can"></i><span>Delete</span></button>`;
  }

  return buttons;
}

async function loadConfig() {
  try {
    const response = await fetch("/config");
    currentConfig = await response.json();
    console.log("Loaded config:", currentConfig);

    if (currentConfig && currentConfig.gitlab_connection_status) {
      updateRepoStatus(currentConfig.gitlab_connection_status);
    }

    if (currentConfig && currentConfig.ssl_enabled === false) {
      const sslBanner = document.getElementById("ssl-warning-banner");
      if (sslBanner) {
        sslBanner.classList.remove("hidden");
      }
    }

    updateConfigDisplay();
    setupAdminUI();

    // ✅ NEW: Show/hide admin tab based on permissions
    const adminTab = document.getElementById("adminTab");
    if (adminTab) {
      if (currentConfig && currentConfig.is_admin) {
        adminTab.classList.remove("hidden");
      } else {
        adminTab.classList.add("hidden");
      }
    }
  } catch (error) {
    console.error("Error loading config:", error);
    updateRepoStatus("error");
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

function updateRepoStatus(status) {
  if (domCache.repoStatus) {
    let statusText = "";
    let statusClass = "";

    switch (status.toLowerCase()) {
      case "ok":
        statusText = "Ready";
        statusClass = "connected"; // Green
        break;

      // ✅ Add this new case for the orange warning
      case "warning":
        statusText = "Not Configured";
        statusClass = "warning"; // Orange
        break;

      case "error":
        statusText = "Error";
        statusClass = "disconnected"; // Red
        break;
      default:
        statusText = "Unknown";
        statusClass = "disconnected";
    }

    domCache.repoStatus.textContent = statusText;
    domCache.repoStatus.className = `status ${statusClass}`;
  }
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
    document.getElementById("allowInsecureSsl").checked =
      currentConfig.allow_insecure_ssl || false;
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

        // Update button appearance with animation
        adminToggle.classList.add("scale-95");
        setTimeout(() => adminToggle.classList.remove("scale-95"), 100);

        // Toggle styles
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
        adminToggle.classList.toggle("ring-2", isAdminModeEnabled);
        adminToggle.classList.toggle("ring-amber-400", isAdminModeEnabled);
        adminToggle.classList.toggle("shadow-lg", isAdminModeEnabled);

        // Show notification
        showNotification(
          isAdminModeEnabled ? "Admin mode enabled" : "Admin mode disabled",
          isAdminModeEnabled ? "warning" : "info"
        );
        renderFiles(); // Re-render to show/hide admin buttons
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

async function checkoutFile(filename) {
  setFileStateToLoading(filename);
  try {
    const response = await fetch(`/files/${filename}/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: currentUser }),
    });
    if (!response.ok) {
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

  // Add tooltips to modal elements after it's shown
  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
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
    if (new_major_rev) {
      formData.append("new_major_rev", new_major_rev);
    }
    const response = await fetch(`/files/${filename}/checkin`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Unknown error during check-in");
    }
  } catch (error) {
    debounceNotifications(`Check-in Error: ${error.message}`, "error");
  }
}

async function adminOverride(filename) {
  showConfirmModal(
    `Are you sure you want to override the lock on '${filename}'?`,
    async () => {
      try {
        const response = await fetch(`/files/${filename}/override`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ admin_user: currentUser }),
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Unknown error");
        }
      } catch (error) {
        debounceNotifications(`Override Error: ${error.message}`, "error");
      }
    }
  );
}

async function adminDeleteFile(filename) {
  showConfirmModal(
    `DANGER!<br><br>Are you sure you want to permanently delete '${filename}'?<br><br>This action cannot be undone.`,
    async () => {
      try {
        const response = await fetch(`/files/${filename}/delete`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ admin_user: currentUser }),
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "An unknown error occurred.");
        }
      } catch (error) {
        debounceNotifications(`Delete Error: ${error.message}`, "error");
      }
    }
  );
}

async function revertCheckin(filename, commit_hash) {
  showConfirmModal(
    `Are you sure you want to revert the check-in for commit ${commit_hash.substring(
      0,
      7
    )}?<br><br>This will create a NEW check-in that undoes the changes from this version.`,
    async () => {
      try {
        const response = await fetch(`/files/${filename}/revert_commit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            admin_user: currentUser,
            commit_hash: commit_hash,
          }),
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.detail || "Failed to revert check-in.");
        }
        debounceNotifications(
          result.message || "Check-in reverted successfully!",
          "success"
        );
        document.querySelector(".js-history-modal")?.remove();
        loadFiles();
      } catch (error) {
        debounceNotifications(`Revert Error: ${error.message}`, "error");
      }
    }
  );
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
    "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100] js-history-modal";
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.remove();
  });

  const allRevisions = Array.from(
    new Set(
      historyData.history
        .map((commit) => (commit.revision ? parseFloat(commit.revision) : null))
        .filter((rev) => rev !== null && !isNaN(rev))
    )
  ).sort((a, b) => a - b);

  let historyListHtml = "";
  if (historyData.history && historyData.history.length > 0) {
    historyData.history.forEach((commit, index) => {
      const revisionBadge = commit.revision
        ? `<span class="font-bold text-xs bg-primary-200 text-primary-800 dark:bg-primary-700 dark:text-primary-200 px-2 py-1 rounded-full">REV ${commit.revision}</span>`
        : "";

      let adminActions = "";
      const adminBtnVisibility = isAdminModeEnabled ? "" : "hidden";

      // Check if this is a link by looking at the filename
      const isLink = historyData.filename.includes("(Link)");

      if (
        currentConfig &&
        currentConfig.is_admin &&
        index === 0 &&
        historyData.history.length > 1 &&
        !isLink // Can't revert links
      ) {
        adminActions = `<button class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-red-500 to-red-600 border-2 border-red-700 text-white rounded-md hover:bg-opacity-80 transition-all text-sm font-semibold admin-action-btn js-revert-btn ${adminBtnVisibility}" data-filename="${historyData.filename}" data-commit-hash="${commit.commit_hash}"><i class="fa-solid fa-undo"></i><span>Revert</span></button>`;
      }

      // Don't show download button for links
      const downloadButton = isLink
        ? ""
        : `<a href="/files/${historyData.filename}/versions/${commit.commit_hash}" class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-primary-300 to-primary-400 border-2 border-primary-500 dark:from-mc-dark-accent dark:to-primary-700 dark:border-primary-600 text-primary-900 dark:text-primary-200 rounded-md hover:shadow-lg transition-all text-sm font-semibold">
    <i class="fa-solid fa-file-arrow-down"></i><span>Download</span>
  </a>`;

      historyListHtml += `<div class="p-4 bg-gradient-to-r from-primary-100 to-primary-200 dark:from-mc-dark-accent dark:to-primary-700 rounded-lg border border-primary-300 dark:border-mc-dark-accent bg-opacity-95 history-item" data-revision="${
        commit.revision || ""
      }">
    <div class="flex justify-between items-start">
        <div>
            <div class="flex items-center space-x-3 text-sm mb-2 flex-wrap gap-y-1">
                <span class="font-mono font-bold text-accent dark:text-accent">${commit.commit_hash.substring(
                  0,
                  8
                )}</span>
                ${revisionBadge}
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
        <div class="flex-shrink-0 ml-4 flex items-center space-x-2">
            ${adminActions}
            ${downloadButton}
        </div>
    </div>
  </div>`;
    });
  } else {
    historyListHtml = `<p class="text-center text-primary-600 dark:text-primary-300">No version history available.</p>`;
  }

  const revisionFilterHtml =
    allRevisions.length > 1
      ? `
    <div class="flex items-center justify-center space-x-6 mt-4">
        <div class="flex items-center space-x-2">
            <label for="revFilterFrom" class="text-sm font-medium text-primary-800 dark:text-primary-200">From Rev:</label>
            <input type="number" id="revFilterFrom" value="${
              allRevisions[0]
            }" min="${allRevisions[0]}" max="${
          allRevisions[allRevisions.length - 1]
        }" step="0.1" 
                   class="w-24 p-1 text-center font-semibold border border-primary-400 dark:border-mc-dark-accent rounded-md bg-white dark:bg-mc-dark-accent text-primary-900 dark:text-primary-100 focus:ring-accent focus:border-accent">
        </div>
        <div class="flex items-center space-x-2">
            <label for="revFilterTo" class="text-sm font-medium text-primary-800 dark:text-primary-200">To Rev:</label>
            <input type="number" id="revFilterTo" value="${
              allRevisions[allRevisions.length - 1]
            }" min="${allRevisions[0]}" max="${
          allRevisions[allRevisions.length - 1]
        }" step="0.1" 
                   class="w-24 p-1 text-center font-semibold border border-primary-400 dark:border-mc-dark-accent rounded-md bg-white dark:bg-mc-dark-accent text-primary-900 dark:text-primary-100 focus:ring-accent focus:border-accent">
        </div>
    </div>
  `
      : "";

  modal.innerHTML = `<div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg w-full max-w-4xl flex flex-col max-h-[90vh] bg-opacity-95 border border-transparent bg-gradient-to-br from-white to-mc-light-accent dark:from-mc-dark-bg dark:to-mc-dark-accent">
    <div class="flex-shrink-0 p-6 pb-4 border-b border-primary-300 dark:border-mc-dark-accent">
        <div class="flex justify-between items-center">
            <h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100">Version History - ${historyData.filename}</h3>
            <button class="text-primary-600 hover:text-primary-900 dark:text-primary-300 dark:hover:text-accent" onclick="this.closest('.js-history-modal').remove()">
                <i class="fa-solid fa-xmark text-2xl"></i>
            </button>
        </div>
        ${revisionFilterHtml}
    </div>
    <div id="historyListContainer" class="overflow-y-auto p-6 space-y-4">
        ${historyListHtml}
    </div>
  </div>`;
  document.body.appendChild(modal);

  const historyItems = modal.querySelectorAll(".history-item");
  const fromInput = document.getElementById("revFilterFrom");
  const toInput = document.getElementById("revFilterTo");

  const applyFilters = () => {
    const minRev = parseFloat(fromInput.value) || allRevisions[0];
    const maxRev =
      parseFloat(toInput.value) || allRevisions[allRevisions.length - 1];

    if (minRev > maxRev) {
      return;
    }

    historyItems.forEach((item) => {
      const itemRevStr = item.dataset.revision;
      let revMatch = true;

      if (itemRevStr && itemRevStr !== "") {
        const itemRev = parseFloat(itemRevStr);
        revMatch = itemRev >= minRev && itemRev <= maxRev;
      } else {
        revMatch = false;
      }

      item.style.display = revMatch ? "" : "none";
    });
  };

  if (fromInput && toInput) {
    fromInput.addEventListener("input", applyFilters);
    toInput.addEventListener("input", applyFilters);
    applyFilters();
  }
}

function showNewFileDialog() {
  const modal = document.getElementById("newUploadModal");
  const form = document.getElementById("newUploadForm");

  // Reset form
  form.reset();

  // Reset to file upload mode by default
  document.getElementById("uploadTypeFile").checked = true;
  document.getElementById("uploadTypeLink").checked = false;

  // Clear any validation classes
  clearFormValidation();

  // Update the view
  updateUploadTypeView();

  // Show modal
  modal.classList.remove("hidden");

  // Add tooltips after modal is shown
  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
}

function updateUploadTypeView() {
  const selectedValue =
    document.querySelector('input[name="uploadType"]:checked')?.value || "file";
  const fileContainer = document.getElementById("fileUploadContainer");
  const linkContainer = document.getElementById("linkCreateContainer");

  if (selectedValue === "link") {
    fileContainer.classList.add("hidden");
    linkContainer.classList.remove("hidden");
    populateMasterFileList();
  } else {
    fileContainer.classList.remove("hidden");
    linkContainer.classList.add("hidden");
  }
}

async function uploadNewFile(formData) {
  const submitBtn = document.querySelector(
    '#newUploadForm button[type="submit"]'
  );
  const submitText = document.getElementById("submitBtnText");
  const submitSpinner = document.getElementById("submitSpinner");

  // Show loading state
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.classList.add("opacity-75", "cursor-not-allowed");
    if (submitText) submitText.textContent = "Creating...";
    if (submitSpinner) submitSpinner.classList.remove("hidden");
  }

  try {
    const response = await fetch(`/files/new_upload`, {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (!response.ok) {
      let errorMessage = result.detail || "Upload failed";

      if (response.status === 409) {
        errorMessage = `❌ ${errorMessage}\n\nTip: Try a different filename or check if a similar file/link already exists.`;
      } else if (response.status === 404) {
        errorMessage = `❌ ${errorMessage}\n\nTip: Make sure the master file exists and is spelled correctly.`;
      } else if (response.status === 400) {
        errorMessage = `❌ ${errorMessage}`;
      }

      throw new Error(errorMessage);
    }

    debounceNotifications(
      `✅ ${result.message || "Action completed successfully!"}`,
      "success"
    );

    // Close modal on success
    document.getElementById("newUploadModal").classList.add("hidden");

    // Clear form for next use
    document.getElementById("newUploadForm").reset();
    clearFormValidation();

    // Reset to file upload mode
    document.getElementById("uploadTypeFile").checked = true;
    updateUploadTypeView();
  } catch (error) {
    let displayError = error.message;

    if (error.name === "TypeError" || error.message.includes("fetch")) {
      displayError =
        "❌ Network Error: Could not connect to server.\n\nPlease check your connection and try again.";
    }

    debounceNotifications(displayError, "error");
    console.error("Upload error:", error);
  } finally {
    // Reset button state
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove("opacity-75", "cursor-not-allowed");
      if (submitText) submitText.textContent = "Create";
      if (submitSpinner) submitSpinner.classList.add("hidden");
    }
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

  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
}

async function sendMessage(recipient, message) {
  const submitBtn = document.querySelector(
    '#sendMessageForm button[type="submit"]'
  );
  const originalText = submitBtn.innerHTML; // Store original HTML content

  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML =
        '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Sending...';
    }

    const response = await fetch("/messages/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipient: recipient,
        message: message,
        sender: currentUser, // Ensure currentUser is up-to-date
      }),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Failed to send message");
    }

    debounceNotifications(`✅ Message sent to ${recipient}`, "success");
    return true; // Indicate success
  } catch (error) {
    debounceNotifications(`❌ Send Error: ${error.message}`, "error");
    return false; // Indicate failure
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText; // Restore original content
    }
  }
}

function populateAndShowMessagesModal(messages) {
  const modal = document.getElementById("viewMessagesModal");
  const container = document.getElementById("messageListContainer");

  if (!modal || !container) {
    console.error("Messages modal elements not found in DOM");
    return;
  }

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

  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
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
  showConfirmModal(
    `Are you sure you want to cancel checkout for '${filename}'? Any local changes will be lost.`,
    async () => {
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
          loadFiles();
        } else {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Cancel failed");
        }
      } catch (error) {
        debounceNotifications(`Cancel Error: ${error.message}`, "error");
      }
    }
  );
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

// ===== ENHANCED NOTIFICATION SYSTEM =====
class NotificationManager {
  constructor() {
    this.queue = [];
    this.currentNotification = null;
    this.container = document.getElementById("notification-container");
  }

  show(message, type = "info", duration = 4000) {
    // Prevent duplicate notifications within 5 seconds
    const now = Date.now();
    if (
      lastNotification.message === message &&
      now - lastNotification.timestamp < 5000
    ) {
      return;
    }
    lastNotification = { message, timestamp: now };

    // If there's a current notification, queue this one
    if (this.currentNotification) {
      this.queue.push({ message, type, duration });
      return;
    }

    this._display(message, type, duration);
  }

  _display(message, type, duration) {
    if (!this.container) return;

    const notification = document.createElement("div");
    notification.className = `p-4 rounded-lg shadow-lg transform transition-all duration-300 translate-x-full bg-opacity-95 flex items-start space-x-3`;

    // Icon mapping
    const iconMap = {
      success: "fa-check-circle",
      error: "fa-exclamation-circle",
      warning: "fa-exclamation-triangle",
      info: "fa-info-circle",
    };

    const icon = iconMap[type] || iconMap.info;

    // Color mapping
    switch (type) {
      case "success":
        notification.classList.add("bg-green-600", "text-white");
        break;
      case "error":
        notification.classList.add("bg-red-600", "text-white");
        break;
      case "warning":
        notification.classList.add("bg-amber-400", "text-gray-900");
        break;
      default:
        notification.classList.add("bg-accent", "text-white");
    }

    notification.innerHTML = `
      <div class="flex-shrink-0 pt-0.5">
        <i class="fa-solid ${icon}"></i>
      </div>
      <div class="flex-1 text-sm font-medium">${message}</div>
      <button class="flex-shrink-0 ml-2 text-current opacity-70 hover:opacity-100" onclick="this.closest('div').remove()">
        <i class="fa-solid fa-times"></i>
      </button>
    `;

    this.currentNotification = notification;
    this.container.appendChild(notification);

    // Animate in
    setTimeout(() => notification.classList.remove("translate-x-full"), 50);

    // Auto-dismiss
    const dismissTimer = setTimeout(() => {
      this._dismiss(notification);
    }, duration);

    // Manual dismiss
    notification.querySelector("button").addEventListener("click", () => {
      clearTimeout(dismissTimer);
      this._dismiss(notification);
    });
  }

  _dismiss(notification) {
    notification.classList.add("translate-x-full");
    notification.addEventListener("transitionend", () => {
      notification.remove();
      this.currentNotification = null;

      // Show next notification in queue
      if (this.queue.length > 0) {
        const next = this.queue.shift();
        this._display(next.message, next.type, next.duration);
      }
    });
  }
}

// Initialize global notification manager
const notificationManager = new NotificationManager();

// Replace the old showNotification function
function showNotification(message, type = "info", duration = 4000) {
  notificationManager.show(message, type, duration);
}
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function debounce(func, delay) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), delay);
  };
}

function formatDate(dateString) {
  if (!dateString) return "Unknown";
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return "Invalid Date";
    const options = {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    };
    return date.toLocaleString(undefined, options);
  } catch (error) {
    console.error("Error formatting date:", dateString, error);
    return "Date Error";
  }
}

function formatDuration(totalSeconds) {
  if (totalSeconds < 60) {
    return `${Math.round(totalSeconds)}s`;
  }
  const days = Math.floor(totalSeconds / 86400);
  totalSeconds %= 86400;
  const hours = Math.floor(totalSeconds / 3600);
  totalSeconds %= 3600;
  const minutes = Math.floor(totalSeconds / 60);

  let parts = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);

  return parts.join(" ") || "0m";
}

async function loadAndRenderDashboard() {
  const activeCheckoutsContainer = document.getElementById(
    "activeCheckoutsContainer"
  );
  const activityFeedContainer = document.getElementById(
    "activityFeedContainer"
  );
  const loadingSpinner = `<div class="flex justify-center items-center py-12"><div class="animate-spin rounded-full h-12 w-12 border-4 border-primary-400 dark:border-mc-dark-accent border-t-accent"></div></div>`;

  activeCheckoutsContainer.innerHTML = loadingSpinner;

  if (currentConfig && currentConfig.is_admin) {
    activityFeedContainer.style.display = "flex";
    activeCheckoutsContainer.classList.remove("w-full");
    activeCheckoutsContainer.classList.add("md:w-1/2");
    activityFeedContainer.innerHTML = loadingSpinner;

    await Promise.all([
      loadAndRenderActiveCheckouts(),
      loadAndRenderActivityFeed(),
    ]);
  } else {
    activityFeedContainer.innerHTML = "";
    activityFeedContainer.style.display = "none";
    activeCheckoutsContainer.classList.remove("md:w-1/2");
    activeCheckoutsContainer.classList.add("w-full");

    await loadAndRenderActiveCheckouts();
  }
}

async function loadAndRenderActiveCheckouts() {
  const container = document.getElementById("activeCheckoutsContainer");
  try {
    const response = await fetch("/dashboard/stats");
    if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
    const data = await response.json();

    let contentHtml = `<h4 class="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4 flex-shrink-0">Active Checkouts</h4>`;

    if (data.active_checkouts.length === 0) {
      contentHtml += `<div class="text-center text-primary-600 dark:text-primary-300 py-8">
                <i class="fa-solid fa-check-circle text-4xl mb-3 text-green-500"></i>
                <p>No files are currently checked out.</p>
            </div>`;
    } else {
      contentHtml += `<div class="overflow-x-auto flex-grow">
                <table class="min-w-full divide-y divide-primary-300 dark:divide-mc-dark-accent">
                    <thead class="bg-primary-100 dark:bg-mc-dark-accent">
                        <tr>
                            <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-primary-600 dark:text-primary-300 uppercase tracking-wider">File</th>
                            <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-primary-600 dark:text-primary-300 uppercase tracking-wider">User</th>
                            <th scope="col" class="px-4 py-2 text-left text-xs font-medium text-primary-600 dark:text-primary-300 uppercase tracking-wider">Duration</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white dark:bg-mc-dark-bg divide-y divide-primary-200 dark:divide-primary-700">`;
      data.active_checkouts.forEach((item) => {
        contentHtml += `
                    <tr>
                        <td class="px-4 py-3 whitespace-nowrap text-sm font-medium text-primary-900 dark:text-primary-100">${
                          item.filename
                        }</td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm text-primary-700 dark:text-primary-300">${
                          item.locked_by
                        }</td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm text-primary-700 dark:text-primary-300">${formatDuration(
                          item.duration_seconds
                        )}</td>
                    </tr>`;
      });
      contentHtml += `</tbody></table></div>`;
    }
    container.innerHTML = contentHtml;
  } catch (error) {
    container.innerHTML = `<h4 class="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4">Active Checkouts</h4><p class="text-center text-red-500">Error: ${error.message}</p>`;
  }
}

async function loadAndRenderActivityFeed(append = false) {
  const container = document.getElementById("activityFeedContainer");

  if (!append) {
    currentActivityOffset = 0;
    isLoadingMoreActivity = true;
  }

  try {
    const response = await fetch(
      `/dashboard/activity?limit=${ACTIVITY_LIMIT}&offset=${currentActivityOffset}`
    );
    if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
    const data = await response.json();

    const users = Array.from(
      new Set(data.activities.map((act) => act.user))
    ).sort();

    let contentHtml = "";

    if (!append) {
      // Only add header and filter on initial load
      const filterHtml = `
        <div class="relative mb-4 flex-shrink-0">
          <label for="activityUserFilter" class="text-sm font-medium text-primary-800 dark:text-primary-200 mr-2">Filter by User:</label>
          <select id="activityUserFilter" class="w-full sm:w-auto p-2 border border-primary-400 dark:border-mc-dark-accent rounded-md bg-white dark:bg-mc-dark-accent text-primary-900 dark:text-primary-100 focus:ring-accent focus:border-accent">
            <option value="all">All Users</option>
            ${users
              .map((user) => `<option value="${user}">${user}</option>`)
              .join("")}
          </select>
        </div>`;

      contentHtml = `
        <h4 class="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-2 flex-shrink-0">Recent Activity</h4>
        ${filterHtml}
        <div id="activity-list" class="space-y-4 flex-grow overflow-y-auto">`;
    }

    // Build activity items
    let activityListHtml = "";
    if (data.activities.length === 0 && !append) {
      activityListHtml = `<p class="text-center text-primary-600 dark:text-primary-300 py-8">No recent activity found.</p>`;
    } else {
      data.activities.forEach((item) => {
        const iconMap = {
          CHECK_IN: { icon: "fa-upload", color: "text-blue-500" },
          CHECK_OUT: { icon: "fa-download", color: "text-green-500" },
          NEW_FILE: { icon: "fa-plus-circle", color: "text-green-600" },
          NEW_LINK: { icon: "fa-link", color: "text-purple-500" },
          CANCEL: { icon: "fa-times-circle", color: "text-yellow-500" },
          OVERRIDE: { icon: "fa-unlock", color: "text-orange-500" },
          DELETE_FILE: { icon: "fa-trash", color: "text-red-600" },
          DELETE_LINK: { icon: "fa-unlink", color: "text-red-500" },
          REVERT: { icon: "fa-undo", color: "text-purple-600" },
          MESSAGE: { icon: "fa-envelope", color: "text-blue-400" },
          REFRESH_LOCK: { icon: "fa-refresh", color: "text-gray-500" },
        };

        const { icon, color } = iconMap[item.event_type] || {
          icon: "fa-question-circle",
          color: "text-gray-500",
        };

        const verbMap = {
          CHECK_IN: "checked in",
          CHECK_OUT: "checked out",
          NEW_FILE: "uploaded new file",
          NEW_LINK: "created link",
          CANCEL: "canceled checkout for",
          OVERRIDE: "overrode lock on",
          DELETE_FILE: "deleted file",
          DELETE_LINK: "removed link",
          REVERT: "reverted",
          MESSAGE: "sent message",
          REFRESH_LOCK: "refreshed lock on",
        };

        const verb = verbMap[item.event_type] || "interacted with";

        activityListHtml += `
          <div class="flex items-start space-x-3 activity-item" data-user="${
            item.user
          }">
            <div class="pt-1"><i class="fa-solid ${icon} ${color}"></i></div>
            <div>
              <p class="text-sm text-primary-800 dark:text-primary-200">
                <strong>${item.user}</strong> 
                ${verb}
                <strong>${item.filename}</strong>
                ${item.revision ? ` (Rev ${item.revision})` : ""}
              </p>
              <p class="text-xs text-primary-600 dark:text-primary-400">${formatDate(
                item.timestamp
              )}</p>
            </div>
          </div>`;
      });
    }

    if (!append) {
      contentHtml += activityListHtml;

      // Add Load More button if we got the full limit (meaning there might be more)
      if (data.activities.length === ACTIVITY_LIMIT) {
        contentHtml += `
          <div class="text-center mt-4">
            <button id="loadMoreActivityBtn" class="px-4 py-2 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-md hover:bg-opacity-80 transition-colors">
              Load More Activity
            </button>
          </div>`;
      }

      contentHtml += `</div>`;
      container.innerHTML = contentHtml;

      // Set up user filter
      const userFilter = document.getElementById("activityUserFilter");
      const activityItems = container.querySelectorAll(".activity-item");
      userFilter.addEventListener("change", () => {
        const selectedUser = userFilter.value;
        activityItems.forEach((item) => {
          if (selectedUser === "all" || item.dataset.user === selectedUser) {
            item.style.display = "flex";
          } else {
            item.style.display = "none";
          }
        });
      });

      // Set up Load More button
      const loadMoreBtn = document.getElementById("loadMoreActivityBtn");
      if (loadMoreBtn) {
        loadMoreBtn.addEventListener("click", loadMoreActivity);
      }
    } else {
      // Append new activities
      const activityList = document.getElementById("activity-list");
      if (activityList) {
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = activityListHtml;
        while (tempDiv.firstChild) {
          activityList.appendChild(tempDiv.firstChild);
        }

        // Update Load More button
        const loadMoreBtn = document.getElementById("loadMoreActivityBtn");
        if (data.activities.length < ACTIVITY_LIMIT) {
          // No more data, hide button
          if (loadMoreBtn) loadMoreBtn.style.display = "none";
        }
      }
    }

    isLoadingMoreActivity = false;
  } catch (error) {
    isLoadingMoreActivity = false;
    if (!append) {
      container.innerHTML = `<h4 class="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4">Recent Activity</h4><p class="text-center text-red-500">Error: ${error.message}</p>`;
    }
  }
}

async function loadMoreActivity() {
  if (isLoadingMoreActivity) return;

  isLoadingMoreActivity = true;
  const loadMoreBtn = document.getElementById("loadMoreActivityBtn");

  if (loadMoreBtn) {
    loadMoreBtn.disabled = true;
    loadMoreBtn.innerHTML =
      '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading...';
  }

  currentActivityOffset += ACTIVITY_LIMIT;
  await loadAndRenderActivityFeed(false); // append = true

  if (loadMoreBtn) {
    loadMoreBtn.disabled = false;
    loadMoreBtn.innerHTML = "Load More Activity";
  }
}

function openDashboardModal() {
  const modal = document.getElementById("dashboardModal");
  if (modal) {
    modal.classList.remove("hidden");
    loadAndRenderDashboard().then(() => {
      setTimeout(() => {
        updateTooltipVisibility();
      }, 200);
    });
  }
}

function closeDashboardModal() {
  const modal = document.getElementById("dashboardModal");
  if (modal) {
    modal.classList.add("hidden");
  }
}

function validateUploadForm(form) {
  const errors = [];
  let isValid = true;

  const description = form.querySelector("#newFileDescription").value.trim();
  const rev = form.querySelector("#newFileRev").value.trim();
  const uploadType =
    form.querySelector('input[name="uploadType"]:checked')?.value || "file";

  clearFormValidation();

  const descInput = form.querySelector("#newFileDescription");
  if (!description) {
    errors.push("Description is required");
    addValidationClass(descInput, false);
    isValid = false;
  } else if (description.length < 3) {
    errors.push("Description must be at least 3 characters");
    addValidationClass(descInput, false);
    isValid = false;
  } else {
    addValidationClass(descInput, true);
  }

  const revInput = form.querySelector("#newFileRev");
  if (!rev) {
    errors.push("Revision is required");
    addValidationClass(revInput, false);
    isValid = false;
  } else if (!/^\d+\.\d+$/.test(rev)) {
    errors.push("Revision must be in format X.Y (e.g., 1.0)");
    addValidationClass(revInput, false);
    isValid = false;
  } else {
    addValidationClass(revInput, true);
  }

  if (uploadType === "link") {
    const newLinkFilename = form.querySelector("#newLinkFilename").value.trim();
    const linkToMaster = form.querySelector("#linkToMaster").value.trim();

    const linkNameInput = form.querySelector("#newLinkFilename");
    if (!newLinkFilename) {
      errors.push("Link name is required");
      addValidationClass(linkNameInput, false);
      isValid = false;
    } else if (newLinkFilename.length < 7) {
      errors.push("Link name must follow naming convention (7+ digits)");
      addValidationClass(linkNameInput, false);
      isValid = false;
    } else {
      addValidationClass(linkNameInput, true);
    }

    const linkMasterInput = form.querySelector("#linkToMaster");
    if (!linkToMaster) {
      errors.push("Master file selection is required");
      addValidationClass(linkMasterInput, false);
      isValid = false;
    } else {
      addValidationClass(linkMasterInput, true);
    }

    if (newLinkFilename === linkToMaster) {
      errors.push("A link cannot point to itself");
      addValidationClass(linkNameInput, false);
      addValidationClass(linkMasterInput, false);
      isValid = false;
    }
  } else {
    const fileInput = form.querySelector("#newFileUpload");
    if (!fileInput.files || fileInput.files.length === 0) {
      errors.push("File selection is required");
      addValidationClass(fileInput, false);
      isValid = false;
    } else {
      addValidationClass(fileInput, true);

      const file = fileInput.files[0];
      const maxSize = 100 * 1024 * 1024; // 100MB
      if (file.size > maxSize) {
        errors.push("File size must be less than 100MB");
        addValidationClass(fileInput, false);
        isValid = false;
      }
    }
  }

  return { isValid, errors };
}

function addValidationClass(element, isValid) {
  if (!element) return;

  element.classList.remove(
    "border-red-500",
    "border-green-500",
    "ring-red-500",
    "ring-green-500",
    "ring-2",
    "ring-opacity-25"
  );

  if (isValid) {
    element.classList.add(
      "border-green-500",
      "ring-green-500",
      "ring-2",
      "ring-opacity-25"
    );
  } else {
    element.classList.add(
      "border-red-500",
      "ring-red-500",
      "ring-2",
      "ring-opacity-25"
    );
  }
}

function clearFormValidation() {
  const inputs = document.querySelectorAll("#newUploadForm input");
  inputs.forEach((input) => {
    input.classList.remove(
      "border-red-500",
      "border-green-500",
      "ring-red-500",
      "ring-green-500",
      "ring-2",
      "ring-opacity-25"
    );
  });
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

function populateMasterFileList() {
  const datalist = document.getElementById("masterFileList");
  if (!datalist) return;

  datalist.innerHTML = "";

  if (!groupedFiles || Object.keys(groupedFiles).length === 0) {
    return;
  }

  const physicalFiles = Object.values(groupedFiles)
    .flat()
    .filter((file) => !file.is_link);

  const uniqueFilenames = new Set(physicalFiles.map((file) => file.filename));

  uniqueFilenames.forEach((filename) => {
    const option = document.createElement("option");
    option.value = filename;
    datalist.appendChild(option);
  });
}

function showConfirmModal(message, onConfirm, onCancel = () => {}) {
  message = message.replace(/\n/g, "<br>");
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100]";
  modal.innerHTML = `
    <div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg w-full max-w-md p-6 bg-opacity-95 border border-transparent bg-gradient-to-br from-white to-mc-light-accent dark:from-mc-dark-bg dark:to-mc-dark-accent">
      <h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100 mb-4">Confirm Action</h3>
      <p class="text-primary-700 dark:text-primary-300 mb-6">${message}</p>
      <div class="flex justify-end space-x-3">
        <button class="px-4 py-2 bg-gradient-to-r from-gray-300 to-gray-400 dark:from-gray-600 dark:to-gray-700 text-primary-900 dark:text-primary-100 rounded-md hover:bg-opacity-80" id="cancelBtn">Cancel</button>
        <button class="px-4 py-2 bg-gradient-to-r from-red-600 to-red-700 text-white rounded-md hover:bg-opacity-80" id="confirmBtn">Confirm</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const cancelBtn = modal.querySelector("#cancelBtn");
  const confirmBtn = modal.querySelector("#confirmBtn");

  cancelBtn.addEventListener("click", () => {
    modal.remove();
    onCancel();
  });

  confirmBtn.addEventListener("click", () => {
    modal.remove();
    onConfirm();
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.remove();
      onCancel();
    }
  });

  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
}

function showDownloadModal(filename) {
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100]";

  modal.innerHTML = `
    <div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg w-full max-w-md p-6 bg-opacity-95 border border-transparent bg-gradient-to-br from-white to-mc-light-accent dark:from-mc-dark-bg dark:to-mc-dark-accent">
      <div class="flex items-center mb-4">
        <i class="fa-solid fa-info-circle text-blue-500 text-2xl mr-3"></i>
        <h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100">Download for Viewing</h3>
      </div>
      
      <div class="mb-6">
        <p class="text-primary-700 dark:text-primary-300 mb-3">
          You are downloading <strong>${filename}</strong> for viewing purposes only.
        </p>
        <div class="bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded-md p-3">
          <p class="text-yellow-800 dark:text-yellow-200 text-sm">
            <i class="fa-solid fa-exclamation-triangle mr-2"></i>
            <strong>Important:</strong> This file is not checked out. Any changes you make will not be saved to the repository unless you first checkout the file.
          </p>
        </div>
      </div>
      
      <div class="flex justify-end space-x-3">
        <button class="px-4 py-2 bg-gradient-to-r from-gray-300 to-gray-400 dark:from-gray-600 dark:to-gray-700 text-primary-900 dark:text-primary-100 rounded-md hover:bg-opacity-80" onclick="this.closest('.fixed').remove()">
          Cancel
        </button>
        <a href="/files/${filename}/download" class="inline-flex items-center px-4 py-2 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-md hover:bg-opacity-80" onclick="this.closest('.fixed').remove()">
          <i class="fa-solid fa-file-arrow-down mr-2"></i>
          Download File
        </a>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  // Close modal when clicking outside
  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.remove();
    }
  });

  // Add tooltips after modal is shown
  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
}

// Modify WebSocket onclose to handle persistent connection failures
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
      // If max reconnect attempts are reached, treat as offline
      handleOfflineStatus();
    }
  };

  ws.onerror = function (error) {
    console.error("WebSocket error:", error);
    updateConnectionStatus(false);
  };
}

async function checkLFSStatus() {
  try {
    const response = await fetch("/system/lfs_status");
    const lfsStatus = await response.json();

    const statusContainer = document.getElementById("lfsStatusContainer");
    if (!statusContainer) return;

    let statusHtml = '<div class="p-4 rounded-lg border">';

    if (!lfsStatus.lfs_installed) {
      statusHtml += `
                <div class="flex items-center space-x-2 text-yellow-600 dark:text-yellow-400">
                    <i class="fa-solid fa-exclamation-triangle"></i>
                    <span class="font-semibold">Git LFS Not Installed</span>
                </div>
                <p class="text-sm mt-2 text-gray-600 dark:text-gray-400">
                    Large files will be stored directly in Git. Consider installing Git LFS for better performance.
                </p>`;
    } else if (!lfsStatus.lfs_configured) {
      statusHtml += `
                <div class="flex items-center space-x-2 text-blue-600 dark:text-blue-400">
                    <i class="fa-solid fa-info-circle"></i>
                    <span class="font-semibold">Git LFS Available (${lfsStatus.lfs_version})</span>
                </div>
                <p class="text-sm mt-2 text-gray-600 dark:text-gray-400">
                    LFS is installed but not yet configured for this repository.
                </p>`;
    } else {
      statusHtml += `
                <div class="flex items-center space-x-2 text-green-600 dark:text-green-400">
                    <i class="fa-solid fa-check-circle"></i>
                    <span class="font-semibold">Git LFS Active (${
                      lfsStatus.lfs_version
                    })</span>
                </div>
                <p class="text-sm mt-2 text-gray-600 dark:text-gray-400">
                    Tracking: ${lfsStatus.tracked_patterns.join(", ")}
                </p>`;
    }

    statusHtml += "</div>";
    statusContainer.innerHTML = statusHtml;
  } catch (error) {
    console.error("Failed to check LFS status:", error);
  }
}

function switchConfigTab(tabName) {
  currentConfigTab = tabName;

  // Update tab buttons
  const tabs = ["config", "admin", "health"];
  tabs.forEach((tab) => {
    const tabBtn = document.getElementById(`${tab}Tab`);
    const tabContent = document.getElementById(`${tab}Content`);

    if (tab === tabName) {
      tabBtn?.classList.add("active");
      tabContent?.classList.remove("hidden");
    } else {
      tabBtn?.classList.remove("active");
      tabContent?.classList.add("hidden");
    }
  });

  // Load data when switching to health tab
  if (tabName === "health") {
    refreshHealthStatus();
  }
}

// ===== LFS STATUS CHECK =====
async function checkLFSStatus() {
  const container = document.getElementById("lfsStatusContainer");
  if (!container) return;

  try {
    const response = await fetch("/system/lfs_status");
    const lfsStatus = await response.json();

    let statusHtml = '<div class="p-4 rounded-lg border">';

    if (!lfsStatus.lfs_installed) {
      statusHtml += `
                <div class="flex items-center space-x-2 text-yellow-600 dark:text-yellow-400">
                    <i class="fa-solid fa-exclamation-triangle"></i>
                    <span class="font-semibold">Git LFS Not Installed</span>
                </div>
                <p class="text-sm mt-2 text-gray-600 dark:text-gray-400">
                    Large files will be stored directly in Git. Consider installing Git LFS for better performance.
                </p>
                <a href="https://git-lfs.github.com/" target="_blank" class="text-xs text-blue-500 hover:underline mt-2 inline-block">
                    Download Git LFS →
                </a>`;
    } else if (!lfsStatus.lfs_configured) {
      statusHtml += `
                <div class="flex items-center space-x-2 text-blue-600 dark:text-blue-400">
                    <i class="fa-solid fa-info-circle"></i>
                    <span class="font-semibold">Git LFS Available (${lfsStatus.lfs_version})</span>
                </div>
                <p class="text-sm mt-2 text-gray-600 dark:text-gray-400">
                    LFS will be configured automatically on next file upload.
                </p>`;
    } else {
      statusHtml += `
                <div class="flex items-center space-x-2 text-green-600 dark:text-green-400">
                    <i class="fa-solid fa-check-circle"></i>
                    <span class="font-semibold">Git LFS Active (${
                      lfsStatus.lfs_version
                    })</span>
                </div>
                <p class="text-sm mt-2 text-gray-600 dark:text-gray-400">
                    Tracking: ${lfsStatus.tracked_patterns.join(", ")}
                </p>`;
    }

    statusHtml += "</div>";
    container.innerHTML = statusHtml;
  } catch (error) {
    console.error("Failed to check LFS status:", error);
    container.innerHTML = `
            <div class="p-4 rounded-lg border border-red-300 dark:border-red-700">
                <div class="flex items-center space-x-2 text-red-600 dark:text-red-400">
                    <i class="fa-solid fa-xmark-circle"></i>
                    <span class="font-semibold">Error Checking LFS Status</span>
                </div>
            </div>`;
  }
}

// ===== HEALTH CHECK SYSTEM =====
async function refreshHealthStatus() {
  // Set all to checking state
  const statusElements = [
    "repoHealthStatus",
    "networkHealthStatus",
    "lfsHealthStatus",
    "performanceStatus",
  ];
  statusElements.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.className = "health-status checking";
      el.textContent = "Checking...";
    }
  });

  // Run all checks in parallel
  await Promise.all([
    checkRepositoryHealth(),
    checkNetworkHealth(),
    checkLFSHealth(),
    checkPerformanceHealth(),
  ]);
}

async function checkRepositoryHealth() {
  const statusEl = document.getElementById("repoHealthStatus");
  const detailsEl = document.getElementById("repoHealthDetails");

  try {
    const response = await fetch("/config");
    const config = await response.json();

    if (config.has_token && config.repo_path) {
      statusEl.className = "health-status ok";
      statusEl.textContent = "Healthy";
      detailsEl.textContent = `Repository at: ${config.repo_path}`;
    } else {
      statusEl.className = "health-status warning";
      statusEl.textContent = "Not Configured";
      detailsEl.textContent = "GitLab credentials not configured";
    }
  } catch (error) {
    statusEl.className = "health-status error";
    statusEl.textContent = "Error";
    detailsEl.textContent = "Failed to check repository status";
  }
}

async function checkNetworkHealth() {
  const statusEl = document.getElementById("networkHealthStatus");
  const detailsEl = document.getElementById("networkHealthDetails");

  const startTime = performance.now();

  try {
    const response = await fetch("/config");
    const endTime = performance.now();
    const latency = Math.round(endTime - startTime);

    if (response.ok) {
      if (latency < 100) {
        statusEl.className = "health-status ok";
        statusEl.textContent = "Excellent";
      } else if (latency < 500) {
        statusEl.className = "health-status ok";
        statusEl.textContent = "Good";
      } else {
        statusEl.className = "health-status warning";
        statusEl.textContent = "Slow";
      }
      detailsEl.textContent = `Response time: ${latency}ms`;
    }
  } catch (error) {
    statusEl.className = "health-status error";
    statusEl.textContent = "Offline";
    detailsEl.textContent = "Cannot connect to server";
  }
}

async function checkLFSHealth() {
  const statusEl = document.getElementById("lfsHealthStatus");
  const detailsEl = document.getElementById("lfsHealthDetails");

  try {
    const response = await fetch("/system/lfs_status");
    const lfsStatus = await response.json();

    if (lfsStatus.lfs_installed && lfsStatus.lfs_configured) {
      statusEl.className = "health-status ok";
      statusEl.textContent = "Active";
      detailsEl.textContent = `Tracking ${lfsStatus.tracked_patterns.length} patterns`;
    } else if (lfsStatus.lfs_installed) {
      statusEl.className = "health-status warning";
      statusEl.textContent = "Not Configured";
      detailsEl.textContent =
        "LFS installed but not configured for this repository";
    } else {
      statusEl.className = "health-status warning";
      statusEl.textContent = "Not Installed";
      detailsEl.textContent = "Git LFS is not installed on this system";
    }
  } catch (error) {
    statusEl.className = "health-status error";
    statusEl.textContent = "Error";
    detailsEl.textContent = "Failed to check LFS status";
  }
}

async function checkPerformanceHealth() {
  const statusEl = document.getElementById("performanceStatus");
  const detailsEl = document.getElementById("performanceDetails");

  try {
    const startTime = performance.now();
    const response = await fetch("/files");
    const endTime = performance.now();
    const loadTime = Math.round(endTime - startTime);

    if (response.ok) {
      const data = await response.json();
      const fileCount = Object.values(data).flat().length;

      if (loadTime < 500) {
        statusEl.className = "health-status ok";
        statusEl.textContent = "Excellent";
      } else if (loadTime < 2000) {
        statusEl.className = "health-status ok";
        statusEl.textContent = "Good";
      } else {
        statusEl.className = "health-status warning";
        statusEl.textContent = "Slow";
      }

      detailsEl.textContent = `${fileCount} files loaded in ${loadTime}ms`;
    }
  } catch (error) {
    statusEl.className = "health-status error";
    statusEl.textContent = "Error";
    detailsEl.textContent = "Failed to measure performance";
  }
}

// ===== REPOSITORY RESET =====
async function resetRepository() {
  const confirmed = await showConfirmDialog(
    "Reset Repository",
    `<div class="space-y-3">
            <p class="text-red-600 dark:text-red-400 font-semibold">
                <i class="fa-solid fa-exclamation-triangle mr-2"></i>WARNING: This will delete your local repository!
            </p>
            <p>This action will:</p>
            <ul class="list-disc list-inside space-y-1 text-sm">
                <li>Delete all local files and changes</li>
                <li>Re-clone from GitLab</li>
                <li>Sync to match GitLab exactly</li>
            </ul>
            <p class="text-sm text-gray-600 dark:text-gray-400">
                Any uncommitted changes will be lost. Are you sure?
            </p>
        </div>`
  );

  if (!confirmed) return;

  showNotification("Resetting repository... This may take a moment.", "info");

  try {
    const response = await fetch("/admin/reset_repository", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });

    const result = await response.json();

    if (response.ok) {
      showNotification("✅ Repository reset successfully!", "success");
      setTimeout(() => window.location.reload(), 2000);
    } else {
      throw new Error(result.detail || "Reset failed");
    }
  } catch (error) {
    showNotification(`❌ Reset failed: ${error.message}`, "error");
  }
}

async function createManualBackup() {
  showNotification("Creating backup... This may take a minute.", "info");

  try {
    const response = await fetch("/admin/create_backup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });

    const result = await response.json();

    if (response.ok) {
      showNotification(
        `Backup created successfully at: ${result.backup_path}`,
        "success"
      );
    } else {
      throw new Error(result.detail || "Backup failed");
    }
  } catch (error) {
    showNotification(`Backup failed: ${error.message}`, "error");
  }
}

// ===== ADMIN CLEANUP WITH PROPER NOTIFICATIONS =====
async function cleanupLfsFiles() {
  const confirmed = await showConfirmDialog(
    "Cleanup LFS Files",
    `<div class="space-y-2">
      <p>This will:</p>
      <ul class="list-disc list-inside text-sm space-y-1">
        <li>Remove unreferenced LFS objects</li>
        <li>Delete stale lock files (older than 7 days)</li>
        <li>Remove old message files</li>
      </ul>
      <p class="text-sm text-gray-600 dark:text-gray-400 mt-2">This is safe and helps free up storage space.</p>
    </div>`
  );

  if (!confirmed) return;

  const loadingNotification = showNotification(
    "Running cleanup... This may take a moment.",
    "info"
  );

  try {
    const response = await fetch("/admin/cleanup_lfs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });

    const result = await response.json();

    if (response.ok) {
      // Build a detailed success message
      let message = "Cleanup complete!";
      if (result.details && result.details.length > 0) {
        const cleanedItems = result.details.length;
        message = `Cleanup complete! Processed ${cleanedItems} item(s).`;
      }
      showNotification(message, "success");
    } else {
      throw new Error(result.detail || "Cleanup failed");
    }
  } catch (error) {
    showNotification(`Cleanup failed: ${error.message}`, "error");
  }
}

async function exportRepository() {
  showNotification("Preparing export... Please wait.", "info");

  try {
    const response = await fetch("/admin/export_repository", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ admin_user: currentUser }),
    });

    if (response.ok) {
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mastercam_repo_export_${
        new Date().toISOString().split("T")[0]
      }.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();

      showNotification("Repository exported successfully!", "success");
    } else {
      const result = await response.json();
      throw new Error(result.detail || "Export failed");
    }
  } catch (error) {
    showNotification(`Export failed: ${error.message}`, "error");
  }
}

// ===== ENHANCED CONFIRM DIALOG =====
function showConfirmDialog(title, message) {
  return new Promise((resolve) => {
    const modal = document.createElement("div");
    modal.className =
      "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100]";

    modal.innerHTML = `
            <div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg w-full max-w-md p-6">
                <h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100 mb-4">
                    ${title}
                </h3>
                <div class="text-primary-700 dark:text-primary-300 mb-6">
                    ${message}
                </div>
                <div class="flex justify-end space-x-3">
                    <button id="cancelConfirmBtn" class="btn btn-secondary">Cancel</button>
                    <button id="confirmConfirmBtn" class="btn bg-red-600 hover:bg-red-700 text-white">Confirm</button>
                </div>
            </div>
        `;

    document.body.appendChild(modal);

    const cancelBtn = modal.querySelector("#cancelConfirmBtn");
    const confirmBtn = modal.querySelector("#confirmConfirmBtn");

    const cleanup = (result) => {
      modal.remove();
      resolve(result);
    };

    cancelBtn.addEventListener("click", () => cleanup(false));
    confirmBtn.addEventListener("click", () => cleanup(true));
    modal.addEventListener("click", (e) => {
      if (e.target === modal) cleanup(false);
    });
  });
}

function handleWebSocketMessage(message) {
  try {
    const data = JSON.parse(message);

    if (data.type === "FILE_LIST_UPDATED") {
      const newHash = JSON.stringify(data.payload);
      if (newHash === lastFileListHash) {
        return;
      }
      lastFileListHash = newHash;
      groupedFiles = data.payload || {};
      renderFiles();
    } else if (data.type === "NEW_MESSAGES") {
      if (data.payload && data.payload.length > 0) {
        console.log(`Received ${data.payload.length} new messages.`);
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

function ensureTooltipToggleExists() {
  const oldBtn = document.getElementById("tooltip-toggle");
  if (oldBtn) oldBtn.remove();

  if (!document.body) {
    setTimeout(ensureTooltipToggleExists, 100);
    return;
  }

  const toggleBtn = document.createElement("button");
  toggleBtn.id = "tooltip-toggle";
  toggleBtn.innerHTML = '<i class="fa-solid fa-question"></i>';
  toggleBtn.title = "Toggle Help Tooltips (Alt+Shift+H)";

  toggleBtn.style.cssText = `
    position: fixed !important;
    top: 70px !important;
    left: 24px !important;
    z-index: 99999 !important;
    width: 40px !important;
    height: 40px !important;
    border-radius: 50% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    border: 3px solid ${tooltipsEnabled ? "#d97706" : "#6b7280"} !important;
    background: ${tooltipsEnabled ? "#f59e0b" : "#9ca3af"} !important;
    color: white !important;
    font-size: 18px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
    transition: all 0.2s ease !important;
    visibility: visible !important;
    opacity: ${tooltipsEnabled ? "1" : "0.7"} !important;
  `;

  toggleBtn.addEventListener("click", toggleTooltips);

  toggleBtn.addEventListener("mouseenter", () => {
    toggleBtn.style.transform = "scale(1.1)";
  });
  toggleBtn.addEventListener("mouseleave", () => {
    toggleBtn.style.transform = "scale(1)";
  });

  document.body.appendChild(toggleBtn);
}
// Debug helper - call from console if button is missing
window.fixTooltipButton = function () {
  ensureTooltipToggleExists();
  console.log("Tooltip button recreation attempted");
};

// Add this as a global function
window.forceShowTooltipButton = function () {
  // Remove any existing button
  const existing = document.getElementById("tooltip-toggle");
  if (existing) existing.remove();

  // Create new button with brute force styling
  const btn = document.createElement("button");
  btn.id = "tooltip-toggle";
  btn.innerHTML = '<i class="fa-solid fa-question"></i>';
  btn.title = "Toggle Tooltips";

  // Absolute brute force styling
  btn.style.cssText = `
    position: fixed !important;
    bottom: 100px !important;
    right: 30px !important;
    z-index: 999999 !important;
    width: 56px !important;
    height: 56px !important;
    border-radius: 50% !important;
    background: #f59e0b !important;
    border: 4px solid #d97706 !important;
    color: white !important;
    font-size: 24px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.3) !important;
    visibility: visible !important;
    opacity: 1 !important;
  `;

  btn.onclick = toggleTooltips;
  document.body.appendChild(btn);

  console.log("✓ Tooltip button force-created");
  return btn;
};

console.log("💡 Run forceShowTooltipButton() in console to show the button");

// -- DOM Content Loaded Event Handler --
document.addEventListener("DOMContentLoaded", function () {
  // Check online status first
  if (!navigator.onLine) {
    handleOfflineStatus();
  } else {
    connectWebSocket();
    loadFiles();
  }

  // Check for messages on page load
  checkForMessages();

  // Poll for messages every 30 seconds as backup
  setInterval(checkForMessages, 30000);

  // Initialize tooltip system
  if (domCache.tooltipToggle) {
    domCache.tooltipToggle.addEventListener("change", updateTooltipVisibility);
  }

  applyThemePreference();
  loadConfig();
  loadFiles();
  checkLFSStatus();
  if (document.readyState === "complete") {
    setTimeout(() => {
      initLazyTooltipSystem();
      console.log("Tooltips initialized (complete)");
    }, 100);
  } else {
    window.addEventListener("load", () => {
      setTimeout(() => {
        initLazyTooltipSystem();
        console.log("Tooltips initialized (load)");
      }, 100);
    });
  }

  // Periodic LFS check (only if config panel is open)
  setInterval(() => {
    const configPanel = document.getElementById("configPanel");
    if (configPanel && !configPanel.classList.contains("translate-x-full")) {
      checkLFSStatus();
    }
  }, 30000);

  // Revision type radio button handlers
  document.querySelectorAll('input[name="rev_type"]').forEach((radio) => {
    radio.addEventListener("change", (e) => {
      const majorRevField = document.getElementById("newMajorRevInput");
      const majorRevLabel = document.querySelector(
        'label[for="newMajorRevInput"]'
      );

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

  // Upload type radio button handlers
  const uploadTypeRadios = document.querySelectorAll(
    'input[name="uploadType"]'
  );
  uploadTypeRadios.forEach((radio) => {
    radio.addEventListener("change", updateUploadTypeView);
  });

  // Visibility change handler
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && ws && ws.readyState !== WebSocket.OPEN) {
      if (reconnectAttempts < maxReconnectAttempts) connectWebSocket();
    }
  });

  // Cleanup on page unload
  window.addEventListener("beforeunload", () => disconnectWebSocket());
  window.manualRefresh = manualRefresh;

  // Fallback refresh for when WebSocket is not working
  setInterval(async () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      try {
        const response = await fetch("/refresh");
        if (response.ok) {
          const result = await response.json();
          if (result.message && result.message !== "No changes detected") {
            loadFiles();
          }
        }
      } catch (error) {
        console.error("Fallback refresh failed:", error);
      }
    }
  }, 30000);

  // ===== OPTIMIZED SEARCH FIELD LOGIC =====
  const searchInput = document.getElementById("searchInput");
  const clearSearchBtn = document.getElementById("clearSearchBtn");

  // Faster debounce for better responsiveness
  const debouncedRender = debounce(() => {
    renderFiles();
  }, 150);

  searchInput.addEventListener("input", () => {
    debouncedRender();
    clearSearchBtn.classList.toggle("hidden", searchInput.value.length === 0);
  });

  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    clearSearchBtn.classList.add("hidden");
    renderFiles();
    searchInput.focus();
  });

  // Collapse all button
  document.getElementById("collapseAllBtn")?.addEventListener("click", () => {
    document
      .querySelectorAll("#fileList details[open]")
      .forEach((detailsEl) => {
        detailsEl.open = false;
      });
    saveExpandedState();
  });

  // Dashboard button
  const dashboardBtn = document.getElementById("dashboardBtn");
  if (dashboardBtn) {
    dashboardBtn.addEventListener("click", openDashboardModal);
  }

  // Dashboard modal close handlers
  const dashboardModal = document.getElementById("dashboardModal");
  const closeDashboardBtn = document.getElementById("closeDashboardBtn");
  if (dashboardModal && closeDashboardBtn) {
    closeDashboardBtn.addEventListener("click", closeDashboardModal);
    dashboardModal.addEventListener("click", (e) => {
      if (e.target === dashboardModal) {
        closeDashboardModal();
      }
    });
  }

  // ===== OPTIMIZED EVENT DELEGATION FOR FILE ACTIONS =====
  // Single listener for all file actions (better performance)
  domCache.fileList.addEventListener("click", (e) => {
    const actionButton = e.target.closest("button, a");

    if (actionButton && actionButton.dataset.filename) {
      const filename = actionButton.dataset.filename;

      // Check which action was clicked
      if (actionButton.classList.contains("js-checkout-btn")) {
        checkoutFile(filename);
      } else if (actionButton.classList.contains("js-checkin-btn")) {
        showCheckinDialog(filename);
      } else if (actionButton.classList.contains("js-download-btn")) {
        showDownloadModal(filename);
      } else if (actionButton.classList.contains("js-cancel-checkout-btn")) {
        cancelCheckout(filename);
      } else if (actionButton.classList.contains("js-override-btn")) {
        adminOverride(filename);
      } else if (actionButton.classList.contains("js-delete-btn")) {
        adminDeleteFile(filename);
      } else if (actionButton.classList.contains("js-history-btn")) {
        viewFileHistory(filename);
      } else if (actionButton.classList.contains("js-view-master-btn")) {
        const masterFile = actionButton.dataset.masterFile;
        if (masterFile) {
          viewMasterFile(masterFile);
        }
      }
    }
  });

  // Handle revert buttons in modals (outside file list)
  document.addEventListener("click", (e) => {
    const revertButton = e.target.closest(".js-revert-btn");
    if (revertButton) {
      const { filename, commitHash } = revertButton.dataset;
      revertCheckin(filename, commitHash);
    }
  });

  // ===== CHECK-IN FORM =====
  const checkinForm = document.getElementById("checkinForm");
  checkinForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const filename = e.target.dataset.filename;
    const fileInput = document.getElementById("checkinFileUpload");
    const messageInput = document.getElementById("commitMessage");
    const revTypeInput = document.querySelector(
      'input[name="rev_type"]:checked'
    );
    const newMajorRevInput = document.getElementById("newMajorRevInput");

    // Validate filename matches
    if (fileInput.files.length > 0 && fileInput.files[0].name !== filename) {
      debounceNotifications(
        `Error: Uploaded file name "${fileInput.files[0].name}" must match the original file name "${filename}".`,
        "error"
      );
      return;
    }

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
        revTypeInput.value === "major" ? newMajorRevInput.value : null
      );
      document.getElementById("checkinModal").classList.add("hidden");
    } else {
      debounceNotifications("Please complete all required fields.", "error");
    }
  });

  document
    .getElementById("cancelCheckin")
    .addEventListener("click", () =>
      document.getElementById("checkinModal").classList.add("hidden")
    );

  // ===== NEW UPLOAD FORM =====
  const newUploadForm = document.getElementById("newUploadForm");
  newUploadForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const formData = new FormData();
    formData.append("user", currentUser);

    const description = document
      .getElementById("newFileDescription")
      .value.trim();
    const rev = document.getElementById("newFileRev").value.trim();
    const uploadType = document.querySelector(
      'input[name="uploadType"]:checked'
    ).value;

    // Validation
    if (!description || !rev) {
      debounceNotifications(
        "Please fill out the Description and Revision fields.",
        "error"
      );
      return;
    }

    if (uploadType === "link") {
      const newLinkFilename = document
        .getElementById("newLinkFilename")
        .value.trim();
      const linkToMaster = document.getElementById("linkToMaster").value.trim();

      if (!newLinkFilename || !linkToMaster) {
        debounceNotifications(
          "Please provide both a new link name and a master file.",
          "error"
        );
        return;
      }

      formData.append("is_link_creation", true);
      formData.append("new_link_filename", newLinkFilename);
      formData.append("link_to_master", linkToMaster);
    } else {
      const fileInput = document.getElementById("newFileUpload");
      if (fileInput.files.length === 0) {
        debounceNotifications("Please select a file to upload.", "error");
        return;
      }
      formData.append("is_link_creation", false);
      formData.append("file", fileInput.files[0]);
    }

    formData.append("description", description);
    formData.append("rev", rev);

    uploadNewFile(formData);
  });

  document
    .getElementById("cancelNewUpload")
    .addEventListener("click", () =>
      document.getElementById("newUploadModal").classList.add("hidden")
    );

  // ===== SEND MESSAGE FORM =====
  const sendMessageForm = document.getElementById("sendMessageForm");

  document
    .getElementById("cancelSendMessage")
    .addEventListener("click", () =>
      document.getElementById("sendMessageModal").classList.add("hidden")
    );

  sendMessageForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const recipient = document.getElementById("recipientUserSelect").value;
    const message = document.getElementById("messageText").value.trim();

    if (!recipient) {
      debounceNotifications("Please select a recipient.", "error");
      return;
    }
    if (!message) {
      debounceNotifications("Please write a message.", "error");
      return;
    }

    const success = await sendMessage(recipient, message);

    // Only close modal if send was successful
    if (success) {
      sendMessageForm.reset();
      document.getElementById("sendMessageModal").classList.add("hidden");
    }
  });

  // ===== MESSAGE ACKNOWLEDGMENT =====
  const messageListContainer = document.getElementById("messageListContainer");
  messageListContainer.addEventListener("click", (e) => {
    const ackButton = e.target.closest(".js-ack-btn");
    if (ackButton) {
      const messageId = ackButton.dataset.messageId;
      acknowledgeMessage(messageId);
    }
  });

  // ===== CONFIG FORM =====
  document
    .getElementById("configForm")
    .addEventListener("submit", async function (e) {
      e.preventDefault();

      const tokenInput = document.getElementById("token");
      const formData = {
        gitlab_url: document.getElementById("gitlabUrl").value,
        project_id: document.getElementById("projectId").value,
        username: document.getElementById("username").value,
        token: document.getElementById("token").value,
        allow_insecure_ssl: document.getElementById("allowInsecureSsl").checked,
      };

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

        // Reconnect WebSocket with new config
        disconnectWebSocket();
        connectWebSocket();

        // Clear token field for security
        tokenInput.value = "";
      } catch (error) {
        debounceNotifications(`Config Error: ${error.message}`, "error");
      }
    });
});
