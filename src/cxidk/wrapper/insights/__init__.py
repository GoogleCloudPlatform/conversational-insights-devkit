"""Wrapper package for Contact Center AI (CCAI) Insights API interactions."""

from random import randint

from google.cloud import contact_center_insights_v1
from google.protobuf.timestamp_pb2 import (  # type: ignore  # pylint: disable=E0611
    Timestamp,
)

from cxidk.core import base
from cxidk.wrapper.insights._enums import AgentType
from cxidk.wrapper.insights._enums import Annotators
from cxidk.wrapper.insights._enums import Masks
from cxidk.wrapper.insights._enums import Mediums
from cxidk.wrapper.insights.config_resources import AnalysisRules
from cxidk.wrapper.insights.config_resources import AssessmentRules
from cxidk.wrapper.insights.config_resources import AutoLabelingRules
from cxidk.wrapper.insights.config_resources import ConfigCollection
from cxidk.wrapper.insights.config_resources import IssueModelIssues
from cxidk.wrapper.insights.config_resources import IssueModels
from cxidk.wrapper.insights.config_resources import LegacyScorecards
from cxidk.wrapper.insights.config_resources import PhraseMatchers
from cxidk.wrapper.insights.config_resources import QaQuestionTags
from cxidk.wrapper.insights.config_resources import QaScorecards
from cxidk.wrapper.insights.config_resources import RevisionQuestions
from cxidk.wrapper.insights.config_resources import ScorecardQuestions
from cxidk.wrapper.insights.config_resources import ScorecardRevisions
from cxidk.wrapper.insights.conversations import Analyses
from cxidk.wrapper.insights.conversations import Conversations
from cxidk.wrapper.insights.conversations import Stats
from cxidk.wrapper.insights.operations import Analysis
from cxidk.wrapper.insights.operations import Export
from cxidk.wrapper.insights.operations import Ingestion
from cxidk.wrapper.insights.operations import LongRunningOperation
from cxidk.wrapper.insights.operations import Settings
from cxidk.wrapper.insights.scorecards import AnswerChoice
from cxidk.wrapper.insights.scorecards import QuestionInfo
from cxidk.wrapper.insights.scorecards import RevisionInfo
from cxidk.wrapper.insights.scorecards import ScorecardDefinition
from cxidk.wrapper.insights.scorecards import ScorecardInfo
from cxidk.wrapper.insights.scorecards import ScorecardSummary
from cxidk.wrapper.insights.scorecards import Scorecards
from cxidk.wrapper.insights.views import AuthorizedViews
from cxidk.wrapper.insights.views import CorrelationConfig

__all__ = [
    "AgentType",
    "Analyses",
    "Analysis",
    "AnalysisRules",
    "Annotators",
    "AnswerChoice",
    "AssessmentRules",
    "AuthorizedViews",
    "AutoLabelingRules",
    "ConfigCollection",
    "Conversations",
    "CorrelationConfig",
    "Export",
    "Ingestion",
    "IssueModelIssues",
    "IssueModels",
    "LegacyScorecards",
    "LongRunningOperation",
    "Masks",
    "Mediums",
    "PhraseMatchers",
    "QaQuestionTags",
    "QaScorecards",
    "QuestionInfo",
    "RevisionInfo",
    "RevisionQuestions",
    "ScorecardDefinition",
    "ScorecardInfo",
    "ScorecardQuestions",
    "ScorecardRevisions",
    "ScorecardSummary",
    "Scorecards",
    "Settings",
    "Stats",
    "Timestamp",
    "base",
    "contact_center_insights_v1",
    "randint",
]
