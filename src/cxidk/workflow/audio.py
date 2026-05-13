# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A class to generate audio from text using Google Cloud Text-to-Speech."""

import enum
import io
import logging
from typing import Optional

from pydub import AudioSegment #type: ignore

from cxidk.wrapper import speech
from cxidk.wrapper import storage
from cxidk.wrapper import sensitive_data_protection
from cxidk.workflow import format as ft


class Roles(enum.StrEnum):
    """Enumeration for supported speaker roles."""

    AGENT = "AGENT"
    CUSTOMER = "CUSTOMER"


class VoiceRole(enum.Enum):
    """Enum for supported voices for each role"""
    # pylint: disable=invalid-name
    CUSTOMER = "en-US-Wavenet-A"
    AGENT = "en-US-Wavenet-D"

class Utils:
    """A collection of utility functions for audio processing."""

    def __init__(self, project_id: Optional[str]=None):
        """Initializes the Utils class.

        Args:
            project_id: The Google Cloud project ID.
        """
        self.project_id = project_id

    def save_audio_locally(self,byte_string_data,output_file_name):
        """Saves byte string audio data to a local file.

        Args:
            byte_string_data: The audio data in bytes.
            output_file_name: The path and name of the output file.
        """
        with open(output_file_name, 'wb') as f:
            f.write(byte_string_data)


class GenerateAudio:
    """
    A class to generate audio from text using Google Cloud Text-to-Speech.
    """

    def __init__(
        self,
        project_id: str,
    ):
        """Initializes the GenerateAudio class.

        Args:
            project_id: The Google Cloud project ID.
        """
        self.project_id = project_id
        logging.info(
            "Be advised: for this module to properly work 'ffmpeg' needs to be locally instaled"
        )

    def bulk(
        self,
        transcripts: list,
        audio_file_path: str,
    ) -> None:
        """Processes multiple transcripts to generate corresponding audio files.

        This method iterates through a list of transcript dictionaries and calls
        the `single` method for each to generate and save an audio file.

        Args:
            transcripts: A list of dictionaries, where each dictionary is a
                conversation transcript.
            audio_file_path: The local directory or GCS path prefix where the
                audio files will be saved.
        """
        for transcript in transcripts:
            self.single(transcript=transcript, audio_file_path=audio_file_path)

    ##TO-DO break down in functions
    def single(
        self,
        transcript,
        audio_file_path: str,
        language: Optional[str] = "en-US",
        agent_voice: Optional[str] = "en-US-Chirp3-HD-Iapetus",
        customer_voice: Optional[str] = "en-US-Chirp3-HD-Zephyr",
        pause_between_utterances_ms: Optional[int] = 500,
        sample_rate_hertz: int = 32000,
    ) -> None:
        """Processes a single transcript to generate and save a stereo audio file.

        This method synthesizes speech for each utterance in a transcript,
        assigning agent and customer audio to separate channels to create a
        stereo effect. The final audio can be saved to a local path or
        uploaded to Google Cloud Storage.

        Args:
            transcript: A dictionary containing the conversation transcript.
            audio_file_path: The local or GCS path (e.g., "gs://bucket/file")
                to save the generated audio file.
            language: The language code for speech synthesis (e.g., "en-US").
            agent_voice: The voice model for the agent.
            customer_voice: The voice model for the customer.
            pause_between_utterances_ms: Milliseconds of silence between utterances.
            sample_rate_hertz: The sample rate of the audio in Hertz.
        """
        speech_client = speech.TextToSpeech(project_id=self.project_id)
        voice_overrides = {Roles.AGENT: agent_voice, Roles.CUSTOMER: customer_voice}
        if "entries" not in transcript or not isinstance(transcript["entries"], list):
            raise ValueError(
                "Transcript must be a dictionary containing an"
                "'entries' key with a list of utterances."
            )

        ##TO-DO: support different audio format selection
        audio_format = "wav"
        combined_audio = AudioSegment.empty()
        entries = transcript["entries"]
        for i, entry in enumerate(entries):
            text = entry.get("text")
            role_str = entry.get("role", "").upper()
            role_enum = Roles[role_str]

            voice = voice_overrides.get(role_enum) or VoiceRole[role_enum.name].value

            mono_audio_bytes = speech_client.synthesize(
                text=text,
                voice=voice,
                language_code=language,
                sample_rate_hertz=sample_rate_hertz,
            )

            mono_segment = AudioSegment.from_file(
                io.BytesIO(mono_audio_bytes), format=audio_format
            )
            silent_segment = AudioSegment.silent(
                duration=len(mono_segment), frame_rate=mono_segment.frame_rate
            )

            # Ensure both segments have the exact same length to prevent errors.
            min_len = min(len(mono_segment), len(silent_segment))
            mono_segment = mono_segment[:min_len]
            silent_segment = silent_segment[:min_len]

            # Define left and right channels based on the role.
            left_channel, right_channel = (
                (mono_segment, silent_segment)
                if role_enum == Roles.CUSTOMER
                else (silent_segment, mono_segment)
            )

            # Create the stereo audio segment.
            stereo_utterance = AudioSegment.from_mono_audiosegments(
                left_channel, right_channel
            )

            combined_audio += stereo_utterance

            if i < len(entries) - 1:
                combined_audio += AudioSegment.silent(
                    duration=pause_between_utterances_ms
                )

        if len(combined_audio) > 0:
            if audio_file_path.startswith("gs://"):
                # Create an in-memory binary stream to hold the audio data
                buffer = io.BytesIO()
                combined_audio.export(buffer, format=audio_format)
                buffer.seek(0)  # Rewind the buffer to the beginning before reading
                gcs_path = audio_file_path.replace("gs://", "")
                bucket_name, blob_name = gcs_path.split("/", 1)

                # Initialize the storage client and upload the in-memory file
                storage_client = storage.Gcs(
                    bucket_name=bucket_name, project_id=self.project_id
                )
                storage_client.upload_blob(
                    file_name=blob_name,
                    data=buffer.read(),
                    content_type=storage.ContentType.WAV,
                )
            else:
                # If it's not a GCS path, save it as a local file
                combined_audio.export(audio_file_path, format=audio_format)
        else:
            raise ValueError("Combined audio is empty.")

