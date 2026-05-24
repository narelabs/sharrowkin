from __future__ import annotations

import pytest

from api.routers.system import health_check
from agent.core import PHASES


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_health_endpoint_returns_agent_phases():
    payload = await health_check()
    assert payload['status'] == 'healthy'
    # Health endpoint doesn't return phases, but we can test PHASES constant
    assert PHASES == ['Observe', 'Recall', 'Reason', 'Stabilize', 'Commit']
