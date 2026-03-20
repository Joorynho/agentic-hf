from src.backtest.accounting.capital_allocator import CapitalAllocator


def _make_allocator(pod_ids: list[str]) -> CapitalAllocator:
    alloc = CapitalAllocator.__new__(CapitalAllocator)
    n = len(pod_ids)
    alloc._allocations = {p: 1.0 / n for p in pod_ids}
    return alloc


def test_suggest_reallocation_floor():
    alloc = _make_allocator(["equities", "crypto", "fx", "commodities"])
    scores = {"equities": 0.80, "crypto": 0.05, "fx": 0.60, "commodities": 0.40}
    new_allocs = alloc.suggest_reallocation(scores)
    assert all(v >= 0.10 for v in new_allocs.values())
    assert abs(sum(new_allocs.values()) - 1.0) < 0.001


def test_better_scorer_gets_more():
    alloc = _make_allocator(["good", "bad"])
    scores = {"good": 0.80, "bad": 0.20}
    new_allocs = alloc.suggest_reallocation(scores)
    assert new_allocs["good"] > new_allocs["bad"]


def test_compute_target_capitals():
    alloc = _make_allocator(["equities", "crypto"])
    alloc._allocations = {"equities": 0.60, "crypto": 0.40}
    targets = alloc.compute_target_capitals(1000.0)
    assert targets["equities"] == 600.0
    assert targets["crypto"] == 400.0


def test_empty_scores_returns_current():
    alloc = _make_allocator(["equities", "crypto"])
    new_allocs = alloc.suggest_reallocation({})
    assert new_allocs == alloc._allocations


def test_single_pod_gets_full_allocation():
    alloc = _make_allocator(["equities"])
    scores = {"equities": 0.75}
    new_allocs = alloc.suggest_reallocation(scores)
    assert abs(new_allocs["equities"] - 1.0) < 0.001