class RedactAudio:
    """
    Redacts sensitive information from audio files based on transcript analysis.

    This class orchestrates a multi-step process involving Cloud DLP to identify
    sensitive text in a transcript, finding the corresponding timestamps in the
    original audio, and replacing those audio segments with silence.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        remote_audio_file_bucket: str,
        remote_audio_file_name: str,
    ):
        """Initializes the RedactAudio class.

        Args:
            project_id: The Google Cloud project ID.
            location: The Google Cloud location (e.g., 'us-central1').
            remote_audio_file_bucket: The GCS bucket containing the audio file.
            remote_audio_file_name: The name of the audio file in the GCS bucket.
        """
        self.project_id = project_id
        self.location = location
        self.remote_audio_file_bucket = remote_audio_file_bucket
        self.remote_audio_file_name = remote_audio_file_name


    def _find_redacted_word_timestamps(self, original_transcript, redacted_transcript):
        """Finds timestamps of redacted words by comparing transcripts.

        This method aligns the original transcript (with word-level timestamps)
        and the redacted transcript (where sensitive words are replaced with
        infoTypes like '[PERSON_NAME]'). It identifies the start and end times
        of the original words that were redacted.

        Args:
            original_transcript: The original STT response with word-level timestamps.
            redacted_transcript: The transcript after being processed by DLP.

        Returns:
            A list of tuples, where each tuple contains the start and end time
            (in seconds) of a redacted audio segment.
        """
        redacted_timestamps = []
        original_words = []
        for result in original_transcript["results"]:
            if "words" not in result["alternatives"][0]:
                raise ValueError(
                    "The 'words' key with word-level timestamps is missing" 
                    "from the original transcript. "
                    "Please ensure that 'enable_word_time_offsets' was set" 
                    "to True during transcription."
                )

            for word_info in result["alternatives"][0]["words"]:
                original_words.append(word_info)

        redacted_transcript_full_string = " ".join([
            result["alternatives"][0]["transcript"] for result in redacted_transcript["results"]
        ])
        redacted_words = redacted_transcript_full_string.split()

        i, j = 0, 0
        while i < len(original_words) and j < len(redacted_words):
            if original_words[i]["word"] == redacted_words[j]:
                i += 1
                j += 1
            else:
                # This assumes that a redacted word is replaced by its info type
                # and might be split into multiple "words" in the redacted transcript.
                # We find the original word that was redacted and get its timestamp.
                start_time = float(original_words[i]["startOffset"][:-1])
                end_time = float(original_words[i]["endOffset"][:-1])
                redacted_timestamps.append((start_time, end_time))

                # Heuristic to advance the redacted_words index. This may need
                # adjustment based on how DLP redacts different info types.
                if '[' in redacted_words[j] and ']' in redacted_words[j]:
                    j += 1
                else: # If the redaction is a single word with no brackets
                    j += 1
                i += 1

        return redacted_timestamps

    def _replace_audio_segments(self, input_audio_path, redacted_timestamps, output_audio_path):
        """Replaces specified segments of an audio file with silence.

        Args:
            input_audio_path: Path to the input audio file.
            redacted_timestamps: A list of (start_time, end_time) tuples for the
                segments to be replaced.
            output_audio_path: Path to save the modified audio file.
        """
        audio = AudioSegment.from_file(input_audio_path)

        for start_time, end_time in redacted_timestamps:
            start_ms = int(start_time * 1000)
            end_ms = int(end_time * 1000)
            duration_ms = end_ms - start_ms

            silence = AudioSegment.silent(duration=duration_ms)
            audio = audio[:start_ms] + silence + audio[end_ms:]

        audio.export(output_audio_path, format="wav")

    def process(
        self,
        raw_transcript: dict,
        local_audio_file_path: str,
        redacted_audio_file_path: str,
        inspect_template: Optional[str] = None,
        deidentify_template: Optional[str] = None,
    )->str:
        """Executes the end-to-end audio redaction process.

        This method coordinates the entire workflow:
        1. Converts the raw transcript to a DLP-compatible format.
        2. Calls the DLP API to de-identify the transcript.
        3. Downloads the original audio from GCS.
        4. Identifies the timestamps of the redacted words.
        5. Replaces the identified audio segments with silence.
        6. Saves the redacted audio to a local file.

        Args:
            raw_transcript: The original speech-to-text response dictionary.
            local_audio_file_path: The local path to save the original downloaded audio.
            redacted_audio_file_path: The local path to save the final redacted audio.
            inspect_template: The full resource name of the DLP inspect template.
            deidentify_template: The full resource name of the DLP de-identify template.

        Returns:
            The path to the locally saved, redacted audio file.
        """
        ## Initiatilize formaters
        format_dlp = ft.Dlp()
        format_insights = ft.Insights()

        ## Converts transcript to table compatible format
        transcript_table = format_dlp.from_recognize_response(data_input=raw_transcript)

        ## Setups and does redaction
        dlp = sensitive_data_protection.DLP(
            project_id=self.project_id,
            location=self.location
        )
        redacted_table = dlp.redact(
            data=transcript_table,
            inspect_template=inspect_template,
            deidentify_template=deidentify_template
        )

        ## Formats from DLP table to insights format
        redacted_transcript = format_insights.from_dlp_recognize_response(
            dlp_item = redacted_table,
            original_conversation=raw_transcript
        )

        ## Setup bucket and downlaods the audio file localy
        bucket = storage.Gcs(
            bucket_name=self.remote_audio_file_bucket,
            project_id=self.project_id
        )

        audio_bytes = bucket.download_blob(
            file_name=self.remote_audio_file_name,
            content_type=storage.ContentType.WAV
        )

        Utils().save_audio_locally(
            byte_string_data = audio_bytes,
            output_file_name=local_audio_file_path
        )

        ## Find the redaction portions
        redacted_bits = self._find_redacted_word_timestamps(
            original_transcript=raw_transcript,
            redacted_transcript=redacted_transcript
        )

        ## Redacts the audio and saves locally
        self._replace_audio_segments(
            input_audio_path=local_audio_file_path,
            redacted_timestamps=redacted_bits,
            output_audio_path=redacted_audio_file_path
        )

        return redacted_audio_file_path
