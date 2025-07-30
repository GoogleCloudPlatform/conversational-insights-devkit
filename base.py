# Assuming the updated V2 class is defined as above

import time
from src.core import base # Assuming base.Auth and base.Config exist
from src.wrapper.speech import V2
# Example placeholder for demonstration if base is not fully defined
class MockAuth:
    pass

class MockConfig:
    def set_speech_endpoint(self):
        return None # In a real scenario, this would set the endpoint


if __name__ == "__main__":
    # Replace with your actual Google Cloud Project ID
    PROJECT_ID = "emea-bootcamp-2025"
    # Replace with a list of GCS URIs for your audio files
    AUDIO_GCS_URIS = [
        "gs://akhil-rolerecognizer/C120006.wav" # Another example
    ]
    # Replace with the GCS URI of a directory where you want to store results
    # Ensure this bucket and directory exist and the service account has write permissions.
    OUTPUT_GCS_URI = "gs://akhil-rolerecognizer/stt/"

    try:
        # Initialize the V2 client
        speech_v2_client = V2(
            project_id=PROJECT_ID,
            diarization=False,  # Enable speaker diarization
            language_code="es-US",
            model="telephony", # Use 'long' model for batch recognition
            auth=MockAuth(), # Using mock for example
            config=MockConfig() # Using mock for example
        )

        # Start batch recognition
        print(f"Starting batch recognition for {len(AUDIO_GCS_URIS)} audio files...")
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