import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
import threading
import time
from .utils import (
    normalize_coordinate_to_hms, 
    normalize_coordinate_to_deg,
    normalize_datetime_field,
    parse_datetime_from_string,
    extract_trigger_time_from_folder
)

from dotenv import load_dotenv
load_dotenv()
# Database file path
TOO_DB_PATH = os.getenv("TOO_DB_PATH")

ref_template_path = "/home/7dt/7dt_too/backend/ref/gcn_template.txt"

# Thread-local storage for database connections
_local = threading.local()

def read_db_connection():
    """Get a thread-local database connection"""
    if not hasattr(_local, 'connection'):
        _local.connection = sqlite3.connect(
            TOO_DB_PATH, 
            check_same_thread=False,
            timeout=10.0  # Wait up to 10 seconds if database is locked
        )
        _local.connection.row_factory = sqlite3.Row
    return _local.connection

def init_db():
    """Initialize the database with the schema and set permissions for multi-user access"""
    # Ensure the database directory exists
    db_dir = os.path.dirname(TOO_DB_PATH)
    os.makedirs(db_dir, exist_ok=True, mode=0o775)
    
    conn = read_db_connection()
    cursor = conn.cursor()
    
    # Create table with required columns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS too_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT,
            requester TEXT,
            objname TEXT,
            tile TEXT,
            ra TEXT,
            dec TEXT,
            ra_deg REAL,
            dec_deg REAL,
            exptime REAL,
            n_image INTEGER,
            gain INTEGER,
            binning INTEGER,
            comments TEXT,
            trigger_time TEXT,
            observation_time TEXT,
            transfer_time TEXT,
            processed_time TEXT,
            v1 INTEGER DEFAULT 0,
            v2 INTEGER DEFAULT 0,
            v2_status TEXT,
            v2_progress REAL,
            file_list TEXT,
            gcn_template TEXT,
            base_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(alert_key, trigger_time)
        )
    ''')
    
    # Create indexes for common queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_key_trigger ON too_requests(alert_key, trigger_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_objname ON too_requests(objname)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tile ON too_requests(tile)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trigger_time ON too_requests(trigger_time)')
    
    # Ensure new columns exist (for backward compatibility with existing databases)
    ensure_column_exists('is_inputted', 'INTEGER')
    ensure_column_exists('is_observed', 'INTEGER')
    ensure_column_exists('base_path', 'TEXT')
    ensure_column_exists('num_filters', 'INTEGER')
    ensure_column_exists('init_notice', 'INTEGER DEFAULT 0')
    ensure_column_exists('interim_notice', 'INTEGER DEFAULT 0')
    ensure_column_exists('final_notice', 'INTEGER DEFAULT 0')
    ensure_column_exists('completed', 'INTEGER DEFAULT 0')
    
    conn.commit()
    
    # Set database file permissions for multi-user access
    # Make it readable and writable by all users
    try:
        # Try to set permissions - this may fail if we don't own the file
        try:
            os.chmod(TOO_DB_PATH, 0o666)
        except OSError:
            # If chmod fails, check if permissions are already correct
            current_stat = os.stat(TOO_DB_PATH)
            current_mode = current_stat.st_mode & 0o777
            if current_mode != 0o666:
                # Only warn if permissions are actually wrong
                pass
        
        # Try to set group ownership to a common group (e.g., sudo, www-data, or a custom group)
        # This allows pipeline users to write to the database if they're in the same group
        # Note: chown requires root privileges, so this will silently fail for non-root users
        try:
            import grp
            import pwd
            
            # Check if we're root - only then can we change ownership
            if os.getuid() == 0:
                # Try to get the current user's group, or use a common group
                current_gid = os.getgid()
                
                # Try common group names that pipeline users might belong to
                # Prioritize www-data so it can modify the database
                group_names = ['www-data', 'sudo', 'users', '7dt']
                group_gid = None
                
                for group_name in group_names:
                    try:
                        group_gid = grp.getgrnam(group_name).gr_gid
                        break
                    except KeyError:
                        continue
                
                # Use found group or current user's group
                if group_gid is None:
                    group_gid = current_gid
                
                # Get current user's UID
                current_uid = os.getuid()
                
                # Change ownership to current user but set group for shared access
                os.chown(TOO_DB_PATH, current_uid, group_gid)
            
        except (ImportError, OSError, PermissionError):
            # If we can't change ownership, that's okay - permissions should still work
            # This is expected for non-root users
            pass
            
    except OSError as e:
        # Only log if it's a real error (not just permission denied for chown)
        # Check if the file is already writable by the group
        try:
            current_stat = os.stat(TOO_DB_PATH)
            current_mode = current_stat.st_mode & 0o777
            # If permissions allow group write (e.g., 666, 664, etc.), don't warn
            if current_mode & 0o020:  # Group write bit is set
                pass  # Permissions are fine, no need to warn
            else:
                print(f"Warning: Could not set database permissions: {e}")
        except:
            print(f"Warning: Could not set database permissions: {e}")

def ensure_column_exists(column_name: str, column_type: str = 'TEXT'):
    """Ensure a column exists in the table, add it if it doesn't"""
    conn = read_db_connection()
    cursor = conn.cursor()
    
    # Try to add the column - if it already exists, the error will be caught
    try:
        cursor.execute(f'ALTER TABLE too_requests ADD COLUMN {column_name} {column_type}')
        conn.commit()
    except sqlite3.OperationalError as e:
        # Column might already exist or there's another issue
        if "duplicate column" not in str(e).lower() and "already exists" not in str(e).lower():
            raise

def _convert_bool_to_int(value: Any) -> int:
    """Convert boolean value to integer (0 or 1) for SQLite storage"""
    if isinstance(value, bool):
        return 1 if value else 0
    elif value is None:
        return 0
    else:
        return 1 if value else 0


def _retry_db_operation(operation, max_attempts: int = 3):
    """Retry database operation on lock error"""
    for attempt in range(max_attempts):
        try:
            return operation()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_attempts - 1:
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
            raise

def _convert_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert database row to dictionary with proper type conversion"""
    row_dict = dict(row)
    
    # Convert integer back to boolean for v1, v2, is_inputted, is_observed
    bool_fields = ['v1', 'v2', 'is_inputted', 'is_observed']
    for field in bool_fields:
        if field in row_dict:
            row_dict[field] = bool(row_dict[field]) if row_dict[field] is not None else False
    
    # Convert file_list from JSON string to list and split into image_list and catalog_list
    if 'file_list' in row_dict and row_dict['file_list']:
        try:
            file_list = json.loads(row_dict['file_list'])
        except (json.JSONDecodeError, TypeError):
            if isinstance(row_dict['file_list'], str):
                file_list = [row_dict['file_list']] if row_dict['file_list'].strip() else []
            else:
                file_list = []
        
        # Split file_list into image_list and catalog_list
        image_list = []
        catalog_list = []
        for file_path in file_list:
            if isinstance(file_path, str) and file_path.endswith('_cat.fits'):
                catalog_list.append(file_path)
            else:
                image_list.append(file_path)
        
        row_dict['file_list'] = file_list
        row_dict['image_list'] = image_list
        row_dict['catalog_list'] = catalog_list
    elif 'file_list' in row_dict and not row_dict['file_list']:
        row_dict['file_list'] = []
        row_dict['image_list'] = []
        row_dict['catalog_list'] = []
    else:
        # If file_list doesn't exist in row, set empty lists
        row_dict['file_list'] = []
        row_dict['image_list'] = []
        row_dict['catalog_list'] = []
    
    # Convert datetime fields from ISO strings to datetime objects
    datetime_fields = ['trigger_time', 'observation_time', 'transfer_time', 'processed_time']
    for field in datetime_fields:
        if field in row_dict and row_dict[field]:
            parsed_dt = parse_datetime_from_string(row_dict[field])
            if parsed_dt:
                row_dict[field] = parsed_dt
    
    return row_dict

def _prepare_data_for_db(data: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare data dictionary for database insertion/update"""
    clean_data = {}
    for key, value in data.items():
        if key in ['id', 'created_at', 'updated_at']:
            continue
        if isinstance(value, list):
            clean_data[key] = value[0] if len(value) > 0 else None
        else:
            clean_data[key] = value
    
    # Normalize coordinates: keep ra/dec in HH:MM:SS format, add ra_deg/dec_deg in degrees
    if 'ra' in clean_data and clean_data['ra']:
        clean_data['ra'] = normalize_coordinate_to_hms(clean_data['ra'], is_ra=True)
        ra_deg_str = normalize_coordinate_to_deg(clean_data['ra'], is_ra=True)
        try:
            clean_data['ra_deg'] = float(ra_deg_str) if ra_deg_str else None
        except (ValueError, TypeError):
            clean_data['ra_deg'] = None
    if 'dec' in clean_data and clean_data['dec']:
        clean_data['dec'] = normalize_coordinate_to_hms(clean_data['dec'], is_ra=False)
        dec_deg_str = normalize_coordinate_to_deg(clean_data['dec'], is_ra=False)
        try:
            clean_data['dec_deg'] = float(dec_deg_str) if dec_deg_str else None
        except (ValueError, TypeError):
            clean_data['dec_deg'] = None
    
    # Convert boolean to integer for v1, v2, is_inputted, is_observed
    bool_fields = ['v1', 'v2', 'is_inputted', 'is_observed']
    for field in bool_fields:
        if field in clean_data:
            clean_data[field] = _convert_bool_to_int(clean_data[field])
    
    # Convert v2_progress to float
    if 'v2_progress' in clean_data and clean_data['v2_progress'] is not None:
        try:
            clean_data['v2_progress'] = float(clean_data['v2_progress'])
        except (ValueError, TypeError):
            clean_data['v2_progress'] = None
    
    # Convert file_list to JSON string if it's a list
    if 'file_list' in clean_data and clean_data['file_list'] is not None:
        if isinstance(clean_data['file_list'], list):
            clean_data['file_list'] = json.dumps(clean_data['file_list'])
        elif not isinstance(clean_data['file_list'], str):
            clean_data['file_list'] = json.dumps([clean_data['file_list']])
    
    # Convert datetime fields to ISO format strings
    datetime_fields = ['trigger_time', 'observation_time', 'transfer_time', 'processed_time']
    for field in datetime_fields:
        if field in clean_data:
            clean_data[field] = normalize_datetime_field(clean_data[field])
    
    # Normalize 'key' to 'alert_key' for consistency
    if 'key' in clean_data and 'alert_key' not in clean_data:
        clean_data['alert_key'] = clean_data['key']
        del clean_data['key']
    
    return clean_data

def insert_or_update_row(data: Dict[str, Any], update_mode: str = "new") -> bool:
    """
    Insert a new row or update an existing one.
    
    Args:
        data: Dictionary with column names as keys
        update_mode: "new" to insert (or update if exists), "update" to update existing
    
    Returns:
        True if successful, False otherwise
    """
    conn = read_db_connection()
    cursor = conn.cursor()
    
    # Ensure all columns exist
    for key in data.keys():
        if key not in ['id', 'created_at', 'updated_at']:
            ensure_column_exists(key)
    
    # Prepare data for database
    clean_data = _prepare_data_for_db(data)
    
    # Check if row exists (by alert_key + trigger_time or objname)
    existing_row = None
    alert_key = clean_data.get('alert_key')
    if alert_key and clean_data.get('trigger_time'):
        cursor.execute(
            'SELECT id FROM too_requests WHERE alert_key = ? AND trigger_time = ?',
            (alert_key, clean_data['trigger_time'])
        )
        existing_row = cursor.fetchone()
    elif clean_data.get('objname') and update_mode == "update":
        cursor.execute(
            'SELECT id FROM too_requests WHERE objname = ? ORDER BY created_at DESC LIMIT 1',
            (clean_data['objname'],)
        )
        existing_row = cursor.fetchone()
    
    if existing_row:
        # Update existing row
        row_id = existing_row[0]
        
        # For update mode, only update the fields provided in clean_data
        # For new mode, update all fields in clean_data
        set_clause = ', '.join([f'{key} = ?' for key in clean_data.keys()])
        set_clause += ', updated_at = CURRENT_TIMESTAMP'
        values = list(clean_data.values()) + [row_id]
        
        # Retry on database lock
        def update_operation():
            cursor.execute(
                f'UPDATE too_requests SET {set_clause} WHERE id = ?',
                values
            )
            conn.commit()
            return True
        
        return _retry_db_operation(update_operation) or False
    else:
        # Insert new row
        if update_mode == "update":
            # If update mode but row doesn't exist, don't insert
            return False
        
        # Create GCN template for new alerts if not already set
        if not clean_data.get('gcn_template') and clean_data.get('trigger_time'):
            # Try to determine alert folder path from trigger_time
            try:
                trigger_time_str = clean_data['trigger_time']
                if isinstance(trigger_time_str, str):
                    trigger_dt = datetime.fromisoformat(trigger_time_str.replace('Z', '').replace('+00:00', ''))
                else:
                    trigger_dt = trigger_time_str
                
                # Format as YYYYMMDD_HHMMSS
                folder_name = trigger_dt.strftime("%Y%m%d_%H%M%S")
                
                # Try to find alert folder in common locations
                data_folder = os.getenv('DATA_FOLDER', './data')
                alert_base_paths = [
                    Path(data_folder) / "7dt" / "sync" / "alert" / folder_name,
                    Path("/home/7dt/7dt_too/backend/data/7dt/sync/alert") / folder_name,
                ]
                
                for alert_folder_path in alert_base_paths:
                    if alert_folder_path.exists():
                        # Create GCN template
                        gcn_template_path = create_gcn_template(str(alert_folder_path.resolve()), clean_data)
                        if gcn_template_path:
                            clean_data['gcn_template'] = gcn_template_path
                        break
            except Exception as e:
                # If we can't determine the path, that's okay - template can be created later
                pass
        
        columns = ', '.join(clean_data.keys())
        placeholders = ', '.join(['?' for _ in clean_data.values()])
        values = list(clean_data.values())
        
        # Retry on database lock
        def insert_operation():
            cursor.execute(
                f'INSERT INTO too_requests ({columns}) VALUES ({placeholders})',
                values
            )
            conn.commit()
            cursor.close()
            return True
        
        return _retry_db_operation(insert_operation) or False

def read_all_rows() -> List[Dict[str, Any]]:
    """Get all rows from the database with proper type conversion"""
    conn = read_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM too_requests ORDER BY created_at DESC')
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        result.append(_convert_row_to_dict(row))
    
    return result

def read_row_by_key_and_trigger(alert_key: str, trigger_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get a row by alert_key and optionally trigger_time.
    
    If trigger_time is provided, returns the exact match.
    If trigger_time is None, returns the most recent row with the given alert_key.
    """
    conn = read_db_connection()
    cursor = conn.cursor()
    
    if trigger_time:
        cursor.execute(
            'SELECT * FROM too_requests WHERE alert_key = ? AND trigger_time = ?',
            (alert_key, trigger_time)
        )
    else:
        cursor.execute(
            'SELECT * FROM too_requests WHERE alert_key = ? ORDER BY created_at DESC LIMIT 1',
            (alert_key,)
        )
    
    row = cursor.fetchone()
    
    if row:
        return _convert_row_to_dict(row)
    return None

def read_row_id(tile: Optional[str] = None, objname: Optional[str] = None, trigger_time: Optional[str] = None) -> Optional[int]:
    """
    Get a row ID from the database using tile name, object name, or trigger_time.
    Priority: trigger_time + (tile or objname) > tile > objname > trigger_time
    
    For trigger_time searches, returns the nearest past row (most recent row with 
    trigger_time <= provided trigger_time).
    
    Args:
        tile: Tile name (e.g., "T13201")
        objname: Object name (e.g., "AT2024hfx")
        trigger_time: Trigger time (ISO format string) - will find nearest past match
    
    Returns:
        Row ID (int) if found, None otherwise
    """
    conn = read_db_connection()
    cursor = conn.cursor()
    
    # Try most specific match first: trigger_time + (tile or objname)
    # For trigger_time, find nearest past row (trigger_time <= provided time)
    if trigger_time:
        if tile:
            # Find nearest past row with matching tile
            cursor.execute(
                '''SELECT id FROM too_requests 
                   WHERE tile = ? AND trigger_time <= ? 
                   ORDER BY trigger_time DESC, created_at DESC 
                   LIMIT 1''',
                (tile, trigger_time)
            )
            result = cursor.fetchone()
            if result:
                return result[0]
        
        if objname:
            # Find nearest past row with matching objname
            cursor.execute(
                '''SELECT id FROM too_requests 
                   WHERE objname = ? AND trigger_time <= ? 
                   ORDER BY trigger_time DESC, created_at DESC 
                   LIMIT 1''',
                (objname, trigger_time)
            )
            result = cursor.fetchone()
            if result:
                return result[0]
    
    # Try tile alone
    if tile:
        cursor.execute(
            'SELECT id FROM too_requests WHERE tile = ? ORDER BY created_at DESC LIMIT 1',
            (tile,)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
    
    # Try objname alone
    if objname:
        cursor.execute(
            'SELECT id FROM too_requests WHERE objname = ? ORDER BY created_at DESC LIMIT 1',
            (objname,)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
    
    # Try trigger_time alone - find nearest past row
    if trigger_time:
        cursor.execute(
            '''SELECT id FROM too_requests 
               WHERE trigger_time <= ? 
               ORDER BY trigger_time DESC, created_at DESC 
               LIMIT 1''',
            (trigger_time,)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
    
    return None

def read_row_by_id(row_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a row by its ID.
    
    Args:
        row_id: The row ID
    
    Returns:
        Dictionary with row data, or None if not found
    """
    conn = read_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM too_requests WHERE id = ?', (row_id,))
    row = cursor.fetchone()
    
    if row:
        return _convert_row_to_dict(row)
    return None

def update_row_by_id(row_id: int, data: Dict[str, Any]) -> bool:
    """
    Update a row by its ID.
    
    Args:
        row_id: The row ID to update
        data: Dictionary with fields to update
    
    Returns:
        True if successful, False otherwise
    """
    conn = read_db_connection()
    cursor = conn.cursor()
    
    # Ensure all columns exist
    for key in data.keys():
        if key not in ['id', 'created_at', 'updated_at']:
            ensure_column_exists(key)
    
    # Prepare data for database
    clean_data = _prepare_data_for_db(data)
    
    # Additional type conversions specific to update_row_by_id
    if 'exptime' in clean_data and clean_data['exptime'] is not None:
        try:
            clean_data['exptime'] = float(clean_data['exptime'])
        except (ValueError, TypeError):
            clean_data['exptime'] = None
    
    # Convert n_image, gain, binning to integer
    for field in ['n_image', 'gain', 'binning']:
        if field in clean_data and clean_data[field] is not None:
            try:
                clean_data[field] = int(float(clean_data[field]))  # Convert via float to handle string numbers
            except (ValueError, TypeError):
                clean_data[field] = None
    
    if not clean_data:
        return False
    
    # Update the row with retry on lock
    set_clause = ', '.join([f'{key} = ?' for key in clean_data.keys()])
    set_clause += ', updated_at = CURRENT_TIMESTAMP'
    values = list(clean_data.values()) + [row_id]
    
    try:
        def update_operation():
            cursor.execute(
                f'UPDATE too_requests SET {set_clause} WHERE id = ?',
                values
            )
            conn.commit()
            return cursor.rowcount > 0
        
        return _retry_db_operation(update_operation) or False
    except Exception as e:
        print(f"Error updating row {row_id}: {e}")
        return False

def create_alert_row(
    alert_key: str,
    requester: str,
    objname: str,
    tile: Optional[str],
    ra: str,
    dec: str,
    exptime: str,
    n_image: str,
    gain: str,
    binning: str,
    comments: Optional[str],
    trigger_time: str
) -> bool:
    """
    Create a new alert row in the database with basic information.
    
    Args:
        alert_key: Unique alert key
        requester: Email of the requester
        objname: Object name
        tile: Tile name (can be None)
        ra: Right ascension (as string)
        dec: Declination (as string)
        exptime: Exposure time
        n_image: Number of images
        gain: Gain value
        binning: Binning value
        comments: Comments (can be None)
        trigger_time: Trigger time (ISO format string)
    
    Returns:
        True if successful, False otherwise
    """
    data = {
        'alert_key': alert_key,
        'requester': requester,
        'objname': objname,
        'tile': tile,
        'ra': ra,
        'dec': dec,
        'exptime': exptime,
        'n_image': n_image,
        'gain': gain,
        'binning': binning,
        'comments': comments,
        'trigger_time': trigger_time
    }
    return insert_or_update_row(data, update_mode="new")

def create_gcn_template(alert_folder_path: str, alert_data: Dict[str, Any]) -> Optional[str]:
    """
    Create a GCN template file for an alert.
    
    Args:
        alert_folder_path: Path to the alert folder
        alert_data: Dictionary containing alert data (objname, ra, dec, etc.)
    
    Returns:
        Path to the created GCN template file, or None if creation failed
    """
    from pathlib import Path
    from datetime import datetime
    
    alert_dir = Path(alert_folder_path)
    template_path = alert_dir / "gcn_template.txt"
    
    # Extract data for template
    objname = alert_data.get('objname', '[Event Name/ID]')
    ra_deg = alert_data.get('ra_deg')
    dec_deg = alert_data.get('dec_deg')
    trigger_time = alert_data.get('trigger_time')
    requester = alert_data.get('requester', '')
    
    # Format coordinates - handle both float and string types
    try:
        if ra_deg is not None:
            ra_deg_val = float(ra_deg) if isinstance(ra_deg, str) else ra_deg
            ra_str = f"{ra_deg_val:.6f}"
        else:
            ra_str = "[RA]"
    except (ValueError, TypeError):
        ra_str = "[RA]"
    
    try:
        if dec_deg is not None:
            dec_deg_val = float(dec_deg) if isinstance(dec_deg, str) else dec_deg
            dec_str = f"{dec_deg_val:.6f}"
        else:
            dec_str = "[DEC]"
    except (ValueError, TypeError):
        dec_str = "[DEC]"
    
    # Parse trigger time
    start_time_str = "[Start Time UTC]"
    date_str = "[Date]"
    if trigger_time:
        try:
            if isinstance(trigger_time, str):
                trigger_dt = datetime.fromisoformat(trigger_time.replace('Z', '').replace('+00:00', ''))
            else:
                trigger_dt = trigger_time
            start_time_str = trigger_dt.strftime("%H:%M:%S UTC")
            date_str = trigger_dt.strftime("%Y-%m-%d")
        except:
            pass

    # Read master template from ref/ (portable path relative to this package)
    
    try:
        with open(ref_template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
    except OSError as e:
        print(f"Error reading GCN template: {e}")
        return None

    template_content = template_content.replace("[Event Name/ID]", objname)
    template_content = template_content.replace("[Start Time UTC]", start_time_str)
    template_content = template_content.replace("[Date]", date_str)
    template_content = template_content.replace("[RA]", ra_str)
    template_content = template_content.replace("[DEC]", dec_str)

    
    try:
        # Ensure directory exists
        alert_dir.mkdir(parents=True, exist_ok=True)
        
        # Write template file
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(template_content)
        
        # Set file permissions
        try:
            os.chmod(template_path, 0o666)
        except OSError:
            pass
        
        # Return absolute path
        return str(template_path.resolve())
    except Exception as e:
        print(f"Error creating GCN template: {e}")
        return None

def create_alert_from_folder(alert_folder_path: str) -> bool:
    """
    Create an alert row from an alert folder.
    This is a convenience function that reads the alert files and creates a database row.
    
    Args:
        alert_folder_path: Path to the alert folder (e.g., /path/to/alert/20250209_023600/)
    
    Returns:
        True if successful, False otherwise
    """
    import json
    from pathlib import Path
    from datetime import datetime, timezone, timedelta
    
    # Try to import astropy, but make it optional
    try:
        from astropy.io import ascii
        ASTROPY_AVAILABLE = True
    except ImportError:
        ASTROPY_AVAILABLE = False
    
    # Add supy path for parse_coordinates
    import sys
    supy_path = "/home/7dt/script/supy"
    if supy_path not in sys.path:
        sys.path.insert(0, supy_path)
    try:
        from supy.tiles import parse_coordinates
        PARSE_COORDS_AVAILABLE = True
    except ImportError:
        PARSE_COORDS_AVAILABLE = False
    
    alert_dir = Path(alert_folder_path)
    
    # Extract trigger time from folder name, else from alert_status.json (both clocks are UTC)
    folder_name = alert_dir.name
    trigger_time = extract_trigger_time_from_folder(folder_name)
    if not trigger_time:
        try:
            with open(alert_dir / "alert_status.json") as f:
                status_trigger = json.load(f).get("trigger_time")
            trigger_dt = datetime.fromisoformat(status_trigger).replace(tzinfo=timezone.utc)
            trigger_time = trigger_dt.astimezone(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
        except Exception as e:
            print(f"Cannot determine trigger time for alert folder {folder_name}: {e}")
            return False
    
    # Read alert_rawdata.json
    rawdata_file = alert_dir / "alert_rawdata.json"
    if not rawdata_file.exists():
        return False
    
    try:
        with open(rawdata_file) as f:
            rawdata = json.load(f)
    except Exception:
        return False
    
    # Read alert_status.json for alert_key
    status_file = alert_dir / "alert_status.json"
    alert_key = None
    if status_file.exists():
        try:
            with open(status_file) as f:
                status = json.load(f)
                alert_key = status.get('key')
        except Exception:
            pass
    
    if not alert_key:
        alert_key = folder_name

    if read_row_by_key_and_trigger(alert_key, trigger_time):
        return False

    # Extract fields
    requester = rawdata.get('requester', '')
    objname = rawdata.get('objname', '')
    ra_str = rawdata.get('RA', '')
    dec_str = rawdata.get('De', '')
    if isinstance(ra_str, list) or isinstance(dec_str, list):
        print(f"Alert folder {folder_name} holds a multi-target list ({len(ra_str)} targets); the ToO table has one target per row, skipping")
        return False
    exptime = str(rawdata.get('exptime', ''))
    n_image = str(rawdata.get('count', ''))
    gain = str(rawdata.get('gain', ''))
    binning = str(rawdata.get('binning', ''))
    comments = rawdata.get('comments', '')
    
    # Parse and normalize coordinates: keep in HH:MM:SS format, also calculate degrees
    if PARSE_COORDS_AVAILABLE:
        try:
            ra_deg_val, dec_deg_val = parse_coordinates([ra_str, dec_str])
            # parse_coordinates returns decimal degrees
            ra_deg = f"{ra_deg_val:.6f}"
            dec_deg = f"{dec_deg_val:.6f}"
            # Convert to HH:MM:SS format
            ra = normalize_coordinate_to_hms(ra_deg, is_ra=True)
            dec = normalize_coordinate_to_hms(dec_deg, is_ra=False)
        except Exception:
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
        except Exception:
            pass
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
        except Exception:
            pass
    
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
    
    # Create the row with both formats
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
    }
    
    # Create GCN template if it doesn't exist
    template_path = alert_dir / "gcn_template.txt"
    if not template_path.exists():
        gcn_template_path = create_gcn_template(str(alert_dir), data)
        if gcn_template_path:
            data['gcn_template'] = gcn_template_path
    else:
        # Template already exists, just save the absolute path
        data['gcn_template'] = str(template_path.resolve())
    
    return insert_or_update_row(data, update_mode="new")

def delete_row(row_id: int) -> bool:
    """Delete a row by ID"""
    conn = read_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM too_requests WHERE id = ?', (row_id,))
    conn.commit()
    return cursor.rowcount > 0

def update_from_alert_status(alert_folder_path: str) -> bool:
    """
    Update database row based on alert_status.json file.
    
    Args:
        alert_folder_path: Path to the alert folder (e.g., /path/to/alert/20250209_023600/)
    
    Returns:
        True if successful, False otherwise
    """
    alert_dir = Path(alert_folder_path)
    status_file = alert_dir / "alert_status.json"
    
    if not status_file.exists():
        return False
    
    try:
        with open(status_file) as f:
            status = json.load(f)
    except Exception as e:
        print(f"Error reading {status_file}: {e}")
        return False
    
    # Extract alert_key from status file
    alert_key = status.get('key')
    if not alert_key:
        return False
    
    # Extract trigger_time from folder name
    folder_name = alert_dir.name
    trigger_time = extract_trigger_time_from_folder(folder_name)
    if not trigger_time:
        return False
    
    # Find the row by alert_key and trigger_time
    row = read_row_by_key_and_trigger(alert_key, trigger_time)
    if not row:
        return False
    
    # Prepare update data
    update_data = {}
    if 'is_inputted' in status:
        update_data['is_inputted'] = status['is_inputted']
    if 'is_observed' in status:
        update_data['is_observed'] = status['is_observed']
    
    if not update_data:
        return False
    
    # Update the row
    return update_row_by_id(row['id'], update_data)

def update_all_from_alert_status(alert_base_dir: str) -> Dict[str, int]:
    """
    Update all database rows based on alert_status.json files in a directory.
    
    Args:
        alert_base_dir: Base directory containing alert folders (e.g., /path/to/alert/)
    
    Returns:
        Dictionary with counts: {'success': int, 'failed': int, 'not_found': int}
    """
    alert_base = Path(alert_base_dir)
    if not alert_base.exists():
        return {'success': 0, 'failed': 0, 'not_found': 0}
    
    results = {'success': 0, 'failed': 0, 'not_found': 0}
    
    # Find all alert folders (those with YYYYMMDD_HHMMSS format)
    for item in alert_base.iterdir():
        if item.is_dir():
            folder_name = item.name
            # Check if it matches YYYYMMDD_HHMMSS format
            if len(folder_name) >= 15 and folder_name[8] == '_' and folder_name[:8].isdigit() and folder_name[9:15].isdigit():
                status_file = item / "alert_status.json"
                if status_file.exists():
                    if update_from_alert_status(str(item)):
                        results['success'] += 1
                    else:
                        # Check if row exists
                        try:
                            with open(status_file) as f:
                                status = json.load(f)
                            alert_key = status.get('key')
                            if alert_key:
                                # Extract trigger_time
                                trigger_time = extract_trigger_time_from_folder(folder_name)
                                if trigger_time and read_row_by_key_and_trigger(alert_key, trigger_time):
                                    results['not_found'] += 1
                                else:
                                    results['failed'] += 1
                            else:
                                results['failed'] += 1
                        except:
                            results['failed'] += 1
                else:
                    results['not_found'] += 1
    
    return results

def fix_db_permissions():
    """
    Fix permissions on the existing database file to allow all users to modify it.
    This function should be run with appropriate privileges (e.g., sudo).
    """
    try:
        # Set file permissions to allow all users to read and write
        os.chmod(TOO_DB_PATH, 0o666)
        
        # Also fix directory permissions to allow all users to access
        db_dir = os.path.dirname(TOO_DB_PATH)
        os.chmod(db_dir, 0o777)
        
        print(f"✓ Database permissions fixed successfully")
        print(f"  File: {TOO_DB_PATH}")
        print(f"  Permissions: 666 (rw-rw-rw-) - all users can read and write")
        return True
            
    except (OSError, PermissionError) as e:
        print(f"Error fixing permissions: {e}")
        print(f"\nTo fix manually, run as root/sudo:")
        print(f"  sudo chmod 666 {TOO_DB_PATH}")
        print(f"  sudo chmod 777 {os.path.dirname(TOO_DB_PATH)}")
        return False

def migrate_notice_null_to_zero():
    """
    Migrate all NULL values in notice columns (init_notice, interim_notice, final_notice, completed) to 0.
    """
    conn = read_db_connection()
    cursor = conn.cursor()
    
    notice_columns = ['init_notice', 'interim_notice', 'final_notice', 'completed']
    total_updated = 0
    
    for column in notice_columns:
        # Check if column exists
        cursor.execute("PRAGMA table_info(too_requests)")
        columns_info = cursor.fetchall()
        column_exists = any(col[1] == column for col in columns_info)
        
        if not column_exists:
            print(f"Column {column} does not exist, skipping...")
            continue
        
        # Update NULL values to 0
        cursor.execute(f'UPDATE too_requests SET {column} = 0 WHERE {column} IS NULL')
        updated = cursor.rowcount
        total_updated += updated
        print(f"Updated {updated} rows for {column}")
    
    conn.commit()
    print(f"\nTotal rows updated: {total_updated}")
    return total_updated

# Initialize database on import
# Note: Database file permissions are set to allow all users to read and write (0o666)
init_db()

