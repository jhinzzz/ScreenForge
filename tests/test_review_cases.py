"""多用例分组 + 权威判定：_build_cases / record_case_result。

这些是工作树相对 plan 的扩展逻辑（失败优先、span 跟踪、有判定无 step 的用例），
plan 未覆盖测试 —— 在此补齐。纯内存，无浏览器。
"""

from review.recorder import ReviewRecorder, StepRecord


def _rec_with_steps(*tests: str) -> ReviewRecorder:
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    for i, nid in enumerate(tests, start=1):
        rec.current_test = nid
        rec.add(StepRecord(step_index=i, action="click"))
    return rec


def test_step_inherits_current_test():
    rec = _rec_with_steps("t.py::a", "t.py::a")
    assert [s.test for s in rec.records] == ["t.py::a", "t.py::a"]


def test_explicit_step_test_not_overwritten():
    rec = ReviewRecorder()
    rec.current_test = "t.py::a"
    rec.add(StepRecord(step_index=1, action="click", test="t.py::explicit"))
    assert rec.records[0].test == "t.py::explicit"


def test_build_cases_tracks_span_and_order():
    rec = _rec_with_steps("t.py::a", "t.py::a", "t.py::b")
    cases = rec._build_cases()
    assert [c["nodeid"] for c in cases] == ["t.py::a", "t.py::b"]
    a, b = cases
    assert (a["step_from"], a["step_to"]) == (1, 2)
    assert (b["step_from"], b["step_to"]) == (3, 3)


def test_record_case_result_failure_priority():
    # setup 先 pass，call 再 fail → 应保持 failed；之后再来一个 pass 不得翻盘。
    rec = ReviewRecorder()
    rec.record_case_result("t.py::a", "passed", duration=0.1)
    rec.record_case_result("t.py::a", "failed", duration=0.2, error="boom")
    rec.record_case_result("t.py::a", "passed", duration=0.3)
    assert rec.case_results["t.py::a"]["outcome"] == "failed"
    assert rec.case_results["t.py::a"]["error"] == "boom"


def test_build_cases_includes_verdict_without_steps():
    # 用例在断言/前置阶段失败、未触发任何被 patch 操作 → 无 step 但仍须出现在 cases。
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.record_case_result("t.py::no_steps", "failed", error="assert failed")
    cases = rec._build_cases()
    assert len(cases) == 1
    c = cases[0]
    assert c["nodeid"] == "t.py::no_steps"
    assert c["outcome"] == "failed"
    assert (c["step_from"], c["step_to"]) == (0, 0)


def test_build_cases_merges_verdict_onto_stepful_case():
    rec = _rec_with_steps("t.py::a")
    rec.record_case_result("t.py::a", "passed", duration=0.5)
    (c,) = rec._build_cases()
    assert c["outcome"] == "passed"
    assert c["duration"] == 0.5
    assert (c["step_from"], c["step_to"]) == (1, 1)


def test_build_cases_empty_when_no_attribution():
    rec = _rec_with_steps()  # 无 step、无判定
    assert rec._build_cases() == []


def test_record_case_result_skipped_outcome():
    # makereport 的 skip 分支：单列 skipped，不被当作 passed/failed。
    rec = ReviewRecorder()
    rec.record_case_result("t.py::s", "skipped", duration=0.0)
    (c,) = rec._build_cases()
    assert c["outcome"] == "skipped"
    assert (c["step_from"], c["step_to"]) == (0, 0)


def test_build_cases_preserves_execution_order_with_stepless_case():
    # 真实执行序: a(有 step) → b(断言阶段失败、无 step) → c(有 step)。
    # 顺序以 case_results 的插入序（makereport 真实执行序）为准，b 不得被甩到末尾。
    rec = ReviewRecorder()
    rec.start_run(run_id="r1", platform="web", test_file="t.py")
    rec.current_test = "t.py::a"
    rec.add(StepRecord(step_index=1, action="click"))
    rec.record_case_result("t.py::a", "passed")
    rec.record_case_result("t.py::b", "failed", error="assert 1==2")  # 无 step
    rec.current_test = "t.py::c"
    rec.add(StepRecord(step_index=2, action="goto"))
    rec.record_case_result("t.py::c", "passed")
    assert [c["nodeid"] for c in rec._build_cases()] == ["t.py::a", "t.py::b", "t.py::c"]
