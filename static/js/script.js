// ==================================================================
// 			Mastercam GitLab Interface Script with Tooltips
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

// -- Enhanced Tooltip System with HTML Element Support --
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

  // Settings and configuration
  gitlabUrl: {
    title: "GitLab URL",
    content:
      "Enter your GitLab project URL (e.g., https://gitlab.com/<project>.git)",
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
  recipientUserSelect: {
    title: "Message Recipient",
    content:
      "Choose who will receive your message. They will see it as a notification.",
    position: "top",
  },
  messageText: {
    title: "Nick message Content",
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

  // File action tooltips (dynamically added)
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
    title: "Taylor cancel Checkout",
    content:
      "Release the lock without saving changes. Local modifications will be lost.",
    position: "top",
  },
  view: {
    title: "View/Download File",
    content: "Download the latest version of this file to your computer.",
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

  // Special tooltips for form validation
  revisionType: {
    title: "Revision Type",
    content:
      "Minor: Small changes (1.1→1.2). Major: Significant changes (1.2→2.0).",
    position: "right",
  },

  // File naming convention tooltips
  fileNaming: {
    title: "File Naming Convention",
    content: `Files should follow this pattern:
    • 7-digit job number (1234567)
    • Machine name (M69)
    • Extension (.mcam, .vnc, etc.)
    
    Example: 1234567_M69.mcx`,
    position: "top",
    multiline: true,
  },
};

function initTooltipSystem() {
  // Add tooltip CSS if not already present
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
      
      .tooltip .tooltip-content {
        font-weight: 400;
      }
      
      .tooltip::after {
        content: '';
        position: absolute;
        width: 0;
        height: 0;
        border: 6px solid transparent;
      }
      
      .tooltip.position-top::after {
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border-top-color: #1f2937;
      }
      
      .tooltip.position-bottom::after {
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        border-bottom-color: #1f2937;
      }
      
      .tooltip.position-left::after {
        left: 100%;
        top: 50%;
        transform: translateY(-50%);
        border-left-color: #1f2937;
      }
      
      .tooltip.position-right::after {
        right: 100%;
        top: 50%;
        transform: translateY(-50%);
        border-right-color: #1f2937;
      }

      .tooltip-enabled {
        position: relative;
      }

      .tooltip-enabled::before {
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

      .tooltip-toggle-btn {
        position: fixed;
        top: 20px;
        left: 20px;
        z-index: 1000;
        background: linear-gradient(135deg, #fbbf24, #f59e0b);
        color: #1f2937;
        border: none;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        font-size: 18px;
        font-weight: bold;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        transition: all 0.2s ease;
      }

      .tooltip-toggle-btn:hover {
        transform: scale(1.1);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
      }

      .tooltip-toggle-btn.disabled {
        background: linear-gradient(135deg, #6b7280, #4b5563);
        color: #9ca3af;
      }
    `;
    document.head.appendChild(style);
  }

  // Create tooltip toggle button
  if (!document.getElementById("tooltip-toggle")) {
    const toggleBtn = document.createElement("button");
    toggleBtn.id = "tooltip-toggle";
    toggleBtn.className = `tooltip-toggle-btn ${
      tooltipsEnabled ? "" : "disabled"
    }`;
    toggleBtn.innerHTML = "?";
    toggleBtn.title = "Toggle Help Tooltips";
    toggleBtn.addEventListener("click", toggleTooltips);
    document.body.appendChild(toggleBtn);
  }

  // Initialize tooltips
  updateTooltipVisibility();
}

function toggleTooltips() {
  tooltipsEnabled = !tooltipsEnabled;
  localStorage.setItem("tooltipsEnabled", tooltipsEnabled.toString());

  const toggleBtn = document.getElementById("tooltip-toggle");
  if (toggleBtn) {
    toggleBtn.classList.toggle("disabled", !tooltipsEnabled);
  }

  updateTooltipVisibility();
  showNotification(
    tooltipsEnabled ? "Help tooltips enabled" : "Help tooltips disabled",
    "info"
  );
}

function updateTooltipVisibility() {
  // Remove existing tooltips and event listeners
  document.querySelectorAll(".tooltip").forEach((tooltip) => tooltip.remove());
  document.querySelectorAll("[data-tooltip]").forEach((el) => {
    el.removeEventListener("mouseenter", showTooltip);
    el.removeEventListener("mouseleave", hideTooltip);
    el.removeAttribute("data-tooltip");
    el.classList.remove("tooltip-enabled");
  });

  if (!tooltipsEnabled) return;

  // Add tooltips to elements by ID
  Object.keys(tooltips).forEach((elementId) => {
    const element = document.getElementById(elementId);
    if (element) {
      addTooltipToElement(element, elementId);
    }
  });

  // Add tooltips to elements by specific selectors and attributes
  const elementMappings = [
    // Floating action buttons (by onclick attributes)
    {
      selector: 'button[onclick="showNewFileDialog()"]',
      tooltip: "newFileBtn",
    },
    { selector: 'button[onclick="manualRefresh()"]', tooltip: "refreshBtn" },
    { selector: 'button[onclick="toggleDarkMode()"]', tooltip: "darkModeBtn" },
    { selector: 'button[onclick="toggleConfigPanel()"]', tooltip: "configBtn" },

    // Modal close buttons
    {
      selector: "button[onclick*=\"classList.add('hidden')\"]",
      tooltip: "closeBtn",
    },
    { selector: 'button[onclick*=".remove()"]', tooltip: "closeBtn" },
  ];

  elementMappings.forEach((mapping) => {
    document.querySelectorAll(mapping.selector).forEach((element) => {
      if (!element.dataset.tooltip) {
        // Don't override existing tooltips
        addTooltipToElement(element, mapping.tooltip);
      }
    });
  });

  // Add special tooltips for form fields based on their purpose
  addFormFieldTooltips();

  // Add tooltips to modal-specific elements
  addModalTooltips();

  // Add tooltips to dynamically created elements
  addDynamicTooltips();
}

function addModalTooltips() {
  if (!tooltipsEnabled) return;

  // Dashboard modal elements
  addDashboardTooltips();

  // History modal elements (when they exist)
  addHistoryModalTooltips();

  // File action tooltips in modals
  addModalActionTooltips();
}

function addDashboardTooltips() {
  // Active checkouts table headers
  const checkoutsTable = document.querySelector(
    "#activeCheckoutsContainer table"
  );
  if (checkoutsTable) {
    const headers = checkoutsTable.querySelectorAll("th");
    headers.forEach((header, index) => {
      const headerText = header.textContent.toLowerCase();
      let tooltipKey = "";

      if (headerText.includes("file")) {
        tooltipKey = "dashboardFileColumn";
      } else if (headerText.includes("user")) {
        tooltipKey = "dashboardUserColumn";
      } else if (headerText.includes("duration")) {
        tooltipKey = "dashboardDurationColumn";
      }

      if (tooltipKey && tooltips[tooltipKey]) {
        addTooltipToElement(header, tooltipKey);
      }
    });
  }

  // Activity filter dropdown
  const activityFilter = document.getElementById("activityUserFilter");
  if (activityFilter) {
    addTooltipToElement(activityFilter, "activityUserFilter");
  }

  // Close dashboard button
  const closeDashboard = document.getElementById("closeDashboardBtn");
  if (closeDashboard) {
    addTooltipToElement(closeDashboard, "closeDashboardBtn");
  }
}

function addHistoryModalTooltips() {
  // History modal filter inputs
  const revFilterFrom = document.getElementById("revFilterFrom");
  const revFilterTo = document.getElementById("revFilterTo");

  if (revFilterFrom) {
    addTooltipToElement(revFilterFrom, "revFilterFrom");
  }
  if (revFilterTo) {
    addTooltipToElement(revFilterTo, "revFilterTo");
  }

  // Download buttons in history
  document
    .querySelectorAll('.js-history-modal a[href*="/versions/"]')
    .forEach((downloadBtn) => {
      addTooltipToElement(downloadBtn, "historyDownload");
    });

  // Revert buttons in history (admin only)
  document.querySelectorAll(".js-revert-btn").forEach((revertBtn) => {
    addTooltipToElement(revertBtn, "historyRevert");
  });
}

function addModalActionTooltips() {
  // Message acknowledgment buttons
  document.querySelectorAll(".js-ack-btn").forEach((ackBtn) => {
    addTooltipToElement(ackBtn, "messageAck");
  });

  // File input elements with specific guidance
  document.querySelectorAll('input[type="file"]').forEach((fileInput) => {
    if (fileInput.id === "checkinFileUpload") {
      // Already handled by ID
    } else if (fileInput.id === "newFileUpload") {
      // Already handled by ID
    } else if (fileInput.accept && fileInput.accept.includes(".mcam")) {
      addTooltipToElement(fileInput, "mastercamFileInput");
    }
  });
}

// Add modal-specific tooltips to the main tooltips object
const modalTooltips = {
  // Dashboard tooltips
  dashboardFileColumn: {
    title: "File Column",
    content:
      "Shows which files are currently locked by users. Click dashboard to see full details.",
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
  closeDashboardBtn: {
    title: "Close Dashboard",
    content: "Return to the main file list view.",
    position: "left",
  },

  // History modal tooltips
  revFilterFrom: {
    title: "From Revision",
    content:
      "Starting revision number for filtering. Shows versions from this revision onwards.",
    position: "top",
  },
  revFilterTo: {
    title: "To Revision",
    content:
      "Ending revision number for filtering. Shows versions up to this revision.",
    position: "top",
  },
  historyDownload: {
    title: "Download Version",
    content:
      "Download this specific version of the file. Useful for comparing or reverting to older versions.",
    position: "top",
  },
  historyRevert: {
    title: "Revert to Version",
    content:
      "Create a new version that undoes changes back to this point. This creates a new commit, doesn't delete history.",
    position: "top",
  },

  // Message modal tooltips
  messageAck: {
    title: "Acknowledge Message",
    content: "Mark this message as read and remove it from your notifications.",
    position: "left",
  },

  // File input tooltips
  mastercamFileInput: {
    title: "Mastercam File Selection",
    content:
      "Choose your .mcam or .mcx file. Ensure the filename follows your company's naming convention.",
    position: "top",
  },

  // Enhanced form tooltips for modals
  checkinSubmit: {
    title: "Submit Check-in",
    content:
      "Upload your changes and create a new revision. Others will be able to access the file after this.",
    position: "top",
  },
  uploadSubmit: {
    title: "Upload New File",
    content:
      "Add this file to the repository. Make sure the description is clear for other team members.",
    position: "top",
  },
  configSubmit: {
    title: "Save Configuration",
    content:
      "Test and save your GitLab connection settings. You'll need valid credentials.",
    position: "top",
  },
  messageSubmit: {
    title: "Send Message",
    content:
      "Deliver this notification to the selected user. They'll see it in their message panel.",
    position: "top",
  },
  cancelBtn: {
    title: "Cancel Action",
    content:
      "Close this dialog without making changes. Any entered information will be lost.",
    position: "top",
  },
  closeBtn: {
    title: "Close",
    content: "Close this dialog or panel.",
    position: "top",
  },
};

const linkTooltips = {
  "view-master": {
    title: "View Master File",
    content:
      "Scroll to and highlight the master file that this link points to.",
    position: "top",
  },
  "link-info": {
    title: "Link Information",
    content:
      "View detailed information about this link and its relationship to the master file.",
    position: "top",
  },
  "remove-link": {
    title: "Remove Link",
    content:
      "Delete this link file without affecting the master file it points to (admin only).",
    position: "top",
  },
};

// Merge modal tooltips with the main tooltips object
Object.assign(tooltips, modalTooltips, linkTooltips);

function addFormFieldTooltips() {
  if (!tooltipsEnabled) return;

  // Revision type radio buttons - add tooltip to the container
  const revisionContainer = document
    .querySelector('input[name="rev_type"]')
    ?.closest(".space-y-2");
  if (revisionContainer) {
    addTooltipToElement(revisionContainer, "revisionType");
  }

  // Add tooltips to submit buttons with context
  document.querySelectorAll('button[type="submit"]').forEach((button) => {
    const form = button.closest("form");
    let tooltipKey = "submitBtn";

    if (form?.id === "checkinForm") {
      tooltipKey = "checkinSubmit";
    } else if (form?.id === "newUploadForm") {
      tooltipKey = "uploadSubmit";
    } else if (form?.id === "configForm") {
      tooltipKey = "configSubmit";
    } else if (form?.id === "sendMessageForm") {
      tooltipKey = "messageSubmit";
    }

    addTooltipToElement(button, tooltipKey);
  });

  // Add tooltips to cancel buttons
  document.querySelectorAll('button[type="button"]').forEach((button) => {
    if (button.textContent.includes("Cancel")) {
      addTooltipToElement(button, "cancelBtn");
    }
  });
}

// Add specific tooltips for different types of submit buttons
const submitButtonTooltips = {
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
  submitBtn: {
    title: "Submit",
    content: "Submit this form with the entered information.",
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

// Merge the submit button tooltips with main tooltips
Object.assign(tooltips, submitButtonTooltips);

function addTooltipToElement(element, tooltipKey) {
  if (!tooltipsEnabled) return;

  element.dataset.tooltip = tooltipKey;
  element.classList.add("tooltip-enabled");
  element.addEventListener("mouseenter", showTooltip);
  element.addEventListener("mouseleave", hideTooltip);
}

function addDynamicTooltips() {
  if (!tooltipsEnabled) return;

  // Regular file action tooltips
  document.querySelectorAll(".js-checkout-btn").forEach((btn) => {
    addTooltipToElement(btn, "checkout");
  });

  document.querySelectorAll(".js-checkin-btn").forEach((btn) => {
    addTooltipToElement(btn, "checkin");
  });

  document.querySelectorAll(".js-cancel-checkout-btn").forEach((btn) => {
    addTooltipToElement(btn, "cancel-checkout");
  });

  document.querySelectorAll('a[href*="/download"]').forEach((btn) => {
    addTooltipToElement(btn, "view");
  });

  document.querySelectorAll(".js-history-btn").forEach((btn) => {
    addTooltipToElement(btn, "history");
  });

  document.querySelectorAll(".js-override-btn").forEach((btn) => {
    addTooltipToElement(btn, "override");
  });

  document.querySelectorAll(".js-delete-btn").forEach((btn) => {
    addTooltipToElement(btn, "delete");
  });

  // Link-specific action tooltips
  document.querySelectorAll(".js-view-master-btn").forEach((btn) => {
    addTooltipToElement(btn, "view-master");
  });

  document.querySelectorAll(".js-link-info-btn").forEach((btn) => {
    addTooltipToElement(btn, "link-info");
  });

  // Admin delete buttons for links have different tooltip text
  document.querySelectorAll(".js-delete-btn").forEach((btn) => {
    const filename = btn.dataset.filename;
    const safeId = `file-${filename.replace(/[^a-zA-Z0-9]/g, "-")}`;
    const fileElement = document.getElementById(safeId);
    const isLink = fileElement && fileElement.querySelector(".fa-link");

    if (isLink) {
      addTooltipToElement(btn, "remove-link");
    } else {
      addTooltipToElement(btn, "delete");
    }
  });
}

function showTooltip(event) {
  if (!tooltipsEnabled) return;

  const tooltipKey = event.currentTarget.dataset.tooltip;
  const tooltipData = tooltips[tooltipKey];

  if (!tooltipData) return;

  // Remove existing tooltips
  document.querySelectorAll(".tooltip").forEach((tooltip) => tooltip.remove());

  // Create new tooltip
  const tooltip = document.createElement("div");
  tooltip.className = `tooltip position-${tooltipData.position || "top"}`;

  const titleHtml = tooltipData.title
    ? `<div class="tooltip-title">${tooltipData.title}</div>`
    : "";
  const contentHtml = tooltipData.multiline
    ? tooltipData.content.replace(/\n/g, "<br>")
    : tooltipData.content;

  tooltip.innerHTML = `${titleHtml}<div class="tooltip-content">${contentHtml}</div>`;

  document.body.appendChild(tooltip);

  // Store reference to target element for repositioning
  tooltip.targetElement = event.currentTarget;
  tooltip.preferredPosition = tooltipData.position || "top";

  // Position tooltip
  positionTooltip(tooltip, event.currentTarget, tooltipData.position || "top");

  // Show tooltip with animation
  setTimeout(() => tooltip.classList.add("show"), 10);

  // Add scroll listener for repositioning
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

  // Store cleanup function
  tooltip.cleanup = () => {
    window.removeEventListener("scroll", repositionOnScroll);
    window.removeEventListener("resize", repositionOnScroll);
  };
}

function hideTooltip() {
  const tooltip = document.querySelector(".tooltip.show");
  if (tooltip) {
    tooltip.classList.remove("show");
    // Clean up event listeners
    if (tooltip.cleanup) {
      tooltip.cleanup();
    }
    setTimeout(() => tooltip.remove(), 200);
  }
}

function positionTooltip(tooltip, targetElement, position) {
  const rect = targetElement.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
  const scrollY = window.pageYOffset || document.documentElement.scrollTop;

  let left, top;

  // Calculate initial position relative to the document (not viewport)
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

  // Adjust for viewport boundaries, considering scroll position
  const minLeft = scrollX + 10;
  const maxLeft = scrollX + viewportWidth - tooltipRect.width - 10;
  const minTop = scrollY + 10;
  const maxTop = scrollY + viewportHeight - tooltipRect.height - 10;

  // If tooltip would go off-screen horizontally, try opposite side
  if (left < minLeft && (position === "left" || position === "right")) {
    if (position === "left") {
      // Switch to right
      left = rect.right + scrollX + 10;
    } else {
      // Switch to left
      left = rect.left + scrollX - tooltipRect.width - 10;
    }
  }

  // If tooltip would go off-screen vertically, try opposite side
  if (top < minTop && (position === "top" || position === "bottom")) {
    if (position === "top") {
      // Switch to bottom
      top = rect.bottom + scrollY + 10;
    } else {
      // Switch to top
      top = rect.top + scrollY - tooltipRect.height - 10;
    }
  }

  // Final boundary check - clamp to viewport
  left = Math.max(minLeft, Math.min(left, maxLeft));
  top = Math.max(minTop, Math.min(top, maxTop));

  tooltip.style.left = left + "px";
  tooltip.style.top = top + "px";
}

// -- Enhanced File Naming Helper --
function addFileNamingHelper() {
  const newFileInput = document.getElementById("newFileUpload");

  if (newFileInput && tooltipsEnabled) {
    // Check if helper already exists
    if (!newFileInput.parentElement.querySelector(".file-naming-helper")) {
      const helper = document.createElement("div");
      helper.className =
        "file-naming-helper text-sm text-blue-700 dark:text-blue-300 mt-2 p-3 bg-blue-50 dark:bg-blue-900 rounded-md border border-blue-200 dark:border-blue-700";
      helper.innerHTML = `
        <div class="flex items-start space-x-2">
          <i class="fa-solid fa-lightbulb text-blue-600 dark:text-blue-400 mt-0.5"></i>
          <div>
            <strong>File Naming Convention:</strong><br>
            <code class="bg-white dark:bg-gray-800 px-1 rounded">1234567_MACHINE.mcam</code><br>
            <small>7-digit part number  + machine if applicable</small>
          </div>
        </div>
      `;
      newFileInput.parentElement.appendChild(helper);
    }
  }
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
      // *** FIX: Check if dashboard modal is hidden before re-rendering file list ***
      const dashboardModal = document.getElementById("dashboardModal");
      if (dashboardModal && dashboardModal.classList.contains("hidden")) {
        renderFiles();
      }
    } else if (data.type === "NEW_MESSAGES") {
      if (data.payload && data.payload.length > 0) {
        populateAndShowMessagesModal(data.payload);
      }
    }
  } catch (error) {
    console.error("Error handling WebSocket message:", error);
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

// Updated file rendering section to properly display linked files
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
    fileListEl.innerHTML = `<div class="flex flex-col items-center justify-center py-12 text-gray-600 dark:text-gray-400"><i class="fa-solid fa-exclamation-triangle text-6xl mb-4"></i><h3 class="text-2xl font-semibold">No Connection</h3><p class="mt-2 text-center">Unable to load files. Check your configuration.</p><button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 text-white rounded-md hover:bg-opacity-80">Try Again</button></div>`;
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
          file.path.toLowerCase().includes(searchTerm) ||
          (file.master_file &&
            file.master_file.toLowerCase().includes(searchTerm))
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
      "file-group group border-t border-gray-300 dark:border-gray-600";
    detailsEl.dataset.groupName = groupName;
    if (expandedGroups.includes(groupName) || searchTerm) {
      detailsEl.open = true;
    }
    detailsEl.addEventListener("toggle", saveExpandedState);

    const summaryEl = document.createElement("summary");
    summaryEl.className =
      "list-none py-3 px-4 bg-gradient-to-r from-gray-100 to-white dark:from-gray-700 dark:to-gray-800 cursor-pointer hover:bg-opacity-80 flex justify-between items-center transition-colors";
    summaryEl.innerHTML = `<div class="flex items-center space-x-3"><i class="fa-solid fa-chevron-right text-xs text-gray-600 dark:text-gray-400 transform transition-transform duration-200 group-open:rotate-90"></i><span class="font-semibold text-gray-800 dark:text-gray-200">${
      groupName.endsWith("XXXXX") ? `${groupName} SERIES` : groupName
    }</span></div><span class="text-sm font-medium text-gray-600 dark:text-gray-400">(${groupFileCount} files)</span>`;
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
          "sub-file-group group border-t border-gray-200 dark:border-gray-600";
        subDetailsEl.dataset.subGroupName = `${groupName}/${subGroupName}`;
        if (
          expandedSubGroups.includes(`${groupName}/${subGroupName}`) ||
          searchTerm
        ) {
          subDetailsEl.open = true;
        }
        subDetailsEl.addEventListener("toggle", saveExpandedSubState);

        const subSummaryEl = document.createElement("summary");
        subSummaryEl.className =
          "list-none py-2 px-3 bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-600 dark:to-gray-700 cursor-pointer hover:bg-opacity-80 flex justify-between items-center transition-colors";
        subSummaryEl.innerHTML = `<div class="flex items-center space-x-3"><i class="fa-solid fa-chevron-right text-xs text-gray-600 dark:text-gray-400 transform transition-transform duration-200 group-open:rotate-90"></i><span class="font-medium text-gray-800 dark:text-gray-200">${subGroupName}</span></div><span class="text-sm font-medium text-gray-600 dark:text-gray-400">(${filesInSubGroup.length} files)</span>`;
        subDetailsEl.appendChild(subSummaryEl);

        const filesContainer = document.createElement("div");
        filesContainer.className = "pl-4";

        filesInSubGroup.forEach((file) => {
          const fileEl = document.createElement("div");
          fileEl.id = `file-${file.filename.replace(/[^a-zA-Z0-9]/g, "-")}`;

          let statusClass = "",
            statusBadgeText = "";

          // Different status handling for linked vs regular files
          if (file.is_link) {
            statusClass =
              "bg-purple-100 text-purple-900 dark:bg-purple-900 dark:text-purple-200";
            statusBadgeText = `Links to ${file.master_file}`;
          } else {
            // Regular file status logic
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

          const actionsHtml = getActionButtons(file);
          fileEl.className =
            "py-6 px-4 bg-white dark:bg-gray-800 hover:bg-opacity-80 transition-colors duration-200 border-b border-gray-300 dark:border-gray-600";

          // Enhanced file display with link indicators
          const linkBadge = file.is_link
            ? `
            <span class="text-xs font-bold px-2.5 py-1 rounded-full bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200" title="Linked to: ${file.master_file}">
              <i class="fa-solid fa-link"></i> Linked
            </span>
          `
            : "";

          const revisionBadge = file.revision
            ? `
            <span class="text-xs font-semibold px-2.5 py-1 rounded-full bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
              REV ${file.revision}
            </span>
          `
            : "";

          fileEl.innerHTML = `
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center space-y-4 sm:space-y-0">
                <div class="flex items-center space-x-4 flex-wrap">
                    <div class="flex items-center space-x-2">
                      ${
                        file.is_link
                          ? '<i class="fa-solid fa-link text-purple-600 dark:text-purple-400"></i>'
                          : '<i class="fa-solid fa-file text-blue-600 dark:text-blue-400"></i>'
                      }
                      <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">${
                        file.filename
                      }</h3>
                    </div>
                    <span class="text-xs font-semibold px-2.5 py-1 rounded-full ${statusClass}">${statusBadgeText}</span>
                    ${revisionBadge}
                    ${linkBadge}
                </div>
                <div class="flex items-center space-x-2 flex-wrap">${actionsHtml}</div>
            </div>
            ${
              file.description
                ? `<div class="mt-2 text-sm text-gray-700 dark:text-gray-300 italic">${file.description}</div>`
                : ""
            }
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4 text-gray-700 dark:text-gray-300 text-sm">
                ${
                  file.is_link
                    ? `
                  <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-link text-purple-600 dark:text-purple-400"></i>
                    <span>Points to: ${file.master_file}</span>
                  </div>
                  <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-info-circle text-gray-600 dark:text-gray-400"></i>
                    <span>Type: Virtual Link</span>
                  </div>
                `
                    : `
                  <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-file text-gray-600 dark:text-gray-400"></i>
                    <span>Path: ${file.path}</span>
                  </div>
                  <div class="flex items-center space-x-2">
                    <i class="fa-solid fa-hard-drive text-gray-600 dark:text-gray-400"></i>
                    <span>Size: ${formatBytes(file.size)}</span>
                  </div>
                `
                }
                <div class="flex items-center space-x-2">
                  <i class="fa-solid fa-clock text-gray-600 dark:text-gray-400"></i>
                  <span>Modified: ${formatDate(file.modified_at)}</span>
                </div>
                ${
                  file.locked_by && file.status !== "checked_out_by_user"
                    ? `
                  <div class="flex items-center space-x-2 sm:col-span-2 lg:col-span-1">
                    <i class="fa-solid fa-lock text-gray-600 dark:text-gray-400"></i>
                    <span>Locked by: ${file.locked_by} at ${formatDate(
                        file.locked_at
                      )}</span>
                  </div>
                `
                    : ""
                }
            </div>
          `;
          filesContainer.appendChild(fileEl);
        });

        subDetailsEl.appendChild(filesContainer);
        subGroupsContainer.appendChild(subDetailsEl);
      });

    detailsEl.appendChild(subGroupsContainer);
    fileListEl.appendChild(detailsEl);
  });

  if (totalFilesFound === 0) {
    fileListEl.innerHTML = `<div class="flex flex-col items-center justify-center py-12 text-gray-600 dark:text-gray-400"><i class="fa-solid fa-folder-open text-6xl mb-4"></i><h3 class="text-2xl font-semibold">No files found</h3><p class="mt-2 text-center">No Mastercam files match your search criteria.</p><button onclick="manualRefresh()" class="mt-4 px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 text-white rounded-md hover:bg-opacity-80">Refresh</button></div>`;
  }

  // Re-apply tooltips to newly rendered elements
  setTimeout(() => {
    addDynamicTooltips();
  }, 100);
}
async function loadConfig() {
  try {
    const response = await fetch("/config");
    currentConfig = await response.json();
    console.log("Loaded config:", currentConfig);
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

function getActionButtons(file) {
  const btnClass =
    "flex items-center space-x-2 px-4 py-2 rounded-md transition-colors text-sm font-semibold";
  let buttons = "";

  let viewBtnHtml = `<a href="/files/${file.filename}/download" class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80"><i class="fa-solid fa-eye"></i><span>View</span></a>`;

  if (file.status === "unlocked") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-green-600 to-green-700 text-white hover:bg-opacity-80 js-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-download"></i><span>Checkout</span></button>`;
  } else if (file.status === "checked_out_by_user") {
    buttons += `<button class="${btnClass} bg-gradient-to-r from-blue-600 to-blue-700 text-white hover:bg-opacity-80 js-checkin-btn" data-filename="${file.filename}"><i class="fa-solid fa-upload"></i><span>Check In</span></button>`;
    buttons += `<button class="${btnClass} bg-gradient-to-r from-yellow-600 to-yellow-700 text-white hover:bg-opacity-80 js-cancel-checkout-btn" data-filename="${file.filename}"><i class="fa-solid fa-times"></i><span>Cancel Checkout</span></button>`;
    viewBtnHtml = viewBtnHtml.replace(
      '<i class="fa-solid fa-eye"></i><span>View</span>',
      '<i class="fa-solid fa-file-arrow-down"></i><span>Download</span>'
    );
  }

  buttons = viewBtnHtml + buttons;
  buttons += `<button class="${btnClass} bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 hover:bg-opacity-80 js-history-btn" data-filename="${file.filename}"><i class="fa-solid fa-history"></i><span>History</span></button>`;

  if (currentConfig && currentConfig.is_admin) {
    const adminBtnVisibility = isAdminModeEnabled ? "" : "hidden";

    if (file.status === "locked" && file.locked_by !== currentUser) {
      const overrideBtnClasses =
        "bg-gradient-to-r from-yellow-400 to-yellow-500 text-yellow-900";
      buttons += `<button class="${btnClass} ${adminBtnVisibility} admin-action-btn ${overrideBtnClasses} hover:bg-opacity-80 js-override-btn" data-filename="${file.filename}"><i class="fa-solid fa-unlock"></i><span>Override</span></button>`;
    }

    const deleteBtnClasses =
      "bg-gradient-to-r from-red-600 to-red-700 text-white";
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
    addModalTooltips();
    updateTooltipVisibility();
  }, 100);
}

function validateSingleInput(input) {
  if (!input) return;

  const value = input.value.trim();
  let isValid = true;

  if (input.hasAttribute("required") && value === "") {
    isValid = false;
  }

  if (input.id === "newFileRev" && value !== "" && !/^\d+\.\d+$/.test(value)) {
    isValid = false;
  }

  addValidationClass(input, isValid);
}

function setupNewUploadModal() {
  // Upload type radio button handlers
  const uploadTypeRadios = document.querySelectorAll(
    'input[name="uploadType"]'
  );
  uploadTypeRadios.forEach((radio) => {
    radio.addEventListener("change", updateUploadTypeView);
  });

  // Form submission handler
  // const newUploadForm = document.getElementById("newUploadForm");
  // if (newUploadForm) {
  //   newUploadForm.removeEventListener("submit", handleFormSubmission); // Remove any existing listeners
  //   newUploadForm.addEventListener("submit", handleFormSubmission);
  // }

  // Cancel button handler
  const cancelBtn = document.getElementById("cancelNewUpload");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      document.getElementById("newUploadModal").classList.add("hidden");
    });
  }

  // Real-time validation handlers
  const inputs = document.querySelectorAll("#newUploadForm input[required]");
  inputs.forEach((input) => {
    input.addEventListener("blur", function () {
      validateSingleInput(this);
    });

    input.addEventListener("input", function () {
      // Clear validation state on input
      this.classList.remove(
        "border-red-500",
        "border-green-500",
        "ring-red-500",
        "ring-green-500",
        "ring-2",
        "ring-opacity-25"
      );
    });
  });

  // Special validation for revision field
  const revInput = document.getElementById("newFileRev");
  if (revInput) {
    revInput.addEventListener("blur", function () {
      const value = this.value.trim();
      const isValid = value !== "" && /^\d+\.\d+$/.test(value);
      addValidationClass(this, isValid);
    });
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

  // Add tooltips to modal elements after it's shown
  setTimeout(() => {
    addModalTooltips();
    updateTooltipVisibility();
  }, 100);
}

