from flask import Blueprint, request, jsonify
from flask_mail import Message
from . import mail  # Import the mail instance from __init__.py
import pandas as pd
import os
from astropy.io import fits
import json
from glob import glob

api_bp = Blueprint('api', __name__)

DATA_FOLDER = os.getenv('DATA_FOLDER', './data')


@api_bp.route('/api/send_email', methods=['POST'])
def send_email():
    try:
        data = request.json

        mode = data.get('mode')

        if mode == "Spec":
            details = data.get('selectedSpecFile')
        elif mode == "Deep":
            details = ", ".join(list(data.get('selectedFilters')))
            details = details+f" / {data.get('selectedTelNumber')}"


        # Construct the email body
        email_body = f"""
        New ToO Request Submitted:

        Target: {data.get('target')}
        R.A.: {data.get('ra')}
        Dec.: {data.get('dec')}
        Exposure (minutes): {data.get('exposure')}
        Mode: {data.get('mode')} ({details})
        Abort Current Observation: {data.get('abortObservation')}

        Detailed Settings:
        Single Frame Exposure (seconds): {data.get('singleFrameExposure')}
        # of Images (counts): {data.get('imageCount')}
        Priority: {data.get('priority')}
        Gain: {data.get('gain')}
        Binning: {data.get('binning')}
        Observation Start Time: {data.get('obsStartTime')}

        Comments: 
        {data.get('comments', 'No additional comments provided')}

        Please take necessary actions.
        """

        # Save the entered data as a JSON file
        file_path = os.path.join(os.getcwd(), "too_request.json")
        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)

        # Send email with the attachment
        msg = Message(
            subject="[Automated] 7DT ToO Observation Request",
            recipients=["7dt.observation.alert@gmail.com", "takdg123@gmail.com"],  # Recipient email
            body=email_body
        )
        with open(file_path, "rb") as file:
            msg.attach("too_request.json", "application/json", file.read())

        mail.send(msg)

        # Clean up the temporary file
        os.remove(file_path)

        return jsonify({"message": "Your ToO request sent successfully!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/targets', methods=['GET'])
def get_targets():

    file_path = os.path.join(DATA_FOLDER, 'targets.fits')
    try:
        # Open the FITS file
        with fits.open(file_path) as hdul:
            # Access the data from the first extension (or adjust as needed)
            data = hdul[1].data
            df = pd.DataFrame(data)  # Convert FITS data to a Pandas DataFrame
            df.rename(columns={"GRBNAME":"name", "RA":"ra", "DEC": "dec"}, inplace=True)
            selected_columns = ['name', 'ra', 'dec']
            filtered_df = df[selected_columns]
            return jsonify(filtered_df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/filtinfo', methods=['GET'])
def get_filtinfo():
    file_path = os.path.join(DATA_FOLDER, "filtinfo.data")
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
    file_path = os.path.join(DATA_FOLDER, "multitelescopes.data")
    try:
        # Read JSON-like data
        with open(file_path, 'r') as f:
            multitelescopes = json.load(f)

        # Prepare the data for the table
        table_data = []
        latest_report = {"reported_by": None, "timestamp": None}

        for telescope, components in multitelescopes.items():
            row = {"Telescope": telescope}
            for component, details in components.items():
                row[component] = details["status"]
                # Update latest reporter and timestamp if needed
                if not latest_report["timestamp"] or details["timestamp"] > latest_report["timestamp"]:
                    latest_report["reported_by"] = details["reported_by"]
                    latest_report["timestamp"] = details["timestamp"]
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
    import os
    import pandas as pd
    
    # Locate the latest "Daily" file
    data_folder = os.getenv('DATA_FOLDER', './data')
    file_path = None
    for file_name in os.listdir(data_folder):
        if file_name.startswith("Daily"):
            file_path = os.path.join(data_folder, file_name)
            break

    if not file_path:
        return jsonify({"error": "No Daily file found"}), 404

    try:
        # Read the file (update the parameters based on your file format)
        schedule_df = pd.read_fwf(file_path)

        # Convert the data to JSON for API response
        schedule_json = schedule_df.to_dict(orient="records")
        return jsonify(schedule_json)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/spec-options', methods=['GET'])
def get_spec_options():
    data_folder = os.getenv('DATA_FOLDER', './data')
    files = [f for f in os.listdir(data_folder) if f.endswith('.specmode')]
    return jsonify(files)

@api_bp.route('/api/spec-file', methods=['GET'])
def get_spec_file():
    file_name = request.args.get('file')
    data_folder = os.getenv('DATA_FOLDER', './data')
    file_path = os.path.join(data_folder, file_name)
    
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            data = json.load(f)  # Correctly use the loaded JSON data
            unique_list = list(set(item for sublist in data.values() for item in sublist))  # Use `data` instead of `spec`
            wavelengths = sorted([float(item[1:]) for item in unique_list if 'm' in item])  # Extract wavelengths
            filters = [item for item in unique_list if 'm' not in item]  # Extract filters
            # Return processed data
            return jsonify({
                "wavelengths": wavelengths,
                "filters": filters
            })

    return jsonify({"error": "File not found"}), 404