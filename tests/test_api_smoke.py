from __future__ import annotations

from main import health, terminal_endpoint


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


def test_health_endpoint_returns_agent_phases():
    payload = health()
    assert payload['status'] == 'ok'
    assert payload['phases'] == ['Observe', 'Recall', 'Reason', 'Stabilize', 'Commit']
