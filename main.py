import time
from google.cloud import storage # Import the storage client
from src.core import base # Assuming base.Auth and base.Config exist
from src.wrapper.speech import V2

def list_gcs_files(bucket_name, prefix=""):
    """Lists all files in a GCS bucket with an optional prefix."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix) # List all blobs (files) in the bucket

    gcs_uris = []
    for blob in blobs:
        # Only include actual files, not directories (blobs ending with '/')
        if not blob.name.endswith('/'):
            gcs_uris.append(f"gs://{bucket_name}/{blob.name}")
    return gcs_uris

if __name__ == "__main__":
    # Replace with your actual Google Cloud Project ID
    PROJECT_ID = "emea-bootcamp-2025"

    # Specify your GCS bucket name
    SOURCE_BUCKET_NAME = "akhil-rolerecognizer"
    # Optional: If your audio files are in a specific "folder" within the bucket,
    # specify that prefix. For example, if files are in "audio_files/".
    # SOURCE_BUCKET_PREFIX = "audio_files/"
    SOURCE_BUCKET_PREFIX = "" # Empty string to list all files in the root of the bucket

    # Replace with the GCS URI of a directory where you want to store results
    # Ensure this bucket and directory exist and the service account has write permissions.
    OUTPUT_GCS_URI = "gs://akhil-rolerecognizer/stt/"

    try:
        # Get all audio files from the specified GCS bucket
        print(f"Listing audio files from gs://{SOURCE_BUCKET_NAME}/{SOURCE_BUCKET_PREFIX}...")
        AUDIO_GCS_URIS = list_gcs_files(SOURCE_BUCKET_NAME, SOURCE_BUCKET_PREFIX)

        if not AUDIO_GCS_URIS:
            print(f"No audio files found in gs://{SOURCE_BUCKET_NAME}/{SOURCE_BUCKET_PREFIX}. Exiting.")
            exit()

        print(f"Found {len(AUDIO_GCS_URIS)} audio files to process.")
        for uri in AUDIO_GCS_URIS:
            print(f"  - {uri}")

        # Initialize the V2 client
        speech_v2_client = V2(
            project_id=PROJECT_ID,
            diarization=False,  # Enable speaker diarization
            language_code="es-US",
            model="telephony", # Use 'long' model for batch recognition
        )

        # Start batch recognition
        print(f"\nStarting batch recognition for {len(AUDIO_GCS_URIS)} audio files...")
        batch_response = speech_v2_client.batch_recognize_audio(
            audio_gcs_uris=AUDIO_GCS_URIS,
            output_gcs_uri=OUTPUT_GCS_URI
        )

        # The batch_recognize_audio method already waits for the operation to complete
        # due to `operation.result()`.
        print("\nBatch Recognition completed!")
        print(f"Results are available at: {OUTPUT_GCS_URI}")

        # You would then typically read the JSON output files from the OUTPUT_GCS_URI
        # to get the actual transcription results for each file.
        print("\n--- To access results, you would download/read the JSON files from the output GCS URI ---")
        print("Example of what the batch_response object contains (metadata about the operation):")
        for result in batch_response.results:
            print(f"  File: {result.uri}, Error: {result.error.message if result.error.message else 'None'}")


    except Exception as e:
        print(f"An error occurred: {e}")
