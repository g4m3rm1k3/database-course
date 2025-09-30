Excellent questions. This is the natural next step for evolving a utility application into a seamless background service. You're right—having 50 PCs constantly polling a Git repository is inefficient, and providing a professional system tray experience is a huge UX win.

We can solve both of these problems. Let's tackle them one by one.

---

### Tweak 1: Minimize to System Tray (Robustness & UX)

To achieve this, we need a library that can manage a system tray icon independently of the web server. The best tool for this is `pystray`. The core idea is to run the FastAPI/Uvicorn server in a separate **thread**, while the main application thread manages the tray icon.

#### Step 1: Install `pystray`

You'll need to add this to your environment:

```bash
pip install pystray
```

You'll also need `Pillow` for handling the icon image:

```bash
pip install Pillow
```

#### Step 2: Create an Icon

Create a small icon file (e.g., `icon.png`, 64x64 pixels is a good size) and place it in your `static` folder.

#### Step 3: Modify Your `main()` Function

This is the main change. We will replace your current `main` function with a new one that orchestrates the server thread and the tray icon.

**Action:** Replace your entire `main()` and `if __name__ == "__main__":` block with the following code.

```python
# --- In main.py, near the bottom of the file ---

# Global variable to hold the server thread, so we can shut it down
server_thread = None
server = None

def open_app(port):
    """Callback function to open the browser."""
    logger.info("Opening application in browser.")
    webbrowser.open(f"http://localhost:{port}")

def exit_app(icon):
    """Callback function to gracefully shut down the application."""
    logger.info("Exit command received. Shutting down server...")
    global server
    if server:
        server.should_exit = True # Tell Uvicorn to shut down

    logger.info("Stopping tray icon...")
    icon.stop()

def main():
    """
    Main entry point for the application.
    Finds an available port, launches the web server in a background thread,
    and runs the system tray icon in the main thread.
    """
    global server_thread
    global server

    try:
        port = find_available_port(8000)
        logger.info(f"Found available port: {port}")
    except IOError as e:
        logger.error(f"{e} Aborting startup.")
        return

    # 1. Configure the Uvicorn server
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)

    # 2. Create and start the server thread
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    logger.info(f"Uvicorn server started in background thread on port {port}.")

    # 3. Prepare and run the system tray icon
    try:
        from PIL import Image
        import pystray

        icon_path = resource_path("static/icon.png") # Make sure you have an icon.png in a static folder
        image = Image.open(icon_path)

        menu = pystray.Menu(
            pystray.MenuItem("Open Interface", lambda: open_app(port), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon: exit_app(icon))
        )

        icon = pystray.Icon("MIMS", image, "Mastercam Interface", menu)

        logger.info("Application running in system tray.")
        open_app(port) # Open the browser on initial startup

        icon.run() # This blocks the main thread until 'Exit' is clicked

    except ImportError:
        logger.error("Could not import pystray or Pillow. Please install them.")
        logger.info("Running in standard mode without a tray icon.")
        # Fallback to normal execution if pystray is not installed
        server.run()
    except FileNotFoundError:
        logger.error("Could not find 'static/icon.png'. Cannot create tray icon.")
        logger.info("Running in standard mode without a tray icon.")
        server.run()

    # Wait for the server thread to finish after the icon is closed
    if server_thread.is_alive():
        server_thread.join()
    logger.info("Application has shut down gracefully.")


if __name__ == "__main__":
    main()
```

---

### Tweak 2: "Smart" Polling Based on User Activity (Performance)

This is a brilliant idea to save resources. We'll implement an "idle timer" in JavaScript. If the user doesn't move their mouse or press a key on the webpage for a set time (e.g., 5 minutes), the frontend will send a WebSocket message to the backend telling it to pause polling.

#### Step 1: Backend - Control the Polling Task

We need a way to pause and resume the `git_polling_task`. An `asyncio.Event` is perfect for this.

