# User Acceptance Test (UAT) – Mastercam GitLab Interface

**Version:** 1.0  
**Date:** YYYY-MM-DD  
**Tester Name:** **********\_**********

---

## 1. Objective

Verify that the Mastercam GitLab Interface meets functional and UI requirements through routine user actions.

---

## 2. Test Environment

- OS: Windows 10 / 11
- Browser: Chrome / Edge / Firefox
- Tailwind CSS: Built and loaded
- GitLab account: Active, with test repository access

---

## 3. Test Scenarios

### Loading & Initial UI

- [ ] Open `index.html` in the browser
  - Expected: App loads with correct dark/light mode and main layout visible
- [ ] Verify connection indicator
  - Expected: Green dot shows connected, text reads "Connected"
- [ ] Check displayed username
  - Expected: Correct username shown
- [ ] Check repository status
  - Expected: Status shows "Ready"

### File Management

- [ ] Search for a file using search box
  - Expected: File list filters correctly
- [ ] Click "Upload New File" and select a `.mcam` file
  - Expected: File uploads and appears in the list
- [ ] Click a file to check-in
  - [ ] Enter commit message
  - [ ] Upload updated file
  - [ ] Submit check-in
  - Expected: File updates in repo and commit message recorded
- [ ] Open check-in modal and click "Cancel"
  - Expected: Modal closes, no changes made

### Configuration & Settings

- [ ] Open Settings panel by clicking gear icon
  - Expected: Panel slides in from right
- [ ] Fill in GitLab URL, Project ID, Username, and Access Token
  - [ ] Click "Save Configuration"
  - Expected: Settings saved, Current Status updates correctly
- [ ] Verify "Current Status" panel shows correct information

### Theme & Appearance

- [ ] Toggle dark/light mode
  - Expected: Page theme switches correctly
- [ ] Inspect fonts and colors
  - Expected: Mastercam gold accent and Tailwind classes applied properly

### UI & Responsiveness

- [ ] Resize window to mobile size
  - Expected: Layout adapts, buttons accessible
- [ ] Click "Refresh" button
  - Expected: File list reloads from repository

---

## 4. Notes

- Validate all required fields before saving configuration
- Ensure modals close properly and no UI elements are blocked
- Check for any user-friendly error messages if actions fail

---

## 5. Tester Sign-off

**Tester Name:** ********\_\_\_********  
**Signature:** ********\_\_\_********  
**Date:** ********\_\_\_********  
**Comments:**
