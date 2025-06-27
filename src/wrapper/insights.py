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

"""A class for all Insigths things related"""

import enum
from random import randint
from typing import Dict, MutableMapping, Optional
from google.longrunning.operations_pb2 import Operations
from google.protobuf import duration_pb2
from google.api_core import exceptions
from google.cloud import contact_center_insights_v1
from google.cloud.contact_center_insights_v1 import types
from src.core import base

class Masks(enum.StrEnum):
    """Enum for supported masks."""
    ANALYSIS = "analysisConfig"
    TTL = "conversationTtl"
    PUBSUB = "pubsubNotificationSettings"
    LANGUAGE = "languageCode"
    SPEECH_RECOGNIZER = "speechConfig.speechRecognizer"
    DLP = "redactionConfig.inspectTemplate,redactionConfig.deidentifyTemplate"

class Annotators(enum.StrEnum):
    """Enum for supported annotators"""
    QAI = "QAI"
    INSIGHTS = "INSIGHTS"
    TOPIC_MODEL = "TOPIC MODEL"
    SUMMARIZATION = "SUMMARIZATION"

class Mediums(enum.Enum):
    """Enum for supported mediums"""
    PHONE_CALL = contact_center_insights_v1.Conversation.Medium.PHONE_CALL,
    CHAT = contact_center_insights_v1.Conversation.Medium.CHAT


class Settings:
    """A way to visualize and configure the settings"""

    def __init__(
        self,
        project_id: str,
        parent: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ):
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.parent = parent
        self.project_id = project_id
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            client_options=self.config.set_insights_endpoint()
        )

    def _send_update_settings(self, request):
        try:
            result = self.client.update_settings(request=request)
            return result
        except NotImplementedError:
            raise NotImplementedError from NotImplementedError

    def _set_annotators(
        self,
        annotators: list[Annotators],
    ) -> contact_center_insights_v1.AnnotatorSelector:
        selected_annotators = contact_center_insights_v1.AnnotatorSelector(
            run_interruption_annotator=False,
            run_silence_annotator=False,
            run_phrase_matcher_annotator=False,
            run_sentiment_annotator=False,
            run_entity_annotator=False,
            run_intent_annotator=False,
            run_issue_model_annotator=False,
            run_summarization_annotator=False,
        )

        for annotator in annotators:
            if annotator == Annotators.SUMMARIZATION:
                selected_annotators.run_summarization_annotator = True
            if annotator == Annotators.TOPIC_MODEL:
                selected_annotators.run_issue_model_annotator = True
            if annotator == Annotators.INSIGHTS:
                selected_annotators.run_intent_annotator = True
                selected_annotators.run_entity_annotator = True
                selected_annotators.run_sentiment_annotator = True
                selected_annotators.run_phrase_matcher_annotator = True
                selected_annotators.run_silence_annotator = True
                selected_annotators.run_interruption_annotator = True
            if annotator == Annotators.QAI:
                selected_annotators.run_qai_annotator = True

        return selected_annotators

    def update_global_auto_analysis(
        self,
        runtime_percentage: float,
        upload_percentage: float,
        analysis_annotators: list,
    ):
        """Update the default auto analysis for Insights"""

        request = contact_center_insights_v1.UpdateSettingsRequest(
            settings=contact_center_insights_v1.Settings(
                name=self.parent,
                analysis_config=contact_center_insights_v1.Settings.AnalysisConfig(
                    runtime_integration_analysis_percentage=runtime_percentage,
                    upload_conversation_analysis_percentage=upload_percentage,
                    annotator_selector=self._set_annotators(analysis_annotators),
                ),
            ),
            update_mask=Masks.ANALYSIS.value,
        )
        return self._send_update_settings(request)

    def update_ttl(
        self,
        ttl_in_days: int,
    ) -> types.resources.Settings:
        """Update the conversation TTL"""
        request = contact_center_insights_v1.UpdateSettingsRequest(
            settings=contact_center_insights_v1.Settings(
                name=self.parent,
                conversation_ttl=duration_pb2.Duration(
                    seconds=ttl_in_days * base.SECONDS_IN_A_YEAR
                ),
            ),
            update_mask=Masks.TTL.value,
        )
        return self._send_update_settings(request)

    def update_pubsub(self, pub_sub_map: Dict[str, str]) -> types.resources.Settings:
        """Update the Pub/Sub configuration"""

        request = contact_center_insights_v1.UpdateSettingsRequest(
            settings=contact_center_insights_v1.Settings(
                name=self.parent, pubsub_notification_settings=pub_sub_map
            ),
            update_mask=Masks.PUBSUB.value,
        )
        return self._send_update_settings(request)

    def update_global_language(self, language_code: str) -> types.resources.Settings:
        """Change the default language in the settings"""

        request = contact_center_insights_v1.UpdateSettingsRequest(
            settings=contact_center_insights_v1.Settings(
                name=self.parent, language_code=language_code
            ),
            update_mask=Masks.LANGUAGE.value,
        )
        return self._send_update_settings(request)

    def update_global_speech(
        self, speech_recognizer_path: str
    ) -> types.resources.Settings:
        """Change the default speech configuration in the settings"""

        request = contact_center_insights_v1.UpdateSettingsRequest(
            update_mask=Masks.SPEECH_RECOGNIZER.value,
            settings=contact_center_insights_v1.Settings(
                name=self.parent,
                speech_config=contact_center_insights_v1.SpeechConfig(
                    speech_recognizer=speech_recognizer_path
                ),
            ),
        )
        return self._send_update_settings(request)

    def update_global_dlp(
        self, inspect_template: str, deidentify_template: str
    ) -> types.resources.Settings:
        """Change the default DLP configuration in the settings"""

        request = contact_center_insights_v1.UpdateSettingsRequest(
            settings=contact_center_insights_v1.Settings(
                name=self.parent,
                redaction_config=contact_center_insights_v1.RedactionConfig(
                    inspect_template=inspect_template,
                    deidentify_template=deidentify_template,
                ),
            ),
            update_mask=Masks.DLP.value,
        )
        return self._send_update_settings(request)

    def get(self) -> types.resources.Settings:
        """Get the current settings configurations on Conversational Insights"""
        result = self.client.get_settings(
            request=contact_center_insights_v1.GetSettingsRequest(name=self.parent)
        )
        return result