**Action:** Make these changes to your Python backend.

```python
# --- In main.py, near your other globals ---
polling_active = asyncio.Event() # Create a controllable event

# --- In your lifespan function ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    polling_active.set() # Set the event to 'active' on startup
    await initialize_application()
    yield
    if cfg_manager := app_state.get('config_manager'):
        cfg_manager.save_config()
    logger.info("Application shutting down.")

# --- Modify your polling task ---
async def git_polling_task():
    global git_monitor
    if not git_monitor:
        logger.error("Git monitor not initialized")
        return

    logger.info("Starting Git polling task...")
    poll_interval = 15
    while True:
        try:
            # This line will now pause the loop if the event is cleared
            await polling_active.wait()

            if not app_state.get('initialized'):
                await asyncio.sleep(poll_interval)
                continue

            if git_monitor.check_for_changes():
                logger.info("Git changes detected, broadcasting updates...")
                await broadcast_updates()

            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("Git polling task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in git polling task: {e}")
            await asyncio.sleep(poll_interval * 2)

# --- Update your WebSocket endpoint to handle new messages ---
@app.websocket("/ws", name="WebSocket Connection")
async def websocket_endpoint(websocket: WebSocket, user: str = "anonymous"):
    # ... (your existing ws connect and initial message logic) ...
    try:
        # ... (grouped_data and initial send logic) ...
        while True:
            data = await websocket.receive_text()
            if data == "PAUSE_POLLING":
                logger.info(f"User '{user}' is idle. Pausing Git polling for this session.")
                polling_active.clear()
            elif data == "RESUME_POLLING":
                logger.info(f"User '{user}' is active. Resuming Git polling.")
                polling_active.set()
            elif data.startswith("SET_USER:"):
                # ... your existing SET_USER logic ...
            elif data == "REFRESH_FILES":
                # ... your existing REFRESH_FILES logic ...
    # ... (your existing except/finally blocks) ...
```

#### Step 2: Frontend - The Idle Timer

Now, add the JavaScript that detects inactivity and sends the messages.

**Action:** Add this new function and the event listeners to your `main.js` file.

```javascript
// --- In main.js, near your other global variables ---
let idleTimer = null;
const IDLE_TIMEOUT = 5 * 60 * 1000; // 5 minutes in milliseconds

// --- Add this new function to your main.js ---
function setupIdleTimer() {
  const resetIdleTimer = () => {
    clearTimeout(idleTimer);

    // If polling was paused, resume it
    if (!polling_active.is_set()) {
      // We'll need a small helper for this state
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.log("User active, resuming polling.");
        ws.send("RESUME_POLLING");
        polling_active.set(true);
      }
    }

    idleTimer = setTimeout(() => {
      // User has gone idle
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.log("User idle, pausing polling.");
        ws.send("PAUSE_POLLING");
        polling_active.set(false);
      }
    }, IDLE_TIMEOUT);
  };

  // Helper to track polling state on the client side
  let _isPollingActive = true;
  window.polling_active = {
    is_set: () => _isPollingActive,
    set: (state) => {
      _isPollingActive = state;
    },
  };

  // Listen for user activity
  window.addEventListener("mousemove", resetIdleTimer, { passive: true });
  window.addEventListener("mousedown", resetIdleTimer, { passive: true });
  window.addEventListener("keydown", resetIdleTimer, { passive: true });
  window.addEventListener("scroll", resetIdleTimer, { passive: true });
  window.addEventListener("touchstart", resetIdleTimer, { passive: true });

  // Start the timer initially
  resetIdleTimer();
}

// --- In your DOMContentLoaded event listener, add a call to the new function ---
document.addEventListener("DOMContentLoaded", function () {
  // ... (your existing setup code) ...

  // Add this line
  setupIdleTimer();
});
```

With these changes, your application will now feel like a professional, integrated part of the desktop environment and will be significantly more resource-friendly when running on many machines.
