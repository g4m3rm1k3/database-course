// Global tooltip state
let tooltipCache = new Map();
let tooltipObserver = null;
let tooltipsInitialized = false;

function initTooltipSystem() {
  // Add CSS (keep this part the same)
  if (!document.getElementById("tooltip-styles")) {
    // ... your existing CSS code ...
  }

  // Create toggle button (keep this part the same)
  if (!document.getElementById("tooltip-toggle")) {
    // ... your existing toggle button code ...
  }

  // Instead of immediately adding tooltips, set up lazy loading
  setupLazyTooltips();
}

function setupLazyTooltips() {
  if (!tooltipsEnabled) return;

  // Use Intersection Observer to only add tooltips when elements come into view
  tooltipObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const element = entry.target;
          const tooltipKey = getTooltipKeyForElement(element);

          if (tooltipKey && !element.dataset.tooltipAdded) {
            addTooltipToElement(element, tooltipKey);
            element.dataset.tooltipAdded = "true";
            tooltipObserver.unobserve(element); // Stop observing once tooltip is added
          }
        }
      });
    },
    {
      rootMargin: "50px", // Start loading tooltips 50px before they're visible
    }
  );

  // Observe all potential tooltip elements
  observeTooltipElements();
}

function observeTooltipElements() {
  // Static elements by ID
  Object.keys(tooltips).forEach((elementId) => {
    const element = document.getElementById(elementId);
    if (element && !element.dataset.tooltipAdded) {
      tooltipObserver.observe(element);
    }
  });

  // Dynamic elements by selector (but don't add listeners yet)
  const dynamicSelectors = [
    ".js-checkout-btn",
    ".js-checkin-btn",
    ".js-cancel-checkout-btn",
    ".js-history-btn",
    ".js-override-btn",
    ".js-delete-btn",
    ".js-view-master-btn",
    'a[href*="/download"]',
    ".revision-badge",
    ".file-description",
  ];

  dynamicSelectors.forEach((selector) => {
    document.querySelectorAll(selector).forEach((element) => {
      if (!element.dataset.tooltipAdded) {
        tooltipObserver.observe(element);
      }
    });
  });
}

function getTooltipKeyForElement(element) {
  // Check if it has an ID that maps to a tooltip
  if (element.id && tooltips[element.id]) {
    return element.id;
  }

  // Check dynamic elements by class/attributes
  if (element.classList.contains("js-checkout-btn")) return "checkout";
  if (element.classList.contains("js-checkin-btn")) return "checkin";
  if (element.classList.contains("js-cancel-checkout-btn"))
    return "cancel-checkout";
  if (element.classList.contains("js-history-btn")) return "history";
  if (element.classList.contains("js-override-btn")) return "override";
  if (element.classList.contains("js-delete-btn")) {
    // Check if it's a link or regular file
    const filename = element.dataset.filename;
    const safeId = `file-${filename?.replace(/[^a-zA-Z0-9]/g, "-")}`;
    const fileElement = document.getElementById(safeId);
    const isLink = fileElement?.querySelector(".fa-link");
    return isLink ? "remove-link" : "delete";
  }
  if (element.classList.contains("js-view-master-btn")) return "view-master";
  if (element.href && element.href.includes("/download")) return "view";
  if (element.textContent?.match(/REV \d+\.\d+/)) return "fileRevision";
  if (
    element.classList.contains("italic") &&
    (element.classList.contains("text-gray-700") ||
      element.classList.contains("dark:text-gray-300"))
  ) {
    return "fileDescription";
  }

  return null;
}

// Optimized tooltip creation - only create when actually shown
function showTooltip(event) {
  if (!tooltipsEnabled) return;

  const tooltipKey = event.currentTarget.dataset.tooltip;
  const tooltipData = tooltips[tooltipKey];
  if (!tooltipData) return;

  // Hide any existing tooltips
  document.querySelectorAll(".tooltip.show").forEach((t) => {
    t.classList.remove("show");
    if (t.cleanup) t.cleanup();
  });

  // Check cache first
  let tooltip = tooltipCache.get(tooltipKey);

  // Only create if not in cache
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

    document.body.appendChild(tooltip);
    tooltipCache.set(tooltipKey, tooltip);
  }

  // Position and show
  tooltip.targetElement = event.currentTarget;
  tooltip.preferredPosition = tooltipData.position || "top";
  positionTooltip(tooltip, tooltip.targetElement, tooltip.preferredPosition);

  setTimeout(() => tooltip.classList.add("show"), 10);

  // Add scroll listener
  const repositionOnScroll = () => {
    if (tooltip.classList.contains("show") && tooltip.targetElement) {
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

// Simplified update function for new content
function updateTooltipVisibility() {
  if (!tooltipsEnabled) {
    // Clean up everything
    if (tooltipObserver) {
      tooltipObserver.disconnect();
    }
    document.querySelectorAll("[data-tooltip]").forEach((el) => {
      el.removeEventListener("mouseenter", showTooltip);
      el.removeEventListener("mouseleave", hideTooltip);
      el.removeAttribute("data-tooltip");
      el.classList.remove("tooltip-enabled");
    });
    return;
  }

  // Re-setup lazy loading for new content
  if (!tooltipObserver) {
    setupLazyTooltips();
  } else {
    // Just observe new elements
    observeTooltipElements();
  }
}

// Clean up when toggling tooltips off
function toggleTooltips() {
  tooltipsEnabled = !tooltipsEnabled;
  localStorage.setItem("tooltipsEnabled", tooltipsEnabled.toString());

  const toggleBtn = document.getElementById("tooltip-toggle");
  if (toggleBtn) {
    toggleBtn.classList.toggle("disabled", !tooltipsEnabled);
  }

  if (tooltipsEnabled) {
    setupLazyTooltips();
  } else {
    // Clean up observer and cached tooltips
    if (tooltipObserver) {
      tooltipObserver.disconnect();
      tooltipObserver = null;
    }
    tooltipCache.forEach((tooltip) => tooltip.remove());
    tooltipCache.clear();
  }

  updateTooltipVisibility();
  showNotification(
    tooltipsEnabled ? "Help tooltips enabled" : "Help tooltips disabled",
    "info"
  );
}
