import time
import json
import os # Import os for basename and splitext
from google.cloud import storage
from src.core import base
from src.wrapper.speech import V2 as speech_v2

from google.cloud.speech_v2 import types 

from src.workflow import format


from src.workflow.role_recognizer import RoleRecognizer

def list_gcs_files(bucket_name, prefix="", file_extension=None):
    """
    Lists files in a GCS bucket with an optional prefix and filters by file extension.
    If file_extension is None, all files are listed.
    """
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    gcs_uris = []
    for blob in blobs:
        if not blob.name.endswith('/'): # Exclude directories
            if file_extension:
                if blob.name.lower().endswith(file_extension.lower()):
                    gcs_uris.append(f"gs://{bucket_name}/{blob.name}")
            else:
                gcs_uris.append(f"gs://{bucket_name}/{blob.name}")
    return gcs_uris

def download_gcs_json_to_memory(gcs_uri: str) -> dict:
    """Downloads a JSON file from GCS and returns its content as a Python dictionary."""
    storage_client = storage.Client()
    if not gcs_uri.startswith("gs://"):
        raise ValueError("GCS URI must start with 'gs://'")
    path_parts = gcs_uri[5:].split('/', 1)
    bucket_name = path_parts[0]
    blob_name = path_parts[1] if len(path_parts) > 1 else ""

    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    if not blob.exists():
        raise FileNotFoundError(f"Blob not found: {gcs_uri}")

    json_data = blob.download_as_text()
    return json.loads(json_data)

def upload_json_to_gcs(data: dict, gcs_uri: str):
    """Uploads a Python dictionary as a JSON file to GCS."""
    storage_client = storage.Client()
    if not gcs_uri.startswith("gs://"):
        raise ValueError("GCS URI must start with 'gs://'")
    path_parts = gcs_uri[5:].split('/', 1)
    bucket_name = path_parts[0]
    blob_name = path_parts[1] if len(path_parts) > 1 else ""

    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
    print(f"Uploaded JSON to {gcs_uri}")


if __name__ == "__main__":
    PROJECT_ID = "emea-bootcamp-2025"
    SOURCE_BUCKET_NAME = "akhil-rolerecognizer"
    SOURCE_BUCKET_PREFIX = "" 
    STT_OUTPUT_GCS_URI = "gs://akhil-rolerecognizer/stt_output/"
    
    # Base path for the combined role recognition output
    COMBINED_ROLE_REC_OUTPUT_BASE_PATH = "gs://akhil-rolerecognizer/roles-recognized/"


    try:
        print(f"Listing .wav audio files from gs://{SOURCE_BUCKET_NAME}/{SOURCE_BUCKET_PREFIX}...")
        AUDIO_GCS_URIS = list_gcs_files(SOURCE_BUCKET_NAME, SOURCE_BUCKET_PREFIX, file_extension=".wav")

        if not AUDIO_GCS_URIS:
            print(f"No .wav audio files found in gs://{SOURCE_BUCKET_NAME}/{SOURCE_BUCKET_PREFIX}. Exiting.")
            exit()

        print(f"Found {len(AUDIO_GCS_URIS)} .wav audio files to process.")
        for uri in AUDIO_GCS_URIS:
            print(f"  - {uri}")

        # Determine the base filename for the combined output
        # Using the filename of the *first* WAV file as the base for the combined JSON
        first_wav_file_basename = os.path.basename(AUDIO_GCS_URIS[0])
        # Remove the .wav extension and append .json
        final_combined_json_filename = os.path.splitext(first_wav_file_basename)[0] + ".json"
        
        # Construct the full GCS URI for the combined output JSON
        COMBINED_ROLE_REC_OUTPUT_GCS_URI = f"{COMBINED_ROLE_REC_OUTPUT_BASE_PATH}{final_combined_json_filename}"
        
        print(f"Combined role recognition output will be named: {final_combined_json_filename}")


        speech_v2_client = speech_v2(
            project_id=PROJECT_ID,
            diarization=False,
            language_code="es-MX",
            model="telephony",
        )

        print(f"\nStarting batch recognition for {len(AUDIO_GCS_URIS)} files...")
        batch_response = speech_v2_client.batch_recognize_audio(
            audio_gcs_uris=AUDIO_GCS_URIS,
            output_gcs_uri=STT_OUTPUT_GCS_URI
        )

        print("\nBatch Recognition completed!")
        print(f"STT results are available at: {STT_OUTPUT_GCS_URI}")

        print("\nInitializing RoleRecognizer...")
        role_recognizer = RoleRecognizer(model_name="gemini-2.5-flash-lite")

        print("\nProcessing STT results for role recognition...")

        stt_output_prefix = STT_OUTPUT_GCS_URI.replace(f"gs://{SOURCE_BUCKET_NAME}/", "")
        stt_output_files = list_gcs_files(SOURCE_BUCKET_NAME, stt_output_prefix, file_extension=".json")

        if not stt_output_files:
            print(f"No STT output JSON files found in {STT_OUTPUT_GCS_URI}. Exiting role recognition.")
            exit()

        ft = format.Speech()
        for stt_json_uri in stt_output_files:

            transcript = download_gcs_json_to_memory(stt_json_uri)
            stt_results = ft.v2_json_to_dict(transcript)

            roles = role_recognizer.predict_roles(conversation=stt_results)
            transcript = role_recognizer.combine(transcript, roles)

            upload_json_to_gcs(json.loads(transcript), COMBINED_ROLE_REC_OUTPUT_GCS_URI)

    except Exception as e:
        print(f"An overarching error occurred: {e}")