function openDashboardModal() {
  const modal = document.getElementById("dashboardModal");
  if (modal) {
    modal.classList.remove("hidden");
    loadAndRenderDashboard().then(() => {
      // Add tooltips to dashboard elements after content is loaded
      setTimeout(() => {
        addDashboardTooltips();
        updateTooltipVisibility();
      }, 200);
    });
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

      if (
        currentConfig &&
        currentConfig.is_admin &&
        index === 0 &&
        historyData.history.length > 1
      ) {
        adminActions = `<button class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-red-500 to-red-600 text-white rounded-md hover:bg-opacity-80 transition-colors text-sm font-semibold admin-action-btn js-revert-btn ${adminBtnVisibility}" data-filename="${historyData.filename}" data-commit-hash="${commit.commit_hash}"><i class="fa-solid fa-undo"></i><span>Revert</span></button>`;
      }

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
                <a href="/files/${historyData.filename}/versions/${
        commit.commit_hash
      }" class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 rounded-md hover:bg-opacity-80 transition-colors text-sm font-semibold">
                    <i class="fa-solid fa-file-arrow-down"></i><span>Download</span>
                </a>
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

  // Add tooltips to history modal elements
  setTimeout(() => {
    addHistoryModalTooltips();
    updateTooltipVisibility();
  }, 100);

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

  // Add tooltips to message modal elements
  setTimeout(() => {
    addModalTooltips();
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
        document.querySelector(".js-history-modal")?.remove(); // Close the history modal
        loadFiles(); // Refresh file list to show the new state
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

// function showFileHistoryModal(historyData) {
//   const modal = document.createElement("div");
//   modal.className =
//     "fixed inset-0 bg-mc-dark-bg bg-opacity-80 flex items-center justify-center p-4 z-[100] js-history-modal";
//   modal.addEventListener("click", (e) => {
//     if (e.target === modal) modal.remove();
//   });

//   const allRevisions = Array.from(
//     new Set(
//       historyData.history
//         .map((commit) => (commit.revision ? parseFloat(commit.revision) : null))
//         .filter((rev) => rev !== null && !isNaN(rev))
//     )
//   ).sort((a, b) => a - b);

//   let historyListHtml = "";
//   if (historyData.history && historyData.history.length > 0) {
//     historyData.history.forEach((commit, index) => {
//       const revisionBadge = commit.revision
//         ? `<span class="font-bold text-xs bg-primary-200 text-primary-800 dark:bg-primary-700 dark:text-primary-200 px-2 py-1 rounded-full">REV ${commit.revision}</span>`
//         : "";

//       let adminActions = "";
//       const adminBtnVisibility = isAdminModeEnabled ? "" : "hidden";

//       if (
//         currentConfig &&
//         currentConfig.is_admin &&
//         index === 0 &&
//         historyData.history.length > 1
//       ) {
//         adminActions = `<button class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-red-500 to-red-600 text-white rounded-md hover:bg-opacity-80 transition-colors text-sm font-semibold admin-action-btn js-revert-btn ${adminBtnVisibility}" data-filename="${historyData.filename}" data-commit-hash="${commit.commit_hash}"><i class="fa-solid fa-undo"></i><span>Revert</span></button>`;
//       }

//       historyListHtml += `<div class="p-4 bg-gradient-to-r from-primary-100 to-primary-200 dark:from-mc-dark-accent dark:to-primary-700 rounded-lg border border-primary-300 dark:border-mc-dark-accent bg-opacity-95 history-item" data-revision="${
//         commit.revision || ""
//       }">
//         <div class="flex justify-between items-start">
//             <div>
//                 <div class="flex items-center space-x-3 text-sm mb-2 flex-wrap gap-y-1">
//                     <span class="font-mono font-bold text-accent dark:text-accent">${commit.commit_hash.substring(
//                       0,
//                       8
//                     )}</span>
//                     ${revisionBadge}
//                     <span class="text-primary-600 dark:text-primary-300">${formatDate(
//                       commit.date
//                     )}</span>
//                 </div>
//                 <div class="text-primary-900 dark:text-primary-200 text-sm mb-1">${
//                   commit.message
//                 }</div>
//                 <div class="text-xs text-primary-600 dark:text-primary-300">Author: ${
//                   commit.author_name
//                 }</div>
//             </div>
//             <div class="flex-shrink-0 ml-4 flex items-center space-x-2">
//                 ${adminActions}
//                 <a href="/files/${historyData.filename}/versions/${
//         commit.commit_hash
//       }" class="flex items-center space-x-2 px-3 py-1.5 bg-gradient-to-r from-primary-300 to-primary-400 dark:from-mc-dark-accent dark:to-primary-700 text-primary-900 dark:text-primary-200 rounded-md hover:bg-opacity-80 transition-colors text-sm font-semibold">
//                     <i class="fa-solid fa-file-arrow-down"></i><span>Download</span>
//                 </a>
//             </div>
//         </div>
//       </div>`;
//     });
//   } else {
//     historyListHtml = `<p class="text-center text-primary-600 dark:text-primary-300">No version history available.</p>`;
//   }

//   const revisionFilterHtml =
//     allRevisions.length > 1
//       ? `
//     <div class="flex items-center justify-center space-x-6 mt-4">
//         <div class="flex items-center space-x-2">
//             <label for="revFilterFrom" class="text-sm font-medium text-primary-800 dark:text-primary-200">From Rev:</label>
//             <input type="number" id="revFilterFrom" value="${
//               allRevisions[0]
//             }" min="${allRevisions[0]}" max="${
//           allRevisions[allRevisions.length - 1]
//         }" step="0.1"
//                    class="w-24 p-1 text-center font-semibold border border-primary-400 dark:border-mc-dark-accent rounded-md bg-white dark:bg-mc-dark-accent text-primary-900 dark:text-primary-100 focus:ring-accent focus:border-accent">
//         </div>
//         <div class="flex items-center space-x-2">
//             <label for="revFilterTo" class="text-sm font-medium text-primary-800 dark:text-primary-200">To Rev:</label>
//             <input type="number" id="revFilterTo" value="${
//               allRevisions[allRevisions.length - 1]
//             }" min="${allRevisions[0]}" max="${
//           allRevisions[allRevisions.length - 1]
//         }" step="0.1"
//                    class="w-24 p-1 text-center font-semibold border border-primary-400 dark:border-mc-dark-accent rounded-md bg-white dark:bg-mc-dark-accent text-primary-900 dark:text-primary-100 focus:ring-accent focus:border-accent">
//         </div>
//     </div>
//   `
//       : "";

//   modal.innerHTML = `<div class="bg-white dark:bg-mc-dark-bg rounded-lg shadow-lg w-full max-w-4xl flex flex-col max-h-[90vh] bg-opacity-95 border border-transparent bg-gradient-to-br from-white to-mc-light-accent dark:from-mc-dark-bg dark:to-mc-dark-accent">
//     <div class="flex-shrink-0 p-6 pb-4 border-b border-primary-300 dark:border-mc-dark-accent">
//         <div class="flex justify-between items-center">
//             <h3 class="text-xl font-semibold text-primary-900 dark:text-primary-100">Version History - ${historyData.filename}</h3>
//             <button class="text-primary-600 hover:text-primary-900 dark:text-primary-300 dark:hover:text-accent" onclick="this.closest('.js-history-modal').remove()">
//                 <i class="fa-solid fa-xmark text-2xl"></i>
//             </button>
//         </div>

//         ${revisionFilterHtml}

//     </div>
//     <div id="historyListContainer" class="overflow-y-auto p-6 space-y-4">
//         ${historyListHtml}
//     </div>
//   </div>`;
//   document.body.appendChild(modal);

//   const historyItems = modal.querySelectorAll(".history-item");
//   const fromInput = document.getElementById("revFilterFrom");
//   const toInput = document.getElementById("revFilterTo");

//   const applyFilters = () => {
//     const minRev = parseFloat(fromInput.value) || allRevisions[0];
//     const maxRev =
//       parseFloat(toInput.value) || allRevisions[allRevisions.length - 1];

//     if (minRev > maxRev) {
//       return;
//     }

//     historyItems.forEach((item) => {
//       const itemRevStr = item.dataset.revision;
//       let revMatch = true;

//       if (itemRevStr && itemRevStr !== "") {
//         const itemRev = parseFloat(itemRevStr);
//         revMatch = itemRev >= minRev && itemRev <= maxRev;
//       } else {
//         revMatch = false;
//       }

//       item.style.display = revMatch ? "" : "none";
//     });
//   };

//   if (fromInput && toInput) {
//     fromInput.addEventListener("input", applyFilters);
//     toInput.addEventListener("input", applyFilters);
//     applyFilters();
//   }
// }

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
    addFileNamingHelper();
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
    populateMasterFileList(); // Populate the datalist when switching to link mode
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
      // Parse specific error types for better user feedback
      let errorMessage = result.detail || "Upload failed";

      // Handle specific error cases
      if (response.status === 409) {
        // File already exists
        errorMessage = `❌ ${errorMessage}\n\nTip: Try a different filename or check if a similar file/link already exists.`;
      } else if (response.status === 404) {
        // Master file not found (for links)
        errorMessage = `❌ ${errorMessage}\n\nTip: Make sure the master file exists and is spelled correctly.`;
      } else if (response.status === 400) {
        // Validation errors
        errorMessage = `❌ ${errorMessage}`;
      }

      throw new Error(errorMessage);
    }

    // Success handling
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
    // Enhanced error display
    let displayError = error.message;

    // If it's a network error, provide helpful guidance
    if (error.name === "TypeError" || error.message.includes("fetch")) {
      displayError =
        "❌ Network Error: Could not connect to server.\n\nPlease check your connection and try again.";
    }

    debounceNotifications(displayError, "error");

    // Keep the modal open so user can fix issues
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

function handleFormSubmission(e) {
  e.preventDefault();

  const form = e.target;
  const formData = new FormData();
  formData.append("user", currentUser);

  const description = form.querySelector("#newFileDescription").value.trim();
  const rev = form.querySelector("#newFileRev").value.trim();
  const uploadType =
    form.querySelector('input[name="uploadType"]:checked')?.value || "file";

  // Client-side validation
  const validation = validateUploadForm(form);

  if (!validation.isValid) {
    debounceNotifications(
      `Please fix the following errors:\n• ${validation.errors.join("\n• ")}`,
      "error"
    );
    return;
  }

  // Add common fields
  formData.append("description", description);
  formData.append("rev", rev);

  if (uploadType === "link") {
    const newLinkFilename = form.querySelector("#newLinkFilename").value.trim();
    const linkToMaster = form.querySelector("#linkToMaster").value.trim();

    formData.append("is_link_creation", "true");
    formData.append("new_link_filename", newLinkFilename);
    formData.append("link_to_master", linkToMaster);
  } else {
    const fileInput = form.querySelector("#newFileUpload");
    formData.append("is_link_creation", "false");
    formData.append("file", fileInput.files[0]);
  }

  uploadNewFile(formData);
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

  // --- NEW: Admin-only logic for the activity feed ---
  if (currentConfig && currentConfig.is_admin) {
    // Admin view: show both columns
    activityFeedContainer.style.display = "flex";
    activeCheckoutsContainer.classList.remove("w-full");
    activeCheckoutsContainer.classList.add("md:w-1/2");
    activityFeedContainer.innerHTML = loadingSpinner;

    await Promise.all([
      loadAndRenderActiveCheckouts(),
      loadAndRenderActivityFeed(),
    ]);
  } else {
    // Regular user view: hide activity feed and expand active checkouts
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

async function loadAndRenderActivityFeed() {
  const container = document.getElementById("activityFeedContainer");
  try {
    const response = await fetch("/dashboard/activity");
    if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
    const data = await response.json();

    // --- NEW: Create user filter dropdown ---
    const users = Array.from(
      new Set(data.activities.map((act) => act.user))
    ).sort();
    const filterHtml = `
          <div class="relative mb-4 flex-shrink-0">
            <label for="activityUserFilter" class="text-sm font-medium text-primary-800 dark:text-primary-200 mr-2">Filter by User:</label>
            <select id="activityUserFilter" class="w-full sm:w-auto p-2 border border-primary-400 dark:border-mc-dark-accent rounded-md bg-white dark:bg-mc-dark-accent text-primary-900 dark:text-primary-100 focus:ring-accent focus:border-accent">
              <option value="all">All Users</option>
              ${users
                .map((user) => `<option value="${user}">${user}</option>`)
                .join("")}
            </select>
          </div>
        `;

    let activityListHtml =
      '<div id="activity-list" class="space-y-4 flex-grow overflow-y-auto">';
    if (data.activities.length === 0) {
      activityListHtml += `<p class="text-center text-primary-600 dark:text-primary-300 py-8">No recent activity found.</p>`;
    } else {
      data.activities.forEach((item) => {
        const iconMap = {
          CHECK_IN: { icon: "fa-upload", color: "text-blue-500" },
          CHECK_OUT: { icon: "fa-download", color: "text-green-500" },
          CANCEL: { icon: "fa-times-circle", color: "text-yellow-500" },
          OVERRIDE: { icon: "fa-unlock", color: "text-orange-500" },
        };
        const { icon, color } = iconMap[item.event_type] || {
          icon: "fa-question-circle",
          color: "text-gray-500",
        };
        const verbMap = {
          CHECK_IN: "checked in",
          CHECK_OUT: "checked out",
          CANCEL: "canceled checkout for",
          OVERRIDE: "overrode lock on",
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
                                ${
                                  item.revision ? ` (Rev ${item.revision})` : ""
                                }
                            </p>
                            <p class="text-xs text-primary-600 dark:text-primary-400">${formatDate(
                              item.timestamp
                            )}</p>
                        </div>
                    </div>`;
      });
    }
    activityListHtml += "</div>";

    container.innerHTML = `
            <h4 class="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-2 flex-shrink-0">Recent Activity</h4>
            ${filterHtml}
            ${activityListHtml}
        `;

    // --- NEW: Add event listener for the filter ---
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
  } catch (error) {
    container.innerHTML = `<h4 class="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4">Recent Activity</h4><p class="text-center text-red-500">Error: ${error.message}</p>`;
  }
}

function openDashboardModal() {
  const modal = document.getElementById("dashboardModal");
  if (modal) {
    modal.classList.remove("hidden");
    loadAndRenderDashboard();
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

  // Clear previous validation
  clearFormValidation();

  // Description validation
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

  // Revision validation
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

    // Check if user is trying to link to themselves
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

      // Additional file validation
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

  // Remove existing classes
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

  datalist.innerHTML = ""; // Clear old options

  // Create a flat list of all physical files (not links)
  if (!groupedFiles || Object.keys(groupedFiles).length === 0) {
    return; // No files available
  }

  const physicalFiles = Object.values(groupedFiles)
    .flat()
    .filter((file) => !file.is_link); // Only include real files, not links

  // Use a Set to ensure unique filenames
  const uniqueFilenames = new Set(physicalFiles.map((file) => file.filename));

  uniqueFilenames.forEach((filename) => {
    const option = document.createElement("option");
    option.value = filename;
    datalist.appendChild(option);
  });
}

// -- New Confirmation Modal Function --
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

  // Add tooltips if enabled
  setTimeout(() => {
    updateTooltipVisibility();
  }, 100);
}

document.addEventListener("DOMContentLoaded", function () {
  applyThemePreference();
  loadConfig();
  loadFiles();

  // Initialize tooltip system
  initTooltipSystem();
  setupNewUploadModal();

  setTimeout(() => connectWebSocket(), 1000);

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

  // Search field logic with clear button
  const searchInput = document.getElementById("searchInput");
  const clearSearchBtn = document.getElementById("clearSearchBtn");

  searchInput.addEventListener("input", () => {
    renderFiles();
    if (searchInput.value.length > 0) {
      clearSearchBtn.classList.remove("hidden");
    } else {
      clearSearchBtn.classList.add("hidden");
    }
  });

  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    clearSearchBtn.classList.add("hidden");
    renderFiles();
    searchInput.focus();
  });

  document.getElementById("collapseAllBtn")?.addEventListener("click", () => {
    document
      .querySelectorAll("#fileList details[open]")
      .forEach((detailsEl) => {
        detailsEl.open = false;
      });
    saveExpandedState();
  });

  const dashboardBtn = document.getElementById("dashboardBtn");
  if (dashboardBtn) {
    dashboardBtn.addEventListener("click", openDashboardModal);
  }

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

  document.addEventListener("click", (e) => {
    const fileListButton = e.target.closest("#fileList button, #fileList a");
    if (fileListButton && fileListButton.dataset.filename) {
      const filename = fileListButton.dataset.filename;
      if (fileListButton.classList.contains("js-checkout-btn"))
        checkoutFile(filename);
      else if (fileListButton.classList.contains("js-checkin-btn"))
        showCheckinDialog(filename);
      else if (fileListButton.classList.contains("js-cancel-checkout-btn"))
        cancelCheckout(filename);
      else if (fileListButton.classList.contains("js-override-btn"))
        adminOverride(filename);
      else if (fileListButton.classList.contains("js-delete-btn"))
        adminDeleteFile(filename);
      else if (fileListButton.classList.contains("js-history-btn"))
        viewFileHistory(filename);
    }

    const revertButton = e.target.closest(".js-revert-btn");
    if (revertButton) {
      const { filename, commitHash } = revertButton.dataset;
      revertCheckin(filename, commitHash);
    }
  });

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

  const newUploadForm = document.getElementById("newUploadForm");
  // Replace your existing 'newUploadForm.addEventListener("submit", ...)' with this
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

    // --- NEW VALIDATION LOGIC ---
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
      // 'file' upload type
      const fileInput = document.getElementById("newFileUpload");
      if (fileInput.files.length === 0) {
        debounceNotifications("Please select a file to upload.", "error");
        return;
      }
      formData.append("is_link_creation", false);
      formData.append("file", fileInput.files[0]);
    }

    // If all validation passes, proceed
    formData.append("description", description);
    formData.append("rev", rev);

    uploadNewFile(formData);
    document.getElementById("newUploadModal").classList.add("hidden");
  });

  document
    .getElementById("cancelNewUpload")
    .addEventListener("click", () =>
      document.getElementById("newUploadModal").classList.add("hidden")
    );

  const sendMessageForm = document.getElementById("sendMessageForm");
  document
    .getElementById("cancelSendMessage")
    .addEventListener("click", () =>
      document.getElementById("sendMessageModal").classList.add("hidden")
    );
  sendMessageForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const recipient = document.getElementById("recipientUserSelect").value;
    const message = document.getElementById("messageText").value;
    if (recipient && message) {
      sendMessage(recipient, message);
      sendMessageForm.reset();
      document.getElementById("sendMessageModal").classList.add("hidden");
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
        token: document.getElementById("token").value,
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
        await loadFiles();
        disconnectWebSocket();
        connectWebSocket();
        tokenInput.value = "";
      } catch (error) {
        debounceNotifications(`Config Error: ${error.message}`, "error");
      }
    });
});
