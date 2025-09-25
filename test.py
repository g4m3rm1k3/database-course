import os
from pathlib import Path


def clear_config_file():
    """
    Finds the config.json file and attempts to clear its contents by
    opening it in write mode and immediately closing it.
    """
    try:
        # Determine the path to the config file, exactly like the main app does
        if os.name == 'nt':  # Windows
            config_file_path = Path.home() / 'AppData' / 'Local' / \
                'MastercamGitInterface' / 'config.json'
        else:  # MacOS/Linux
            config_file_path = Path.home() / '.config' / \
                'mastercam_git_interface' / 'config.json'

        print(f"Attempting to access config file at: {config_file_path}")

        # Check if the file exists before trying to clear it
        if not config_file_path.exists():
            print(
                "\n[RESULT] Failure: The config file does not exist at that location.")
            return

        # The 'w' mode opens a file for writing. If the file exists, its
        # contents are erased (truncated). This is our test.
        with open(config_file_path, 'w') as f:
            # We don't need to write anything; opening it is enough to clear it.
            pass

        print(
            "\n[RESULT] Success! The script was able to open and clear the config file.")
        print("This means the main app is NOT locking the file.")

    except PermissionError:
        print(
            "\n[RESULT] PermissionError: The script was blocked by the operating system.")
        print("This confirms the issue is Windows folder permissions, not a file lock from the app.")
    except Exception as e:
        print(f"\n[RESULT] An unexpected error occurred: {e}")


clear_config_file()
