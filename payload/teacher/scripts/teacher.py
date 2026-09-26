#!/usr/bin/env python3
"""Teacher: one entry point for both ways of using the harness.

Standalone (the harness drives the model):

    python3 teacher.py setup --base-url URL --model NAME [--read-root DIR]
    python3 teacher.py chat                 # talk; the harness runs every turn
    python3 teacher.py ask "问题"            # one turn, non-interactive
    python3 teacher.py serve                # local page on 127.0.0.1

Attached (a host agent does the work; the harness applies the same rules):

    python3 teacher.py frame-check --brief "原话" --draft frame.json
    python3 teacher.py check-answer --brief "原话" --kind KIND --answer answer.json --evidence evidence.json

Assets and state:

    python3 teacher.py index DIR            # plan; then --apply PLAN_SHA256
    python3 teacher.py archive              # show the proposal; then --choice ... --plan SHA
    python3 teacher.py status
    python3 teacher.py engine -- <args>     # objectives, claims, reviews, gates, coverage, maintenance
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from th import config as cfg  # noqa: E402
from th import constants as C  # noqa: E402
from th import archive, retrieval  # noqa: E402
from th.attached import check_answer, frame_check  # noqa: E402
from th.backend import SubprocessBackend, UnavailableBackend  # noqa: E402
from th.coach import Coach  # noqa: E402
from th.render import Renderer, render_json  # noqa: E402
from th.store import Store  # noqa: E402
from th.teach import Teacher  # noqa: E402

BAR = "─" * 60
PRACTICE_COMMANDS = {"/idea", "/conclude", "/route", "/hint", "/incubate", "/done", "/exit", "/help", "/status",
                     "/quit", "/coach"}


def _store(config: dict, override: str | None) -> Store:
    path = Path(override or config["store"]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(path)
    store.init()
    return store


def _backend(config: dict, *, guard: bool = False):
    backend = config.get("backend") or {}
    command = backend.get("command")
    if not command:
        return UnavailableBackend()
    env = cfg.backend_environment(config)
    if guard:
        env["TH_ROLE"] = "guard"
    return SubprocessBackend(list(command), timeout=float(backend.get("timeout", 240)), env=env)


def _teacher(config: dict, store: Store) -> Teacher:
    return Teacher(
        store,
        backend=_backend(config),
        guard_backend=_backend(config, guard=True),
        contract=cfg.contract(config),
        use_model_guard=bool(config.get("use_model_guard")),
        timeout=float((config.get("backend") or {}).get("timeout", 240)),
    )


def _coach(config: dict, store: Store) -> Coach:
    return Coach(store, backend=_backend(config), guard_backend=_backend(config, guard=True),
                 timeout=float((config.get("backend") or {}).get("timeout", 240)))


def _print(payload, as_json: bool) -> None:
    if as_json:
        print(render_json(payload if isinstance(payload, dict) else {"result": payload}))
    elif isinstance(payload, dict) and "visible" in payload and payload["visible"]:
        print(payload["visible"])
    else:
        print(render_json(payload if isinstance(payload, dict) else {"result": payload}))


# --------------------------------------------------------------------------
# Interactive session
# --------------------------------------------------------------------------
HELP = """直接打字就是提问。Teacher 先弄清你真正要问什么（必要时只问你一个选择题），
再查你的笔记/资料库/论文，然后给出简短、带依据的回答。

  /more 编号      看某个来源的原文片段（例如 /more 1）
  /ask 编号       接着问回答末尾提示的那个问题
  /switch 编号    按另一种理解重答
  /archive        把值得保留的结论、来源、未解问题归档（只需选一次）
  /project        把这一串提问升格为研究目标（Teacher 起草，你确认一次）
  /coach 题目      进入练习模式：你自己做，Coach 只检查你的每一步（练习中不能用回答模式的命令）
  /index 目录      把一个笔记/论文目录加入可检索范围
  /status         看状态
  /quit           退出（有待归档内容时会提示一次）

