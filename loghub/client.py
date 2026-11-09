"""Thin OpenSearch client for the log indices written by Fluent Bit."""

from __future__ import annotations

import os

import requests

DEFAULT_URL = os.environ.get("LOGHUB_OPENSEARCH_URL", "http://localhost:9200")
INDEX_PATTERN = "cassandra-logs-*"


class LogHubError(RuntimeError):
    """Raised when OpenSearch cannot be reached or rejects a request."""


class LogClient:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.post(url, json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LogHubError(f"cannot reach OpenSearch at {self.base_url}: {exc}") from exc
        if response.status_code == 404:
            # No index yet: Fluent Bit has not shipped any logs.
            return {"hits": {"hits": [], "total": {"value": 0}}, "aggregations": {}}
        if response.status_code >= 400:
            raise LogHubError(f"OpenSearch returned {response.status_code}: {response.text[:300]}")
        return response.json()

    def search(self, body: dict) -> dict:
        return self._post(f"{INDEX_PATTERN}/_search?ignore_unavailable=true", body)

    def health(self) -> str:
        try:
            response = self.session.get(f"{self.base_url}/_cluster/health", timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LogHubError(f"cannot reach OpenSearch at {self.base_url}: {exc}") from exc
        return response.json().get("status", "unknown")
