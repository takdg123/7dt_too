from flask import g, Blueprint, send_from_directory, request, jsonify, current_app, json, Response, send_file, make_response, session
from flask_mail import Message
from . import mail  # Import the mail instance from __init__.py
import pandas as pd
import os
import json
from datetime import datetime
from astropy.table import Table
from astropy.utils import iers
import numpy as np
import base64
import secrets
from functools import wraps
from supy.observer import *
from supy.tiles import *
from .add_page import WikiManager
from .too_db import read_all_rows, read_row_by_key_and_trigger, insert_or_update_row, init_db, update_row_by_id
from .utils import normalize_coordinate_to_hms, normalize_coordinate_to_deg
import sys

from dotenv import load_dotenv
load_dotenv()

# Add pipeline path to import database services
pipeline_path = "/home/7dt/pipeline"
if pipeline_path not in sys.path:
    sys.path.insert(0, pipeline_path)

try:
    from pipeline.services.database import DatabaseHandler
    db_handler = DatabaseHandler()
    DB_AVAILABLE = True
except ImportError:
    print("Warning: Database connection not available")
    db_handler = None
    DB_AVAILABLE = False

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()  # or any other format you prefer
        return super().default(obj)


iers.conf.auto_download = False  # a cold worker spent 40 s fetching IERS tables per request and hit harakiri

api_bp = Blueprint('too', __name__)

api_bp.json_encoder = DateTimeEncoder

# Initialize database on module load
init_db()

DATA_FOLDER = os.getenv('DATA_FOLDER', './data')

ALLOWED_FILE_ROOTS = tuple(os.path.realpath(p) for p in (
    os.path.join(os.getenv('SDT_DATA_FOLDER', ''), 'alert'),
    '/lyman/data2/processed',
    '/balmer/data1/too',
    '/lyman/data2/too',
))

def allowed_file_path(path):
    """Return the resolved path only if it lies under a root the UI may read or write."""
    real = os.path.realpath(path)
    if any(real == root or real.startswith(root + os.sep) for root in ALLOWED_FILE_ROOTS):
        return real
    return None
REFDATA_DIR = "/home/"



def generate_nonce():
    g.nonce = base64.b64encode(os.urandom(16)).decode("ascii")

def generate_csrf_token():
    """Generate a CSRF token and store it in session"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

def validate_csrf_token():
    """Validate CSRF token from request header, form data, or JSON body
    Supports multiple token field names: csrf_token, CSRFToken, anticsrf, OWASP_CSRFTOKEN
    """
    token = None
    session_token = session.get('csrf_token')
    
    if not session_token:
        return False
    
    # Check X-CSRF-Token header (preferred for AJAX requests)
    token = request.headers.get('X-CSRF-Token')
    
    # Check form data with multiple possible field names
    if not token:
        token = request.form.get('csrf_token') or \
                request.form.get('CSRFToken') or \
                request.form.get('anticsrf') or \
                request.form.get('OWASP_CSRFTOKEN')
    
    # Check JSON body
    if not token and request.is_json and request.json:
        token = request.json.get('csrf_token') or \
                request.json.get('CSRFToken') or \
                request.json.get('anticsrf') or \
                request.json.get('OWASP_CSRFTOKEN')
    
    if not token or token != session_token:
        return False
    return True

def csrf_protect(f):
    """Decorator to protect routes with CSRF validation"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if not validate_csrf_token():
                # Log for debugging (remove in production if needed)
                session_token = session.get('csrf_token')
                received_token = (
                    request.headers.get('X-CSRF-Token') or
                    request.form.get('csrf_token') or
                    request.form.get('CSRFToken') or
                    request.form.get('anticsrf') or
                    (request.json.get('csrf_token') if request.is_json and request.json else None) or
                    (request.json.get('CSRFToken') if request.is_json and request.json else None) or
                    (request.json.get('anticsrf') if request.is_json and request.json else None)
                )
                current_app.logger.warning(
                    f"CSRF validation failed: session_token={'exists' if session_token else 'missing'}, "
                    f"received_token={'exists' if received_token else 'missing'}, "
                    f"method={request.method}, path={request.path}"
                )
                return jsonify({
                    'error': 'CSRF token validation failed',
                    'message': 'Invalid or missing CSRF token. Please refresh the page and try again.'
                }), 403
        return f(*args, **kwargs)
    return decorated_function

