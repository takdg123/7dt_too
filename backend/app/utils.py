"""
Utility functions for coordinate conversion and other helper functions.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Any


def normalize_coordinate_to_hms(coord_str: str, is_ra: bool = True) -> str:
    """
    Normalize coordinate string to HH:MM:SS.S format (for RA) or DD:MM:SS.S format (for DEC).
    
    Args:
        coord_str: Coordinate string in various formats (HH:MM:SS.S, DD:MM:SS.S, or decimal)
        is_ra: True if RA (hours), False if DEC (degrees)
    
    Returns:
        Coordinate in HH:MM:SS.S or DD:MM:SS.S format
    """
    if not coord_str or coord_str.strip() == '':
        return coord_str
    
    coord_str = str(coord_str).strip()
    
    # If already in HH:MM:SS or DD:MM:SS format, return as is
    pattern = r'^([+-]?)(\d+):(\d+):([\d.]+)$'
    if re.match(pattern, coord_str):
        return coord_str
    
    # Try to parse as decimal
    try:
        float_val = float(coord_str)
        
        if is_ra:
            # RA: convert decimal degrees to hours:minutes:seconds
            # Always treat decimal input as degrees (standard astronomical format)
            # Convert degrees to hours (1 hour = 15 degrees)
            hours = float_val / 15.0
            
            h = int(hours)
            minutes = (hours - h) * 60.0
            m = int(minutes)
            seconds = (minutes - m) * 60.0
            
            return f"{h:02d}:{m:02d}:{seconds:05.2f}"
        else:
            # DEC: convert decimal degrees to degrees:minutes:seconds
            sign = '-' if float_val < 0 else ''
            abs_val = abs(float_val)
            
            degrees = int(abs_val)
            minutes = (abs_val - degrees) * 60.0
            m = int(minutes)
            seconds = (minutes - m) * 60.0
            
            return f"{sign}{degrees:02d}:{m:02d}:{seconds:04.1f}"
    except ValueError:
        pass
    
    # If parsing fails, return original string
    return coord_str


def normalize_coordinate_to_deg(coord_str: str, is_ra: bool = True) -> str:
    """
    Normalize coordinate string to decimal degrees format.
    
    Args:
        coord_str: Coordinate string in various formats (HH:MM:SS.S, DD:MM:SS.S, or decimal)
        is_ra: True if RA (hours), False if DEC (degrees)
    
    Returns:
        Coordinate as decimal degrees string (e.g., "123.456789")
    """
    if not coord_str or coord_str.strip() == '':
        return coord_str
    
    coord_str = str(coord_str).strip()
    
    # Check if already in decimal format
    try:
        float_val = float(coord_str)
        # If it's RA in decimal hours, convert to degrees
        if is_ra and float_val < 24:
            float_val = float_val * 15.0  # Convert hours to degrees
        return f"{float_val:.6f}"
    except ValueError:
        pass
    
    # Try to parse as HH:MM:SS.S or DD:MM:SS.S format
    pattern = r'^([+-]?)(\d+):(\d+):([\d.]+)$'
    match = re.match(pattern, coord_str)
    
    if match:
        sign = match.group(1)
        hours_or_deg = float(match.group(2))
        minutes = float(match.group(3))
        seconds = float(match.group(4))
        
        # Calculate decimal degrees
        if is_ra:
            # RA: convert hours:minutes:seconds to decimal degrees
            decimal_hours = hours_or_deg + minutes/60.0 + seconds/3600.0
            decimal_degrees = decimal_hours * 15.0  # Convert hours to degrees
        else:
            # DEC: convert degrees:minutes:seconds to decimal degrees
            decimal_degrees = hours_or_deg + minutes/60.0 + seconds/3600.0
            if sign == '-':
                decimal_degrees = -decimal_degrees
        
        return f"{decimal_degrees:.6f}"
    
    # If parsing fails, return original string
    return coord_str


def normalize_datetime_field(value: Any) -> Optional[str]:
    """Convert datetime field to ISO format string"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    elif not isinstance(value, str):
        return str(value)
    return value


def parse_datetime_from_string(dt_str: str) -> Optional[datetime]:
    """Parse datetime from ISO format string"""
    if not dt_str:
        return None
    try:
        # Handle timezone-aware and timezone-naive formats
        dt_str = dt_str.replace('Z', '').replace('+00:00', '')
        if '+' in dt_str:
            dt_str = dt_str.split('+')[0]
        if '-' in dt_str and dt_str.count('-') > 2:
            # Has timezone offset
            parts = dt_str.rsplit('-', 1)
            if len(parts) == 2 and ':' in parts[1]:
                dt_str = parts[0]
        # Replace space with T for ISO format
        dt_str = dt_str.replace(' ', 'T')
        return datetime.fromisoformat(dt_str)
    except (ValueError, AttributeError):
        return None


def extract_trigger_time_from_folder(folder_name: str) -> Optional[str]:
    """
    Extract trigger time from folder name (YYYYMMDD_HHMMSS format).
    Folder name is in UTC, converts to KST (UTC+9) for storage.
    """
    try:
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
    except (ValueError, IndexError):
        pass
    return None
