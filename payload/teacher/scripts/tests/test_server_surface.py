"""The loopback surface: capability split and read-only guarantee."""

from __future__ import annotations

import http.client
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.app import TOKEN_HEADER, launch, start_in_thread  # noqa: E402
from th import constants as C  # noqa: E402

from th.backend import make_draft  # noqa: E402

from support import ALLOW, Harness  # noqa: E402


class SurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness()
        # drive=False: this surface is an observer, with no model to drive.
        self.server = launch(self.harness.engine, drive=False)
        self.thread = start_in_thread(self.server)
        self.port = int(self.server.server_address[1])

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.harness.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        body: dict | None = None,
        raw: bytes | None = None,
    ) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {} if token is None else {TOKEN_HEADER: token}
        payload = raw
        if payload is None and body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if payload is not None:
            headers["Content-Length"] = str(len(payload))
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        status = response.status
        connection.close()
        return status, data

    def test_binds_to_loopback(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_a_missing_token_is_denied(self) -> None:
        for path in ("/", "/api/status", "/api/obligations", "/api/graph"):
            status, _ = self.request("GET", path, token=None)
            self.assertEqual(status, 403, path)

    def test_a_wrong_token_is_denied(self) -> None:
        status, _ = self.request("GET", "/api/status", token="not-the-token")
        self.assertEqual(status, 403)

    def test_a_wrong_token_and_an_unknown_path_are_indistinguishable(self) -> None:
        """A denial must not reveal whether the resource exists."""

        denied, body_denied = self.request("GET", "/api/status", token="nope")
        unknown, body_unknown = self.request("GET", "/api/status", token=None)
        self.assertEqual(denied, unknown)
        self.assertEqual(body_denied, body_unknown)

    def test_only_the_submit_route_accepts_a_post(self) -> None:
        status, body = self.request("POST", "/api/status", token=self.server.token)
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"], "read_only_surface")

    def test_submit_without_a_configured_backend_is_reported(self) -> None:
        """This server was launched with no model, so there is nothing to drive."""

        status, body = self.request(
            "POST", "/api/submit", token=self.server.token, body={"text": "一个提交"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["error"], "no_backend_configured")

    def test_submit_rejects_a_body_that_carries_more_than_text(self) -> None:
        status, body = self.request(
            "POST",
            "/api/submit",
            token=self.server.token,
            body={"text": "一个提交", "role": "admin", "tools": ["bash"]},
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "body_must_be_text_only")

    def test_submit_rejects_a_malformed_body(self) -> None:
        status, _ = self.request("POST", "/api/submit", token=self.server.token, raw=b"{not json")
        self.assertEqual(status, 400)

    def test_status_exposes_only_closed_fields(self) -> None:
        self.harness.accepted_claim()
        status, body = self.request("GET", "/api/status", token=self.server.token)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        claim = payload["claims"][0]
        self.assertIn("cannot_imply", claim)
        self.assertIn("effect", claim)
        self.assertNotIn("statement", claim, "the surface must not carry free claim text")

    def test_obligations_text_comes_from_the_renderer(self) -> None:
        status, body = self.request("GET", "/api/obligations", token=self.server.token)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        # The renderer translates closed issue codes into fixed phrases; it never
        # prints a raw code and never a free string.
        self.assertIn("缺少已核验的检查点", payload["rendered"])
        self.assertIn("本段由确定性渲染器生成", payload["rendered"])
        self.assertIn("NOT_COMPLETE", payload["assessment"]["status"])

    def test_the_token_never_enters_the_store_or_the_page(self) -> None:
        token = self.server.token
        self.request("GET", "/api/status", token=token)
        status, page = self.request("GET", "/", token=token)

        blob = b"".join(
            path.read_bytes() for path in sorted(self.harness.path.parent.rglob("*")) if path.is_file()
        )
        for stream in (page, blob):
            self.assertNotIn(token.encode("utf-8"), stream)
        # The page learns the token from the URL fragment, which the browser
        # does not transmit, so the page needs no token of its own.
        self.assertIn(b"location.hash", page)

    def test_the_manager_url_keeps_the_token_in_the_fragment(self) -> None:
        url = self.server.manager_url()
        self.assertIn("#token=", url)
        self.assertNotIn("?token=", url)

    def test_graph_snapshot_hash_is_stable_between_reads(self) -> None:
        self.harness.queue_turn()
        self.harness.engine.turn("一个提交", actor="worker")
        first = json.loads(self.request("GET", "/api/graph", token=self.server.token)[1])
        second = json.loads(self.request("GET", "/api/graph", token=self.server.token)[1])
        self.assertEqual(first["graph_snapshot_hash"], second["graph_snapshot_hash"])


class HarnessDrivenSurfaceTests(unittest.TestCase):
    """The surface drives the model. The browser never talks to it directly."""

    def setUp(self) -> None:
        self.harness = Harness(drafts=[make_draft()], verdicts=[ALLOW])
        self.server = launch(self.harness.engine)
        self.thread = start_in_thread(self.server)
        self.port = int(self.server.server_address[1])

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.harness.close()

    def submit(self, text: str) -> tuple[int, dict]:
        payload = json.dumps({"text": text}).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(
            "POST",
            "/api/submit",
            body=payload,
            headers={
                TOKEN_HEADER: self.server.token,
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        status = response.status
        connection.close()
        return status, body

    def test_a_submission_is_driven_by_the_harness(self) -> None:
        status, body = self.submit("一个提交")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("本段由确定性渲染器生成", body["visible"])
        # The harness, not the browser, called the model.
        self.assertIn("review_turn", self.harness.backend.calls)

    def test_the_response_carries_no_free_model_text(self) -> None:
        _, body = self.submit("一个提交")
        allowed = {"schema", "status", "visible", "code", "risk_codes", "operation", "revision"}
        self.assertTrue(set(body) <= allowed, f"unexpected fields: {set(body) - allowed}")

    def test_a_refused_input_is_reported_without_reaching_the_model(self) -> None:
        status, body = self.submit("")
        self.assertEqual(status, 422)
        self.assertEqual(body["status"], "refused")
        self.assertEqual(self.harness.backend.calls, [])

    def test_submitting_never_advances_authority(self) -> None:
        before = self.harness.store.head(C.HEAD_AUTHORITY)
        self.submit("一个提交")
        self.assertEqual(self.harness.store.head(C.HEAD_AUTHORITY), before)


if __name__ == "__main__":
    unittest.main()