练习模式里：直接写步骤；/idea 步骤编号 内容 写一个连到某一步（0 为题目）的探索性想法；/conclude 写结论；
/route 看自己的路线；/hint 用一次受守卫的提示（需先有已记录的障碍和新的尝试）；
/incubate targeted_question 2 [3] | conditional_hypothesis 2 3 | obstacle_map  围绕你自己的步骤做研究孵化；
/done 做完成检查（/done lenient 用宽松标准）；/exit 封存。"""


def chat(config: dict, store: Store) -> int:
    teacher = _teacher(config, store)
    coach = _coach(config, store)
    renderer = Renderer()
    pending_objective: dict | None = None
    pending_archive: dict | None = None
    if isinstance(teacher.backend, UnavailableBackend):
        print("没有配置模型后端：先运行 teacher.py setup。")
    print(BAR)
    print("Teacher 已就绪。直接说你想弄明白的事；/help 查看命令。")
    print(BAR)
    while True:
        try:
            line = input("\n你> ").rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            line = "/quit"
        text = line.strip()
        if pending_archive is not None and text in ("", "1", "2", "3"):
            choice = {"": "verified_only", "1": "verified_only", "2": "all", "3": "none"}[text]
            receipt = archive.apply(store, pending_archive, choice=choice, expect_plan_sha256=pending_archive["plan_sha256"])
            print(renderer.render_archive_receipt(receipt))
            pending_archive = None
            continue
        pending_archive = None
        if not text:
            continue
        command, _, argument = text.partition(" ")
        argument = argument.strip()
        practice = coach.active() is not None
        if practice and command not in PRACTICE_COMMANDS and text.startswith("/"):
            print("练习进行中只能用：" + " ".join(sorted(PRACTICE_COMMANDS)) + "。要离开练习先 /exit。")
            continue
        try:
            if command == "/quit":
                proposal = archive.propose(store)
                if proposal["verified_count"]:
                    print(renderer.render_archive_proposal(proposal))
                    pending_archive = proposal
                    try:
                        answer = input("\n你> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        answer = "3"
                    if answer in ("", "1", "2", "3"):
                        choice = {"": "verified_only", "1": "verified_only", "2": "all", "3": "none"}[answer]
                        receipt = archive.apply(store, proposal, choice=choice, expect_plan_sha256=proposal["plan_sha256"])
                        print(renderer.render_archive_receipt(receipt))
                print("再见。")
                return 0
            if command == "/help":
                print(HELP)
            elif command == "/more":
                print(teacher.expand(f"E{argument}" if argument.isdigit() else argument)["visible"])
            elif command == "/ask" and argument.isdigit():
                print(teacher.followup(int(argument))["visible"])
            elif command == "/switch" and argument.isdigit():
                print(teacher.switch(int(argument))["visible"])
            elif command == "/archive":
                proposal = archive.propose(store)
                print(renderer.render_archive_proposal(proposal))
                if proposal["items"]:
                    pending_archive = proposal
            elif command == "/project":
                result = teacher.propose_objective()
                print(result["visible"])
                pending_objective = result.get("objective")
            elif command == "/set" and pending_objective is not None:
                field, _, value = argument.partition(" ")
                if field not in C.INTAKE_ORDER or not value.strip():
                    print(f"用法：/set <{'/'.join(C.INTAKE_ORDER)}> 新内容")
                else:
                    if field == "assumptions":
                        pending_objective[field] = [item.strip() for item in value.split("；") if item.strip()]
                    else:
                        pending_objective[field] = value.strip()
                    print(renderer.render_objective_proposal(pending_objective))
            elif command == "/confirm" and pending_objective is not None:
                print(teacher.bind_objective(pending_objective)["visible"])
                pending_objective = None
            elif command == "/coach":
                if not argument:
                    print("用法：/coach 题目全文")
                else:
                    print(coach.start(argument)["visible"])
            elif command == "/idea":
                anchor, _, idea = argument.partition(" ")
                if not anchor.isdigit():
                    print("用法：/idea 步骤编号 内容（0 表示题目本身）")
                else:
                    print(coach.step(idea, role="exploratory_idea", connects=int(anchor))["visible"])
            elif command == "/conclude":
                print(coach.step(argument, role="conclusion")["visible"])
            elif command == "/route":
                print(coach.summary()["visible"])
            elif command == "/hint":
                print(coach.hint()["visible"])
            elif command == "/incubate":
                parts = argument.split()
                kind = parts[0] if parts else ""
                anchors = [int(item) for item in parts[1:] if item.isdigit()]
                print(coach.incubate(kind, anchors)["visible"])
            elif command == "/done":
                print(coach.complete(policy="lenient" if argument == "lenient" else "strict")["visible"])
            elif command == "/exit":
                print(coach.exit()["visible"] if practice else "没有正在进行的练习。退出 Teacher 用 /quit。")
            elif command == "/index":
                root = argument or "."
                plan = retrieval.plan_index(root)
                print(f"将索引 {plan['files']} 个文件（其中 PDF {plan['pdf_files']} 个，PDF 文字提取：{plan['pdf_extractor']}）。确认输入 y：")
                if input("你> ").strip().casefold() == "y":
                    receipt = retrieval.apply_index(store, plan, expect_plan_sha256=plan["plan_sha256"])
                    print(f"已索引 {receipt['files']} 个文件、{receipt['sections']} 个片段；没有文字层 {receipt['no_text_layer']} 个，提取失败 {receipt['extraction_failed']} 个。")
            elif command == "/status":
                print(render_json(_status(store)))
            elif text.startswith("/"):
                print("没有这个命令。/help 查看命令。")
            elif coach.active():
                print(coach.step(text)["visible"])
            else:
                result = teacher.ask(text)
                print(result["visible"])
        except Exception as exc:  # noqa: BLE001 - keep the session alive
            print(f"[未完成：{type(exc).__name__}]")


def _status(store: Store) -> dict:
    status = store.status()
    status["library"] = archive.library_status(store)
    status["retrieval"] = retrieval.index_status(store)
    status["asks"] = len(store.asks(limit=100000))
    return status


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teacher", description="Teacher: research teaching harness for CS/AI")
    parser.add_argument("--store", help="project store (SQLite); defaults to the configured store")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="write the receiver-local configuration")
    setup.add_argument("--base-url")
    setup.add_argument("--model")
    setup.add_argument("--guard-model")
    setup.add_argument("--timeout", type=float)
    setup.add_argument("--read-root", action="append", default=None, help="a directory the harness may read (repeatable)")
    setup.add_argument("--network", choices=("on", "off"))
    setup.add_argument("--model-guard", choices=("on", "off"))
    setup.add_argument("--api-key-stdin", action="store_true", help="store the API key in an owner-only key file")
    setup.add_argument("--show", action="store_true")

    sub.add_parser("chat", help="interactive session (standalone)")
    ask = sub.add_parser("ask", help="one standalone turn")
    ask.add_argument("text")
    serve = sub.add_parser("serve", help="local page on 127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-browser", action="store_true")

    fc = sub.add_parser("frame-check", help="attached: apply the need-discovery rule to an agent's framing")
    fc.add_argument("--brief", required=True)
    fc.add_argument("--draft", required=True, help="JSON file with the frame draft")
    ca = sub.add_parser("check-answer", help="attached: run the answer gate on an agent's answer")
    ca.add_argument("--brief", required=True)
    ca.add_argument("--kind", required=True, choices=C.REQUEST_KINDS)
    ca.add_argument("--answer", required=True, help="JSON file with the answer draft")
    ca.add_argument("--evidence", required=True, help="JSON file: list of {id, kind, locator, text}")
    ca.add_argument("--steps", type=int, default=1)

    index = sub.add_parser("index", help="plan (and with --apply, perform) local indexing")
    index.add_argument("root")
    index.add_argument("--apply", metavar="PLAN_SHA256")
    arc = sub.add_parser("archive", help="show the archive proposal, or apply a choice to it")
    arc.add_argument("--choice", choices=C.ARCHIVE_CHOICES)
    arc.add_argument("--plan", metavar="PLAN_SHA256")
    sub.add_parser("status", help="heads, library, index and asks")
    sub.add_parser("cognition", help="the current core cognition, as the model receives it")

    cs = sub.add_parser("coach-start", help="coach: admit a practice problem")
    cs.add_argument("problem")
    cst = sub.add_parser("coach-step", help="coach: submit one learner step")
    cst.add_argument("text")
    cst.add_argument("--role", choices=C.COACH_ROLES, default="local_step")
    cst.add_argument("--connects", type=int, help="for exploratory_idea: learner step number, 0 for the problem")
    sub.add_parser("coach-route", help="coach: deterministic route summary")
    cd = sub.add_parser("coach-done", help="coach: completion gate")
    cd.add_argument("--policy", choices=("strict", "lenient"), default="strict")
    sub.add_parser("coach-exit", help="coach: seal the practice")
    sub.add_parser("coach-hint", help="coach: one guarded hint (HINT_ONCE)")
    ci = sub.add_parser("coach-incubate", help="coach: anchored research incubation")
    ci.add_argument("kind", choices=("targeted_question", "obstacle_map", "conditional_hypothesis"))
    ci.add_argument("anchors", nargs="*", type=int)

    sub.add_parser("project-propose", help="draft a research objective from recent requests")
    pb = sub.add_parser("project-bind", help="bind an objective JSON (advances authority)")
    pb.add_argument("objective")

    eng = sub.add_parser("engine", help="pass the remaining arguments to the research-state CLI")
    eng.add_argument("rest", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = cfg.load()

    if args.command == "setup":
        if args.show:
            print(render_json({"config_path": str(cfg.config_path()), "key_file_present": cfg.key_path().is_file(), **config}))
            return 0
        backend = config["backend"]
        for key, value in (("base_url", args.base_url), ("model", args.model), ("guard_model", args.guard_model),
                           ("timeout", args.timeout)):
            if value is not None:
                backend[key] = value
        if args.read_root is not None:
            config["read_roots"] = sorted({str(Path(root).expanduser().resolve()) for root in args.read_root})
        if args.network:
            config["network"]["enabled"] = args.network == "on"
        if args.model_guard:
            config["use_model_guard"] = args.model_guard == "on"
        path = cfg.save(config)
        if args.api_key_stdin:
            key = sys.stdin.readline() if not sys.stdin.isatty() else getpass.getpass("API key（不回显）：")
            if key.strip():
                cfg.save_key(key)
        print(f"配置已写入 {path}；密钥文件{'已存在' if cfg.key_path().is_file() else '未设置（使用环境变量 TH_API_KEY）'}。")
        return 0

    if args.command == "engine":
        from th.cli import main as engine_main

        rest = [item for item in args.rest if item != "--"]
        # Global options of the research-state CLI precede its subcommand.
        leading = [item for item in rest if item == "--json"]
        rest = [item for item in rest if item != "--json"]
        store_args = ["--store", str(Path(args.store or config["store"]).expanduser())]
        return engine_main(store_args + leading + rest)

    if args.command == "serve":
        from server.app import serve as serve_surface

        return serve_surface(config=config, store_path=args.store or config["store"], port=args.port,
                             open_browser=not args.no_browser)

    store = _store(config, args.store)
    if args.command == "chat":
        return chat(config, store)
    if args.command == "ask":
        _print(_teacher(config, store).ask(args.text), args.json)
        return 0
    if args.command == "frame-check":
        draft = json.loads(Path(args.draft).read_text(encoding="utf-8"))
        _print(frame_check(store, args.brief, draft), args.json)
        return 0
    if args.command == "check-answer":
        answer = json.loads(Path(args.answer).read_text(encoding="utf-8"))
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        try:
            result = check_answer(store, brief=args.brief, kind=args.kind, answer=answer, evidence=evidence,
                                  roots=config.get("read_roots") or [], network=config.get("network") or {},
                                  steps=args.steps)
        except Exception as exc:  # noqa: BLE001
            codes = sorted(set(getattr(exc, "risk_codes", []) or [C.RISK_SCHEMA]))
            print(render_json({"schema": "th-check-answer/v1", "ok": False, "risk_codes": codes}))
            return 3
        _print(result, args.json)
        return 0
    if args.command == "index":
        plan = retrieval.plan_index(args.root)
        if args.apply:
            _print(retrieval.apply_index(store, plan, expect_plan_sha256=args.apply), True)
        else:
            summary = {key: plan[key] for key in ("root", "files", "pdf_files", "pdf_extractor", "plan_sha256")}
            summary["next"] = f"teacher.py index {plan['root']} --apply {plan['plan_sha256']}"
            _print(summary, True)
        return 0
    if args.command == "archive":
        proposal = archive.propose(store)
        if args.choice:
            if not args.plan:
                print("应用归档需要 --plan（即先前展示的 plan_sha256）。")
                return 2
            receipt = archive.apply(store, proposal, choice=args.choice, expect_plan_sha256=args.plan)
            _print({**receipt, "visible": Renderer().render_archive_receipt(receipt)}, args.json)
        else:
            _print({**proposal, "visible": Renderer().render_archive_proposal(proposal)}, args.json)
        return 0
    if args.command == "status":
        _print(_status(store), True)
        return 0
    if args.command == "cognition":
        from th.cognition import current_cognition

        _print(current_cognition(store), True)
        return 0
    if args.command.startswith("coach-"):
        coach = _coach(config, store)
        if args.command == "coach-start":
            result = coach.start(args.problem)
        elif args.command == "coach-step":
            result = coach.step(args.text, role=args.role, connects=args.connects)
        elif args.command == "coach-route":
            result = coach.summary()
        elif args.command == "coach-done":
            result = coach.complete(policy=args.policy)
        elif args.command == "coach-hint":
            result = coach.hint()
        elif args.command == "coach-incubate":
            result = coach.incubate(args.kind, list(args.anchors))
        else:
            result = coach.exit()
        _print(result, args.json)
        return 0
    if args.command == "project-propose":
        _print(_teacher(config, store).propose_objective(), args.json)
        return 0
    if args.command == "project-bind":
        objective = json.loads(Path(args.objective).read_text(encoding="utf-8"))
        _print(_teacher(config, store).bind_objective(objective), args.json)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
