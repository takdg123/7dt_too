"""
Alert monitoring service that watches for new alert folders and creates database rows.
This replaces the old too_table.py monitoring functionality.
"""
import time
import sys
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
load_dotenv()

TOO_DB_PATH = os.getenv("TOO_DB_PATH")

# Add paths
sys.path.insert(0, "/home/7dt/script/supy")

# Import database functions
try:
    from .too_db import create_alert_from_folder, init_db
except ImportError:
    # When run as script
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from app.too_db import create_alert_from_folder, init_db

PARENT_DIR = Path(os.getenv("SDT_DATA_FOLDER"), "alert")

class AlertFolderHandler(FileSystemEventHandler):
    """Handle new alert folder creation"""
    
    def __init__(self):
        super().__init__()
        self.processed_folders = set()
    
    def is_alert_folder(self, path: Path) -> bool:
        """Check if a path is an alert folder (YYYYMMDD_HHMMSS format)"""
        if not path.is_dir():
            return False
        
        folder_name = path.name
        # Check if it matches YYYYMMDD_HHMMSS format
        if len(folder_name) >= 15 and folder_name[8] == '_':
            if folder_name[:8].isdigit() and folder_name[9:15].isdigit():
                return True
        return False
    
    def on_created(self, event):
        """Called when a new file or directory is created"""
        if event.is_directory:
            folder_path = Path(event.src_path)
            if self.is_alert_folder(folder_path):
                # Wait a bit for files to be written
                time.sleep(2)
                self.process_alert_folder(folder_path)
    
    def process_alert_folder(self, folder_path: Path):
        """Process a new alert folder and create database row"""
        folder_name = folder_path.name
        
        # Skip if already processed
        if folder_name in self.processed_folders:
            return
        
        # Check if required files exist
        rawdata_file = folder_path / "alert_rawdata.json"
        if not rawdata_file.exists():
            print(f"Waiting for alert_rawdata.json in {folder_name}...")
            # Wait a bit more and try again
            time.sleep(3)
            if not rawdata_file.exists():
                print(f"Warning: alert_rawdata.json not found in {folder_name}, skipping")
                return
        
        print(f"Processing new alert folder: {folder_name}")
        
        try:
            success = create_alert_from_folder(str(folder_path))
            if success:
                print(f"✓ Successfully created database row for {folder_name}")
                self.processed_folders.add(folder_name)
            else:
                # Check if it already exists in database
                try:
                    import sqlite3
                    from app.utils import extract_trigger_time_from_folder
                    conn = sqlite3.connect(TOO_DB_PATH)
                    cursor = conn.cursor()
                    
                    # Extract trigger_time from folder name (converts UTC to KST)
                    trigger_time = extract_trigger_time_from_folder(folder_name)
                    
                    if trigger_time:
                        cursor.execute(
                            "SELECT id, alert_key FROM too_requests WHERE trigger_time = ?",
                            (trigger_time,)
                        )
                        existing = cursor.fetchone()
                    else:
                        existing = None
                    conn.close()
                    
                    if existing:
                        print(f"ℹ Alert {folder_name} already exists in database (id={existing[0]}, key={existing[1]})")
                        self.processed_folders.add(folder_name)
                    else:
                        print(f"✗ Failed to create database row for {folder_name} - check folder contents and logs")
                except Exception as check_error:
                    print(f"✗ Failed to create database row for {folder_name}: {check_error}")
        except Exception as e:
            print(f"Error processing {folder_name}: {e}")
            import traceback
            traceback.print_exc()

def process_existing_folders():
    """Process any existing alert folders that might not be in the database"""
    print("Checking for existing alert folders...")
    
    if not PARENT_DIR.exists():
        print(f"Error: Alert directory {PARENT_DIR} does not exist")
        return
    
    handler = AlertFolderHandler()
    alert_folders = []
    
    for item in PARENT_DIR.iterdir():
        if item.is_dir() and handler.is_alert_folder(item):
            alert_folders.append(item)
    
    print(f"Found {len(alert_folders)} existing alert folders")
    
    # Process each folder (this will skip if already in database due to unique constraint)
    for folder in sorted(alert_folders):
        handler.process_alert_folder(folder)

def main():
    """Main monitoring loop"""
    print(f"Starting alert monitoring service...")
    print(f"Watching directory: {PARENT_DIR}")
    
    # Initialize database
    init_db()
    
    # Process any existing folders first
    process_existing_folders()
    
    # Set up file system watcher
    event_handler = AlertFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, path=str(PARENT_DIR), recursive=False)
    observer.start()
    
    print("Monitoring for new alerts...")
    print("Press Ctrl+C to stop")
    
    # Periodic check for missed alerts (every 60 seconds)
    last_check = time.time()
    check_interval = 60
    
    try:
        while True:
            time.sleep(1)
            
            # Periodic check for any missed alert folders
            current_time = time.time()
            if current_time - last_check >= check_interval:
                last_check = current_time
                # Quick check for new folders
                if PARENT_DIR.exists():
                    for item in PARENT_DIR.iterdir():
                        if item.is_dir() and event_handler.is_alert_folder(item):
                            folder_name = item.name
                            if folder_name not in event_handler.processed_folders:
                                # Check if it's actually in the database
                                try:
                                    import sqlite3
                                    from app.utils import extract_trigger_time_from_folder
                                    conn = sqlite3.connect(TOO_DB_PATH)
                                    cursor = conn.cursor()
                                    
                                    # Extract trigger_time from folder name (converts UTC to KST)
                                    trigger_time = extract_trigger_time_from_folder(folder_name)
                                    
                                    if trigger_time:
                                        cursor.execute(
                                            "SELECT id FROM too_requests WHERE trigger_time = ?",
                                            (trigger_time,)
                                        )
                                        existing = cursor.fetchone()
                                    else:
                                        existing = None
                                    conn.close()
                                    
                                    if not existing:
                                        print(f"Found missed alert folder: {folder_name}, processing...")
                                        event_handler.process_alert_folder(item)
                                except Exception as e:
                                    # If check fails, try processing anyway
                                    if folder_name not in event_handler.processed_folders:
                                        event_handler.process_alert_folder(item)
    except KeyboardInterrupt:
        print("\nStopping monitor...")
        observer.stop()
    
    observer.join()
    print("Monitoring stopped.")

if __name__ == "__main__":
    main()

