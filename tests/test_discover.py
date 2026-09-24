"""Tests for the discover_jobs MCP tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from components.tools.discover import _resolve_configs_from_prow, discover_jobs


class TestResolveConfigsFromProw:
    @pytest.mark.asyncio
    async def test_empty_build_url_returns_empty(self):
        result = await _resolve_configs_from_prow("")
        assert result == []

    @pytest.mark.asyncio
    async def test_url_without_prow_prefix_returns_empty(self):
        result = await _resolve_configs_from_prow("https://example.com/build/123")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_sorted_configs_from_prow_artifacts(self):
        artifacts_html = "> e2e-test/<"
        step_html = "> openshift-qe-orion-step-b/< > openshift-qe-orion-step-a/<"
        build_log_a = "some log\nORION_CONFIG=examples/node-density.yaml\nmore log"
        build_log_b = "some log\nORION_CONFIG=examples/cluster-density.yaml\nmore log"

        async def mock_get(url, **kwargs):
            response = MagicMock()
            response.status_code = 200
            if url.endswith("/artifacts/"):
                response.text = artifacts_html
            elif url.endswith("e2e-test/"):
                response.text = step_html
            elif "step-a" in url:
                response.text = build_log_a
            else:
                response.text = build_log_b
            return response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client):
            result = await _resolve_configs_from_prow(
                "https://prow.ci.openshift.org/view/gs/bucket/build/123"
            )

        assert result == sorted(result)
        assert "node-density.yaml" in result
        assert "cluster-density.yaml" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_artifacts_request_fails(self):
        async def mock_get(url, **kwargs):
            response = MagicMock()
            response.status_code = 404
            response.text = ""
            return response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client):
            result = await _resolve_configs_from_prow(
                "https://prow.ci.openshift.org/view/gs/bucket/build/123"
            )
        assert result == []


class TestDiscoverJobs:
    def _make_es_response(self, job_name="periodic-ci-test", benchmark="kube-burner"):
        return {
            "aggregations": {
                "jobs": {
                    "buckets": [
                        {
                            "key": job_name,
                            "benchmarks": {"buckets": [{"key": benchmark}]},
                            "top_hit": {
                                "hits": {
                                    "hits": [
                                        {
                                            "_source": {
                                                "platform": "AWS",
                                                "clusterType": "self-managed",
                                                "workerNodesCount": 6,
                                                "networkType": "OVNKubernetes",
                                                "fips": "false",
                                                "ipsec": "false",
                                                "encrypted": "false",
                                                "masterNodesType": "m6i.xlarge",
                                                "masterNodesCount": 3,
                                                "workerNodesType": "m6i.xlarge",
                                                "ocpVersion": "4.18",
                                                "buildUrl": "",
                                            }
                                        }
                                    ]
                                }
                            },
                        }
                    ]
                }
            }
        }

    @pytest.mark.asyncio
    async def test_returns_jobs_dict_on_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self._make_es_response()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client),
            patch("components.tools.discover.get_data_source", return_value="http://es:9200"),
            patch("components.tools.discover.get_es_metadata_index", return_value="perf_scale_ci*"),
            patch("components.tools.discover.extract_and_set_es_server"),
        ):
            result = await discover_jobs()

        assert "jobs" in result
        assert "total" in result
        assert result["total"] == 1
        job = result["jobs"]["periodic-ci-test"]
        assert job["benchmarks"] == ["kube-burner"]
        assert job["metadata"]["platform"] == "AWS"
        assert "configs" in job

    @pytest.mark.asyncio
    async def test_returns_error_on_es_failure(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client),
            patch("components.tools.discover.get_data_source", return_value="http://es:9200"),
            patch("components.tools.discover.get_es_metadata_index", return_value="perf_scale_ci*"),
            patch("components.tools.discover.extract_and_set_es_server"),
        ):
            result = await discover_jobs()

        assert "error" in result

    @pytest.mark.asyncio
    async def test_filters_applied_to_es_query(self):
        """Verify platform and cluster_type filters appear in the ES must clauses."""
        captured_query = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"aggregations": {"jobs": {"buckets": []}}}
        mock_response.raise_for_status = MagicMock()

        async def capture_post(url, json=None, **kwargs):
            captured_query.update(json or {})
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = capture_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client),
            patch("components.tools.discover.get_data_source", return_value="http://es:9200"),
            patch("components.tools.discover.get_es_metadata_index", return_value="perf_scale_ci*"),
            patch("components.tools.discover.extract_and_set_es_server"),
        ):
            await discover_jobs(platform="AWS", cluster_type="self-managed")

        must_clauses = captured_query["query"]["bool"]["must"]
        assert {"term": {"platform.keyword": "AWS"}} in must_clauses
        assert {"term": {"clusterType.keyword": "self-managed"}} in must_clauses

    @pytest.mark.asyncio
    async def test_version_filter_uses_prefix(self):
        """Version filter uses prefix query, not exact match."""
        captured_query = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"aggregations": {"jobs": {"buckets": []}}}
        mock_response.raise_for_status = MagicMock()

        async def capture_post(url, json=None, **kwargs):
            captured_query.update(json or {})
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = capture_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client),
            patch("components.tools.discover.get_data_source", return_value="http://es:9200"),
            patch("components.tools.discover.get_es_metadata_index", return_value="perf_scale_ci*"),
            patch("components.tools.discover.extract_and_set_es_server"),
        ):
            await discover_jobs(version="4.18")

        must_clauses = captured_query["query"]["bool"]["must"]
        assert {"prefix": {"ocpVersion.keyword": "4.18"}} in must_clauses

    @pytest.mark.asyncio
    async def test_workload_filter_goes_into_bool_filter_not_must(self):
        """workload uses a wildcard in filter context, not must — different ES semantics."""
        captured_query = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"aggregations": {"jobs": {"buckets": []}}}
        mock_response.raise_for_status = MagicMock()

        async def capture_post(url, json=None, **kwargs):
            captured_query.update(json or {})
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = capture_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("components.tools.discover.httpx.AsyncClient", return_value=mock_client),
            patch("components.tools.discover.get_data_source", return_value="http://es:9200"),
            patch("components.tools.discover.get_es_metadata_index", return_value="perf_scale_ci*"),
            patch("components.tools.discover.extract_and_set_es_server"),
        ):
            await discover_jobs(workload="payload")

        filter_clauses = captured_query["query"]["bool"].get("filter", [])
        must_clauses = captured_query["query"]["bool"]["must"]
        expected_wildcard = {"wildcard": {"upstreamJob.keyword": {"value": "*payload*"}}}
        assert expected_wildcard in filter_clauses
        assert expected_wildcard not in must_clauses

    @pytest.mark.asyncio
    async def test_invalid_job_type_returns_error(self):
        """Passing an unrecognized job_type returns a validation error before hitting ES."""
        result = await discover_jobs(job_type="invalid-type")
        assert "error" in result
        assert "job_type" in result["error"]
