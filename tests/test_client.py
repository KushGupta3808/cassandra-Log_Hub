"""Exercise LogClient over real HTTP against a tiny fake OpenSearch server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from loghub.client import LogClient, LogHubError


class FakeOpenSearch(BaseHTTPRequestHandler):
    status = 200
    payload: dict = {}
    received: list = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        FakeOpenSearch.received.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
        self._reply()

    def do_GET(self):
        self._reply()

    def _reply(self):
        body = json.dumps(FakeOpenSearch.payload).encode()
        self.send_response(FakeOpenSearch.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeOpenSearch)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    FakeOpenSearch.received = []
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_search_posts_to_the_log_indices(server):
    FakeOpenSearch.status, FakeOpenSearch.payload = 200, {"hits": {"hits": [], "total": {"value": 0}}}
    result = LogClient(server).search({"size": 1})
    path, body = FakeOpenSearch.received[0]
    assert path.startswith("/cassandra-logs-*/_search")
    assert body == {"size": 1}
    assert result["hits"]["total"]["value"] == 0


def test_missing_index_returns_empty_result(server):
    FakeOpenSearch.status, FakeOpenSearch.payload = 404, {"error": "index_not_found_exception"}
    assert LogClient(server).search({})["hits"]["hits"] == []


def test_server_errors_raise_loghub_error(server):
    FakeOpenSearch.status, FakeOpenSearch.payload = 400, {"error": "parsing_exception"}
    with pytest.raises(LogHubError, match="400"):
        LogClient(server).search({})


def test_health_reports_cluster_status(server):
    FakeOpenSearch.status, FakeOpenSearch.payload = 200, {"status": "green"}
    assert LogClient(server).health() == "green"


def test_unreachable_server_raises_loghub_error():
    with pytest.raises(LogHubError, match="cannot reach"):
        LogClient("http://127.0.0.1:9", timeout=1).search({})
