"""Coach, HARD_LOCK: the learner owns the route.

This path exists for practice: the learner proposes the steps of an algorithm
design, a correctness or complexity argument, a derivation, an experiment
design or a debugging hypothesis, and the Coach checks each step. The Coach
never supplies an answer, a complete argument, a decisive new idea or a
replacement route.

The data-flow property on this path is stronger than on the answer path:

    no model-authored text reaches the screen at all.

The renderer receives only closed values — admission status, epistemic code,
decision, first-error category, route progress, byte-verified learner quotes
and counts — and prints fixed sentences. Admission uses two isolated calls
(reviewer and auditor) that must agree; a step review uses two isolated calls
(coach and guard) that must agree on scope and route progress. Disagreement,
malformed output or an unavailable backend fails closed with a fixed sentence.

Completion is a gate, not a declaration: `strict` is computed from the attempt
graph; `lenient` needs two isolated closed opinions that agree. A passing gate
renders the learner's own route map deterministically; it adds no solution.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from . import constants as C
from .backend import BackendError, StructuredBackend, UnavailableBackend
from .model import ModelError, digest, new_id, utc_now
from .store import Store

SAFE_COACH_FAILURE = "本轮反馈无法在安全边界内生成。请把当前步骤再拆小一些，并写明所用依据。"

TEXT = {
    "READY_NONE": "初始化检查已通过。请写出你准备尝试的第一步，并说明这一步依据什么；在你提交尝试前，Coach 不提供解题内容。",
    "READY_OPEN": "题目已准入探索，但它的真值没有得到认证；局部成功不能当作整个论断成立的证明。请写出你准备尝试的第一步，并说明依据。",
    "NOT_CS_AI": "这不是一个计算机科学或人工智能的练习问题，Coach 不会为它建立训练。",
    "NEEDS_CLARIFICATION": "题目还不能唯一理解：缺少目标、定义、输入约定、量词或关键条件。请补全题目后重新提交。",
    "INCORRECT_AS_STATED": "按现在的表述，题目的前提或要求不成立。请核对题目原文后重新提交。",
    "UNVERIFIED": "题目的结构检查没能可靠完成，训练暂不开始。请稍后重试，或把题目写得更完整。",
    "input_rejected": "请写出一个具体的步骤，并说明这一步依据什么；只要答案、只问对不对、列候选方法都不能进入检查。",
    "sealed": "这道题的训练已经封存。要练新的题目，请提交新题。",
    "no_problem": "还没有正在训练的题目。先用 /coach 提交一道题。",
    "state_unverified": "请重新陈述你当前正在检查的那一步，并说明它使用了哪些已经写出的依据；在状态重新确认前，Coach 不补充任何新的内容。",
}

DECISION_TEXT = {
    "valid_so_far": "这一步在局部成立（不代表整条路线已经成功）。",
    "invalid": "这一步不成立。",
    "needs_justification": "这一步可能可用，但你给出的依据不足以支持它。",
    "unclear": "现有信息不足以安全判断这一步。",
    "not_applicable": "这条输入不属于步骤检查。",
}

ERROR_TEXT = {
    "ASSUMPTION_FALSE": "前提不成立",
    "QUANTIFIER_ERROR": "量词或适用范围用错（对所有输入 / 存在某个输入 / 高概率）",
    "BOUNDARY_CASE_OMITTED": "漏掉了边界情形（空输入、单元素、溢出、退化情形）",
    "INVARIANT_BROKEN": "循环不变式或归纳假设没有保持",
    "COMPLEXITY_MISCOUNT": "复杂度计数有误或代价模型不一致",
    "TYPE_OR_SHAPE_MISMATCH": "类型或张量形状不匹配",
    "UNJUSTIFIED_STEP": "这一步的推导没有依据",
    "NOT_EQUIVALENT": "变换前后并不等价",
    "CASE_OMISSION": "分情况讨论不完整",
    "CIRCULAR_REASONING": "循环论证",
    "LOGIC_GAP": "逻辑缺口",
    "ARITHMETIC_ERROR": "计算错误",
    "DATA_LEAKAGE": "评测数据泄漏进了训练或选择过程",
    "METRIC_MISUSE": "指标用错或与结论不对应",
    "DEPENDENCY_MISSING": "依赖的前一步尚未建立",
}

PROGRESS_TEXT = {"progressed": "路线有推进", "stalled": "路线停滞", "unclear": "推进情况不明", "not_applicable": "不适用"}

COMPLETION_TEXT = {
    "NOT_COMPLETE": "完成检查：尚未发现已经跑通的路线。本次只给阶段性整理；第一个未解决的义务是：{obligation}。",
    "ROUTE_READY": "完成检查：ROUTE_READY（宽松标准）。下面是你的试错路线图，只整理你自己的步骤，不补充新的解法。",
    "VERIFIED_SOLVED": "完成检查：VERIFIED_SOLVED（严格标准）。下面是你已经核验的完整路线图。",
}

OBLIGATION_TEXT = {
    "no_conclusion": "提交并核验结论",
    "no_valid_step": "提交至少一个经检查成立的步骤",
    "open_error": "修复已经记录的错误",
    "reviewers_disagree": "两位独立复核意见不一致",
}

# Conservative syntax barrier: inputs that are only answer requests.
ANSWER_REQUEST_RE = re.compile(
    r"(直接(给|告诉|说)|给我(答案|完整|标准)|答案是什么|完整(证明|解答|代码)|标准(解法|答案)|最优解是|"
    r"give me the (answer|solution|proof)|just tell me|full (solution|proof)|what is the answer)",
    re.I,
)
YES_NO_ONLY_RE = re.compile(r"^\s*(对不对|是不是|对吗|是吗|行不行|is (it|this) (right|correct))[？?。.!！]*\s*$", re.I)
SLASH_RE = re.compile(r"(^|\s)/[a-zA-Z]")

ADMIT_KEYS = ("admission", "epistemic", "certainty")
AUDIT_KEYS = ("allow", "consistent", "risk_codes")
REVIEW_KEYS = ("decision", "first_error", "focus_quote", "route_progress", "scope", "resolves_obstacle")
GUARD_KEYS = ("allow", "risk_codes", "route_progress", "scope", "resolves_obstacle")
OFFER_COOLDOWN = 3
SCOPES = ("current_problem", "off_topic")


INCUBATION_KINDS = ("targeted_question", "obstacle_map", "conditional_hypothesis")
QUESTION_CODES = ("relation_between", "assumption_role", "first_obstacle", "conditional_if_then")
QUESTION_TEMPLATES = {
    "relation_between": "你写的「{a}」和「{b}」之间，你打算用哪一条关系把它们连起来？请写出这条关系和它的依据。",
    "assumption_role": "「{a}」这一步用到了题目里的哪一个条件？如果去掉那个条件，这一步还成立吗？",
    "first_obstacle": "围绕「{a}」，你记录的第一个障碍卡在哪个具体条件上？请把它写成一个你能检查的小问题。",
    "conditional_if_then": "待验证的问题（未证实，也不属于你的路线）：如果「{a}」成立，能否推出「{b}」？想采用它，请用你自己的依据重新提交。",
}
INCUBATE_KEYS = ("question_code", "primary_node_id", "secondary_node_id", "certainty")
HINT_LIMIT = 120


class CoachError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _closed(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ModelError(f"{C.RISK_SCHEMA}: closed keys expected {list(keys)}")
    return value


def _enum(value: Any, allowed: Any, *, nullable: bool = False) -> Any:
    """Membership only after a type check, so a list or an object in a model
    answer is a schema failure rather than a crash."""

    if value is None and nullable:
        return None
    if not isinstance(value, str) or value not in allowed:
        raise ModelError(C.RISK_SCHEMA)
    return value


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ModelError(C.RISK_SCHEMA)
    return value


def gate_step(text: str) -> str | None:
    """Deterministic input gate. Returns a rejection code, or None."""

    if not isinstance(text, str) or len(text.strip()) < 6:
        return "input_rejected"
    if SLASH_RE.search(text):
        return "input_rejected"
    if YES_NO_ONLY_RE.match(text) or (ANSWER_REQUEST_RE.search(text) and len(text.strip()) < 80):
        return "input_rejected"
    return None


class Coach:
    def __init__(self, store: Store, *, backend: StructuredBackend | None = None,
                 guard_backend: StructuredBackend | None = None, timeout: float = 120.0) -> None:
        self.store = store
        self.backend: StructuredBackend = backend if backend is not None else UnavailableBackend()
        self.guard_backend: StructuredBackend = guard_backend or self.backend
        self.timeout = timeout

    # -- persistence ------------------------------------------------------
    def _write(self, action: str, problem: Mapping[str, Any], nodes: list[dict[str, Any]] | None = None) -> None:
        def mutate(connection: Any) -> dict[str, Any]:
            self.store.put_coach_problem(connection, dict(problem))
            for node in nodes or []:
                self.store.put_coach_node(connection, node)
            return {"action": action, "notes": [problem["problem_id"]]}

        self.store.transact(
            operation_id=new_id("COACH"),
            head=C.HEAD_EXECUTION,
            expected=self.store.head(C.HEAD_EXECUTION),
            request={"problem_id": problem["problem_id"], "action": action, "state": problem["state"]},
            mutate=mutate,
        )

    def active(self) -> dict[str, Any] | None:
        problem = self.store.latest_coach_problem()
        if problem is None or problem["state"] != "HARD_LOCK":
            return None
        return problem

    # -- initialization ---------------------------------------------------
    def start(self, problem_text: str) -> dict[str, Any]:
        if not isinstance(problem_text, str) or not problem_text.strip():
            return {"status": "refused", "visible": TEXT["NEEDS_CLARIFICATION"]}
        current = self.active()
        if current is not None:
            # A clearly new problem closes the current one; it is never left
            # open and unreachable.
            self._write("coach_superseded", {**current, "state": "SEALED", "superseded_at": utc_now()})
        packet = {
            "schema": "th-coach-problem/v1",
            "problem": problem_text,
            "admissions": list(C.COACH_ADMISSIONS),
            "epistemic": list(C.COACH_EPISTEMIC),
            "instruction": "Classify admission only. Do not solve, hint, repair or give a counterexample.",
        }
        admission, epistemic = "UNVERIFIED", "NONE"
        try:
            review = _closed(self.backend.coach_admit(packet, timeout=self.timeout), ADMIT_KEYS)
            _enum(review["admission"], C.COACH_ADMISSIONS)
            _enum(review["epistemic"], C.COACH_EPISTEMIC)
            audit = _closed(self.guard_backend.coach_audit(packet, dict(review), timeout=self.timeout), AUDIT_KEYS)
            _bool(audit["allow"])
            _bool(audit["consistent"])
            if audit["allow"] and audit["consistent"]:
                admission, epistemic = review["admission"], review["epistemic"]
            # Disagreement about structural admission stays UNVERIFIED; it never
            # falls back to a single-review READY.
        except (BackendError, ModelError):
            admission, epistemic = "UNVERIFIED", "NONE"
        if admission != "READY":
            epistemic = "NONE"
        problem = {
            "schema": "th-coach-problem-state/v1",
            "problem_id": new_id("CP"),
            "problem_sha256": digest(problem_text),
            "problem": problem_text,
            "admission": admission,
            "epistemic": epistemic,
            "state": "HARD_LOCK" if admission == "READY" else "SEALED",
            "created_at": utc_now(),
        }
        self._write("coach_admitted", problem)
        if admission == "READY":
            visible = TEXT["READY_NONE"] if epistemic == "NONE" else TEXT["READY_OPEN"]
        else:
            visible = TEXT[admission]
        return {"status": "admitted" if admission == "READY" else "blocked", "admission": admission,
                "epistemic": epistemic, "problem_id": problem["problem_id"], "visible": visible}

    # -- steps -------------------------------------------------------------
    def step(self, text: str, *, role: str = "local_step", connects: int | None = None) -> dict[str, Any]:
        problem = self.active()
        if problem is None:
            latest = self.store.latest_coach_problem()
            return {"status": "refused", "visible": TEXT["sealed"] if latest else TEXT["no_problem"]}
        if role not in C.COACH_ROLES:
            return {"status": "refused", "visible": TEXT["input_rejected"]}
        rejected = gate_step(text)
        if rejected:
            return {"status": "refused", "visible": TEXT[rejected]}
        nodes = self.store.coach_nodes(problem["problem_id"])
        learner = [node for node in nodes if node["origin"] == "learner"]
        open_obstacle = next((node for node in nodes if node["origin"] == "coach" and node["role"] == "obstacle"
                              and node["status"] == "open"), None)
        if role == "conclusion" and open_obstacle is not None:
            # No conclusion is sent for checking while a recorded error is open.
            return {"status": "refused", "visible": "还有一个已记录的错误没有修复（"
                    + ERROR_TEXT[open_obstacle["first_error"]] + "）。先修复它，再提交结论。"}
        connection = None
        if role == "exploratory_idea":
            if connects is None or not 0 <= connects <= len(learner):
                return {"status": "refused", "visible": "探索性想法需要写明它连到哪里：/idea 步骤编号 内容（0 表示题目本身）。"}
            connection = "problem" if connects == 0 else learner[connects - 1]["text"][:600]
        packet = {
            "schema": "th-coach-step/v1",
            "problem": problem["problem"],
            "learner_history": [
                {"ordinal": node["ordinal"], "role": node["role"], "status": node["status"], "text": node["text"]}
                for node in learner
            ][-12:],
            "open_obstacle": ERROR_TEXT[open_obstacle["first_error"]] if open_obstacle else None,
            "step": text,
            "role": role,
            "connects_to": connection,
            "decisions": list(C.COACH_DECISIONS),
            "first_errors": list(C.COACH_FIRST_ERRORS),
            "instruction": (
                "Judge only this learner step against the learner's own record. Return closed values. "
                "focus_quote must be copied verbatim from the step. resolves_obstacle is true only if this step "
                "repairs the open obstacle. Never propose a method, object or next step."
            ),
        }
        try:
            draft = _closed(self.backend.coach_review(packet, timeout=self.timeout), REVIEW_KEYS)
            _enum(draft["decision"], C.COACH_DECISIONS)
            _enum(draft["route_progress"], PROGRESS_TEXT)
            _enum(draft["scope"], SCOPES)
            _enum(draft["first_error"], C.COACH_FIRST_ERRORS, nullable=True)
            _bool(draft["resolves_obstacle"])
            if draft["decision"] == "invalid" and draft["first_error"] is None:
                raise ModelError(C.RISK_SCHEMA)
            quote = draft["focus_quote"]
            if quote is not None and (not isinstance(quote, str) or not quote.strip() or quote not in text or len(quote) > 200):
                raise ModelError("quote_unverified")
            verdict = _closed(self.guard_backend.coach_guard(packet, dict(draft), timeout=self.timeout), GUARD_KEYS)
            if _bool(verdict["allow"]) is not True:
                raise ModelError("coach_content_leak")
            _enum(verdict["route_progress"], PROGRESS_TEXT)
            _enum(verdict["scope"], SCOPES)
            _bool(verdict["resolves_obstacle"])
            if (verdict["route_progress"] != draft["route_progress"] or verdict["scope"] != draft["scope"]
                    or (open_obstacle is not None and verdict["resolves_obstacle"] != draft["resolves_obstacle"])):
                # Copying an unverified classification is not agreement.
                raise ModelError(C.RISK_ASSESSMENT_INCONSISTENT)
        except (BackendError, ModelError) as exc:
            self.store.observe(event_type="coach_step_failed",
                               payload={"problem_id": problem["problem_id"], "code": type(exc).__name__},
                               mutate=lambda connection: None)
            return {"status": "failed", "visible": SAFE_COACH_FAILURE}

        if draft["scope"] == "off_topic":
            count = int(problem.get("off_topic_count", 0)) + 1
            self._write("coach_off_topic", {**problem, "off_topic_count": count})
            if count == 1:
                return {"status": "off_topic", "visible": "这条内容与当前题目无关。Coach 只陪你做当前这道题：请提交一个具体步骤和它的依据，或用 /exit 结束练习。"}
            return {"status": "off_topic", "visible": "Coach 不继续与当前题目无关的内容。"}

        if draft["decision"] == "not_applicable":
            return {"status": "checked", "decision": "not_applicable", "first_error": None,
                    "visible": DECISION_TEXT["not_applicable"] + "\n请提交一个具体步骤，并说明依据。"}

        ordinal = max((node["ordinal"] for node in nodes), default=0) + 1
        status = {"valid_so_far": "verified", "invalid": "refuted"}.get(draft["decision"], "unresolved")
        learner_node = {
            "node_id": new_id("CN"), "problem_id": problem["problem_id"], "ordinal": ordinal,
            "origin": "learner", "role": role, "status": status, "text": text,
            "decision": draft["decision"], "first_error": draft["first_error"],
            # Only a judged attempt earns hint eligibility.
            "attempt": draft["decision"] in ("valid_so_far", "invalid", "needs_justification"),
            "connects": connects,
        }
        new_nodes = [learner_node]
        if draft["decision"] == "invalid":
            new_nodes.append({
                "node_id": new_id("CN"), "problem_id": problem["problem_id"], "ordinal": ordinal + 1,
                "origin": "coach", "role": "obstacle", "status": "open", "text": "",
                "blocks": learner_node["node_id"], "first_error": draft["first_error"],
            })
        resolved = False
        if (open_obstacle is not None and draft["decision"] == "valid_so_far"
                and draft["resolves_obstacle"] and role != "exploratory_idea"):
            # Both isolated calls agreed that this valid step repairs the open
            # obstacle; the learner cannot resolve it by saying so.
            new_nodes.append({**open_obstacle, "status": "resolved", "resolved_by": learner_node["node_id"],
                              "resolved_at": ordinal})
            resolved = True
        offer = self._stall_offer(problem, learner + [learner_node], text, draft)
        state = dict(problem)
        if offer:
            state["last_offer_ordinal"] = ordinal
        self._write("coach_step", state, new_nodes)

        lines = [DECISION_TEXT[draft["decision"]]]
        if draft["first_error"]:
            lines.append(f"第一个能确定的问题：{ERROR_TEXT[draft['first_error']]}。")
        if draft["focus_quote"]:
            lines.append(f"对应你写的：“{draft['focus_quote']}”")
        if resolved:
            lines.append("先前记录的那个错误已由这一步修复。")
        lines.append(f"（{PROGRESS_TEXT[draft['route_progress']]}）")
        if draft["decision"] in ("invalid", "needs_justification", "unclear"):
            lines.append("请修复或重新陈述这一步，并写明它依据的是哪些已经写出的内容。")
        else:
            lines.append("请提交下一步，并说明依据。")
        if offer:
            lines.append("你已经在同一处卡了几轮。需要看一下只含你自己步骤的路线整理吗？输入 /route。")
        lines.append("（本段由确定性渲染器生成，不含模型撰写的文字。）")
        return {"status": "checked", "decision": draft["decision"], "first_error": draft["first_error"],
                "visible": "\n".join(lines)}

    @staticmethod
    def _stall_offer(problem: Mapping[str, Any], learner: list[dict[str, Any]], text: str,
                     draft: Mapping[str, Any]) -> bool:
        """Offer a route summary on three consecutive unverified steps or a
        repeated refuted step; after an offer, wait for three new learner steps
        or a new verified step before offering again."""

        last = int(problem.get("last_offer_ordinal", 0))
        since = [node for node in learner if node["ordinal"] > last]
        if last and len(since) < OFFER_COOLDOWN and not any(node["status"] == "verified" for node in since[:-1]):
            return False
        recent = learner[-3:]
        repeated = draft["decision"] == "invalid" and any(
            node["status"] == "refuted" and node["text"].strip() == text.strip() for node in learner[:-1])
        return (len(recent) == 3 and all(node["status"] != "verified" for node in recent)) or repeated

    # -- guarded exceptions -----------------------------------------------
    def _latest(self, problem: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for node in self.store.coach_nodes(problem["problem_id"]):
            latest[node["node_id"]] = node
        return latest

    def hint(self) -> dict[str, Any]:
        """HINT_ONCE: the only coach path where model text is shown.

        Eligible only when a genuine learner attempt was stored after the last
        visible hint and an obstacle is open. The hint addresses that obstacle,
        is at most 120 characters, and is guarded together with every earlier
        hint so small disclosures cannot accumulate into a solution. It is
        labelled as outside the HARD_LOCK output guarantee.
        """

        problem = self.active()
        if problem is None:
            return {"status": "refused", "visible": TEXT["no_problem"]}
        latest = self._latest(problem)
        nodes = sorted(latest.values(), key=lambda node: node["ordinal"])
        hints = [node for node in nodes if node["role"] == "hint"]
        last_hint = hints[-1]["ordinal"] if hints else 0
        attempts_since = [node for node in nodes if node["origin"] == "learner" and node.get("attempt")
                          and node["ordinal"] > last_hint]
        obstacle = next((node for node in nodes if node["origin"] == "coach" and node["role"] == "obstacle" and node["status"] == "open"), None)
        if not attempts_since or obstacle is None:
            return {"status": "refused", "visible": "现在没有可用的提示：需要先有一个已记录的障碍，并且在上次提示之后提交过新的尝试。"}
        packet = {
            "schema": "th-coach-hint/v1",
            "problem": problem["problem"],
            "obstacle": ERROR_TEXT[obstacle["first_error"]],
            "learner_history": [{"role": node["role"], "status": node["status"], "text": node["text"]}
                                for node in nodes if node["origin"] == "learner"][-8:],
            "earlier_hints": [node["text"] for node in hints],
            "limit_chars": HINT_LIMIT,
        }
        try:
            raw = self.backend.coach_hint(packet, timeout=self.timeout)
            if not isinstance(raw, dict) or set(raw) != {"hint"} or not isinstance(raw["hint"], str):
                raise ModelError(C.RISK_SCHEMA)
            text = " ".join(raw["hint"].split())
            if not text or len(text) > HINT_LIMIT or text.count("$") > 2 or "\n" in raw["hint"].strip():
                raise ModelError("length_exceeded")
            verdict = _closed(self.guard_backend.coach_guard({**packet, "mode": "hint"}, {"hint": text}, timeout=self.timeout), GUARD_KEYS)
            if _bool(verdict["allow"]) is not True or _enum(verdict["scope"], SCOPES) != "current_problem":
                raise ModelError("coach_content_leak")
        except (BackendError, ModelError):
            return {"status": "failed", "visible": SAFE_COACH_FAILURE}
        node = {"node_id": new_id("CN"), "problem_id": problem["problem_id"], "ordinal": len(nodes) + 1,
                "origin": "coach", "role": "hint", "status": "shown", "text": text}
        self._write("coach_hint", problem, [node])
        return {"status": "hint", "visible": f"提示（一次）：{text}\n（本提示不属于 HARD_LOCK 的绝对输出保证。）"}

    def incubate(self, kind: str, anchors: list[int]) -> dict[str, Any]:
        """Anchored research incubation around learner-owned nodes only.

        `obstacle_map` is deterministic. The other two ask a model to pick a
        closed question code and existing learner node ids; the text shown is a
        fixed template filled with at most 120 characters copied from the
        learner's own nodes. Nothing is written to the attempt graph, and one
        model-backed incubation is allowed per new learner node.
        """

        problem = self.active()
        if problem is None:
            return {"status": "refused", "visible": TEXT["no_problem"]}
        if kind not in INCUBATION_KINDS:
            return {"status": "refused", "visible": "孵化类型只能是 targeted_question、obstacle_map 或 conditional_hypothesis。"}
        if kind == "obstacle_map":
            return self.summary()
        latest = self._latest(problem)
        learner = [node for node in sorted(latest.values(), key=lambda node: node["ordinal"]) if node["origin"] == "learner"]
        if not learner:
            return {"status": "refused", "visible": "先提交至少一个你自己的步骤，再请求孵化。"}
        chosen = []
        for index in anchors:
            if not 1 <= index <= len(learner):
                return {"status": "refused", "visible": "锚点必须是你路线里的步骤编号。"}
            chosen.append(learner[index - 1])
        if not 1 <= len(chosen) <= 2 or len({node["node_id"] for node in chosen}) != len(chosen):
            return {"status": "refused", "visible": "请给一个或两个不同的步骤编号。"}
        if kind == "conditional_hypothesis" and len(chosen) != 2:
            return {"status": "refused", "visible": "条件性假设需要恰好两个步骤编号。"}
        incubations = [node for node in latest.values() if node["role"] == "incubation"]
        if incubations and max(node["ordinal"] for node in incubations) > max(node["ordinal"] for node in learner):
            return {"status": "refused", "visible": "上一次孵化之后你还没有提交新的步骤；先推进一步再来。"}
        packet = {
            "schema": "th-coach-incubation/v1",
            "kind": kind,
            "nodes": [{"id": node["node_id"], "text": node["text"][:600]} for node in chosen],
            "question_codes": ["conditional_if_then"] if kind == "conditional_hypothesis" else
                              ["relation_between", "assumption_role", "first_obstacle"],
        }
        ids = {node["node_id"]: node for node in chosen}
        try:
            raw = _closed(self.backend.coach_incubate(packet, timeout=self.timeout), INCUBATE_KEYS)
            _enum(raw["question_code"], packet["question_codes"])
            _enum(raw["primary_node_id"], ids)
            _enum(raw["secondary_node_id"], ids, nullable=True)
            _enum(raw["certainty"], ("high", "medium", "low"))
            if raw["secondary_node_id"] == raw["primary_node_id"]:
                raise ModelError(C.RISK_SCHEMA)
            if raw["question_code"] in ("relation_between", "conditional_if_then") and raw["secondary_node_id"] is None:
                raise ModelError(C.RISK_SCHEMA)
            verdict = _closed(self.guard_backend.coach_guard({**packet, "mode": "incubation"}, dict(raw), timeout=self.timeout), GUARD_KEYS)
            if _bool(verdict["allow"]) is not True or _enum(verdict["scope"], SCOPES) != "current_problem":
                raise ModelError("coach_content_leak")
        except (BackendError, ModelError):
            return {"status": "failed", "visible": "本次研究孵化无法在安全边界内生成，路线没有改变。"}
        first = ids[raw["primary_node_id"]]["text"][:120]
        second = ids[raw["secondary_node_id"]]["text"][:120] if raw["secondary_node_id"] else ""
        marker = {"node_id": new_id("CN"), "problem_id": problem["problem_id"],
                  "ordinal": max(node["ordinal"] for node in latest.values()) + 1,
                  "origin": "coach", "role": "incubation", "status": "shown", "text": ""}
        self._write("coach_incubation", problem, [marker])
        visible = QUESTION_TEMPLATES[raw["question_code"]].format(a=first, b=second)
        return {"status": "incubated", "visible": visible + "\n（本段由固定模板与你的原话生成，不含模型撰写的文字。）"}

    # -- summaries and completion ----------------------------------------
    def summary(self) -> dict[str, Any]:
        problem = self.store.latest_coach_problem()
        if problem is None:
            return {"status": "refused", "visible": TEXT["no_problem"]}
        nodes = self.store.coach_nodes(problem["problem_id"])
        latest: dict[str, dict[str, Any]] = {}
        for node in nodes:
            latest[node["node_id"]] = node
        lines = ["你的路线（只含你自己写下的步骤与记录的状态）："]
        index = 0
        for node in latest.values():
            if node["origin"] != "learner":
                continue
            index += 1
            status = {"verified": "成立", "refuted": "不成立", "unresolved": "未定"}[node["status"]]
            lines.append(f"{index}. [{status}] {node['text'][:120]}")
        obstacle = next((node for node in latest.values() if node["origin"] == "coach" and node["status"] == "open"), None)
        if obstacle:
            lines.append(f"第一个未解决的义务：{ERROR_TEXT[obstacle['first_error']]}。")
        if problem["state"] == "HARD_LOCK":
            lines.append("可选：继续修复 ｜ 提交另一个你自己的想法（/idea 步骤编号 内容） ｜ /exit 封存。")
        else:
            lines.append("这道题的练习已经封存。")
        return {"status": "ok", "visible": "\n".join(lines)}

    def complete(self, *, policy: str = "strict") -> dict[str, Any]:
        """Completion is a gate.

        `lenient` → ROUTE_READY: no open recorded error, at least one verified
        learner step, and two isolated audits agree that only routine
        exposition remains. `strict` → VERIFIED_SOLVED: computed from the graph —
        no open error, a verified local step, and a verified conclusion that
        comes after every recorded error and its repair.
        """

        problem = self.active()
        if problem is None:
            return {"status": "refused", "visible": TEXT["no_problem"]}
        if policy not in ("strict", "lenient"):
            return {"status": "refused", "visible": "完成标准只能是 strict 或 lenient。"}
        nodes = self.store.coach_nodes(problem["problem_id"])
        learner = [node for node in nodes if node["origin"] == "learner"]
        obstacles = [node for node in nodes if node["origin"] == "coach" and node["role"] == "obstacle"]
        open_errors = [node for node in obstacles if node["status"] == "open"]
        valid_steps = [node for node in learner if node["role"] == "local_step" and node["status"] == "verified"]
        last_error_point = max([node["ordinal"] for node in obstacles] + [int(node.get("resolved_at", 0)) for node in obstacles],
                               default=0)
        conclusion = next((node for node in reversed(learner)
                           if node["role"] == "conclusion" and node["status"] == "verified"
                           and node["ordinal"] > last_error_point
                           and any(step["ordinal"] < node["ordinal"] for step in valid_steps)), None)

        obligation = None
        if open_errors:
            obligation = "open_error"
        elif not valid_steps:
            obligation = "no_valid_step"
        elif policy == "strict" and conclusion is None:
            obligation = "no_conclusion"

        status = "NOT_COMPLETE"
        if obligation is None:
            if policy == "strict":
                status = "VERIFIED_SOLVED"
            else:
                packet = {"schema": "th-coach-completion/v1", "problem": problem["problem"], "policy": "lenient",
                          "route": [{"role": node["role"], "status": node["status"], "text": node["text"]} for node in learner]}
                try:
                    first = _closed(self.backend.coach_audit(packet, {"policy": "lenient"}, timeout=self.timeout), AUDIT_KEYS)
                    second = _closed(self.guard_backend.coach_audit(packet, {"policy": "lenient"}, timeout=self.timeout), AUDIT_KEYS)
                    if all(_bool(item["allow"]) and _bool(item["consistent"]) for item in (first, second)):
                        status = "ROUTE_READY"
                    else:
                        obligation = "reviewers_disagree"
                except (BackendError, ModelError):
                    obligation = "reviewers_disagree"
        if status == "NOT_COMPLETE":
            visible = COMPLETION_TEXT[status].format(obligation=OBLIGATION_TEXT[obligation])
            return {"status": status, "visible": visible + "\n" + self.summary()["visible"]}

        sealed = {**problem, "state": "SEALED", "completion": status, "sealed_at": utc_now()}
        self._write("coach_completed", sealed)
        lines = [COMPLETION_TEXT[status], "试错路线图："]
        for index, node in enumerate(learner, start=1):
            mark = {"verified": "✓", "refuted": "✗", "unresolved": "?"}[node["status"]]
            lines.append(f"  {index}. {mark} [{node['role']}] {node['text'][:160]}")
        lines.append("可迁移的模式、练习选择请你自己总结；Coach 不在这里补写新的解法。")
        lines.append("（本段由确定性渲染器生成，不含模型撰写的文字。）")
        return {"status": status, "visible": "\n".join(lines)}

    def exit(self) -> dict[str, Any]:
        problem = self.active()
        if problem is None:
            return {"status": "refused", "visible": TEXT["no_problem"]}
        self._write("coach_exited", {**problem, "state": "SEALED", "exited": True, "exited_at": utc_now()})
        return {"status": "exited", "visible": "训练已封存。这道题不会在本会话里转成答案模式。"}


def protected_problem_overlap(store: Store, text: str, *, threshold: float = 0.5) -> bool:
    """True when `text` asks about a practice problem that is still protected.

    Protected means: in active practice, or closed without passing completion
    (exited or superseded by a new problem). Leaving practice never turns the
    same problem into an answer. A problem that passed completion is not
    protected. The check is lexical and conservative: a clearly different
    question passes, and a disguised rewording is not claimed to be caught.
    """

    def terms(value: str) -> set[str]:
        lowered = value.casefold()
        words = set(re.findall(r"[a-z0-9_]{2,}", lowered))
        cjk = re.sub(r"[^一-鿿]", "", lowered)
        words |= {cjk[index:index + 2] for index in range(len(cjk) - 1)}
        return words

    asked = terms(text)
    if not asked:
        return False
    import json

    for row in store.rows("SELECT body FROM coach_problems"):
        problem = json.loads(row["body"])
        if problem.get("admission") != "READY" or problem.get("completion"):
            continue
        known = terms(problem.get("problem", ""))
        if known and len(asked & known) / max(1, min(len(asked), len(known))) >= threshold:
            return True
    return False


# The name used by the answer path.
exited_problem_overlap = protected_problem_overlap