class Ingestion:
    """To Ingest formated files or audios to insights"""

    def __init__(
        self,
        parent: str,
        audio_path: Optional[str] = None,
        transcript_path: Optional[str] = None,
        dlp_redact_template: Optional[str] = None,
        dlp_deidentify_template: Optional[str] = None,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        self.auth = auth or base.Auth()
        self.config = config or base.Config()
        self.parent = parent
        self.audio_path = audio_path
        self.transcript_path = transcript_path
        self.dlp_redact_template = dlp_redact_template
        self.dlp_deidentify_template = dlp_deidentify_template
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            client_options=self.config.set_insights_endpoint()
        )

    def _generate_conversation_id(self) -> str:
        random_id = randint(10000000000000000, 999999999999999999)
        return str(random_id)

    def _set_upload_conversation_request(
        self,
        conversation_id: str,
        conversation: contact_center_insights_v1.Conversation,
    ) -> contact_center_insights_v1.UpdateConversationRequest:
        """Create the request for Upload Conversation"""
        if not conversation_id or conversation_id == "None":
            conversation_id = self._generate_conversation_id()

        req = contact_center_insights_v1.UploadConversationRequest(
            parent=self.parent,
            conversation_id=conversation_id,
            conversation=conversation,
        )

        if self.dlp_redact_template:
            req.redaction_config.inspect_template = self.dlp_redact_template

        if self.dlp_deidentify_template:
            req.redaction_config.deidentify_template = self.dlp_deidentify_template
        return req

    def _set_conversation(
        self,
        language_code: str = "en-US",
        medium: Mediums = Mediums.PHONE_CALL,
        audio_uri: Optional[str] = None,
        transcript_uri: Optional[str] = None,
        agent: Optional[Dict[str, str]] = None,
        labels: Optional[MutableMapping[str, str]] = None,
        start_time: Optional[int] = None,
        customer_satisfaction: Optional[int] = None,
    ) -> contact_center_insights_v1.Conversation:
        convo = contact_center_insights_v1.Conversation(
            start_time=start_time,
            medium=medium.value[0],
            language_code=language_code,
            quality_metadata=contact_center_insights_v1.Conversation.QualityMetadata(
                agent_info=[]
            ),
            data_source=contact_center_insights_v1.ConversationDataSource(
                gcs_source=contact_center_insights_v1.GcsSource(
                    audio_uri=audio_uri,
                    transcript_uri=transcript_uri,
                )
            ),
        )

        if agent:
            agent_info = contact_center_insights_v1.Conversation.QualityMetadata.AgentInfo()
            if "name" in agent:
                agent_info.display_name = agent["name"]

            if "id" in agent:
                agent_info.agent_id = agent["id"]
                convo.agent_id = agent["id"]

            if "team" in agent:
                agent_info.team = agent["team"]

            convo.quality_metadata.agent_info.append(agent_info)

        if labels:
            convo.labels = labels

        if customer_satisfaction:
            convo.quality_metadata.customer_satisfaction_rating = customer_satisfaction

        return convo

    def _set_ingest_conversations_request(
        self, metadata: Optional[str] = None, medium: Mediums = Mediums.PHONE_CALL
    ) -> contact_center_insights_v1.IngestConversationsRequest:
        """Create the request for Ingest Conversations"""
        req = contact_center_insights_v1.IngestConversationsRequest(
            parent=self.parent,
            gcs_source=contact_center_insights_v1.IngestConversationsRequest.GcsSource(
                bucket_uri=self.transcript_path,
                # bucket_object_typ=contact_center_insights_v1.IngestConversationsRe
                # quest.GcsSource.BucketObjectType.TRANSCRIPT
            ),
            transcript_object_config=types.IngestConversationsRequest.TranscriptObjectConfig(
                medium=medium.value[0]
            ),
        )

        if metadata:
            req.gcs_source.metadata_bucket_uri = metadata

        if self.dlp_redact_template:
            req.redaction_config.inspect_template = self.dlp_redact_template

        if self.dlp_deidentify_template:
            req.redaction_config.deidentify_template = self.dlp_deidentify_template

        return req

    def single(
        self,
        language_code: str = "en-US",
        medium: Optional[Mediums] = Mediums.PHONE_CALL,
        conversation_id: Optional[str] = None,
        agent: Optional[Dict[str, str]] = None,
        labels: Optional[MutableMapping[str, str]] = None,
        customer_satisfaction: Optional[int] = None,
    ) -> Operations:
        """Ingesting a single conversation with metadata"""

        convo = self._set_conversation(
            audio_uri=self.audio_path,
            transcript_uri=self.transcript_path,
            language_code=language_code,
            medium=medium,
            agent=agent,
            labels=labels,
            customer_satisfaction=customer_satisfaction,
        )
        result: Operations = self.client.upload_conversation(
            request=self._set_upload_conversation_request(
                conversation_id=str(conversation_id), conversation=convo
            )
        )
        return result

    def bulk(
        self, metadata_path: Optional[str] = None, medium: Mediums = Mediums.PHONE_CALL
    ) -> Operations:
        """Ingestion many conversations with metadata"""
        result: Operations = self.client.ingest_conversations(
            request=self._set_ingest_conversations_request(
                metadata=metadata_path, medium=medium
            )
        )
        return result


