"""Testing redact audio files"""


# from cxidk.wrapper import storage
from cxidk.wrapper import speech
from cxidk.wrapper import storage
from cxidk.workflow import format as ft
from cxidk.wrapper import sensitive_data_protection
from cxidk.workflow import audio


_TRANSCRIPT_BUCKET = "sample-audio-pipeline"
_AUDIO_LOCATION = "251126015938371258.wav"
_RECOGNIZER = "insights-default-recognizer"
_PROJECT_ID = "insights-pipeline-producer"
_LOCATION = "global"

_RECOGNIZER_PATH = f"projects/{_PROJECT_ID}/locations/{_LOCATION}/recognizers/{_RECOGNIZER}"


utils = audio.Utils()
### Transcribe the conversation

sp = speech.V2(
    project_id=_PROJECT_ID,
    location=_LOCATION
)

# transcription = sp.create_transcription(
#     audio_file_path=f"gs://{_TRANSCRIPT_BUCKET}/{_AUDIO_LOCATION}",
#     recognizer_path=_RECOGNIZER_PATH
# )

## Downlaod the transcript

# _TRANSCRIPT = "tmp/251126015938371258_transcript_9366f98b-0000-2f1e-b17a-582429c4e100.json"
raw_transcript = {"results":[{"alternatives":[{"transcript":"hi Alex my internet has been out for the last hour I've tried rebooting the modem but nothing seems to work","confidence":0.9848919,"words":[{"startOffset":"5.400s","endOffset":"5.700s","word":"hi"},{"startOffset":"5.700s","endOffset":"6.100s","word":"Alex"},{"startOffset":"6.100s","endOffset":"6.700s","word":"my"},{"startOffset":"6.700s","endOffset":"6.800s","word":"internet"},{"startOffset":"6.800s","endOffset":"7s","word":"has"},{"startOffset":"7s","endOffset":"7s","word":"been"},{"startOffset":"7s","endOffset":"7.200s","word":"out"},{"startOffset":"7.200s","endOffset":"7.400s","word":"for"},{"startOffset":"7.400s","endOffset":"7.600s","word":"the"},{"startOffset":"7.600s","endOffset":"7.600s","word":"last"},{"startOffset":"7.600s","endOffset":"7.900s","word":"hour"},{"startOffset":"7.900s","endOffset":"8.600s","word":"I've"},{"startOffset":"8.600s","endOffset":"8.800s","word":"tried"},{"startOffset":"8.800s","endOffset":"9.100s","word":"rebooting"},{"startOffset":"9.100s","endOffset":"9.400s","word":"the"},{"startOffset":"9.400s","endOffset":"9.700s","word":"modem"},{"startOffset":"9.700s","endOffset":"9.800s","word":"but"},{"startOffset":"9.800s","endOffset":"10s","word":"nothing"},{"startOffset":"10s","endOffset":"10.400s","word":"seems"},{"startOffset":"10.400s","endOffset":"10.400s","word":"to"},{"startOffset":"10.400s","endOffset":"10.700s","word":"work"}]}],"resultEndOffset":"11.450s","languageCode":"en-us"},{"alternatives":[{"transcript":" it's David chin","confidence":0.8878378,"words":[{"startOffset":"19.300s","endOffset":"19.600s","word":"it's"},{"startOffset":"19.600s","endOffset":"19.900s","word":"David"},{"startOffset":"19.900s","endOffset":"20.200s","word":"chin"}]}],"resultEndOffset":"20.870s","languageCode":"en-us"},{"alternatives":[{"transcript":" sure the power light is solid green but the online light is blinking Amber","confidence":0.9808544,"words":[{"startOffset":"29.200s","endOffset":"29.500s","word":"sure"},{"startOffset":"29.500s","endOffset":"30.200s","word":"the"},{"startOffset":"30.200s","endOffset":"30.600s","word":"power"},{"startOffset":"30.600s","endOffset":"30.900s","word":"light"},{"startOffset":"30.900s","endOffset":"31s","word":"is"},{"startOffset":"31s","endOffset":"31.500s","word":"solid"},{"startOffset":"31.500s","endOffset":"31.800s","word":"green"},{"startOffset":"31.800s","endOffset":"32.100s","word":"but"},{"startOffset":"32.100s","endOffset":"32.200s","word":"the"},{"startOffset":"32.200s","endOffset":"32.700s","word":"online"},{"startOffset":"32.700s","endOffset":"33.200s","word":"light"},{"startOffset":"33.200s","endOffset":"33.300s","word":"is"},{"startOffset":"33.300s","endOffset":"33.700s","word":"blinking"},{"startOffset":"33.700s","endOffset":"34.300s","word":"Amber"}]}],"resultEndOffset":"34.930s","languageCode":"en-us"},{"alternatives":[{"transcript":" okay I'll wait","confidence":0.8432646,"words":[{"startOffset":"45.600s","endOffset":"45.900s","word":"okay"},{"startOffset":"45.900s","endOffset":"46.600s","word":"I'll"},{"startOffset":"46.600s","endOffset":"46.700s","word":"wait"}]}],"resultEndOffset":"47.430s","languageCode":"en-us"},{"alternatives":[{"transcript":" okay let me check yeah they're both feel snug I gave them a little twist to be sure","confidence":0.8811402,"words":[{"startOffset":"64.900s","endOffset":"65.200s","word":"okay"},{"startOffset":"65.200s","endOffset":"66.300s","word":"let"},{"startOffset":"66.300s","endOffset":"66.400s","word":"me"},{"startOffset":"66.400s","endOffset":"66.400s","word":"check"},{"startOffset":"66.400s","endOffset":"67.200s","word":"yeah"},{"startOffset":"67.200s","endOffset":"67.900s","word":"they're"},{"startOffset":"67.900s","endOffset":"67.900s","word":"both"},{"startOffset":"67.900s","endOffset":"68.100s","word":"feel"},{"startOffset":"68.100s","endOffset":"68.600s","word":"snug"},{"startOffset":"68.600s","endOffset":"69.400s","word":"I"},{"startOffset":"69.400s","endOffset":"69.500s","word":"gave"},{"startOffset":"69.500s","endOffset":"69.600s","word":"them"},{"startOffset":"69.600s","endOffset":"69.700s","word":"a"},{"startOffset":"69.700s","endOffset":"69.700s","word":"little"},{"startOffset":"69.700s","endOffset":"70.100s","word":"twist"},{"startOffset":"70.100s","endOffset":"70.500s","word":"to"},{"startOffset":"70.500s","endOffset":"70.600s","word":"be"},{"startOffset":"70.600s","endOffset":"70.800s","word":"sure"}]}],"resultEndOffset":"71.520s","languageCode":"en-us"},{"alternatives":[{"transcript":"yes that's fine","confidence":0.98695165,"words":[{"startOffset":"87.400s","endOffset":"87.900s","word":"yes"},{"startOffset":"87.900s","endOffset":"88.400s","word":"that's"},{"startOffset":"88.400s","endOffset":"88.700s","word":"fine"}]}],"resultEndOffset":"89.380s","languageCode":"en-us"},{"alternatives":[{"transcript":" go ahead","confidence":0.9688417,"words":[{"startOffset":"89.600s","endOffset":"89.700s","word":"go"},{"startOffset":"89.700s","endOffset":"89.900s","word":"ahead"}]}],"resultEndOffset":"90.680s","languageCode":"en-us"},{"alternatives":[{"transcript":" okay the lights are all flashing now","confidence":0.95273894,"words":[{"startOffset":"95.400s","endOffset":"95.500s","word":"okay"},{"startOffset":"95.500s","endOffset":"95.600s","word":"the"},{"startOffset":"95.600s","endOffset":"95.900s","word":"lights"},{"startOffset":"95.900s","endOffset":"96s","word":"are"},{"startOffset":"96s","endOffset":"96.200s","word":"all"},{"startOffset":"96.200s","endOffset":"96.700s","word":"flashing"},{"startOffset":"96.700s","endOffset":"96.800s","word":"now"}]}],"resultEndOffset":"97.490s","languageCode":"en-us"},{"alternatives":[{"transcript":" I guess it's restarting","confidence":0.96548355,"words":[{"startOffset":"97.500s","endOffset":"97.800s","word":"I"},{"startOffset":"97.800s","endOffset":"97.800s","word":"guess"},{"startOffset":"97.800s","endOffset":"98s","word":"it's"},{"startOffset":"98s","endOffset":"98.600s","word":"restarting"}]}],"resultEndOffset":"99.270s","languageCode":"en-us"},{"alternatives":[{"transcript":" hey you're right the online light is solid green now let me try loading a web page yes it's working that's great","confidence":0.971209,"words":[{"startOffset":"111.500s","endOffset":"112s","word":"hey"},{"startOffset":"112s","endOffset":"112.300s","word":"you're"},{"startOffset":"112.300s","endOffset":"112.600s","word":"right"},{"startOffset":"112.600s","endOffset":"113.200s","word":"the"},{"startOffset":"113.200s","endOffset":"113.500s","word":"online"},{"startOffset":"113.500s","endOffset":"113.800s","word":"light"},{"startOffset":"113.800s","endOffset":"113.900s","word":"is"},{"startOffset":"113.900s","endOffset":"114.200s","word":"solid"},{"startOffset":"114.200s","endOffset":"114.500s","word":"green"},{"startOffset":"114.500s","endOffset":"114.700s","word":"now"},{"startOffset":"114.700s","endOffset":"115.300s","word":"let"},{"startOffset":"115.300s","endOffset":"115.300s","word":"me"},{"startOffset":"115.300s","endOffset":"115.500s","word":"try"},{"startOffset":"115.500s","endOffset":"115.900s","word":"loading"},{"startOffset":"115.900s","endOffset":"116.100s","word":"a"},{"startOffset":"116.100s","endOffset":"116.300s","word":"web"},{"startOffset":"116.300s","endOffset":"116.400s","word":"page"},{"startOffset":"116.400s","endOffset":"116.900s","word":"yes"},{"startOffset":"116.900s","endOffset":"117.200s","word":"it's"},{"startOffset":"117.200s","endOffset":"117.500s","word":"working"},{"startOffset":"117.500s","endOffset":"118s","word":"that's"},{"startOffset":"118s","endOffset":"118.200s","word":"great"}]}],"resultEndOffset":"118.910s","languageCode":"en-us"},{"alternatives":[{"transcript":" no that's it thank you so much for your help Alex you fixed it really quickly","confidence":0.9903032,"words":[{"startOffset":"124.600s","endOffset":"124.800s","word":"no"},{"startOffset":"124.800s","endOffset":"125.100s","word":"that's"},{"startOffset":"125.100s","endOffset":"125.200s","word":"it"},{"startOffset":"125.200s","endOffset":"125.500s","word":"thank"},{"startOffset":"125.500s","endOffset":"125.600s","word":"you"},{"startOffset":"125.600s","endOffset":"125.700s","word":"so"},{"startOffset":"125.700s","endOffset":"125.900s","word":"much"},{"startOffset":"125.900s","endOffset":"126s","word":"for"},{"startOffset":"126s","endOffset":"126.200s","word":"your"},{"startOffset":"126.200s","endOffset":"126.400s","word":"help"},{"startOffset":"126.400s","endOffset":"126.800s","word":"Alex"},{"startOffset":"126.800s","endOffset":"127s","word":"you"},{"startOffset":"127s","endOffset":"127.200s","word":"fixed"},{"startOffset":"127.200s","endOffset":"127.400s","word":"it"},{"startOffset":"127.400s","endOffset":"127.500s","word":"really"},{"startOffset":"127.500s","endOffset":"127.800s","word":"quickly"}]}],"resultEndOffset":"128.540s","languageCode":"en-us"}]}





