import os
import json
import copy
from collections import defaultdict
from datetime import datetime, timezone

from flask import Flask, request, jsonify, abort, render_template, Response
from flask_cors import CORS
from google.cloud import storage
from google.api_core import exceptions as google_exceptions
from google.cloud import contact_center_insights_v1

# --- FLASK APP INITIALIZATION CHANGED HERE ---
# Tells Flask to look for HTML, CSS, and JS inside the 'frontend' folder
app = Flask(__name__, template_folder='frontend', static_folder='frontend')
app.config['JSON_SORT_KEYS'] = False
CORS(app)

# --- Configuration & Initialization ---
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
PROJECTS_FILENAME = "projects.json"
DISPLAY_NAMES_FILENAME = "display_names.json"
NUMBERS_FILENAME = "numbers.json"

if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME environment variable not set.")

storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)

def _get_json_from_gcs(filename):
    blob = bucket.blob(filename)
    try:
        content = blob.download_as_string()
        return json.loads(content)
    except google_exceptions.NotFound:
        if filename == PROJECTS_FILENAME: return {"projects": []}
        if filename == NUMBERS_FILENAME: return {"projects": {}, "last_run_utc": None}
        return {}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error: Failed to parse JSON from '{filename}': {e}")
        if filename == PROJECTS_FILENAME: return {"projects": []}
        if filename == NUMBERS_FILENAME: return {"projects": {}, "last_run_utc": None}
        return {}

def _write_json_to_gcs(filename, data):
    blob = bucket.blob(filename)
    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")

def _structure_and_order_project(data):
    # This function cleans and structures the raw form data into the correct JSON schema
    _to_list = lambda v: [item.strip() for item in v.split(',')] if isinstance(v, str) and v.strip() else (v if isinstance(v, list) else [])
    _to_float = lambda v: float(v) if v is not None and str(v).strip() not in ['', 'None'] else None
    _to_int = lambda v: int(float(v)) if v is not None and str(v).strip() not in ['', 'None'] else 0
    _to_list_of_floats = lambda v: [_to_float(i.strip()) for i in v.split(',') if _to_float(i.strip()) is not None] if isinstance(v, str) and v.strip() else (v if isinstance(v, list) else [])
    
    project_id = data.get('project_id', '').strip()
    theme = data.get('gen_theme', [])
    language = data.get('gen_language', [])

    return {
        "display_name": data.get('display_name', '').strip() or project_id,
        "project_id": project_id,
        "project_number": data.get('project_number', ""),
        "location": data.get('location', ""),
        "environments": _to_list(data.get('environments', [])),
        "buckets": {
            "audios": data.get('buckets_audios', ""),
            "transcripts": data.get('buckets_transcripts', ""),
            "metadata": data.get('buckets_metadata', "")
        },
        "virtual_agents": data.get('virtual_agents', []),
        "generation_profile": {
            "theme": [theme] if isinstance(theme, str) else _to_list(theme),
            "company_name": data.get('gen_company_name', ""),
            "language": [language] if isinstance(language, str) else _to_list(language),
            "topics": _to_list(data.get('gen_topics', [])),
            "model": data.get('gen_model', ""),
            "temperature": _to_list_of_floats(data.get('gen_temperature', [])),
            "topk": _to_list_of_floats(data.get('gen_topk', [])),
            "topp": _to_list_of_floats(data.get('gen_topp', [])),
            "sentiment_journeys": _to_list(data.get('gen_sentiment_journeys', [])),
            "max_conversations_per_run": {
                "audio": _to_int(data.get('max_conversations_per_run_audio')),
                "chat": _to_int(data.get('max_conversations_per_run_chat')),
                "agentic": _to_int(data.get('max_conversations_per_run_agentic'))
            },
            "probabilities": {
                "bad_sentiment": _to_list_of_floats(data.get('probabilities_bad_sentiment', [])),
                "long_conversation": _to_list_of_floats(data.get('probabilities_long_conversation', [])),
                "bad_performance": _to_list_of_floats(data.get('probabilities_bad_performance', []))
            },
            "prompt_hint": _to_list(data.get('gen_prompt_hint', []))
        }
    }

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/configurations", methods=["GET"])
def get_configurations():
    projects_data = _get_json_from_gcs(PROJECTS_FILENAME)
    projects_list = projects_data.get("projects", [])
    display_names_map = _get_json_from_gcs(DISPLAY_NAMES_FILENAME)
    final_configurations = []
    
    # Merge display names for UI
    for project in projects_list:
        if isinstance(project, dict) and 'project_id' in project:
            project_id = project['project_id']
            display_names = display_names_map.get(project_id, [])
            if display_names:
                for name in display_names:
                    project_copy = copy.deepcopy(project)
                    project_copy['display_name'] = name
                    final_configurations.append(project_copy)
            else:
                project['display_name'] = project_id
                final_configurations.append(project)
    
    final_configurations.sort(key=lambda x: x.get('display_name', '').lower())
    return jsonify({"configurations": final_configurations, "project_count": len(final_configurations)})

@app.route("/configurations/raw", methods=["GET"])
def get_projects_config_raw():
    try:
        content = bucket.blob(PROJECTS_FILENAME).download_as_string()
        return Response(json.dumps(json.loads(content), indent=4), mimetype='application/json')
    except google_exceptions.NotFound:
        return "{\n  \"projects\": []\n}", 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return Response(str(e), mimetype='text/plain', status=500)