class Analysis:
    """Create analysis for one or many conversations"""

    def __init__(
        self,
        parent: Optional[str],
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.parent = parent
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            client_options=self.config.set_insights_endpoint()
        )

    def _set_annotators(
        self,
        annotators: list[Annotators],
    ) -> contact_center_insights_v1.AnnotatorSelector:

        selected_annotators = contact_center_insights_v1.AnnotatorSelector(
            run_interruption_annotator=False,
            run_silence_annotator=False,
            run_phrase_matcher_annotator=False,
            run_sentiment_annotator=False,
            run_entity_annotator=False,
            run_intent_annotator=False,
            run_issue_model_annotator=False,
            run_summarization_annotator=False,
        )

        for annotator in annotators:
            if annotator == Annotators.SUMMARIZATION:
                selected_annotators.run_summarization_annotator = True
            if annotator == Annotators.TOPIC_MODEL:
                selected_annotators.run_issue_model_annotator = True
            if annotator == Annotators.INSIGHTS:
                selected_annotators.run_intent_annotator = True
                selected_annotators.run_entity_annotator = True
                selected_annotators.run_sentiment_annotator = True
                selected_annotators.run_phrase_matcher_annotator = True
                selected_annotators.run_silence_annotator = True
                selected_annotators.run_interruption_annotator = True
            if annotator == Annotators.INSIGHTS:
                raise ValueError("QAI annotator is not available")
        return selected_annotators

    def single(
        self,
        annotators: list,
    ):
        """Create analysis for a single conversation"""
        result = self.client.create_analysis(
            request=contact_center_insights_v1.CreateAnalysisRequest(
                parent=self.parent,
                analysis=contact_center_insights_v1.Analysis(
                    name=self.parent,
                    annotator_selector=self._set_annotators(annotators),
                ),
            )
        )
        return result

    def bulk(
        self,
        annotators: list,
        analysis_percentage: float,
        analysis_filter: str,
    ):
        """Create analysis for many conversations"""
        result = self.client.bulk_analyze_conversations(
            request=contact_center_insights_v1.BulkAnalyzeConversationsRequest(
                parent=self.parent,
                filter=analysis_filter,
                analysis_percentage=analysis_percentage,
                annotator_selector=self._set_annotators(annotators),
            )
        )
        return result


class Export:
    """Class for all native export actions from Insights"""

    def __init__(
        self,
        parent: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.parent = parent
        self.client = contact_center_insights_v1.ContactCenterInsightsClient(
            client_options=self.config.set_insights_endpoint()
        )

    def to_bq(
        self,
        project_id: str,
        dataset: str,
        table: str,
        insights_filter: Optional[str] = None,
    ):
        """Export data from Conversational Insights to BQ"""
        result = self.client.export_insights_data(
            request=contact_center_insights_v1.ExportInsightsDataRequest(
                parent=self.parent,
                filter=insights_filter,
                big_query_destination=types.ExportInsightsDataRequest.BigQueryDestination(
                    project_id=project_id, dataset=dataset, table=table
                ),
            )
        )
        return result
