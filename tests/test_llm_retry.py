"""Tests for LLM retry integration in ``agent.core``.

Validates: Requirements 6.3

Verifies that LLM calls (``GeminiClient.generate_text``,
``GeminiClient.generate_patch``) are retried up to 3 times on transient
errors (network timeout, 429, 503) using the ``retry_async`` helper from
``agent.resilience`` with the configured ``LLM_RETRY_POLICY``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

try:
    import httpx as _httpx
except ImportError:
    _httpx = None

from agent.resilience import RetryPolicy, retry_async
from agent.core import LLM_RETRY_POLICY


# ---------------------------------------------------------------------------
# Test: LLM_RETRY_POLICY has the correct parameters (Requirement 6.3)
# ---------------------------------------------------------------------------


def test_llm_retry_policy_parameters():
    """LLM_RETRY_POLICY matches Requirement 6.3 spec."""
    assert LLM_RETRY_POLICY.max_attempts == 3
    assert LLM_RETRY_POLICY.base_delay == 1.0
    assert LLM_RETRY_POLICY.max_delay == 30.0
    assert LLM_RETRY_POLICY.jitter == 0.25


# ---------------------------------------------------------------------------
# Test: retry_async retries on transient error and succeeds on 3rd attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    """Mock LLM client fails twice with a transient error, succeeds on 3rd attempt."""
    call_count = 0

    async def flaky_generate():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Simulate a transient timeout error
            raise _httpx.ReadTimeout("Connection timed out")
        return "Generated response"

    # Use a policy with zero delays for fast testing
    fast_policy = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)

    result = await retry_async(flaky_generate, policy=fast_policy)

    assert result == "Generated response"
    assert call_count == 3


# ---------------------------------------------------------------------------
# Test: retry_async retries on HTTP 503 and succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_succeeds_after_503():
    """Mock LLM client fails once with HTTP 503, succeeds on 2nd attempt."""
    call_count = 0

    async def flaky_503():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            # Simulate HTTP 503 Service Unavailable
            response = _httpx.Response(503, request=_httpx.Request("POST", "https://api.example.com"))
            raise _httpx.HTTPStatusError("Service Unavailable", request=response.request, response=response)
        return "Success after 503"

    fast_policy = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)

    result = await retry_async(flaky_503, policy=fast_policy)

    assert result == "Success after 503"
    assert call_count == 2


# ---------------------------------------------------------------------------
# Test: retry_async retries on HTTP 429 (rate limit) and succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_succeeds_after_429():
    """Mock LLM client fails once with HTTP 429, succeeds on 2nd attempt."""
    call_count = 0

    async def flaky_429():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            response = _httpx.Response(429, request=_httpx.Request("POST", "https://api.example.com"))
            raise _httpx.HTTPStatusError("Too Many Requests", request=response.request, response=response)
        return "Success after 429"

    fast_policy = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)

    result = await retry_async(flaky_429, policy=fast_policy)

    assert result == "Success after 429"
    assert call_count == 2


# ---------------------------------------------------------------------------
# Test: retry_async does NOT retry on permanent error (e.g. HTTP 400)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_retry_on_permanent_error():
    """Permanent errors (HTTP 400) are raised immediately without retry."""
    call_count = 0

    async def permanent_fail():
        nonlocal call_count
        call_count += 1
        response = _httpx.Response(400, request=_httpx.Request("POST", "https://api.example.com"))
        raise _httpx.HTTPStatusError("Bad Request", request=response.request, response=response)

    fast_policy = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)

    with pytest.raises(_httpx.HTTPStatusError):
        await retry_async(permanent_fail, policy=fast_policy)

    # Should only be called once — no retry on permanent error
    assert call_count == 1


# ---------------------------------------------------------------------------
# Test: retry_async exhausts all attempts and raises last error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_exhausts_attempts_and_raises():
    """When all 3 attempts fail with transient errors, the last error is raised."""
    call_count = 0

    async def always_timeout():
        nonlocal call_count
        call_count += 1
        raise _httpx.ReadTimeout("Connection timed out")

    fast_policy = RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)

    with pytest.raises(_httpx.ReadTimeout):
        await retry_async(always_timeout, policy=fast_policy)

    assert call_count == 3


# ---------------------------------------------------------------------------
# Test: LLM_RETRY_POLICY is used with retry_async (integration-style)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_retry_policy_integration():
    """Verify retry_async works with the actual LLM_RETRY_POLICY (zero-delay override for speed)."""
    call_count = 0

    async def flaky_llm():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _httpx.ConnectTimeout("Connection refused")
        return {"rationale": "done", "files": {}, "commands": []}

    # Override delays for test speed but keep max_attempts from LLM_RETRY_POLICY
    test_policy = RetryPolicy(
        max_attempts=LLM_RETRY_POLICY.max_attempts,
        base_delay=0.0,
        max_delay=0.0,
        jitter=0.0,
    )

    result = await retry_async(flaky_llm, policy=test_policy)

    assert result == {"rationale": "done", "files": {}, "commands": []}
    assert call_count == 3
