"""The Teacher loop: need discovery, investigation, the answer gate.

Every test injects a scripted backend. Each asserts a decision the harness
makes in code, and — where it matters — that a rejected candidate leaves no
trace in the store or on the surface.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from th import constants as C  # noqa: E402
from th import need  # noqa: E402
from th import retrieval  # noqa: E402
from th.answer import AnswerRejected, validate_answer  # noqa: E402
from th.backend import ScriptedBackend  # noqa: E402
from th.model import ModelError  # noqa: E402
from th.store import Store  # noqa: E402
from th.teach import Teacher  # noqa: E402

CANARY = "MODEL_CANARY_7d31::never-render::END"
BRIEF = "训练老是抖，想知道换掉损失函数有没有用"


def frame(**overrides):
    base = {
        "kind": "experiment_debugging",
        "stuck_point": "experiment_computation",
        "clarity": "clear",
        "depth": "brief",
        "interpretations": [{"text": "训练不稳定时换损失函数是否有帮助", "quote": "换掉损失函数", "differs_by": "goal"}],
        "material_ambiguity": False,
        "investigation_can_resolve": False,
        "defaults": ["python_pytorch_stack"],
    }
    base.update(overrides)
    return base


def ambiguous_frame(**overrides):
    values = {
        "clarity": "ambiguous",
        "interpretations": [
            {"text": "想定位训练抖动的根因", "quote": "训练老是抖", "differs_by": "goal"},
            {"text": "想比较几种损失函数的稳定性", "quote": "换掉损失函数", "differs_by": "object"},
        ],
        "material_ambiguity": True,
    }
    values.update(overrides)
    return frame(**values)


READY = {"action": "ready_to_answer", "operations": [], "reason_code": "enough_evidence"}


def reasoning_answer(**overrides):
    base = {
        "conclusion": "先确认抖动来自优化而不是数据，再考虑换损失函数。",
        "points": [{
            "text": "学习率过大时，换损失函数通常解决不了抖动。",
            "strength": "conditional", "basis": "reasoning", "grade": None,
            "evidence": [], "quote": None, "cannot_imply": "不能推出损失函数与抖动无关",
        }],
        "explanation": [],
        "unknowns": ["没有看到你的训练曲线与配置"],
        "next_checks": [{"text": "把学习率减半重跑一次", "operation": None}],
        "followups": [],
        "confidence": "low",
    }
    base.update(overrides)
    return base


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = Store(self.root / "s.sqlite3")
        self.store.init()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def teacher(self, backend, **kwargs) -> Teacher:
        return Teacher(self.store, backend=backend, contract={"network": {"enabled": False}}, **kwargs)

    def all_text(self) -> str:
        connection = sqlite3.connect(self.store.path)
        chunks = []
        for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            try:
                for row in connection.execute(f"SELECT * FROM {table}"):
                    chunks.extend(str(value) for value in row)
            except sqlite3.OperationalError:
                continue
        connection.close()
        return "\n".join(chunks)


class NeedDiscoveryTests(Base):
    def test_a_reading_must_quote_the_request(self) -> None:
        bad = frame(interpretations=[{"text": "x", "quote": "用户根本没说过的话", "differs_by": "goal"}])
        with self.assertRaises(ModelError):
            need.validate_frame_draft(bad, brief=BRIEF)

    def test_at_most_three_short_distinct_readings(self) -> None:
        many = [{"text": f"理解{i}", "quote": "训练", "differs_by": "goal"} for i in range(4)]
        with self.assertRaises(ModelError):
            need.validate_frame_draft(frame(clarity="ambiguous", interpretations=many), brief=BRIEF)
        long_text = [{"text": "长" * 81, "quote": "训练", "differs_by": "goal"}]
        with self.assertRaises(ModelError):
            need.validate_frame_draft(frame(interpretations=long_text), brief=BRIEF)
        duplicate = [{"text": "同一个理解", "quote": "训练", "differs_by": "goal"},
                     {"text": "同一个 理解", "quote": "抖", "differs_by": "object"}]
        with self.assertRaises(ModelError):
            need.validate_frame_draft(frame(clarity="ambiguous", interpretations=duplicate), brief=BRIEF)

    def test_clear_with_several_readings_is_incoherent(self) -> None:
        with self.assertRaises(ModelError):
            need.validate_frame_draft(ambiguous_frame(clarity="clear"), brief=BRIEF)

    def test_decision_rule(self) -> None:
        state = need.new_frame(BRIEF)
        self.assertEqual(need.decide(state, frame()), need.DECISION_PROCEED)
        self.assertEqual(need.decide(state, ambiguous_frame(material_ambiguity=False)), need.DECISION_PROCEED)
        self.assertEqual(need.decide(state, ambiguous_frame()), need.DECISION_ASK)
        self.assertEqual(need.decide(state, ambiguous_frame(investigation_can_resolve=True)), need.DECISION_INVESTIGATE_FIRST)
        # The one clarification is spent: the harness proceeds instead of asking again.
        spent = dict(state, clarifications_asked=1)
        self.assertEqual(need.decide(spent, ambiguous_frame()), need.DECISION_PROCEED)
        # Investigation was already tried once: now the requester may be asked.
        tried = dict(state, reframes=1)
        self.assertEqual(need.decide(tried, ambiguous_frame(investigation_can_resolve=True)), need.DECISION_ASK)

    def test_material_ambiguity_asks_one_closed_choice_and_nothing_else(self) -> None:
        backend = ScriptedBackend(frames=[ambiguous_frame()])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["status"], "clarify")
        self.assertIn("1) 想定位训练抖动的根因", result["visible"])
        self.assertIn("回复编号即可", result["visible"])
        # No investigation, no answer was attempted before the requester chose.
        self.assertEqual(backend.calls, ["frame_request"])

    def test_choice_by_digit_answers_that_reading_without_reframing(self) -> None:
        backend = ScriptedBackend(frames=[ambiguous_frame()], plans=[READY], answers=[reasoning_answer()])
        teacher = self.teacher(backend)
        teacher.ask(BRIEF)
        result = teacher.ask("2")
        self.assertEqual(result["status"], "answered", result)
        self.assertEqual(backend.calls.count("frame_request"), 1)
        self.assertIn("我的理解：想比较几种损失函数的稳定性", result["visible"])

    def test_enter_takes_the_default_and_new_text_extends_the_brief(self) -> None:
        backend = ScriptedBackend(frames=[ambiguous_frame(), frame()], plans=[READY], answers=[reasoning_answer()])
        teacher = self.teacher(backend)
        teacher.ask(BRIEF)
        result = teacher.ask("其实我是想问 loss 突然 nan 的问题")
        self.assertEqual(result["status"], "answered", result)
        packets = [packet for method, packet in backend.packets if method == "frame_request"]
        self.assertIn("loss 突然 nan", packets[-1]["brief"])
        self.assertIn(BRIEF, packets[-1]["brief"])

    def test_investigate_first_searches_the_requesters_material_before_asking(self) -> None:
        backend = ScriptedBackend(frames=[ambiguous_frame(investigation_can_resolve=True), frame()],
                                  plans=[READY], answers=[reasoning_answer()])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["status"], "answered")
        self.assertEqual(backend.calls.count("frame_request"), 2)


class InvestigationTests(Base):
    def test_assets_are_consulted_before_the_model_plans(self) -> None:
        backend = ScriptedBackend(frames=[frame()], plans=[READY], answers=[reasoning_answer()])
        self.teacher(backend).ask(BRIEF)
        plan_packet = next(packet for method, packet in backend.packets if method == "plan_step")
        operations = [item["operation"] for item in plan_packet["recent_results"]]
        self.assertEqual(operations[:2], ["search_library", "search_local"])

    def test_budget_is_enforced_and_reported(self) -> None:
        loop = {"action": "request_operations", "operations": [{"operation": "search_local", "arguments": {"query": "loss"}}],
                "reason_code": "need_source"}
        backend = ScriptedBackend(frames=[frame(depth="brief")], plans=[loop] * 10, answers=[reasoning_answer()])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(backend.calls.count("plan_step"), C.STEP_BUDGET["brief"])
        self.assertTrue(result["metrics"]["budget_exhausted"])
        self.assertIn("调查预算已用尽", result["visible"])

    def test_evidence_required_kind_cannot_skip_investigation(self) -> None:
        answer = reasoning_answer()
        backend = ScriptedBackend(frames=[frame(kind="literature_search", depth="standard")],
                                  plans=[READY] * 4, answers=[answer])
        result = self.teacher(backend).ask(BRIEF)
        # The harness kept asking for a plan instead of accepting "ready".
        self.assertEqual(backend.calls.count("plan_step"), C.STEP_BUDGET["standard"])
        self.assertEqual(result["status"], "answered")
        # No source exists anywhere: this is reported, and unknowns were required.
        self.assertTrue(result["metrics"]["sources_unavailable"])

    def test_a_refused_operation_is_counted_and_has_no_effect(self) -> None:
        plan = {"action": "request_operations", "operations": [{"operation": "fetch_url", "arguments": {"url": "https://example.com/x"}}],
                "reason_code": "need_source"}
        backend = ScriptedBackend(frames=[frame()], plans=[plan, READY], answers=[reasoning_answer()])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["metrics"]["operations_refused"], 1)


class AnswerGateTests(Base):
    def evidence(self):
        return {"E1": {"kind": "retrieved_source", "locator": "notes/a.md#x", "text": "Warmup stabilises early training."},
                "E2": {"kind": "executed_check", "locator": "run:tests:returncode=0", "text": "4 passed", "returncode": 0}}

    def investigation(self, **overrides):
        base = {"steps": 1, "budget": 2, "minimum_met": True, "budget_exhausted": False,
                "sources_unavailable": False, "omitted": 0}
        base.update(overrides)
        return base

    def check(self, answer, *, kind="experiment_debugging", **inv):
        return validate_answer(answer, kind=kind, evidence=self.evidence(), user_text=BRIEF,
                               investigation=self.investigation(**inv))

    def point(self, **overrides):
        base = {"text": "预热能稳定训练初期。", "strength": "bounded", "basis": "retrieved_source",
                "grade": "bounded_empirical", "evidence": ["E1"], "quote": "Warmup stabilises early training.",
                "cannot_imply": "不能推出对所有优化器都成立"}
        base.update(overrides)
        return base

    def test_a_well_formed_answer_passes_and_is_measured(self) -> None:
        metrics = self.check(reasoning_answer(points=[self.point()], unknowns=[], confidence="high"))
        self.assertEqual(metrics["quotes_verified"], 1)
        self.assertEqual(metrics["points_with_checked_evidence"], 1)
        self.assertFalse(metrics["semantic_correctness_proven"])

    def rejected(self, answer, **kwargs) -> list[str]:
        with self.assertRaises(AnswerRejected) as caught:
            self.check(answer, **kwargs)
        return caught.exception.risk_codes

    def test_fabricated_quote_is_rejected(self) -> None:
        self.assertIn("quote_unverified", self.rejected(reasoning_answer(points=[self.point(quote="Warmup always helps.")])))

    def test_unknown_evidence_is_rejected(self) -> None:
        self.assertIn("evidence_unresolved", self.rejected(reasoning_answer(points=[self.point(evidence=["E9"])])))

    def test_basis_and_evidence_kind_must_agree(self) -> None:
        self.assertIn("evidence_unresolved", self.rejected(reasoning_answer(points=[self.point(evidence=["E2"], quote=None)])))

    def test_reasoning_cannot_be_graded_or_universal(self) -> None:
        codes = self.rejected(reasoning_answer(points=[self.point(basis="reasoning", evidence=[], quote=None,
                                                                   strength="universal", grade=None)]))
        self.assertIn("reasoning_overclaim", codes)

    def test_a_program_that_ran_is_not_a_proof_checker(self) -> None:
        codes = self.rejected(reasoning_answer(points=[self.point(basis="executed_check", evidence=["E2"], quote=None,
                                                                   strength="universal", grade="formal")]))
        self.assertIn(C.RISK_EVIDENCE_INSUFFICIENT, codes)

    def test_a_retrieved_text_cannot_carry_formal_or_certificate(self) -> None:
        for grade in ("formal", "certificate"):
            codes = self.rejected(reasoning_answer(points=[self.point(strength="conditional", grade=grade)]))
            self.assertIn(C.RISK_EVIDENCE_INSUFFICIENT, codes)

    def test_strength_needs_grade_and_cannot_imply(self) -> None:
        self.assertIn(C.RISK_EVIDENCE_INSUFFICIENT,
                      self.rejected(reasoning_answer(points=[self.point(strength="universal", grade="bounded_empirical")])))
        self.assertIn(C.RISK_CANNOT_IMPLY_MISSING, self.rejected(reasoning_answer(points=[self.point(cannot_imply=None)])))

    def test_unknowns_are_mandatory_when_evidence_is_incomplete(self) -> None:
        self.assertIn("unknowns_missing", self.rejected(reasoning_answer(unknowns=[])))
        self.assertIn("unknowns_missing", self.rejected(reasoning_answer(points=[self.point()], unknowns=[]),
                                                          budget_exhausted=True))

    def test_high_confidence_needs_checked_evidence(self) -> None:
        self.assertIn("confidence_unsupported", self.rejected(reasoning_answer(confidence="high")))

    def test_explanations_must_dissect_the_step(self) -> None:
        self.assertIn("explanation_slots_missing", self.rejected(reasoning_answer(), kind="concept_explanation"))
        partial = reasoning_answer(explanation=[{"step": "a", "motivation": "b", "boundary": "", "alternative": "d"}])
        self.assertIn("explanation_slots_missing", self.rejected(partial, kind="concept_explanation"))

    def test_brevity_is_enforced(self) -> None:
        self.assertIn("length_exceeded", self.rejected(reasoning_answer(conclusion="长" * (C.LIMIT_CONCLUSION + 1))))
        too_many = [self.point(text=f"要点{i}") for i in range(C.MAX_POINTS + 1)]
        self.assertIn(C.RISK_SCHEMA, self.rejected(reasoning_answer(points=too_many)))

    def test_evidence_required_kind_without_investigation_is_rejected(self) -> None:
        self.assertIn("investigation_minimum_unmet",
                      self.rejected(reasoning_answer(), kind="literature_search", minimum_met=False))


class FailClosedTests(Base):
    def test_one_repair_then_success(self) -> None:
        bad = reasoning_answer(unknowns=[])
        backend = ScriptedBackend(frames=[frame()], plans=[READY], answers=[bad, reasoning_answer()])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["status"], "answered")
        repair = [packet for method, packet in backend.packets if method == "compose_answer"][-1]["repair"]
        self.assertEqual(repair["risk_codes"], ["unknowns_missing"])

    def test_two_rejections_fail_closed_and_leave_no_trace(self) -> None:
        bad = reasoning_answer(unknowns=[], conclusion=CANARY)
        backend = ScriptedBackend(frames=[frame()], plans=[READY], answers=[bad, bad])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn(CANARY, result["visible"])
        self.assertEqual(self.store.asks(), [])
        self.assertEqual(self.store.candidates(), [])
        self.assertNotIn(CANARY, self.all_text())

    def test_undeclared_keys_in_any_model_answer_are_rejected(self) -> None:
        extra = dict(reasoning_answer(), commentary=CANARY)
        backend = ScriptedBackend(frames=[dict(frame(), note=CANARY)])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["status"], "failed")
        backend = ScriptedBackend(frames=[frame()], plans=[READY], answers=[extra, extra])
        result = self.teacher(backend).ask(BRIEF)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn(CANARY, self.all_text())

    def test_a_guard_can_veto_but_never_approve(self) -> None:
        deny = {"allow": False, "risk_codes": ["quote_unverified"]}
        backend = ScriptedBackend(frames=[frame()], plans=[READY], answers=[reasoning_answer(), reasoning_answer()],
                                  answer_verdicts=[deny, deny])
        result = self.teacher(backend, use_model_guard=True).ask(BRIEF)
        self.assertEqual(result["status"], "failed")
        # An approving guard cannot rescue an answer the gate rejects.
        allow = {"allow": True, "risk_codes": []}
        backend = ScriptedBackend(frames=[frame()], plans=[READY], answers=[reasoning_answer(unknowns=[])] * 2,
                                  answer_verdicts=[allow, allow])
        result = self.teacher(backend, use_model_guard=True).ask(BRIEF)
        self.assertEqual(result["status"], "failed")

    def test_no_backend_fails_closed(self) -> None:
        result = Teacher(self.store).ask(BRIEF)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.store.asks(), [])


class EndToEndEvidenceTests(Base):
    def test_a_quote_from_a_retrieved_note_is_verified_and_shown(self) -> None:
        notes = self.root / "notes"
        notes.mkdir()
        (notes / "warmup.md").write_text("# Warmup\n\nLinear warmup over the first 2k steps stabilised training.\n", encoding="utf-8")
        plan = retrieval.plan_index(notes)
        retrieval.apply_index(self.store, plan, expect_plan_sha256=plan["plan_sha256"])
        calls = {"n": 0}

        def plan_step(packet, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                section = packet["recent_results"][1]["value"]["candidates"][0]["section_id"]
                return {"action": "request_operations", "reason_code": "need_detail",
                        "operations": [{"operation": "read_section", "arguments": {"section_id": section}}]}
            return READY

        def compose(packet, timeout=None):
            ref = [item for item in packet["evidence"] if "warmup" in item["text"].casefold()][-1]["id"]
            return reasoning_answer(points=[{
                "text": "你的笔记记录了预热让训练稳定。", "strength": "observation", "basis": "retrieved_source",
                "grade": "numerical_evidence", "evidence": [ref],
                "quote": "Linear warmup over the first 2k steps stabilised training.", "cannot_imply": None,
            }])

        backend = ScriptedBackend(frames=[frame(interpretations=[{"text": "预热是否有用", "quote": "warmup", "differs_by": "goal"}])])
        backend.plan_step = plan_step
        backend.compose_answer = compose
        teacher = self.teacher(backend)
        result = teacher.ask(BRIEF + " warmup")
        self.assertEqual(result["status"], "answered", result)
        self.assertIn("原文：“Linear warmup over the first 2k steps stabilised training.”", result["visible"])
        self.assertEqual(result["metrics"]["quotes_verified"], 1)
        self.assertIn("warmup.md#Warmup", teacher.expand("E1")["visible"] + teacher.expand("E2")["visible"])
        self.assertTrue(any(item["kind"] == "claim" for item in self.store.candidates()))


if __name__ == "__main__":
    unittest.main()
