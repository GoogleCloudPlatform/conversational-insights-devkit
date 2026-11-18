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

"""Shared retry helpers for rate-limited and transient API failures.

Bulk configuration imports issue hundreds of writes in a tight loop, which is
exactly the shape of traffic that trips per-minute quotas. This module provides
a single exponential-backoff-with-jitter implementation so that behaviour is
consistent across REST wrappers and long-running operation polling instead of
being re-implemented ad hoc.
"""

import functools
import logging
import random
import time
from typing import Any, Callable, Iterable, Optional, Tuple, Type, TypeVar

from google.api_core import exceptions as api_exceptions

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_INITIAL_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_MULTIPLIER = 2.0

RETRYABLE_STATUS_CODES: Tuple[int, ...] = (429, 500, 502, 503, 504)

RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    api_exceptions.TooManyRequests,
    api_exceptions.InternalServerError,
    api_exceptions.BadGateway,
    api_exceptions.ServiceUnavailable,
    api_exceptions.GatewayTimeout,
)


class RetryError(RuntimeError):
    """Raised when an operation still fails after exhausting every attempt."""


def compute_delay(
    attempt: int,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    multiplier: float = DEFAULT_MULTIPLIER,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> float:
    """Computes the backoff delay for a given attempt, with full jitter.

    Full jitter (a uniform draw over the whole interval rather than a fixed
    exponential value) is used deliberately: when many writes are retried at
    once, a deterministic backoff makes every caller retry at the same instant
    and re-trips the same quota.

    Args:
        attempt: The zero-based attempt number that just failed.
        initial_delay: The delay applied after the first failure, in seconds.
        multiplier: The exponential growth factor between attempts.
        max_delay: An upper bound on the delay, in seconds.

    Returns:
        The number of seconds to sleep before the next attempt.
    """
    capped = min(initial_delay * (multiplier**attempt), max_delay)
    return random.uniform(0.0, capped)


def is_retryable_status(status_code: Optional[int]) -> bool:
    """Reports whether an HTTP status code is worth retrying.

    Args:
        status_code: The HTTP status code returned by the API, if any.

    Returns:
        True when the status code represents a transient failure.
    """
    return status_code in RETRYABLE_STATUS_CODES


def retry_call(
    func: Callable[[], T],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    multiplier: float = DEFAULT_MULTIPLIER,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on: Optional[Iterable[Type[Exception]]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Calls a zero-argument function, retrying transient failures.

    Args:
        func: The zero-argument callable to invoke.
        max_attempts: The total number of attempts, including the first.
        initial_delay: The delay applied after the first failure, in seconds.
        multiplier: The exponential growth factor between attempts.
        max_delay: An upper bound on the delay, in seconds.
        retry_on: Exception types treated as transient. Defaults to the
            standard set of rate-limit and server-error exceptions.
        sleep: The sleep implementation, injectable so tests do not wait.

    Returns:
        Whatever ``func`` returns on its first successful attempt.

    Raises:
        RetryError: If every attempt failed with a retryable error.
        Exception: Any non-retryable exception is propagated immediately.
    """
    retryable: Tuple[Type[Exception], ...] = (
        tuple(retry_on) if retry_on is not None else RETRYABLE_EXCEPTIONS
    )
    last_error: Optional[BaseException] = None

    for attempt in range(max_attempts):
        try:
            return func()
        # pylint cannot prove a variable tuple contains exception classes;
        # mypy does verify it via the Tuple[Type[Exception], ...] annotation.
        except retryable as error:  # pylint: disable=catching-non-exception
            last_error = error
            if attempt == max_attempts - 1:
                break
            delay = compute_delay(attempt, initial_delay, multiplier, max_delay)
            logger.warning(
                "Retryable error on attempt %d/%d (%s); sleeping %.2fs",
                attempt + 1,
                max_attempts,
                type(error).__name__,
                delay,
            )
            sleep(delay)

    raise RetryError(
        f"Operation failed after {max_attempts} attempts: {last_error}"
    ) from last_error


def with_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    multiplier: float = DEFAULT_MULTIPLIER,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on: Optional[Iterable[Type[Exception]]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorates a function so that transient failures are retried.

    Args:
        max_attempts: The total number of attempts, including the first.
        initial_delay: The delay applied after the first failure, in seconds.
        multiplier: The exponential growth factor between attempts.
        max_delay: An upper bound on the delay, in seconds.
        retry_on: Exception types treated as transient.

    Returns:
        A decorator that adds retry behaviour to the wrapped function.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return retry_call(
                lambda: func(*args, **kwargs),
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                multiplier=multiplier,
                max_delay=max_delay,
                retry_on=retry_on,
            )

        return wrapper

    return decorator
