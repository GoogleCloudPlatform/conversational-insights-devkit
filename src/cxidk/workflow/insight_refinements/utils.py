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

"""
Shared Utilities for QAI Optimization Framework.

This module provides decorators and helpers for API resilience (retries)
and observability (structured logging), following official GCC best practices.
"""

from __future__ import annotations

import time
import random
import logging
import json
from functools import wraps
from typing import Any, Callable, TYPE_CHECKING
from google.api_core.exceptions import (
    ResourceExhausted,
    InternalServerError,
    ServiceUnavailable,
)

if TYPE_CHECKING:
    from google.cloud import bigquery, storage
    from google import genai


logger = logging.getLogger(__name__)

# Quota/Retry Defaults from GCC Example
MAX_RETRIES = 5
RETRY_DELAY = 2.0


def get_bq_client(config, credentials=None) -> bigquery.Client:
    """Centralized BigQuery client factory."""
    # Imported lazily so that importing this module does not require the optional
    # google-cloud-bigquery dependency (see the TYPE_CHECKING block above).
    from google.cloud import bigquery  # pylint: disable=import-outside-toplevel

    project_id = config.bigquery.project_id or config.gcp.project_id
    return bigquery.Client(project=project_id, credentials=credentials)


def get_storage_client(config, credentials=None) -> storage.Client:
    """Centralized Cloud Storage client factory."""
    # Imported lazily so that importing this module does not require the optional
    # google-cloud-storage dependency (see the TYPE_CHECKING block above).
    from google.cloud import storage  # pylint: disable=import-outside-toplevel

    project_id = config.bigquery.project_id or config.gcp.project_id
    return storage.Client(project=project_id, credentials=credentials)


def get_gemini_client(config, credentials=None) -> genai.Client:
    """Centralized Gemini client factory."""
    # Imported lazily so that importing this module does not require the optional
    # google-genai dependency (see the TYPE_CHECKING block above).
    from google import genai  # pylint: disable=import-outside-toplevel

    return genai.Client(
        vertexai=True,
        project=config.gcp.project_id,
        location=config.llm.location_id,
        credentials=credentials,
    )


def handle_api_quota(
    max_retries: int = MAX_RETRIES, initial_delay: float = RETRY_DELAY
) -> Callable:
    """
    Decorator that implements exponential backoff for GCP API rate limits.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Imported lazily so that importing this module does not require the optional
            # google-genai dependency (see the TYPE_CHECKING block above).
            from google.genai.errors import APIError  # pylint: disable=import-outside-toplevel
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (
                    ResourceExhausted,
                    ServiceUnavailable,
                    InternalServerError,
                    APIError
                ) as e:
                    # For Gemini APIError, ensure it's a retriable error (e.g., 429 or 503)
                    if isinstance(e, APIError) and e.code not in [429, 503, 500]:
                        raise e

                    if i == max_retries - 1:
                        logger.error(
                            "API call failed after %s attempts: %s", max_retries, str(e)
                        )
                        raise e

                    # Exponential backoff with jitter exactly as in GCC example
                    exponential_delay = initial_delay * (2**i + random.random())
                    logger.warning(
                        "API returned rate limit/transient error: %s. "
                        "Waiting %.2f seconds and trying again... (Attempt %s/%s)",
                        str(e),
                        exponential_delay,
                        i + 1,
                        max_retries,
                    )
                    time.sleep(exponential_delay)
            # This part should technically never be reached due to the raise in the loop
            return func(*args, **kwargs)

        return wrapper

    return decorator


class StructuredLogger:
    """
    A simple wrapper for logging structured JSON payloads.
    Uses Google Cloud Logging if available, otherwise falls back to standard logging.
    """

    def __init__(self, name: str):
        """
        Initializes the StructuredLogger.

        Args:
            name (str): The name of the logger (e.g., 'analysis_logger').
        """
        self.name = name
        self.cloud_logger = None
        try:
            # Imported lazily: Cloud Logging is optional, and the import itself is part
            # of the capability probe below.
            from google.cloud import (  # pylint: disable=import-outside-toplevel
                logging as cloud_logging,
            )

            client = cloud_logging.Client()
            self.cloud_logger = client.logger(name)
        # The probe must never fail the caller: a missing package, missing credentials
        # or any transport error simply means we fall back to standard logging.
        except Exception:  # pylint: disable=broad-exception-caught
            # Fallback or local development
            pass

        self.local_logger = logging.getLogger(name)

    def log(self, message: str, severity: str = "INFO", **kwargs):
        """
        Logs a structured message.

        Args:
            message (str): The primary log message.
            severity (str): The log level (INFO, WARNING, ERROR).
            **kwargs: Additional key-value pairs to include in the structured payload.
        """
        payload = {
            "message": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **kwargs,
        }

        # 1. Cloud Logging (if available)
        if self.cloud_logger:
            self.cloud_logger.log_struct(payload, severity=severity)

        # 2. Local Logging (always)
        log_msg = json.dumps({**payload, "severity": severity})
        if severity == "ERROR":
            self.local_logger.error(log_msg)
        elif severity == "WARNING":
            self.local_logger.warning(log_msg)
        elif severity == "DEBUG":
            self.local_logger.debug(log_msg)
        else:
            self.local_logger.info(log_msg)


# Default instance
qai_logger = StructuredLogger("qai_framework")
