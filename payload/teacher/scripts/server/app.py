"""Loopback-only surface.

This is what makes the harness a hardened surface rather than an instruction. A
product that owns the conversation can guarantee things about it; a skill inside
someone else's chat cannot. Everything the browser shows comes from the
deterministic renderer or from closed store fields. On the answer path the
renderer places model-authored text only into labelled slots that passed the
answer gate; on the coach path no model-authored text reaches the page at all.

Boundary rules, all enforced here rather than documented as intentions:

  * bind to 127.0.0.1 and pick a random port unless one is given;
  * mint a random token at start, keep it in memory only, so a restart
    invalidates every previous link;
  * require the token on every request and read no role from the request body;
  * a wrong or missing token gets the same 403 before any lookup, so the
    response cannot be used to probe what exists;
  * never write the token into the store, the page, an error or a log;
  * a submission from the page goes through exactly the same loop and gates as
    the command line, so a browser has no path that skips one.
"""

from __future__ import annotations

import json
import runpy
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # allow `python server/app.py`
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from th import constants as C
from th.assets import build_context_packet
from th.backend import UnavailableBackend
from th.engine import Engine
from th.render import Renderer, render_json
from th.store import Store

TOKEN_HEADER = "X-Teacher-Harness-Token"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class HarnessServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        engine: Engine,
        *,
        token: str,
        port: int = 0,
        assets_dir: Path | None = None,
        session: Any | None = None,
    ) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.engine = engine
        self.store: Store = engine.store
        self.token = token
        self.renderer = Renderer()
        self.assets_dir = assets_dir
        # A session exists only when a model backend is configured. Without one
        # the surface stays a pure observer, which is the honest default: there
        # is nothing for the harness to drive.
        self.session = session

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def manager_url(self) -> str:
        # The token travels in the URL fragment, which a browser does not send
        # to the server. It is read into memory and the fragment removed.
        return f"{self.base_url}/#token={self.token}"


