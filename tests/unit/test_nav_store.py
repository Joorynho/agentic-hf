"""
Unit tests for NavStore — SQLite-backed NAV history store.
"""

import pytest

from src.core.state.nav_store import NavStore


@pytest.fixture()
def store(tmp_path):
    """Fresh in-memory-equivalent store in a temp dir."""
    db_path = str(tmp_path / "test_nav.db")
    s = NavStore(db_path)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(store, pod_id, nav, cash=0.0, invested=0.0, realized=0.0, ts=None):
    store.write_snapshot(pod_id, nav=nav, cash=cash, invested=invested,
                         realized=realized, ts=ts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWriteAndReadHistory:
    def test_round_trip_single_pod(self, store):
        """Written rows come back intact."""
        _write(store, "equities", nav=100_000.0, cash=50_000.0,
               invested=50_000.0, realized=1_000.0, ts="2026-01-01T00:00:00")

        rows = store.read_history(pod_id="equities")

        assert len(rows) == 1
        r = rows[0]
        assert r["pod_id"] == "equities"
        assert r["nav"] == pytest.approx(100_000.0)
        assert r["cash"] == pytest.approx(50_000.0)
        assert r["invested"] == pytest.approx(50_000.0)
        assert r["realized"] == pytest.approx(1_000.0)
        assert r["ts"] == "2026-01-01T00:00:00"

    def test_multiple_writes_sorted_ascending(self, store):
        """Multiple rows are returned sorted by ts ascending."""
        _write(store, "equities", nav=100_000.0, ts="2026-01-03T00:00:00")
        _write(store, "equities", nav=101_000.0, ts="2026-01-01T00:00:00")
        _write(store, "equities", nav=102_000.0, ts="2026-01-02T00:00:00")

        rows = store.read_history(pod_id="equities")

        assert len(rows) == 3
        navs = [r["nav"] for r in rows]
        assert navs == [101_000.0, 102_000.0, 100_000.0]  # sorted by ts

    def test_limit_is_respected(self, store):
        for i in range(10):
            _write(store, "equities", nav=float(i), ts=f"2026-01-{i+1:02d}T00:00:00")

        rows = store.read_history(pod_id="equities", limit=3)
        assert len(rows) == 3

    def test_auto_timestamp_when_ts_none(self, store):
        """write_snapshot uses current UTC time when ts is None."""
        _write(store, "equities", nav=999.0)  # ts=None
        rows = store.read_history(pod_id="equities")
        assert len(rows) == 1
        assert rows[0]["ts"] is not None
        assert len(rows[0]["ts"]) > 0


class TestReadHistoryFilter:
    def test_pod_id_filter_excludes_other_pods(self, store):
        _write(store, "equities", nav=100.0, ts="2026-01-01T00:00:00")
        _write(store, "fx", nav=200.0, ts="2026-01-01T00:00:00")
        _write(store, "equities", nav=110.0, ts="2026-01-02T00:00:00")

        rows = store.read_history(pod_id="equities")

        assert len(rows) == 2
        assert all(r["pod_id"] == "equities" for r in rows)

    def test_no_filter_returns_all_pods(self, store):
        _write(store, "equities", nav=100.0, ts="2026-01-01T00:00:00")
        _write(store, "fx", nav=200.0, ts="2026-01-02T00:00:00")

        rows = store.read_history()
        assert len(rows) == 2

    def test_empty_db_returns_empty_list(self, store):
        rows = store.read_history(pod_id="equities")
        assert rows == []

    def test_empty_db_no_filter_returns_empty_list(self, store):
        rows = store.read_history()
        assert rows == []


class TestReadFirmHistory:
    def test_aggregates_pods_per_timestamp(self, store):
        """nav/cash/invested/realized are summed across pods for same ts."""
        ts = "2026-01-01T00:00:00"
        _write(store, "equities", nav=100_000.0, cash=40_000.0,
               invested=60_000.0, realized=1_000.0, ts=ts)
        _write(store, "fx", nav=50_000.0, cash=20_000.0,
               invested=30_000.0, realized=500.0, ts=ts)

        rows = store.read_firm_history()

        assert len(rows) == 1
        r = rows[0]
        assert r["ts"] == ts
        assert r["nav"] == pytest.approx(150_000.0)
        assert r["cash"] == pytest.approx(60_000.0)
        assert r["invested"] == pytest.approx(90_000.0)
        assert r["realized"] == pytest.approx(1_500.0)

    def test_multiple_timestamps_sorted_ascending(self, store):
        _write(store, "equities", nav=100.0, ts="2026-01-02T00:00:00")
        _write(store, "equities", nav=200.0, ts="2026-01-01T00:00:00")

        rows = store.read_firm_history()

        assert len(rows) == 2
        assert rows[0]["ts"] == "2026-01-01T00:00:00"
        assert rows[1]["ts"] == "2026-01-02T00:00:00"

    def test_limit_applied_to_last_n_timestamps(self, store):
        for i in range(10):
            _write(store, "equities", nav=float(i * 1000),
                   ts=f"2026-01-{i+1:02d}T00:00:00")

        rows = store.read_firm_history(limit=3)

        assert len(rows) == 3
        # Should be last 3 timestamps in ascending order
        assert rows[0]["ts"] == "2026-01-08T00:00:00"
        assert rows[1]["ts"] == "2026-01-09T00:00:00"
        assert rows[2]["ts"] == "2026-01-10T00:00:00"

    def test_empty_db_returns_empty_list(self, store):
        assert store.read_firm_history() == []

    def test_multiple_pods_different_timestamps(self, store):
        """Two pods writing at different timestamps produce separate entries."""
        _write(store, "equities", nav=100.0, ts="2026-01-01T00:00:00")
        _write(store, "fx",       nav=200.0, ts="2026-01-02T00:00:00")

        rows = store.read_firm_history()

        assert len(rows) == 2
        assert rows[0]["nav"] == pytest.approx(100.0)
        assert rows[1]["nav"] == pytest.approx(200.0)


class TestClose:
    def test_close_can_be_called_safely(self, tmp_path):
        db_path = str(tmp_path / "close_test.db")
        s = NavStore(db_path)
        # Should not raise
        s.close()

    def test_double_close_does_not_raise(self, tmp_path):
        db_path = str(tmp_path / "double_close.db")
        s = NavStore(db_path)
        s.close()
        s.close()  # second close must be silent

    def test_parent_dirs_created(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "nav.db")
        s = NavStore(deep_path)
        s.close()
        from pathlib import Path
        assert Path(deep_path).exists()
