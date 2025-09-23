import os
from pathlib import Path

def test_folder_creation():
    """
    Tests if the script has permission to create the application's
    default configuration folder.
    """
    print("--- Starting Permission Test ---")

    try:
        # Determine the target path exactly like the main application does
        if os.name == 'nt': # This is for Windows
            target_dir = Path.home() / 'AppData' / 'Local' / 'MastercamGitInterface'
        else: # This is for macOS/Linux
            target_dir = Path.home() / '.config' / 'mastercam_git_interface'

        print(f"Attempting to create folder at: {target_dir}")

        # Try to create the directory
        target_dir.mkdir(parents=True, exist_ok=True)
        print("\nSUCCESS: The folder was created successfully.")
        print("This means the application *should* have the correct permissions.")

        # Clean up by removing the created folder
        target_dir.rmdir()
        print(f"Cleaned up by removing the test folder.")

    except PermissionError:
        print("\n*** TEST FAILED ***")
        print("A PermissionError was caught. This confirms the application is being blocked")
        print("by the operating system's security policies from writing to that location.")
        print("Moving the config to the Documents folder is the correct solution.")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

    print("\n--- Test Complete ---")

if __name__ == "__main__":
    test_folder_creation()