format_dlp = ft.Dlp()
format_insights = ft.Insights()
### Format the conversation
table_transcript = format_dlp.from_recognize_response(data_input=raw_transcript)
print("--------------"*8)
print("Transcript formated")

### Redact the conversation
dlp = sensitive_data_protection.DLP(
    project_id=_PROJECT_ID,
    location=_LOCATION
)
redacted_table = dlp.redact(
    data=table_transcript,
    inspect_template="projects/insights-pipeline-producer/locations/global/inspectTemplates/default_insights_template",
    deidentify_template="projects/insights-pipeline-producer/locations/global/deidentifyTemplates/default_deidentify_template"
)
print("--------------"*8)
print("Transcript redacted")

### Format the conversation

conversation_object = format_insights.from_dlp_recognize_response(
    dlp_item = redacted_table,
    original_conversation=raw_transcript
)
print("--------------"*8)
print("Transcript combined")


### Download audio locally

stg = storage.Gcs(
    bucket_name=_TRANSCRIPT_BUCKET,
    project_id=_PROJECT_ID
)
audio_bytes = stg.download_blob(
    file_name=_AUDIO_LOCATION,
    content_type=storage.ContentType.WAV
)
print("--------------"*8)
print("Audio downloaded")
utils.save_audio_locally(
    byte_string_data = audio_bytes,
    output_file_name="local_file.wav"
)

### Edit the audio
ara = audio.RedactAudio(
    project_id=_PROJECT_ID
)
print("--------------"*8)
print("Audio saved locally")
print(raw_transcript)
print("--------------"*8)
print(conversation_object)
redacted_bits = ara.find_redacted_word_timestamps(
    original_transcript=raw_transcript,
    redacted_transcript=conversation_object
)
print("--------------"*8)
print("Finding redacting bits")
ara.replace_audio_segments(
    input_audio_path="local_file.wav",
    redacted_timestamps=redacted_bits,
    output_audio_path="redacted_local_file.wav"
)
print("--------------"*8)
print("Redacted audio saved locally")
### Save the audio