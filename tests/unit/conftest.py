from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from career_agent.models.control.controller import Controller


@pytest.fixture
def stub_control_owner(monkeypatch):
    from career_agent.ops import lifecycle

    @asynccontextmanager
    async def owner(settings):
        yield SimpleNamespace(controller=Controller(settings.runtime_control))

    monkeypatch.setattr(lifecycle, "control_owner", owner)
