from flask import Blueprint, send_from_directory, request, jsonify
from flask_mail import Message
from . import mail  # Import the mail instance from __init__.py
import pandas as pd
import os
import json
from glob import glob
from datetime import datetime
from .scripts.mainobserver import mainObserver
from .scripts.staralt import Staralt
from astropy.table import Table
import numpy as np

api_bp = Blueprint('api', __name__, static_folder='../../frontend/build')

DATA_FOLDER = os.getenv('DATA_FOLDER', './data')

@api_bp.route('/')
def serve():
    return send_from_directory(api_bp.static_folder, 'index.html')

@api_bp.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(api_bp.static_folder, path)

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
    file_path = os.path.join(DATA_FOLDER, "7dt/filtinfo.dict")
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
    file_path = os.path.join(DATA_FOLDER, "7dt/multitelescopes.dict")
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
    
    file_path = os.path.join(DATA_FOLDER, "7dt/DB_Daily.ascii")

    try:
        # Read the file (update the parameters based on your file format)
        data_table= pd.read_csv(file_path, delimiter=' ')
        data_table = data_table.replace({np.nan: None})
        return jsonify(data_table.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/spec-options', methods=['GET'])
def get_spec_options():
    data_folder = os.getenv('DATA_FOLDER', './data')
    specmode_folder = os.path.join(data_folder, '7dt/specmode')
    specmode_files = []

    for root, dirs, files in os.walk(specmode_folder):
        for file in files:
            if file.endswith('.specmode'):
                specmode_files.append(file)

    return jsonify(specmode_files)

@api_bp.route('/api/spec-file', methods=['GET'])
def get_spec_file():
    data_folder = os.getenv('DATA_FOLDER', './data')
    specmode_folder = os.path.join(data_folder, '7dt/specmode')
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

@api_bp.route('/api/send_email', methods=['POST'])
def send_email():
    try:
        data = request.json

        obsmode = data.get('obsmode')

        if obsmode == "Spec":
            details1 = f"- Specmode: {data.get('selectedSpecFile')}"
            details2 = ""
        elif obsmode == "Deep":
            selected_filters = ",".join(list(data.get('selectedFilters')))
            details1 = f"- Filters: {selected_filters}"
            details2 = f"- NumberofTelescopes: {data.get('selectedTelNumber')}"


        # Construct the email body
    
        email_body = f"""
        ================================
        New ToO Request Submitted
        ================================

        **Observation Information**
        ----------------------
        - Target Name: {data.get('requester')}
        - Target Name: {data.get('target')}
        - Right Ascension (R.A.): {data.get('ra')}
        - Declination (Dec.): {data.get('dec')}
        - Total Exposure Time (seconds): {data.get('exposure')}
        - Obsmode: {data.get('obsmode')}
            {details1}
            {details2}

        **Detailed Settings**
        --------------------
        - Abort Current Observation: {data.get('abortObservation')}
        - Priority: {data.get('priority')}
        - Single Frame Exposure: {data.get('singleFrameExposure')}
        - Number of Images: {data.get('imageCount')}
        - Gain: {data.get('gain')}
        - Binning: {data.get('binning')}
        - Observation Start Time: {data.get('obsStartTime')}
        - Comments: {data.get('comments')}

        ================================
        Please take necessary actions.
        ================================
        """

        # Save the entered data as a JSON file
        now_str = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"too_request_{now_str}.json"
        file_path = os.path.join(os.getcwd(), file_name)
        data["id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)

        # Send email with the attachment
        msg = Message(
            subject="[Automated] 7DT ToO Observation Request",
            recipients=["7dt.observation.alert@gmail.com", "takdg123@gmail.com"],  # Recipient email
            body=email_body
        )
        with open(file_path, "rb") as file:
            msg.attach(file_name, "application/json", file.read())

        mail.send(msg)

        # Clean up the temporary file
        os.remove(file_path)

        return jsonify({"message": "Your ToO request sent successfully!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/staralt_data', methods=['GET'])
def get_staralt_data():
    """
    Provides star altitude data as JSON. 
    Expected query params: ra, dec, (optional) objname, target_minalt, target_minmoonsep
    Example: /api/staralt_data?ra=20.5243&dec=-20.245&objname=ABC&target_minalt=30&target_minmoonsep=40
    """
    try:
        ra = float(request.args.get('ra'))
        dec = float(request.args.get('dec'))
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
        star.staralt_data(ra=ra, dec=dec, objname=objname, target_minalt=target_minalt, target_minmoonsep=target_minmoonsep)

        # Return the data dictionary as JSON
        return jsonify(star.data_dict)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

