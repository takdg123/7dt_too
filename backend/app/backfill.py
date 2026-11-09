"""
Backfill script to migrate existing alert folders to SQLite database.
This script scans all alert folders and creates database rows with basic information.
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()

# Try to import astropy, but make it optional
try:
    from astropy.io import ascii
    ASTROPY_AVAILABLE = True
except ImportError as e:
    print(f"Warning: astropy not available ({e}). Some features may be limited.")
    ASTROPY_AVAILABLE = False
    ascii = None

# Add supy path for parse_coordinates
sys.path.insert(0, "/home/7dt/script/supy")
try:
    from supy.tiles import parse_coordinates
    PARSE_COORDS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: supy.tiles.parse_coordinates not available ({e}). Coordinate parsing will be limited.")
    PARSE_COORDS_AVAILABLE = False
    parse_coordinates = None

# Import database functions
# Handle both script execution and module import
import os
try:
    from .too_db import create_alert_row, init_db, read_row_by_key_and_trigger
except ImportError:
    # When run as script
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from app.too_db import create_alert_row, init_db, read_row_by_key_and_trigger

PARENT_DIR = Path(os.getenv("SDT_DATA_FOLDER"), "alert")

def extract_trigger_time_from_path(dir_path):
    """
    Extract trigger time from the folder name.
    Folder structure: /path/to/alert/{YYYYMMDD_HHMMSS}/
    Folder name is in UTC, converts to KST (UTC+9) for storage.
    Returns trigger time as ISO format string, or None if not found.
    """
    try:
        folder_name = dir_path.name
        
        # Try to parse YYYYMMDD_HHMMSS format
        if len(folder_name) >= 15 and folder_name[8] == '_':
            year = int(folder_name[0:4])
            month = int(folder_name[4:6])
            day = int(folder_name[6:8])
            hour = int(folder_name[9:11])
            minute = int(folder_name[11:13])
            second = int(folder_name[13:15])
            
            # Folder name is in UTC, convert to KST (UTC+9)
            trigger_dt_utc = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
            kst = timezone(timedelta(hours=9))
            trigger_dt_kst = trigger_dt_utc.astimezone(kst)
            return trigger_dt_kst.isoformat()
    except (ValueError, IndexError) as e:
        print(f"Error parsing trigger time from folder name {folder_name}: {e}")
    
    return None

def process_alert_folder(alert_dir: Path) -> str:
    """
    Process a single alert folder and create a database row.
    
    Args:
        alert_dir: Path to the alert folder (e.g., /path/to/alert/20250209_023600/)
    
    Returns:
        "success" if a new row is created,
        "skipped" if row already exists,
        "error" otherwise
    """
    # Read alert_rawdata.json
    rawdata_file = alert_dir / "alert_rawdata.json"
    if not rawdata_file.exists():
        print(f"Warning: {rawdata_file} not found, skipping {alert_dir.name}")
        return False
    
    try:
        with open(rawdata_file) as f:
            rawdata = json.load(f)
    except Exception as e:
        print(f"Error reading {rawdata_file}: {e}")
        return False
    
    # Read alert_status.json
    status_file = alert_dir / "alert_status.json"
    alert_key = None
    is_inputted = None
    is_observed = None
    if status_file.exists():
        try:
            with open(status_file) as f:
                status = json.load(f)
                alert_key = status.get('key')
                is_inputted = status.get('is_inputted')
                is_observed = status.get('is_observed')
        except Exception as e:
            print(f"Error reading {status_file}: {e}")
    
    # Extract trigger time from folder name
    trigger_time = extract_trigger_time_from_path(alert_dir)
    if not trigger_time:
        print(f"Warning: Could not extract trigger time from {alert_dir.name}")
        return False
    
    # Use alert_key from status, or generate from folder name if not available
    effective_alert_key = alert_key or alert_dir.name

    # Check if row already exists
    if read_row_by_key_and_trigger(effective_alert_key, trigger_time):
        print(f"Row already exists for {alert_dir.name}, skipping")
        return "skipped"
    
    # Extract basic fields from rawdata
    requester = rawdata.get('requester', '')
    objname = rawdata.get('objname', '')
    ra_str = rawdata.get('RA', '')
    dec_str = rawdata.get('De', '')
    exptime = str(rawdata.get('exptime', ''))
    n_image = str(rawdata.get('count', ''))
    gain = str(rawdata.get('gain', ''))
    binning = str(rawdata.get('binning', ''))
    comments = rawdata.get('comments', '')
    
    # Parse and normalize coordinates: keep in HH:MM:SS format, also calculate degrees
    from app.utils import normalize_coordinate_to_hms, normalize_coordinate_to_deg
    if PARSE_COORDS_AVAILABLE:
        try:
            ra_deg_val, dec_deg_val = parse_coordinates([ra_str, dec_str])
            # parse_coordinates returns decimal degrees
            ra_deg = f"{ra_deg_val:.6f}"
            dec_deg = f"{dec_deg_val:.6f}"
            # Convert to HH:MM:SS format
            ra = normalize_coordinate_to_hms(ra_deg, is_ra=True)
            dec = normalize_coordinate_to_hms(dec_deg, is_ra=False)
        except Exception as e:
            print(f"Error parsing coordinates for {alert_dir.name}: {e}")
            # Fallback to normalization functions
            ra = normalize_coordinate_to_hms(ra_str, is_ra=True)
            dec = normalize_coordinate_to_hms(dec_str, is_ra=False)
            ra_deg = normalize_coordinate_to_deg(ra, is_ra=True)
            dec_deg = normalize_coordinate_to_deg(dec, is_ra=False)
    else:
        # Use normalization functions
        ra = normalize_coordinate_to_hms(ra_str, is_ra=True)
        dec = normalize_coordinate_to_hms(dec_str, is_ra=False)
        ra_deg = normalize_coordinate_to_deg(ra, is_ra=True)
        dec_deg = normalize_coordinate_to_deg(dec, is_ra=False)
    
    # Read alert_formatted.ascii_fixed_width to get tile
    tile = None
    formatted_file = alert_dir / "alert_formatted.ascii_fixed_width"
    if formatted_file.exists() and ASTROPY_AVAILABLE:
        try:
            formatted_table = ascii.read(str(formatted_file), format='fixed_width')
            if len(formatted_table) > 0 and 'objname' in formatted_table.colnames:
                tile = str(formatted_table[0]['objname'])
        except Exception as e:
            print(f"Error reading formatted file for {alert_dir.name}: {e}")
    elif formatted_file.exists() and not ASTROPY_AVAILABLE:
        # Try to parse manually without astropy
        try:
            with open(formatted_file, 'r') as f:
                lines = f.readlines()
                if len(lines) >= 2:
                    # Second line should have the data
                    parts = lines[1].split('|')
                    if len(parts) >= 3:
                        # objname is typically the second column
                        tile = parts[2].strip()
        except Exception as e:
            print(f"Error reading formatted file for {alert_dir.name}: {e}")
    
    alert_key = effective_alert_key
    
    # Ensure ra_deg and dec_deg are set as floats
    if 'ra_deg' not in locals():
        ra_deg_str = normalize_coordinate_to_deg(ra, is_ra=True)
        try:
            ra_deg = float(ra_deg_str)
        except (ValueError, TypeError):
            ra_deg = None
    if 'dec_deg' not in locals():
        dec_deg_str = normalize_coordinate_to_deg(dec, is_ra=False)
        try:
            dec_deg = float(dec_deg_str)
        except (ValueError, TypeError):
            dec_deg = None
    
    # Convert exptime to float, n_image/gain/binning to integer
    try:
        exptime = float(exptime) if exptime else None
    except (ValueError, TypeError):
        exptime = None
    
    try:
        n_image = int(float(n_image)) if n_image else None
    except (ValueError, TypeError):
        n_image = None
    
    try:
        gain = int(float(gain)) if gain else None
    except (ValueError, TypeError):
        gain = None
    
    try:
        binning = int(float(binning)) if binning else None
    except (ValueError, TypeError):
        binning = None
    
    # Create database row with both coordinate formats
    from app.too_db import insert_or_update_row
    try:
        data = {
            'alert_key': alert_key,
            'requester': requester,
            'objname': objname,
            'tile': tile,
            'ra': ra,
            'dec': dec,
            'ra_deg': ra_deg,
            'dec_deg': dec_deg,
            'exptime': exptime,
            'n_image': n_image,
            'gain': gain,
            'binning': binning,
            'comments': comments,
            'trigger_time': trigger_time,
            'is_inputted': is_inputted,
            'is_observed': is_observed,
            'init_notice': 0,
            'interim_notice': 0,
            'final_notice': 0,
            'num_filters': 0,
            'completed': 0
        }
        success = insert_or_update_row(data, update_mode="new")
        if success:
            print(f"✓ Processed {alert_dir.name}")
            return "success"
        else:
            print(f"✗ Failed to create row for {alert_dir.name}")
            return "error"
    except Exception as e:
        print(f"Error creating row for {alert_dir.name}: {e}")
        import traceback
        traceback.print_exc()
        return "error"

def backfill_all_alerts():
    """
    Backfill all alert folders in PARENT_DIR.
    """
    print(f"Starting backfill from {PARENT_DIR}...")
    
    if not PARENT_DIR.exists():
        print(f"Error: Alert directory {PARENT_DIR} does not exist")
        return
    
    # Initialize database
    init_db()
    
    # Find all alert folders (those with YYYYMMDD_HHMMSS format)
    alert_folders = []
    for item in PARENT_DIR.iterdir():
        if item.is_dir():
            folder_name = item.name
            # Check if it matches YYYYMMDD_HHMMSS format
            if len(folder_name) >= 15 and folder_name[8] == '_' and folder_name[:8].isdigit() and folder_name[9:15].isdigit():
                alert_folders.append(item)
    
    print(f"Found {len(alert_folders)} alert folders")
    
    # Process each folder
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, folder in enumerate(sorted(alert_folders), 1):
        print(f"[{i}/{len(alert_folders)}] Processing {folder.name}...", end=" ")
        
        result = process_alert_folder(folder)
        if result == "success":
            success_count += 1
        elif result == "skipped":
            skip_count += 1
        else:
            error_count += 1
    
    print(f"\nBackfill complete!")
    print(f"  Success: {success_count}")
    print(f"  Skipped (already exists): {skip_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {len(alert_folders)}")

if __name__ == "__main__":
    backfill_all_alerts()