@api_bp.before_request
def set_nonce():
    generate_nonce()
    # Generate CSRF token for all requests (will be used when needed)
    generate_csrf_token()

@api_bp.route('/')
def serve():
    nonce = getattr(g, "nonce", None)
    csrf_token = generate_csrf_token()

    index_path = os.path.join(current_app.static_folder, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace CSP nonce placeholder
    # <meta name="csp-nonce" content="__CSP_NONCE__" />
    if nonce:
        html = html.replace("__CSP_NONCE__", nonce)
    
    # Add CSRF token to meta tag if placeholder exists
    # <meta name="csrf-token" content="__CSRF_TOKEN__" />
    if "__CSRF_TOKEN__" in html:
        html = html.replace("__CSRF_TOKEN__", csrf_token)

    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

@api_bp.route('/api/csrf-token', methods=['GET'])
def get_csrf_token():
    """Endpoint to get CSRF token for frontend"""
    token = generate_csrf_token()
    return jsonify({'csrf_token': token}), 200

@api_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(current_app.static_folder, "static"), filename)

@api_bp.after_request
def add_header(response):
    nonce = getattr(g, "nonce", None)

    response.set_cookie(
        "key",
        "value",
        secure=True,
        httponly=True,
        samesite="Lax",
        max_age=3600
    )

    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # XSS Protection - helps prevent XSS attacks that could steal CSRF tokens
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # CSP with XSS protection - strict CSP helps prevent XSS that could bypass CSRF protection
    response.headers['Content-Security-Policy'] = ( 
        f"default-src 'self'; " 
        f"script-src 'self'; " 
        f"style-src 'self' 'unsafe-inline'; " 
        f"style-src-attr 'self'; " 
        f"img-src 'self' data: blob:; " 
        f"connect-src 'self'; " 
        f"font-src 'self' data:; " 
        f"object-src 'none'; " 
        f"base-uri 'self'; " 
        f"frame-ancestors 'none'; " 
    )
    #'nonce-{nonce}'
    return response
    
    

