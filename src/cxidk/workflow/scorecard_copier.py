# Copyright 2026 Google LLC
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

"""Workflow for copying QA Scorecards between GCP environments."""

import logging
from typing import Optional, List, Dict, Any
from google.cloud.contact_center_insights_v1 import types
from cxidk.core import base
from cxidk.wrapper import insights


class Copier:
    """Copies QA Scorecard metadata between Google Cloud projects and locations.

    This class automates retrieving a source QA Scorecard and all its associated
    QA Questions, preparing clean payloads by stripping immutable system properties,
    and sequentially recreating them in a destination project and location.

    Attributes:
        source_project_id: The source GCP project ID.
        source_location: The source GCP location.
        dest_project_id: The destination GCP project ID.
        dest_location: The destination GCP location.
        auth: Pre-configured or default authentication object.
        config: Pre-configured or default configuration object.
    """

    def __init__(
        self,
        source_project_id: str,
        source_location: str,
        dest_project_id: str,
        dest_location: str,
        auth: Optional[base.Auth] = None,
        config: Optional[base.Config] = None,
    ) -> None:
        """Initializes the Copier workflow client.

        Args:
            source_project_id: The source GCP project ID.
            source_location: The source GCP location.
            dest_project_id: The destination GCP project ID.
            dest_location: The destination GCP location.
            auth: Optional pre-configured authentication object.
            config: Optional pre-configured configuration object.
        """
        self.source_project_id = source_project_id
        self.source_location = source_location
        self.dest_project_id = dest_project_id
        self.dest_location = dest_location
        self.auth = auth or base.Auth()
        self.config = config or base.Config()

        self.source_scorecards_wrapper = insights.Scorecards(
            project_id=self.source_project_id,
            location=self.source_location,
            auth=self.auth,
            config=self.config,
        )
        self.dest_scorecards_wrapper = insights.Scorecards(
            project_id=self.dest_project_id,
            location=self.dest_location,
            auth=self.auth,
            config=self.config,
        )

    def copy_scorecard(
        self,
        scorecard_id: str,
        new_display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Copies a full QA Scorecard and its questions to the destination environment.

        Args:
            scorecard_id: The source scorecard ID to copy.
            new_display_name: Optional new display name for the copied scorecard.
                If not provided, keeps the original source display name.

        Returns:
            A dictionary containing the new destination scorecard ID and summary metrics.
        """
        logging.info(
            "Fetching source scorecard '%s' from %s/%s",
            scorecard_id,
            self.source_project_id,
            self.source_location,
        )
        source_scorecard = self.source_scorecards_wrapper.get_scorecard(
            scorecard_id=scorecard_id
        )

        # Prepare clean scorecard payload
        clean_scorecard = types.QaScorecard(
            display_name=new_display_name or source_scorecard.display_name,
            description=source_scorecard.description,
        )

        logging.info("Creating destination scorecard...")
        dest_scorecard = self.dest_scorecards_wrapper.create_scorecard(
            qa_scorecard=clean_scorecard
        )
        dest_scorecard_id = dest_scorecard.name.split("/")[-1]
        logging.info("Successfully created destination scorecard '%s'", dest_scorecard_id)

        # Fetch source questions
        source_questions_wrapper = insights.ScorecardQuestions(
            project_id=self.source_project_id,
            location=self.source_location,
            scorecard_id=scorecard_id,
            auth=self.auth,
            config=self.config,
        )
        dest_questions_wrapper = insights.ScorecardQuestions(
            project_id=self.dest_project_id,
            location=self.dest_location,
            scorecard_id=dest_scorecard_id,
            auth=self.auth,
            config=self.config,
        )

        logging.info("Listing source questions for scorecard '%s'...", scorecard_id)
        source_questions_pager = source_questions_wrapper.list_questions()

        copied_questions_count = 0
        for q in source_questions_pager:
            clean_question = types.QaQuestion(
                display_name=q.display_name,
                question_body=q.question_body,
                answer_choice_config=q.answer_choice_config,
                tags=q.tags,
                order=q.order,
            )
            dest_questions_wrapper.create_question(qa_question=clean_question)
            copied_questions_count += 1

        logging.info(
            "Successfully copied %d questions to destination scorecard '%s'",
            copied_questions_count,
            dest_scorecard_id,
        )

        return {
            "dest_scorecard_id": dest_scorecard_id,
            "copied_questions_count": copied_questions_count,
        }
