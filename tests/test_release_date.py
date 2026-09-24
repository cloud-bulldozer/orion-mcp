"""Tests for the get_release_date MCP tool."""

import pytest

from components.tools.release_date import get_release_date


class TestGetReleaseDate:
    @pytest.mark.asyncio
    async def test_returns_date_for_known_version(self):
        result = await get_release_date(version="4.18")
        assert result == "2025-02-28"

    @pytest.mark.asyncio
    async def test_returns_date_for_another_known_version(self):
        result = await get_release_date(version="4.17")
        assert result == "2024-10-29"

    @pytest.mark.asyncio
    async def test_returns_date_for_future_version(self):
        result = await get_release_date(version="5.0")
        assert result == "2026-10-31"

    @pytest.mark.asyncio
    async def test_returns_invalid_for_unknown_version(self):
        result = await get_release_date(version="3.99")
        assert "Invalid version" in result
        assert "3.99" in result

    @pytest.mark.asyncio
    async def test_default_version_is_valid(self):
        result = await get_release_date()
        assert result != ""
        assert "Invalid" not in result
