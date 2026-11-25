"""Fixtures for the NovaStar VX tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from .fake_device import FakeController


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def fake_controller(socket_enabled) -> AsyncGenerator[FakeController]:
    """A fake controller listening on localhost."""
    device = FakeController()
    await device.start()
    yield device
    await device.stop()
