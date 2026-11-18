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

"""Unit tests for the shared retry helpers.

Every test injects its own `sleep`, so the suite exercises the backoff schedule
without ever waiting for it.
"""

from typing import Any, List

import pytest
from google.api_core import exceptions as api_exceptions

from cxidk.core import retry


class SleepRecorder:
    """A `sleep` replacement that records delays instead of waiting.

    Attributes:
        delays: Every delay the retry loop asked for, in order.
    """

    def __init__(self) -> None:
        """Initializes an empty recorder."""
        self.delays: List[float] = []

    def __call__(self, seconds: float) -> None:
        """Records a requested delay.

        Args:
            seconds: The delay the caller wanted to sleep for.
        """
        self.delays.append(seconds)


class FlakyCall:
    """A callable that fails a fixed number of times, then succeeds.

    Attributes:
        calls: How many times the callable has been invoked.
    """

    def __init__(
        self, failures: int, error: Exception, result: str = "ok"
    ) -> None:
        """Initializes the callable.

        Args:
            failures: How many invocations should raise before one succeeds.
            error: The exception to raise.
            result: The value returned once the failures are exhausted.
        """
        self.failures = failures
        self.error = error
        self.result = result
        self.calls = 0

    def __call__(self) -> str:
        """Raises or returns, depending on how many calls have happened.

        Returns:
            The configured result.

        Raises:
            Exception: The configured error, until the failures run out.
        """
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return self.result


class TestComputeDelay:
    """The backoff schedule itself."""

    def test_stays_within_the_exponential_envelope(self) -> None:
        """Full jitter draws from [0, cap], so the cap is the only guarantee."""
        for attempt in range(5):
            cap = min(1.0 * 2**attempt, 60.0)
            assert 0.0 <= retry.compute_delay(attempt) <= cap

    def test_respects_the_ceiling(self) -> None:
        """Without a ceiling a long retry chain would sleep for hours."""
        assert retry.compute_delay(20, max_delay=5.0) <= 5.0

    def test_jitters_rather_than_repeating(self) -> None:
        """Identical delays would make concurrent callers re-trip one quota."""
        draws = {retry.compute_delay(6) for _ in range(20)}
        assert len(draws) > 1


class TestIsRetryableStatus:
    """Which HTTP statuses are worth a second attempt."""

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_transient_statuses_are_retryable(self, status: int) -> None:
        """Rate limiting and server errors usually clear on their own.

        Args:
            status: The status code under test.
        """
        assert retry.is_retryable_status(status) is True

    @pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 409, None])
    def test_everything_else_is_not(self, status: Any) -> None:
        """Retrying a 403 just spends quota on the same rejection.

        Args:
            status: The status code under test.
        """
        assert retry.is_retryable_status(status) is False


class TestRetryCall:
    """Attempt counting, propagation, and exhaustion."""

    def test_returns_without_sleeping_on_first_success(self) -> None:
        """The common path must not pay for the retry machinery."""
        sleep = SleepRecorder()

        assert retry.retry_call(lambda: "ok", sleep=sleep) == "ok"
        assert not sleep.delays

    def test_recovers_after_transient_failures(self) -> None:
        """Two 429s followed by a success is the case this exists for."""
        call = FlakyCall(2, api_exceptions.TooManyRequests("slow down"))
        sleep = SleepRecorder()

        assert retry.retry_call(call, sleep=sleep) == "ok"
        assert call.calls == 3
        assert len(sleep.delays) == 2

    def test_gives_up_after_the_last_attempt(self) -> None:
        """Retrying forever turns a transient failure into a hung process."""
        call = FlakyCall(99, api_exceptions.ServiceUnavailable("down"))
        sleep = SleepRecorder()

        with pytest.raises(retry.RetryError, match="after 3 attempts"):
            retry.retry_call(call, max_attempts=3, sleep=sleep)

        assert call.calls == 3
        assert len(sleep.delays) == 2

    def test_preserves_the_original_error_as_the_cause(self) -> None:
        """The wrapped error is what tells an operator which quota was hit."""
        original = api_exceptions.TooManyRequests("quota exceeded")
        call = FlakyCall(99, original)

        with pytest.raises(retry.RetryError) as caught:
            retry.retry_call(call, max_attempts=2, sleep=SleepRecorder())

        assert caught.value.__cause__ is original

    def test_propagates_a_permanent_error_immediately(self) -> None:
        """A 403 will not fix itself, so retrying only wastes time."""
        call = FlakyCall(99, api_exceptions.PermissionDenied("nope"))
        sleep = SleepRecorder()

        with pytest.raises(api_exceptions.PermissionDenied):
            retry.retry_call(call, sleep=sleep)

        assert call.calls == 1
        assert not sleep.delays

    def test_honours_a_custom_retryable_set(self) -> None:
        """Callers with their own transport need their own exception types."""
        call = FlakyCall(1, ValueError("transient"))

        assert (
            retry.retry_call(call, retry_on=[ValueError], sleep=SleepRecorder()) == "ok"
        )

    def test_a_custom_set_narrows_as_well_as_widens(self) -> None:
        """Passing `retry_on` replaces the defaults rather than adding to them."""
        call = FlakyCall(99, api_exceptions.TooManyRequests("slow down"))

        with pytest.raises(api_exceptions.TooManyRequests):
            retry.retry_call(call, retry_on=[ValueError], sleep=SleepRecorder())


class TestWithRetry:
    """The decorator form."""

    def test_retries_the_wrapped_function(self) -> None:
        """Arguments must survive the retry, not just the first call."""
        attempts = {"count": 0}

        @retry.with_retry(max_attempts=3, initial_delay=0.0, max_delay=0.0)
        def flaky(value: str) -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise api_exceptions.ServiceUnavailable("down")
            return value.upper()

        assert flaky("ok") == "OK"
        assert attempts["count"] == 3

    def test_preserves_the_function_identity(self) -> None:
        """A decorator that eats the docstring breaks the API reference."""

        @retry.with_retry()
        def documented() -> None:
            """Does nothing, memorably."""

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "Does nothing, memorably."