@app.route("/configurations/single", methods=["POST"])
def update_single_configuration():
    """
    Handles atomic Add or Edit operations.
    Prevents race conditions by reading the latest file state, modifying it, and writing it back.
    """
    request_data = request.get_json()
    action = request_data.get('action') # 'add' or 'edit'
    payload = request_data.get('configuration')
    original_project_id = request_data.get('original_project_id') # needed for edits if ID changed
    original_display_name = request_data.get('original_display_name') # needed to find the specific entry

    if not action or not payload:
        abort(400, description="Missing action or configuration data.")

    # 1. READ LATEST STATE
    projects_data = _get_json_from_gcs(PROJECTS_FILENAME)
    current_projects = projects_data.get("projects", [])
    display_names_map = _get_json_from_gcs(DISPLAY_NAMES_FILENAME)

    # 2. PROCESS
    structured_config = _structure_and_order_project(payload)
    new_project_id = structured_config['project_id']
    new_display_name = structured_config['display_name']
    
    # Remove display_name from storage object (it lives in map)
    config_for_storage = copy.deepcopy(structured_config)
    del config_for_storage['display_name']

    if action == 'add':
        # Check if project already exists in storage list
        existing_idx = next((i for i, p in enumerate(current_projects) if p['project_id'] == new_project_id), -1)
        if existing_idx > -1: 
             # If project exists, we just update the config
             current_projects[existing_idx] = config_for_storage
        else:
            current_projects.append(config_for_storage)
            
        # Update display map
        if new_project_id not in display_names_map:
            display_names_map[new_project_id] = []
        if new_display_name not in display_names_map[new_project_id]: 
             display_names_map[new_project_id].append(new_display_name)

    elif action == 'edit':
        # Find the project definition by original_project_id
        existing_idx = next((i for i, p in enumerate(current_projects) if p['project_id'] == original_project_id), -1)
        
        if existing_idx == -1:
            # If original project not found (e.g. race condition), append as new
            current_projects.append(config_for_storage)
        else:
            # Update the configuration logic
            current_projects[existing_idx] = config_for_storage

        # Handle ID Change cleanup
        if original_project_id and original_project_id != new_project_id: 
             # Migrate display names map if ID changed
             if original_project_id in display_names_map: 
                 # Move the list to the new key
                 display_names_map[new_project_id] = display_names_map.pop(original_project_id)
                 
        # Ensure new key exists in map
        if new_project_id not in display_names_map: 
             display_names_map[new_project_id] = []
                 
        # Remove old display name if it changed
        if original_display_name and original_display_name in display_names_map[new_project_id]:
            display_names_map[new_project_id].remove(original_display_name)
            
        # Add new display name
        if new_display_name not in display_names_map[new_project_id]:
            display_names_map[new_project_id].append(new_display_name)

    # 3. WRITE BACK
    try:
        _write_json_to_gcs(PROJECTS_FILENAME, {"projects": current_projects})
        _write_json_to_gcs(DISPLAY_NAMES_FILENAME, display_names_map)
        return jsonify({"message": "Configuration saved successfully!"}), 200
    except Exception as e:
        abort(500, description=f"Could not save to GCS: {e}")

@app.route("/conversation-counts", methods=["POST"])
def update_conversation_counts():
    try:
        current_counts_data = _get_json_from_gcs(NUMBERS_FILENAME)
        projects_data = _get_json_from_gcs(PROJECTS_FILENAME).get("projects", [])
        
        last_run_str = current_counts_data.get("last_run_utc")
        if last_run_str:
            time_filter = f'create_time > "{last_run_str}"'
            new_counts_data = copy.deepcopy(current_counts_data)
        else:
            time_filter = 'create_time > "2025-01-01T00:00:00Z"'
            new_counts_data = {"projects": {}, "last_run_utc": None}

        current_run_time = datetime.now(timezone.utc)
        print(f"--- Starting Conversation Count Job at {current_run_time.isoformat()} ---")

        unique_projects = {p['project_id']: p for p in projects_data}.values()

        for project in unique_projects:
            project_id = project.get("project_id")
            location = project.get("location", "us-central1")
            if not project_id: continue

            print(f"--- Processing project: '{project_id}' in location '{location}' ---")
            
            client_options = {"api_endpoint": f"{location}-contactcenterinsights.googleapis.com"}
            client = contact_center_insights_v1.ContactCenterInsightsClient(client_options=client_options)
            parent = f"projects/{project_id}/locations/{location}"
            
            project_counts = new_counts_data["projects"].get(project_id, {"total": 0})
            
            try:
                request = contact_center_insights_v1.ListConversationsRequest(parent=parent, filter=time_filter, page_size=1000, view=contact_center_insights_v1.ConversationView.BASIC)
                iterator = client.list_conversations(request=request)
                total_delta = 0
                for page in iterator.pages:
                    page_count = len(list(page.conversations))
                    if page_count > 0: total_delta += page_count
                
                project_counts["total"] += total_delta
                new_counts_data["projects"][project_id] = project_counts
                print(f"  > [{project_id}] TOTALS updated. New total count: {project_counts['total']}")

            except Exception as e:
                print(f"  > [{project_id}] ERROR: Could not process: {e}")

        new_counts_data["last_run_utc"] = current_run_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        _write_json_to_gcs(NUMBERS_FILENAME, new_counts_data)
        return jsonify({"message": "Conversation counts updated successfully.", "data": new_counts_data})

    except Exception as e:
        print(f"FATAL ERROR in update_conversation_counts: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/conversation-counts", methods=["GET"])
def get_conversation_counts():
    counts = _get_json_from_gcs(NUMBERS_FILENAME)
    return jsonify(counts)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
