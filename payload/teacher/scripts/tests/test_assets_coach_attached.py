"""Assets, retrieval, the coach HARD_LOCK path, and attached use."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from th import archive, retrieval  # noqa: E402
from th.attached import check_answer, frame_check  # noqa: E402
from th.backend import ScriptedBackend  # noqa: E402
from th.broker import Broker, OperationRefused, validate_request  # noqa: E402
from th.coach import Coach  # noqa: E402
from th.cognition import current_cognition  # noqa: E402
from th.store import Store  # noqa: E402
from th import constants as C  # noqa: E402

CANARY = "MODEL_CANARY_c0ac4::no-surface::END"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.store = Store(self.root / "s.sqlite3")
        self.store.init()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()


class RetrievalTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.notes = self.root / "notes"
        self.notes.mkdir()
        (self.notes / "adam.md").write_text("# Adam\n\nAdam keeps running averages of gradients.\n\n# Bias\n\nBias correction divides by 1-beta^t.\n", encoding="utf-8")

    def index(self) -> dict:
        plan = retrieval.plan_index(self.notes)
        return retrieval.apply_index(self.store, plan, expect_plan_sha256=plan["plan_sha256"])

    def test_indexing_requires_the_exact_plan_hash(self) -> None:
        plan = retrieval.plan_index(self.notes)
        with self.assertRaises(retrieval.RetrievalError):
            retrieval.apply_index(self.store, plan, expect_plan_sha256="0" * 64)
        self.assertEqual(retrieval.index_status(self.store)["roots"], [])

    def test_search_returns_candidates_not_bodies(self) -> None:
        self.index()
        found = retrieval.search_sections(self.store, "running averages")
        self.assertEqual(found["total_matches"], 1)
        candidate = found["candidates"][0]
        self.assertEqual(set(candidate), {"section_id", "path", "heading", "snippet"})
        self.assertLessEqual(len(candidate["snippet"]), retrieval.SNIPPET_CHARS)
        self.assertIn("coverage_note", found)

    def test_reading_rereads_the_current_file(self) -> None:
        self.index()
        section = retrieval.search_sections(self.store, "Bias correction")["candidates"][0]["section_id"]
        (self.notes / "adam.md").write_text("# Adam\n\nchanged\n\n# Bias\n\nBias correction divides by (1-beta^t), updated.\n", encoding="utf-8")
        read = retrieval.read_section(self.store, section)
        self.assertEqual(read["state"], "changed_since_index")
        self.assertIn("updated", read["text"])
        (self.notes / "adam.md").write_text("# Other\n\nnothing\n", encoding="utf-8")
        self.assertEqual(retrieval.read_section(self.store, section)["state"], "stale")

    def test_network_operations_obey_policy(self) -> None:
        broker = Broker(read_roots=(), store=self.store, network={"enabled": False})
        with self.assertRaises(OperationRefused):
            broker.execute(validate_request({"operation": "fetch_url", "arguments": {"url": "https://arxiv.org/abs/1706.03762"}}))
        broker = Broker(read_roots=(), store=self.store, network={"enabled": True, "allow_domains": ["arxiv.org"]})
        with self.assertRaises(OperationRefused):
            broker.execute(validate_request({"operation": "fetch_url", "arguments": {"url": "https://evil.example/x"}}))

    def test_arxiv_results_become_excerpts(self) -> None:
        class Fake:
            @staticmethod
            def arxiv_search(query, policy):
                return {"entries": [{"id": "1706.03762", "url": "http://arxiv.org/abs/1706.03762v7", "title": "Attention Is All You Need",
                                     "published": "2017-06-12", "authors": ["A. Vaswani"], "summary": "The dominant sequence transduction models..."}],
                        "total_matches": 40, "omitted": 39}

        broker = Broker(read_roots=(), store=self.store, network={"enabled": True}, fetcher=Fake())
        result = broker.execute(validate_request({"operation": "arxiv_search", "arguments": {"query": "attention"}}))
        self.assertEqual(result["value"]["omitted"], 39)
        self.assertEqual(result["excerpts"][0]["kind"], "retrieved_source")
        self.assertIn("Attention Is All You Need", result["excerpts"][0]["text"])

    def test_declared_command_output_reaches_the_model_only_as_an_excerpt(self) -> None:
        broker = Broker(read_roots=(self.root,), declared_commands={"tests": ("true",)},
                        executor=lambda command, cwd, timeout: (0, "3 passed\n", ""))
        result = broker.execute(validate_request({"operation": "run_declared", "arguments": {"name": "tests", "arguments": []}}))
        self.assertNotIn("stdout", result["value"])
        self.assertEqual(result["excerpts"][0]["kind"], "executed_check")
        self.assertEqual(result["excerpts"][0]["returncode"], 0)


def _ask_with(points, unknowns=(), ask_id="ASK-1"):
    return {"ask_id": ask_id, "answer": {"points": points, "unknowns": list(unknowns)}}


def _point(text, basis="retrieved_source", grade="bounded_empirical", evidence=("E-1",), quote=None):
    return {"text": text, "strength": "bounded", "basis": basis, "grade": grade, "evidence": list(evidence),
            "quote": quote, "cannot_imply": "不能推出更大规模也成立"}


class ArchiveTests(Base):
    def seed(self) -> None:
        evidence = {"E-1": {"kind": "retrieved_source", "locator": "notes/a.md#A", "text": "x"},
                    "E-2": {"kind": "executed_check", "locator": "run:bench:returncode=1", "text": "fail", "returncode": 1}}
        candidates = archive.candidates_from_answer(
            _ask_with([_point("结论一"), _point("仅推理", basis="reasoning", grade=None, evidence=())], ["未知一"]),
            evidence, self.store)

        def mutate(connection):
            for candidate in candidates:
                self.store.put_candidate(connection, candidate)
            return {"action": "seed"}

        self.store.transact(operation_id="seed", head=C.HEAD_EXECUTION, expected=self.store.head(C.HEAD_EXECUTION),
                            request={}, mutate=mutate)

    def test_reasoning_never_becomes_a_claim_candidate(self) -> None:
        self.seed()
        kinds = sorted(item["kind"] for item in self.store.candidates())
        self.assertEqual(kinds, ["claim", "failure", "open_question", "source"])
        self.assertNotIn("仅推理", [item["text"] for item in self.store.candidates()])

    def test_duplicates_are_not_proposed_twice(self) -> None:
        self.seed()
        again = archive.candidates_from_answer(_ask_with([_point("结论 一")]), {"E-1": {"kind": "retrieved_source", "locator": "notes/a.md#A", "text": "x"}}, self.store)
        self.assertEqual(again, [])

    def test_one_decision_bound_to_the_shown_list(self) -> None:
        self.seed()
        proposal = archive.propose(self.store)
        before = self.store.head(C.HEAD_AUTHORITY)
        with self.assertRaises(archive.ArchiveError):
            archive.apply(self.store, proposal, choice="all", expect_plan_sha256="f" * 64)
        self.assertEqual(self.store.head(C.HEAD_AUTHORITY), before)
        receipt = archive.apply(self.store, proposal, choice="verified_only", expect_plan_sha256=proposal["plan_sha256"])
        self.assertEqual(receipt["archived"], 3)          # claim, source, failure
        self.assertEqual(receipt["kept_pending"], 1)      # the open question stays pending
        self.assertNotEqual(self.store.head(C.HEAD_AUTHORITY), before)
        # The archived material is now found before anything else is searched.
        self.assertEqual(retrieval.search_library(self.store, "结论一")["total_matches"], 1)

    def test_cognition_is_recomputed_from_the_library(self) -> None:
        self.seed()
        proposal = archive.propose(self.store)
        archive.apply(self.store, proposal, choice="verified_only", expect_plan_sha256=proposal["plan_sha256"])
        cognition = current_cognition(self.store)
        self.assertIn("结论一", cognition["text"])
        self.assertIn("不能推出更大规模也成立", cognition["text"])
        self.assertTrue(cognition["receipt"]["continues"])


def admit(admission="READY", epistemic="NONE"):
    return {"admission": admission, "epistemic": epistemic, "certainty": "high"}


def audit(allow=True, consistent=True):
    return {"allow": allow, "consistent": consistent, "risk_codes": []}


def review(decision="valid_so_far", first_error=None, quote=None, progress="progressed", resolves=False, scope="current_problem"):
    return {"decision": decision, "first_error": first_error, "focus_quote": quote,
            "route_progress": progress, "scope": scope, "resolves_obstacle": resolves}


def guard(progress="progressed", allow=True, resolves=False, scope="current_problem"):
    return {"allow": allow, "risk_codes": [], "route_progress": progress, "scope": scope, "resolves_obstacle": resolves}


PROBLEM = "证明：在长度为 n 的数组上，二分查找在最坏情况下比较 O(log n) 次。"
STEP = "每次比较后搜索区间长度至少减半，所以 k 次比较后区间长度不超过 n/2^k。"


class CoachTests(Base):
    def coach(self, **queues) -> Coach:
        return Coach(self.store, backend=ScriptedBackend(**queues))

    def test_admission_needs_two_agreeing_reviews(self) -> None:
        result = self.coach(coach_admissions=[admit()], coach_audits=[audit(consistent=False)]).start(PROBLEM)
        self.assertEqual(result["admission"], "UNVERIFIED")
        result = self.coach(coach_admissions=[admit(epistemic="TRUTH_UNVERIFIED")], coach_audits=[audit()]).start(PROBLEM)
        self.assertEqual(result["admission"], "READY")
        self.assertIn("真值没有得到认证", result["visible"])

    def test_a_step_is_judged_with_closed_values_only(self) -> None:
        coach = self.coach(coach_admissions=[admit()], coach_audits=[audit()],
                           coach_reviews=[review(decision="invalid", first_error="BOUNDARY_CASE_OMITTED", quote="区间长度至少减半")],
                           coach_guards=[guard()])
        coach.start(PROBLEM)
        result = coach.step(STEP)
        self.assertEqual(result["decision"], "invalid")
        self.assertIn("漏掉了边界情形", result["visible"])
        self.assertIn("“区间长度至少减半”", result["visible"])
        self.assertIn("不含模型撰写的文字", result["visible"])

    def test_a_fabricated_quote_or_disagreeing_guard_fails_closed(self) -> None:
        coach = self.coach(coach_admissions=[admit()], coach_audits=[audit()],
                           coach_reviews=[review(quote=CANARY), review()],
                           # The first step fails before its guard is asked, so the
                           # only guard verdict belongs to the second step.
                           coach_guards=[guard(progress="stalled")])
        coach.start(PROBLEM)
        first = coach.step(STEP)
        second = coach.step(STEP)
        for result in (first, second):
            self.assertEqual(result["status"], "failed")
            self.assertNotIn(CANARY, result["visible"])
        self.assertEqual([node for node in self.store.coach_nodes(coach.active()["problem_id"])], [])

    def test_answer_requests_never_reach_a_model(self) -> None:
        backend = ScriptedBackend(coach_admissions=[admit()], coach_audits=[audit()])
        coach = Coach(self.store, backend=backend)
        coach.start(PROBLEM)
        for text in ("直接告诉我答案", "对不对？", "/hint"):
            self.assertEqual(coach.step(text)["status"], "refused")
        self.assertNotIn("coach_review", backend.calls)

    def test_strict_completion_is_computed_and_the_review_is_the_learners_route(self) -> None:
        coach = self.coach(coach_admissions=[admit()], coach_audits=[audit()],
                           coach_reviews=[review(decision="invalid", first_error="LOGIC_GAP"),
                                          review(resolves=True), review()],
                           coach_guards=[guard(), guard(resolves=True), guard()])
        coach.start(PROBLEM)
        coach.step(STEP)
        self.assertEqual(coach.complete()["status"], "NOT_COMPLETE")
        # No conclusion is even sent for checking while the error is open.
        self.assertEqual(coach.step("所以最坏比较次数是 O(log n)，证毕。", role="conclusion")["status"], "refused")
        repaired = coach.step("补充：区间为空时循环终止，所以比较次数不超过 floor(log2 n)+1。")
        self.assertIn("已由这一步修复", repaired["visible"])
        self.assertIn("提交并核验结论", coach.complete()["visible"])
        coach.step("所以最坏比较次数是 O(log n)，证毕。", role="conclusion")
        done = coach.complete()
        self.assertEqual(done["status"], "VERIFIED_SOLVED")
        self.assertIn("试错路线图", done["visible"])
        self.assertIn(STEP[:20], done["visible"])
        self.assertIsNone(coach.active())


class CoachFlowTests(Base):
    def started(self, **queues) -> Coach:
        base = {"coach_admissions": [admit()], "coach_audits": [audit()]}
        base.update(queues)
        coach = Coach(self.store, backend=ScriptedBackend(**base))
        coach.start(PROBLEM)
        return coach

    def test_a_valid_step_resolves_an_obstacle_only_when_both_calls_agree(self) -> None:
        coach = self.started(coach_reviews=[review(decision="invalid", first_error="LOGIC_GAP"), review(resolves=True)],
                             coach_guards=[guard(), guard(resolves=False)])
        coach.step(STEP)
        self.assertEqual(coach.step("补一个与该错误无关的正确观察：数组有序。")["status"], "failed")

    def test_an_unrelated_valid_step_does_not_resolve_the_error(self) -> None:
        coach = self.started(coach_reviews=[review(decision="invalid", first_error="LOGIC_GAP"), review()],
                             coach_guards=[guard(), guard()])
        coach.step(STEP)
        coach.step("数组是有序的，这一点题目已经给出。")
        self.assertIn("修复已经记录的错误", coach.complete()["visible"])

    def test_a_malformed_value_fails_closed_instead_of_crashing(self) -> None:
        coach = self.started(coach_reviews=[dict(review(), route_progress=["progressed"])], coach_guards=[guard()])
        self.assertEqual(coach.step(STEP)["status"], "failed")

    def test_lenient_is_route_ready_without_a_conclusion(self) -> None:
        coach = self.started(coach_reviews=[review()], coach_guards=[guard()],
                             coach_audits=[audit(), audit(), audit()])
        coach.step(STEP)
        self.assertEqual(coach.complete(policy="lenient")["status"], "ROUTE_READY")

    def test_exploratory_ideas_must_name_what_they_connect_to(self) -> None:
        backend = ScriptedBackend(coach_admissions=[admit()], coach_audits=[audit()])
        coach = Coach(self.store, backend=backend)
        coach.start(PROBLEM)
        self.assertEqual(coach.step("试试用递归树来数比较次数。", role="exploratory_idea")["status"], "refused")
        self.assertNotIn("coach_review", backend.calls)

    def test_off_topic_gets_one_reminder_then_a_fixed_refusal(self) -> None:
        coach = self.started(coach_reviews=[review(scope="off_topic"), review(scope="off_topic")],
                             coach_guards=[guard(scope="off_topic"), guard(scope="off_topic")])
        first = coach.step("顺便问一下今天的新闻怎么样呀")
        second = coach.step("再聊聊电影好不好呀朋友")
        self.assertIn("只陪你做当前这道题", first["visible"])
        self.assertEqual(second["visible"], "Coach 不继续与当前题目无关的内容。")

    def test_a_new_problem_seals_the_current_one(self) -> None:
        coach = self.started()
        first = coach.active()["problem_id"]
        coach.backend._queues["coach_admissions"].append(admit())
        coach.backend._queues["coach_audits"].append(audit())
        coach.start("证明：归并排序的时间复杂度是 O(n log n)。")
        self.assertNotEqual(coach.active()["problem_id"], first)
        self.assertEqual(self.store.coach_problem(first)["state"], "SEALED")

    def test_an_exited_problem_does_not_become_an_answer(self) -> None:
        from th.teach import Teacher

        coach = self.started()
        coach.exit()
        result = Teacher(self.store, backend=ScriptedBackend()).ask("二分查找最坏情况下比较次数为什么是 O(log n)，给我证明")
        self.assertEqual(result["status"], "refused")
        other = Teacher(self.store, backend=ScriptedBackend()).ask("Adam 优化器的偏差修正是什么意思")
        self.assertNotEqual(other.get("code"), "protected_practice_problem")

    def test_active_and_superseded_problems_are_protected_and_switch_cannot_bypass(self) -> None:
        from th.teach import Teacher

        coach = self.started()
        teacher = Teacher(self.store, backend=ScriptedBackend())
        self.assertEqual(teacher.ask("二分查找最坏情况比较次数 O(log n) 的证明是什么")["status"], "refused")
        coach.backend._queues["coach_admissions"].append(admit())
        coach.backend._queues["coach_audits"].append(audit())
        coach.start("证明：归并排序的时间复杂度是 O(n log n)。")
        self.assertEqual(teacher.ask("二分查找最坏情况比较次数 O(log n) 的证明是什么")["status"], "refused")
        # A frame recorded earlier cannot be re-answered around the check.
        from th import need

        frame = need.new_frame("二分查找最坏情况比较次数为什么是 O(log n)")
        frame.update({"status": need.STATUS_ANSWERED, "interpretations": [{"id": 1, "text": "x", "quote": "二分查找", "differs_by": "goal"}]})
        teacher._save_frame(frame, action="seed")
        self.assertEqual(teacher.switch(1)["status"], "refused")


class CoachExceptionTests(Base):
    def started(self, **queues) -> Coach:
        base = {"coach_admissions": [admit()], "coach_audits": [audit()]}
        base.update(queues)
        coach = Coach(self.store, backend=ScriptedBackend(**base))
        coach.start(PROBLEM)
        return coach

    def test_hint_needs_an_obstacle_and_a_new_attempt_and_is_labelled(self) -> None:
        coach = self.started(coach_reviews=[review(decision="invalid", first_error="LOGIC_GAP")], coach_guards=[guard(), guard()],
                             coach_hints=[{"hint": "看看区间为空时循环如何终止。"}, {"hint": "再来一次"}])
        self.assertEqual(coach.hint()["status"], "refused")
        coach.step(STEP)
        first = coach.hint()
        self.assertEqual(first["status"], "hint")
        self.assertIn("不属于 HARD_LOCK 的绝对输出保证", first["visible"])
        # No new attempt since the last hint: not eligible again.
        self.assertEqual(coach.hint()["status"], "refused")

    def test_an_overlong_hint_fails_closed(self) -> None:
        coach = self.started(coach_reviews=[review(decision="invalid", first_error="LOGIC_GAP")], coach_guards=[guard()],
                             coach_hints=[{"hint": "长" * 121}])
        coach.step(STEP)
        result = coach.hint()
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("长长长", result["visible"])

    def test_incubation_renders_a_fixed_template_from_learner_text(self) -> None:
        coach = self.started(coach_reviews=[review(), review()], coach_guards=[guard(), guard(), guard()],
                             coach_incubations=[{"question_code": "relation_between", "primary_node_id": None,
                                                 "secondary_node_id": None, "certainty": "medium"}])
        coach.step(STEP)
        coach.step("补充：区间为空时循环终止。")
        nodes = [node for node in self.store.coach_nodes(coach.active()["problem_id"]) if node["origin"] == "learner"]
        coach.backend._queues["coach_incubations"][0].update(primary_node_id=nodes[0]["node_id"], secondary_node_id=nodes[1]["node_id"])
        result = coach.incubate("targeted_question", [1, 2])
        self.assertEqual(result["status"], "incubated")
        self.assertIn("「每次比较后搜索区间长度至少减半", result["visible"])
        self.assertIn("不含模型撰写的文字", result["visible"])
        # One model-backed incubation per new learner node.
        self.assertEqual(coach.incubate("targeted_question", [1, 2])["status"], "refused")

    def test_incubation_rejects_foreign_anchors_before_any_model_call(self) -> None:
        backend = ScriptedBackend(coach_admissions=[admit()], coach_audits=[audit()], coach_reviews=[review()], coach_guards=[guard()])
        coach = Coach(self.store, backend=backend)
        coach.start(PROBLEM)
        coach.step(STEP)
        self.assertEqual(coach.incubate("conditional_hypothesis", [1])["status"], "refused")
        self.assertEqual(coach.incubate("targeted_question", [7])["status"], "refused")
        self.assertNotIn("coach_incubate", backend.calls)


class AttachedTests(Base):
    def test_frame_check_applies_the_same_rule(self) -> None:
        draft = {"kind": "concept_explanation", "stuck_point": "concept", "clarity": "ambiguous", "depth": "brief",
                 "interpretations": [{"text": "想知道动机", "quote": "为什么", "differs_by": "goal"},
                                     {"text": "想看推导", "quote": "除以", "differs_by": "output_form"}],
                 "material_ambiguity": True, "investigation_can_resolve": False, "defaults": []}
        result = frame_check(self.store, "为什么要除以根号d", draft)
        self.assertTrue(result["ask_requester"])
        self.assertIn("1) 想知道动机", result["visible"])

    def test_check_answer_rereads_local_files(self) -> None:
        notes = self.root / "notes"
        notes.mkdir()
        (notes / "a.md").write_text("Gradient clipping bounds the update norm.\n", encoding="utf-8")
        answer = {"conclusion": "裁剪限制更新范数。", "confidence": "medium", "explanation": [], "next_checks": [],
                  "followups": [], "unknowns": [],
                  "points": [{"text": "梯度裁剪限制每步更新的范数。", "strength": "observation", "basis": "retrieved_source",
                              "grade": None, "evidence": ["E1"], "quote": "Gradient clipping bounds the update norm.",
                              "cannot_imply": None}]}
        good = [{"id": "E1", "kind": "retrieved_source", "locator": "a.md", "text": "Gradient clipping bounds the update norm."}]
        result = check_answer(self.store, brief="梯度裁剪是干嘛的", kind="implementation_help", answer=answer,
                              evidence=good, roots=[str(notes)], network={"enabled": False})
        self.assertEqual(result["verification"]["E1"], "verified")
        self.assertEqual(result["metrics"]["excerpts_verified_by_harness"], 1)
        self.assertIn("片段由 Teacher 在原位置核对 1 条、只能采信 agent 0 条", result["visible"])
        forged = [{"id": "E1", "kind": "retrieved_source", "locator": "a.md", "text": "Gradient clipping bounds the update norm."
                   .replace("bounds", "removes")}]
        answer_forged = json.loads(json.dumps(answer).replace("bounds", "removes"))
        with self.assertRaises(Exception):
            # The excerpt is not in the file, so it is dropped, and the point citing it no longer resolves.
            check_answer(self.store, brief="梯度裁剪是干嘛的", kind="implementation_help", answer=answer_forged,
                         evidence=forged, roots=[str(notes)], network={"enabled": False})


class ConfigTests(unittest.TestCase):
    def test_the_key_never_enters_the_configuration(self) -> None:
        from th import config as cfg

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TEACHER_CONFIG_DIR"] = tmp
            try:
                config = cfg.load()
                config["backend"]["base_url"] = "https://example.invalid/v1"
                cfg.save(config)
                cfg.save_key("sk-" + "x" * 30)
                text = cfg.config_path().read_text(encoding="utf-8")
                self.assertNotIn("sk-", text)
                self.assertEqual(os.stat(cfg.key_path()).st_mode & 0o077, 0)
                env = cfg.backend_environment(cfg.load())
                if "TH_API_KEY" not in os.environ:
                    self.assertEqual(env["TH_API_KEY_FILE"], str(cfg.key_path()))
            finally:
                os.environ.pop("TEACHER_CONFIG_DIR", None)


if __name__ == "__main__":
    unittest.main()