@api_bp.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint that verifies database connectivity"""
    try:
        rows = read_all_rows()
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "total_requests": len(rows)
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "error",
            "error": str(e)
        }), 500

@api_bp.route('/api/targets', methods=['GET'])
def get_targets():

    file_path = os.path.join(DATA_FOLDER, 'targets.ascii')
    try:
        data_table = Table.read(file_path, format='ascii')
        selected_columns = ['Name', 'RA', 'DEC']
        filtered_df = data_table[selected_columns]
        filtered_df.rename_columns(['Name', 'RA', 'DEC'], ['name', 'ra', 'dec'])
        return jsonify(filtered_df.to_pandas().to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/filtinfo', methods=['GET'])
def get_filtinfo():
    file_path = os.path.join(os.getenv("SDT_CONFIG_FOLDER"), "filtinfo.dict")
    try:
        # Read the JSON-like structure from the file
        with open(file_path, 'r') as f:
            filtinfo = json.load(f)

        # Process the data to filter out empty slots
        processed_data = {}
        for telescope, filters in filtinfo.items():
            real_filters = [f for f in filters if not f.startswith("Slot")]
            processed_data[telescope] = real_filters

        # Convert to a list of dictionaries for API output
        result = [{"Telescope": k, "Filters": v} for k, v in processed_data.items()]

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/status', methods=['GET'])
def get_status():
    file_path = os.path.join(os.getenv("SDT_DATA_FOLDER"), "multitelescopes.dict")
    try:
        # Read JSON-like data
        with open(file_path, 'r') as f:
            multitelescopes = json.load(f)

        # Prepare the data for the table
        table_data = []
        latest_report = {"reported_by": None, "timestamp": None}

        for telescope, components in multitelescopes.items():
            row = {"Telescope": telescope}
            row["Status"] = components.pop("Status")
            row["Status_update_time"] = components.pop("Status_update_time")
            for name, component in components.items():
                row[name] = component["status"]
                row["Instrument_update_time"] = component["timestamp"]
                # Update latest reporter and timestamp if needed
                if not latest_report["timestamp"] or component["timestamp"] > latest_report["timestamp"]:
                    latest_report["reported_by"] = component["reported_by"]
                    latest_report["timestamp"] = component["timestamp"]
            table_data.append(row)

        # Combine table data and the latest report info
        response = {
            "table": table_data,
            "latest_report": latest_report
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/daily_schedule', methods=['GET'])
def get_daily_schedule():
    
    file_path = os.path.join(os.getenv("SDT_DATA_FOLDER"), "DB_Program.ascii")

    try:
        # Read the file (update the parameters based on your file format)
        data_table= pd.read_csv(file_path, delimiter=' ')
        data_table = data_table.replace({np.nan: None})
        return jsonify(data_table.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/spec-options', methods=['GET'])
def get_spec_options():
    specmode_folder = os.path.join(os.getenv("SDT_CONFIG_FOLDER"), "specmode")
    specmode_files = []

    for root, dirs, files in os.walk(specmode_folder):
        for file in files:
            if file.endswith('.specmode'):
                specmode_files.append(file)

    return jsonify(specmode_files)

@api_bp.route('/api/weather', methods=['GET'])
def get_weather_info():
    weather_file_path = os.path.join(os.getenv("SDT_DATA_FOLDER"), "weatherinfo.dict")

    try:
        with open(weather_file_path, 'r') as file:
            weather_data = json.load(file)
        return jsonify(weather_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/spec-file', methods=['GET'])
def get_spec_file():
    specmode_folder = os.path.join(os.getenv("SDT_CONFIG_FOLDER"), "specmode")
    file_name = request.args.get('file')

    if not file_name or not file_name.endswith('.specmode'):
        return jsonify({'error': 'Invalid file name'}), 400
    
    file_path = None
    for root, dirs, files in os.walk(specmode_folder):
        if file_name in files:
            file_path = os.path.join(root, file_name)
            break

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    with open(file_path, 'r') as f:
        data = json.load(f)  # Correctly use the loaded JSON data
        unique_list = list(set(item.replace('w', '') for sublist in data.values() for item in sublist))  # Remove 'w' from items
        wavelengths = sorted([float(item[1:]) for item in unique_list if 'm' in item])  # Extract wavelengths
        filters = [item for item in unique_list if 'm' not in item]  # Extract filters
        # Return processed data
        return jsonify({
            "wavelengths": wavelengths,
            "filters": filters
        })

@api_bp.route('/api/validate-password', methods=['POST'])
@csrf_protect
def validate_password():
    data = request.json
    password = data.get('password')
    valid_password = os.getenv("SDT_ACCESS_PASSWORD")

    if password == valid_password:
        return jsonify({'valid': True}), 200
    else:
        return jsonify({'valid': False}), 401
    
@api_bp.route('/api/send_email', methods=['POST'])
@csrf_protect
def send_email():
    try:
        data = request.json

        obsmode = data.get('obsmode')
        details1 = details2 = ""

        if obsmode == "Spec":
            details1 = f"- Specmode: {data.get('selectedSpecFile')}"
            details2 = ""
        elif obsmode == "Deep":
            selected_filters = ",".join(list(data.get('selectedFilters')))
            details1 = f"- Filters: {selected_filters}"
            details2 = f"- NumberofTelescopes: {data.get('selectedTelNumber')}"


        # Construct the email body
        data["singleExposure"] = data.get('exposure')
        data["exposure"] = float(data.get('singleExposure'))*float(data.get('imageCount'))
        # Modified by HHCHOI 251121
        data["is_Too"] = True
        data["is_rapidToo"] = data.get('abortObservation')
        data["cadence"] = 1
        data["Too_starttime"] = None
        data["Too_endtime"] = None
        target = data.get('target')

        email_body = f"""
        ================================
        New ToO Request Submitted
        ================================

        **Observation Information**
        ----------------------
        - Requester: {data.get('requester')}
        - Target Name: {data.get('target')}
        - Right Ascension (R.A.): {data.get('ra')}
        - Declination (Dec.): {data.get('dec')}
        - Total Exposure Time (seconds): {data.get('exposure')}
        - Single Exposure Time (seconds): {data.get('singleExposure')}
        - # of images: {data.get('imageCount')}
        - Obsmode: {data.get('obsmode')}
            {details1}
            {details2}

        **Detailed Settings**
        --------------------
        - Is_ToO: {data.get('is_Too')}
        - Is_rapidToO: {data.get('is_rapidToo')}
        - Cadence: {data.get('cadence')} 
        - Number of Observation: 1
        - ToO start time: {data.get('Too_starttime')}
        - ToO end time: {data.get('Too_endtime')}
        - Priority: {data.get('priority')} 
        - Gain: {data.get('gain')}
        - Radius (arcmin): {data.get('radius')}
        - Binning: {data.get('binning')}
        - Observation Start Time: {data.get('obsStartTime')}
        - Comments: {data.get('comments')}

        ================================
        Please take necessary actions.
        Link to the wiki (please update the page with relevant information)
        https://proton.snu.ac.kr/en/too/{target.replace(' ', '')}
        ================================
        """

        # Save the entered data as a JSON file
        now_str = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"too_request_{now_str}.json"
        file_path = os.path.join(os.getcwd(), file_name)

        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)
        # # Send email with the attachment
        msg = Message(
            subject="[Automated] 7DT ToO Observation Request",
            recipients=["7dt.observation.alert@gmail.com"],  # Recipient email
            body=email_body
        )
        with open(file_path, "rb") as file:
            msg.attach(file_name, "application/json", file.read())

        mail.send(msg)
        
        try:
            wiki_manager = WikiManager()
            result = wiki_manager.create_page(data)
            if result is None:
                print("Fail to create wiki page: API returned None")
        except Exception as e:
            print(f"Fail to create wiki page: {str(e)}")
            import traceback
            traceback.print_exc()
        
        try:
            msg = Message(
                subject="[Automated] Your TOO Request has been Submitted",
                recipients=[data.get('requester')],  # Recipient email
                body=email_body
            )
            mail.send(msg)
        except Exception as e:
            print(f"Failed to send confirmation email: {e}")
        
        # Clean up the temporary file
        os.remove(file_path)
        return jsonify({"message": "Your ToO request was sent successfully!"}), 200

    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500



@api_bp.route('/api/staralt_data', methods=['GET'])
def get_staralt_data():
    """
    Provides star altitude data as JSON. 
    Expected query params: ra, dec, (optional) objname, target_minalt, target_minmoonsep
    Example: /api/staralt_data?ra=20.5243&dec=-20.245&objname=ABC&target_minalt=30&target_minmoonsep=40
    """
    try:
        
        ra = request.args.get('ra')
        dec = request.args.get('dec')

        try: 
            ra = float(ra)
            dec = float(dec)
        except:
            pass
        
        objname = request.args.get('objname', None)
        target_minalt = float(request.args.get('target_minalt', 20))
        target_minmoonsep = float(request.args.get('target_minmoonsep', 30))
        
        # Create an observer instance. 
        # Make sure you have a valid mainObserver setup. For example:
        # observer = mainObserver()  # Adjust as necessary for your environment.
        observer = mainObserver()

        # Instantiate Staralt
        star = Staralt(observer=observer)

        # Generate star altitude data
        star.set_target(ra=ra, dec=dec, objname=objname, target_minalt=target_minalt, target_minmoonsep=target_minmoonsep)
        # Return the data dictionary as JSON
        return jsonify(star.data_dict)

    except Exception as e:
        
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/tile', methods=['GET'])
def get_tile():
    """
    Provides tile information as JSON. 
    Expected query params: ra and dec
    Example: /api/tile?ra=20.5243&dec=-20.245
    """
    try:
        try:
            ra = float(normalize_coordinate_to_deg(request.args.get('ra'), is_ra=True))
            dec = float(normalize_coordinate_to_deg(request.args.get('dec'), is_ra=False))
        except (TypeError, ValueError) as e:
            return jsonify({"error": f"Invalid coordinates: {e}", "tile_id": ""}), 400

        T = Tiles()
        T.find_overlapping_tiles(ra=ra, dec=dec, list_aperture = 0,
                         match_tolerance_minutes=4, fraction_overlap_lower= 0.1 )
                         
        if T.tile_table is None:
            return jsonify({"error": "No tile found", "tile_id": ""}), 404
        else:
            tile_id = T.tile_table["id"][0]
            return jsonify({"tile_id": tile_id})
    except Exception as e:
        print(e)
        return jsonify({"error": str(e), "tile_id": ""}), 500


@api_bp.route('/api/convert', methods=['GET'])
def convert():
    try:
        ra = request.args.get('ra')
        dec = request.args.get('dec')
        ra, dec = parse_coordinates((ra, dec))
        return jsonify({"ra": ra, "dec": dec})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/too_table', methods=['GET'])
def get_too_table():
    """
    Get all ToO requests from the database.
    
    Returns:
        JSON array of all ToO requests. All time fields (trigger_time, observation_time, 
        transfer_time, processed_time) are in KST (Korea Standard Time, UTC+9) ISO format.
    """
    rows = read_all_rows()
    # Convert to list of dicts, handling None values
    result = []
    for row in rows:
        row_dict = {}
        for key, value in row.items():
            # Skip internal SQLite columns
            if key in ['created_at', 'updated_at']:
                continue
            # Convert None to None (JSON null)
            if value is None:
                row_dict[key] = None
            else:
                row_dict[key] = value
        result.append(row_dict)
    return jsonify(result)

@api_bp.route('/api/too_table/<alert_key>', methods=['GET'])
def get_too_by_key(alert_key):
    """
    Get a specific ToO request by alert_key and optional trigger_time.
    
    Query parameters:
    - trigger_time: Optional trigger time to filter (ISO format, KST/UTC+9)
    
    Returns:
        JSON object with ToO request data. All time fields are in KST (Korea Standard Time, UTC+9) ISO format.
    """
    try:
        trigger_time = request.args.get('trigger_time')
        
        row = read_row_by_key_and_trigger(alert_key, trigger_time)
        if not row:
            return jsonify({"error": "ToO request not found"}), 404
        
        # Convert to dict, excluding internal columns
        row_dict = {}
        for key, value in row.items():
            if key in ['id', 'created_at', 'updated_at']:
                continue
            row_dict[key] = value
        
        return jsonify(row_dict)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/too_table', methods=['POST', 'PUT', 'PATCH'])
@csrf_protect
def update_too_table():
    """
    Update a ToO request in the database.
    
    Request body should contain the fields to update.
    - For POST: Creates a new row (if alert_key and trigger_time are unique)
    - For PUT/PATCH: Updates an existing row (requires alert_key and trigger_time in body)
    
    Note: All time fields (trigger_time, observation_time, transfer_time, processed_time) 
    should be provided in KST (Korea Standard Time, UTC+9) ISO format. Times will be 
    stored in KST in the database.
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Determine update mode
        if request.method == 'POST':
            update_mode = "new"
        else:
            update_mode = "update"
        
        # Insert or update the row
        success = insert_or_update_row(data, update_mode=update_mode)
        
        if success:
            return jsonify({"message": "ToO request updated successfully"}), 200
        else:
            return jsonify({"error": "Failed to update ToO request"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@api_bp.route('/api/gcn', methods=['GET'])
def get_gcn_circular():
    import requests
    circular_id = request.args.get('id')
    if not circular_id:
        return jsonify({"error": "Missing circular ID"}), 400
    
    url = f'https://gcn.nasa.gov/circulars/{circular_id}.json'
    response = requests.get(url)
    
    if response.status_code != 200:
        return jsonify({"error": "GCN circular not found"}), 404
    
    data = response.json()
    
    title = data.get("subject", "Unknown Title")
    circular_url = f'https://gcn.nasa.gov/circulars/{circular_id}'
    body = data.get("body", "No content available")
    
    formatted_text = f"""
**[GCN{circular_id}]({circular_url}): {title}**
<div class="gcn-report">
{body}
</div>
    """
    
    return Response(formatted_text, content_type="text/plain")

@api_bp.route('/api/text', methods=['GET'])
def get_text():
    """Get log or configuration file for a given ToO.
    
    Query parameters:
    - file_path: Direct file path to the log or config file (preferred)
    - obj: Object name (tile name) to identify the ToO (alternative, requires date or file_type)
    - date: Optional date filter in YYYY-MM-DD format (used with obj)
    - file_type: Optional file type filter ('log' or 'config') when using obj parameter
    """
    # Get file path directly from request (like web-pipeline)
    file_path = request.args.get('file_path')
    if not file_path:
        return jsonify({'error': 'Missing file_path parameter'}), 400

    if file_path:
        # Direct file path provided - use it directly
        if not os.path.exists(file_path):
            # Try to construct full path from filename (like web-pipeline)
            # For config files, the file_path might be just the name like "T02228_m875_2025-10-11"
            # We need to construct the full path: /lyman/data2/processed/{date}/{obj}/{filt}/{name}.yml
            original_file_path = file_path
            # Remove .yml extension if present for parsing
            if file_path.endswith('.yml') or file_path.endswith('.yaml'):
                file_path = file_path[:-4] if file_path.endswith('.yml') else file_path[:-5]
            
            vals = file_path.split("_")
            if len(vals) >= 3:
                # Try to parse as obj_filt_date format
                # Last part should be date (YYYY-MM-DD or YYYYMMDD)
                date_part = vals[-1]
                obj_part = vals[0]
                filt_part = "_".join(vals[1:-1]) if len(vals) > 3 else vals[1]
                
                # Normalize date format (YYYY-MM-DD or YYYYMMDD -> YYYY-MM-DD)
                if len(date_part) == 8 and date_part.isdigit():
                    # YYYYMMDD format
                    date_formatted = f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]}"
                elif len(date_part) == 10 and date_part.count('-') == 2:
                    # Already YYYY-MM-DD format
                    date_formatted = date_part
                else:
                    date_formatted = date_part
                
                # Construct full path for config file (add .yml extension)
                constructed_path = f"/lyman/data2/processed/{date_formatted}/{obj_part}/{filt_part}/{file_path}.yml"
                if os.path.exists(constructed_path):
                    file_path = constructed_path
                else:
                    return jsonify({'error': 'File not found'}), 404
            else:
                return jsonify({'error': 'File not found'}), 404
        
        if allowed_file_path(file_path) is None:
            return jsonify({'error': 'file_path is outside the alert and ToO output folders'}), 403

        try:
            # Read file content
            with open(file_path, 'r') as file:
                content = file.read()
            
            # Detect file type and format response accordingly
            if file_path.endswith(".json"):
                try:
                    json_content = json.loads(content)  # Parse JSON
                    return jsonify({'type': 'config', 'content': json_content})
                except json.JSONDecodeError:
                    return jsonify({'error': 'Invalid JSON format'}), 400
            elif file_path.endswith(".yml") or file_path.endswith(".yaml"):
                # Try YAML parsing
                try:
                    import yaml
                    yaml_content = yaml.safe_load(content)
                    return jsonify({'type': 'config', 'content': yaml_content})
                except ImportError:
                    # If yaml module not available, return as plain text
                    return jsonify({'type': 'log', 'content': content})
                except Exception:
                    # If YAML parsing fails, return as plain text
                    return jsonify({'type': 'log', 'content': content})
            else:
                return jsonify({'type': 'log', 'content': content})
        
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@api_bp.route('/api/gcn-template', methods=['GET', 'POST'])
@csrf_protect
def get_gcn_template():
    """Get or save GCN template for a ToO.
    
    GET: Returns the GCN template. If a customized template exists at the file_path, 
         returns that; otherwise returns the default template.
    POST: Saves/updates the GCN template at the specified file_path.
    
    Query parameters:
    - file_path: Path to the GCN template file 
    """
    
    # Get file_path directly (preferred)
    file_path = request.args.get('file_path')
    if file_path and allowed_file_path(file_path) is None:
        return jsonify({'error': 'file_path is outside the alert and ToO output folders'}), 403

    if request.method == 'POST':
        # Save/update the template
        if not file_path or str(file_path).strip() == '' or str(file_path).lower() == 'none':
            return jsonify({'error': 'Missing file_path parameter'}), 400
        
        try:
            data = request.json
            if not data or 'content' not in data:
                return jsonify({'error': 'Missing content in request body'}), 400
            
            template_path = str(file_path)
            template_dir = os.path.dirname(template_path)
            
            # Ensure directory exists
            if template_dir:
                try:
                    # Check if directory exists and is writable
                    if os.path.exists(template_dir):
                        if not os.access(template_dir, os.W_OK):
                            return jsonify({'error': f'Permission denied: Directory {template_dir} is not writable'}), 403
                    else:
                        # Try to create directory with proper permissions
                        try:
                            os.makedirs(template_dir, exist_ok=True, mode=0o755)
                        except PermissionError:
                            return jsonify({'error': f'Permission denied: Cannot create directory {template_dir}'}), 403
                        except OSError as e:
                            return jsonify({'error': f'Cannot create directory {template_dir}: {str(e)}'}), 500
                except Exception as e:
                    return jsonify({'error': f'Error checking directory: {str(e)}'}), 500
            
            # Check if file exists and is writable
            if os.path.exists(template_path):
                if not os.access(template_path, os.W_OK):
                    return jsonify({'error': f'Permission denied: File {template_path} exists but is not writable'}), 403
            
            # Write the file
            try:
                with open(template_path, 'w') as f:
                    f.write(data['content'])
                
                # Set file permissions to be readable and writable by all users
                # 0o666 = rw-rw-rw- (read/write for owner, group, and others)
                try:
                    os.chmod(template_path, 0o666)
                except OSError:
                    pass  # Ignore chmod errors if we can't set permissions, file was written successfully
                
                # Try to change ownership to www-data if possible
                try:
                    import pwd
                    import grp
                    www_data_uid = pwd.getpwnam('www-data').pw_uid
                    # Try to get www-data group, fallback to same group as user
                    try:
                        www_data_gid = grp.getgrnam('www-data').gr_gid
                    except KeyError:
                        # If www-data group doesn't exist, use the group of the current user
                        www_data_gid = os.getgid()
                    os.chown(template_path, www_data_uid, www_data_gid)
                except (ImportError, KeyError, OSError, PermissionError):
                    # If we can't change ownership, that's okay - permissions should still work
                    pass
                
                return jsonify({'success': True, 'message': f'Template saved to {template_path}'})
            except PermissionError:
                return jsonify({'error': f'Permission denied: Cannot write to {template_path}'}), 403
            except IOError as e:
                return jsonify({'error': f'Cannot write file: {str(e)}'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    else:  # GET request
        # Try to read template from file_path
        if file_path and str(file_path).strip() != '' and str(file_path).lower() != 'none':
            template_path = str(file_path)
            if os.path.exists(template_path):
                try:
                    with open(template_path, 'r') as f:
                        content = f.read()
                    
                    # Try to find base_path from database and update [table] section if text output exists
                    try:
                        # Find the row in database that has this gcn_template path
                        rows = read_all_rows()
                        matching_row = None
                        for row in rows:
                            if row.get('gcn_template') == template_path:
                                matching_row = row
                                break
                        
                        # If found, check for text output file
                        if matching_row:
                            base_path = matching_row.get('base_path')
                            if base_path:
                                text_output_path = os.path.join(base_path, 'combined_sed_cutouts_output.txt')
                                if os.path.exists(text_output_path):
                                    try:
                                        with open(text_output_path, 'r') as text_file:
                                            table_content = text_file.read().strip()
                                        # Replace [table] with the actual content
                                        content = content.replace('[table]', table_content)
                                    except Exception as e:
                                        print(f"Error reading text output file: {e}")
                    except Exception as e:
                        print(f"Error updating template with text output: {e}")
                    
                    return jsonify({
                        'content': content,
                        'source': 'custom',
                        'path': template_path
                    })
                except Exception as e:
                    return jsonify({'error': f'Cannot read template: {str(e)}'}), 500
            return jsonify({'error': f'Template file not found: {template_path}'}), 404
        return jsonify({'error': 'Missing file_path parameter'}), 400


@api_bp.route('/api/too_table/coordinates', methods=['PUT'])
@csrf_protect
def update_coordinates():
    try:
        data = request.get_json()
        alert_key = data.get('alert_key')
        trigger_time = data.get('trigger_time')
        ra = data.get('ra')
        dec = data.get('dec')
        
        if not alert_key:
            return jsonify({"error": "alert_key is required"}), 400
        
        if ra is None or dec is None:
            return jsonify({"error": "ra and dec are required"}), 400
        
        # Find the TOO row by alert_key
        row = read_row_by_key_and_trigger(alert_key, trigger_time)
        
        if not row:
            return jsonify({"error": "ToO request not found"}), 404
        
        # Normalize coordinates: convert to HH:MM:SS format and calculate degrees
        # The normalization functions handle both degrees and hh:mm:ss format inputs
        ra_hms = normalize_coordinate_to_hms(str(ra), is_ra=True)
        dec_hms = normalize_coordinate_to_hms(str(dec), is_ra=False)
        ra_deg_str = normalize_coordinate_to_deg(str(ra), is_ra=True)
        dec_deg_str = normalize_coordinate_to_deg(str(dec), is_ra=False)
        
        # Convert to float for database storage
        try:
            ra_deg = float(ra_deg_str)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid RA format: {ra}"}), 400
        
        try:
            dec_deg = float(dec_deg_str)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid Dec format: {dec}"}), 400
        
        # Prepare update data
        update_data = {
            'ra': ra_hms,
            'dec': dec_hms,
            'ra_deg': ra_deg,
            'dec_deg': dec_deg
        }
        
        # Update the database row by ID
        success = update_row_by_id(row['id'], update_data)

        try:
            from pipeline.pipeline.too.plotting import make_too_output
            make_too_output(row['id'])

            print(f"TOO output made successfully for {alert_key}")
        except Exception as e:
            print(f"Error making TOO output: {e}")
        
        if success:
            return jsonify({
                "message": "Coordinates updated successfully",
                "alert_key": alert_key,
                "ra": ra_hms,
                "dec": dec_hms,
                "ra_deg": ra_deg,
                "dec_deg": dec_deg
            }), 200
        else:
            return jsonify({"error": "Failed to update coordinates. Row not found or update failed."}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/output', methods=['GET'])
def get_output():
    """Get output files (image or text) for a ToO.
    
    Query parameters:
    - alert_key: Alert key to identify the ToO (optional, can use objname or tile instead)
    - trigger_time: Optional trigger time to filter (ISO format, KST/UTC+9, used with alert_key)
    - objname: Object name to identify the ToO (alternative to alert_key)
    - tile: Tile name to identify the ToO (alternative to alert_key)
    - type: Type of output to return - 'image' or 'text' (required)
    
    Note: All time fields in the database are stored in KST (Korea Standard Time, UTC+9).
    """
    try:
        # Get type parameter (required)
        output_type = request.args.get('type')
        if not output_type or output_type not in ['image', 'text']:
            return jsonify({"error": "Missing or invalid 'type' parameter. Must be 'image' or 'text'"}), 400
        
        # Get TOO identifier from query parameters
        alert_key = request.args.get('alert_key')
        trigger_time = request.args.get('trigger_time')
        objname = request.args.get('objname')
        tile = request.args.get('tile')
        
        # Find the TOO row in the database
        row = None
        if alert_key:
            row = read_row_by_key_and_trigger(alert_key, trigger_time)
        elif objname:
            rows = read_all_rows()
            matching_rows = [r for r in rows if r.get('objname') == objname]
            if matching_rows:
                row = max(matching_rows, key=lambda x: x.get('created_at', ''))
        elif tile:
            rows = read_all_rows()
            matching_rows = [r for r in rows if r.get('tile') == tile]
            if matching_rows:
                row = max(matching_rows, key=lambda x: x.get('created_at', ''))
        else:
            return jsonify({"error": "Missing identifier. Provide alert_key, objname, or tile"}), 400
        
        if not row:
            return jsonify({"error": "ToO request not found"}), 404
        
        # Get base_path from the row
        base_path = row.get('base_path')
        if not base_path:
            return jsonify({"error": "base_path not found in database for this ToO"}), 404
        
        # Construct file path based on type
        if output_type == 'image':
            file_path = os.path.join(base_path, 'combined_sed_cutouts.png')
            if not os.path.exists(file_path):
                return jsonify({"error": f"Image file not found: {file_path}"}), 404
            return send_file(file_path, mimetype='image/png')
        else:  # text
            file_path = os.path.join(base_path, 'combined_sed_cutouts_output.txt')
            if not os.path.exists(file_path):
                return jsonify({"error": f"Text file not found: {file_path}"}), 404
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                return Response(content, content_type="text/plain")
            except Exception as e:
                return jsonify({"error": f"Error reading text file: {str(e)}"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