class _Handler(BaseHTTPRequestHandler):
    server: HarnessServer
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # noqa: D102 - suppress access logs
        return

    # -- helpers ----------------------------------------------------------
    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get(TOKEN_HEADER, ""), self.server.token)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, render_json(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _forbidden(self) -> None:
        # One response shape for every denial, emitted before any lookup.
        self._json(403, {"schema": "th-denied/v1", "error": "forbidden"})

    # -- routes -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if not self._authorized():
            self._forbidden()
            return
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._serve_index()
            return
        if path == "/api/status":
            self._json(200, self._status_payload())
            return
        if path == "/api/obligations":
            self._json(200, self._obligations_payload())
            return
        if path == "/api/graph":
            self._json(200, self._graph_payload())
            return
        self._json(404, {"schema": "th-error/v1", "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        """Submit one turn through the harness.

        This is not a bypass. The surface does not talk to a model and does not
        write: it hands text to the session, which runs the same gate, packet,
        validation, guard, render and commit sequence the CLI runs. The
        difference from a prompt-only deployment is who drives: here the harness
        does, and the model is the thing it calls.
        """

        if not self._authorized():
            self._forbidden()
            return
        path = self.path.split("?", 1)[0]
        if path != "/api/submit":
            self._json(405, {"schema": "th-error/v1", "error": "read_only_surface"})
            return

        # Shape is checked before availability: a malformed body is malformed
        # whether or not a backend is configured, and the caller should be told
        # which of the two problems it has.
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 64 * 1024:
            self._json(413, {"schema": "th-error/v1", "error": "bad_request_size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"schema": "th-error/v1", "error": "malformed_json"})
            return
        if not isinstance(body, dict) or set(body) != {"text"} or not isinstance(body["text"], str):
            self._json(400, {"schema": "th-error/v1", "error": "body_must_be_text_only"})
            return

        if self.server.session is None:
            self._json(409, {"schema": "th-error/v1", "error": "no_backend_configured"})
            return

        result = self.server.session.submit(body["text"])
        # The surface returns the renderer's text and closed codes. There is no
        # field here a model could have written into.
        self._json(200 if result["status"] == "ok" else 422, {"schema": "th-submit/v1", **result})

    # -- payloads ---------------------------------------------------------
    def _status_payload(self) -> dict[str, Any]:
        store = self.server.store
        engine = self.server.engine
        status = store.status()
        return {
            "schema": "th-surface/v1",
            "version": C.VERSION,
            "heads": status["heads"],
            "counts": status["counts"],
            "claims": [
                {
                    "record_id": record["record_id"],
                    "title": record["title"],
                    "review_state": store.review_state(record["record_id"]),
                    "effect": engine.record_effect(record["record_id"]),
                    "grade": record["body"].get("claim", {}).get("grade"),
                    "strength": record["body"].get("claim", {}).get("strength"),
                    "cannot_imply": list(record["body"].get("claim", {}).get("cannot_imply", [])),
                }
                for record in store.records(kind=C.KIND_CLAIM)
            ],
            "attempts": [
                {
                    "attempt_id": attempt["attempt_id"],
                    "route_id": attempt["route_id"],
                    "status": attempt["status"],
                    "outcome": attempt["outcome"],
                }
                for attempt in store.attempts()
            ],
            "chain": {name: store.verify_chain(name) for name in C.HEADS},
        }

    def _obligations_payload(self) -> dict[str, Any]:
        engine = self.server.engine
        assessment = engine.assess_completion(record_id=self._latest_claim_id())["assessment"]
        return {
            "schema": "th-surface/v1",
            "assessment": assessment,
            # The only text on the surface, and it is produced by the renderer.
            "rendered": self.server.renderer.render_completion(assessment),
        }

    def _latest_claim_id(self) -> str | None:
        claims = self.server.store.records(kind=C.KIND_CLAIM)
        return claims[-1]["record_id"] if claims else None

    def _graph_payload(self) -> dict[str, Any]:
        store = self.server.store
        return {
            "schema": "th-surface/v1",
            "nodes": [
                {"node_id": node["node_id"], "kind": node["kind"], "label": node["label"], "status": node["status"]}
                for node in store.nodes()
            ],
            "edges": store.all_edges(),
            "graph_snapshot_hash": store.graph_snapshot_hash(),
        }

    def _serve_index(self) -> None:
        if self.server.assets_dir is None:
            self._json(404, {"schema": "th-error/v1", "error": "no_assets"})
            return
        index = self.server.assets_dir / "index.html"
        if not index.is_file():
            self._json(404, {"schema": "th-error/v1", "error": "no_index"})
            return
        self._send(200, index.read_bytes(), "text/html; charset=utf-8")


class TeacherSurfaceSession:
    """Routes page submissions into the Teacher loop, or the coach when a
    practice problem is active. Returns renderer text and closed codes only."""

    OK = ("answered", "clarify", "checked", "admitted", "blocked", "off_topic", "ok", "exited", "hint",
          "incubated", "NOT_COMPLETE", "ROUTE_READY", "VERIFIED_SOLVED")

    def __init__(self, teacher: Any, coach: Any) -> None:
        self.teacher = teacher
        self.coach = coach

    def submit(self, text: str) -> dict[str, Any]:
        command, _, argument = text.strip().partition(" ")
        argument = argument.strip()
        if command == "/coach":
            result = self.coach.start(argument)
        elif self.coach.active():
            if command == "/idea":
                anchor, _, idea = argument.partition(" ")
                result = (self.coach.step(idea, role="exploratory_idea", connects=int(anchor)) if anchor.isdigit()
                          else {"status": "refused", "visible": "用法：/idea 步骤编号 内容（0 表示题目本身）"})
            elif command == "/conclude":
                result = self.coach.step(argument, role="conclusion")
            elif command == "/route":
                result = self.coach.summary()
            elif command == "/hint":
                result = self.coach.hint()
            elif command == "/incubate":
                parts = argument.split()
                result = self.coach.incubate(parts[0] if parts else "", [int(item) for item in parts[1:] if item.isdigit()])
            elif command == "/done":
                result = self.coach.complete(policy="lenient" if argument == "lenient" else "strict")
            elif command == "/exit":
                result = self.coach.exit()
            elif text.startswith("/"):
                result = {"status": "refused", "visible": "练习进行中只能用练习命令；要离开练习先 /exit。"}
            else:
                result = self.coach.step(text)
        else:
            result = self.teacher.ask(text)
        return {
            "status": "ok" if result.get("status") in self.OK else "failed",
            "stage": result.get("status"),
            "visible": result.get("visible"),
            "code": result.get("code"),
            "risk_codes": list(result.get("risk_codes", [])),
            "revision": self.teacher.store.head(C.HEAD_EXECUTION),
        }


def serve(*, config: dict[str, Any], store_path: str, port: int = 0, open_browser: bool = True) -> int:
    """Start the page for the configured Teacher. Used by `teacher.py serve`."""

    import webbrowser

    from th import config as cfg
    from th.backend import SubprocessBackend
    from th.coach import Coach
    from th.teach import Teacher

    store = Store(Path(store_path).expanduser())
    store.init()
    backend_config = config.get("backend") or {}
    backend: Any = UnavailableBackend()
    guard: Any = UnavailableBackend()
    if backend_config.get("command"):
        env = cfg.backend_environment(config)
        backend = SubprocessBackend(list(backend_config["command"]), timeout=float(backend_config.get("timeout", 240)), env=env)
        guard = SubprocessBackend(list(backend_config["command"]), timeout=float(backend_config.get("timeout", 240)),
                                  env={**env, "TH_ROLE": "guard"})
    teacher = Teacher(store, backend=backend, guard_backend=guard, contract=cfg.contract(config),
                      use_model_guard=bool(config.get("use_model_guard")))
    coach = Coach(store, backend=backend, guard_backend=guard)
    engine = Engine(store, backend=None, contract=cfg.contract(config))
    session = TeacherSurfaceSession(teacher, coach) if not isinstance(backend, UnavailableBackend) else None
    server = launch(engine, port=port, session=session, drive=session is not None)
    print("Teacher 已在本机启动。关闭此终端即可停止服务。", flush=True)
    print(f"库：{store.path}", flush=True)
    print(f"驱动模式：{'harness 调用模型' if server.session is not None else '只读观察（未配置后端）'}", flush=True)
    print(f"入口：{server.manager_url()}", flush=True)
    if open_browser:
        threading.Timer(0.15, lambda: webbrowser.open(server.manager_url(), new=2)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()
    return 0


def start_in_thread(server: HarnessServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    return thread


def launch(
    engine: Engine,
    *,
    port: int = 0,
    token: str | None = None,
    assets_dir: Path | None = None,
    drive: bool = True,
    session: Any | None = None,
) -> HarnessServer:
    """Start a surface.

    `drive=True` makes the harness own the turn loop, which is the point of the
    design: the human talks to the harness and the harness calls the model. With
    no usable backend there is nothing to drive, so the session stays absent and
    the surface is a pure observer.
    """

    if session is None and drive and not isinstance(engine.backend, UnavailableBackend):
        from th.session import Session

        session = Session(engine)
    return HarnessServer(
        engine,
        token=token or secrets.token_urlsafe(24),
        port=port,
        assets_dir=assets_dir or Path(__file__).resolve().parent / "assets",
        session=session,
    )


def context_packet_for_surface(store: Store, contract: dict[str, Any], *, actor: str = "router") -> dict[str, Any]:
    """Convenience for embedding: a bounded packet for the surface to show."""

    return build_context_packet(
        store, contract=contract, actor=actor, purpose="surface", record_ids=store.record_ids()
    )


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import webbrowser

    parser = argparse.ArgumentParser(prog="teacher-harness-surface", description="Launch the local surface")
    parser.add_argument("--store", required=True)
    parser.add_argument("--contract")
    parser.add_argument("--port", type=int, default=0, help="0 chooses a free loopback port")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--backend-command",
        help="command speaking the structured JSONL protocol; without it the surface is an observer",
    )
    args = parser.parse_args(argv)

    store = Store(args.store)
    store.init()
    contract: dict[str, Any] = {}
    if args.contract:
        contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    if args.backend_command:
        from th.backend import SubprocessBackend

        backend: Any = SubprocessBackend(args.backend_command.split())
    else:
        backend = None
    engine = Engine(store, backend=backend, contract=contract)
    server = launch(engine, port=args.port)
    print("Teacher 已在本机启动。关闭此终端即可停止服务。", flush=True)
    print(f"库：{store.path}", flush=True)
    print(f"驱动模式：{'harness 调用模型' if server.session is not None else '只读观察（未配置后端）'}", flush=True)
    print(f"管理者入口：{server.manager_url()}", flush=True)
    if not args.no_browser:
        threading.Timer(0.15, lambda: webbrowser.open(server.manager_url(), new=2)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
