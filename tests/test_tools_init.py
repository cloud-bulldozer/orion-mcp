"""Tests for components/tools package exports."""

from components.tools import discover_jobs, get_release_date


def test_discover_jobs_importable():
    assert callable(discover_jobs)


def test_get_release_date_importable():
    assert callable(get_release_date)
