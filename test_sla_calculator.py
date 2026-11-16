"""
Comprehensive Pytest Suite for ECE-008: Leased Line Uptime SLA and Penalty Calculator
Team ID: E043 (Vishnu Krishna & Vishrutha L)
Run with: pytest -v
"""

from datetime import datetime, timedelta
import pytest
from sla_calculator import SLACalculatorEngine, SLATier, SampleStatus


def add_samples_run(
    engine: SLACalculatorEngine,
    circuit_id: str,
    start_time: datetime,
    count: int,
    latency_ms: float = 10.0,
    packet_loss_pct: float = 0.0,
    reachable: bool = True,
) -> datetime:
    """Helper to ingest `count` consecutive 5-minute samples and return next timestamp."""
    curr = start_time
    for _ in range(count):
        engine.ingest_sample(circuit_id, curr, latency_ms, packet_loss_pct, reachable)
        curr += timedelta(minutes=5)
    return curr


# =====================================================================
# BR-01 & Explicit Edge Case: Sample Status Classification
# =====================================================================

def test_br01_sample_classification_silver_and_gold_thresholds():
    """
    BR-01: unreachable -> DOWN; latency > 40ms or loss > 0.5% -> DEGRADED for SILVER;
    GOLD uses 30ms and 0.2%.
    Edge Case: Latency exactly 40 ms is OK for SILVER, DEGRADED for GOLD.
    """
    engine = SLACalculatorEngine()
    c_silver = engine.register_circuit("CKT-S1", "CustA", 100, 10000, "SILVER")
    c_gold = engine.register_circuit("CKT-G1", "CustA", 100, 20000, "GOLD")
    t0 = datetime(2026, 10, 1, 0, 0)

    # Edge Case: Latency exactly 40.0 ms
    s_40 = engine.ingest_sample("CKT-S1", t0, 40.0, 0.0, True)
    status_s, _ = engine.classify_sample(s_40, c_silver.sla_tier)
    status_g, _ = engine.classify_sample(s_40, c_gold.sla_tier)
    assert status_s == SampleStatus.OK, "Latency exactly 40ms must be OK for SILVER"
    assert status_g == SampleStatus.DEGRADED, "Latency exactly 40ms must be DEGRADED for GOLD"

    # Boundary tests for GOLD (30.0 ms, 0.2% loss)
    s_30 = engine.ingest_sample("CKT-G1", t0, 30.0, 0.2, True)
    assert engine.classify_sample(s_30, SLATier.GOLD)[0] == SampleStatus.OK
    s_30_1 = engine.ingest_sample("CKT-G1", t0 + timedelta(minutes=5), 30.1, 0.2, True)
    assert engine.classify_sample(s_30_1, SLATier.GOLD)[0] == SampleStatus.DEGRADED

    # Unreachable -> DOWN regardless of latency/loss
    s_down = engine.ingest_sample("CKT-G1", t0 + timedelta(minutes=10), 5.0, 0.0, False)
    assert engine.classify_sample(s_down, SLATier.GOLD)[0] == SampleStatus.DOWN


# =====================================================================
# BR-02 & Explicit Edge Case: Outage Detection Hysteresis (3 to Open, 2 to Close)
# =====================================================================

def test_br02_two_down_samples_do_not_open_outage():
    """BR-02: Fewer than 3 consecutive DOWN samples do not open an outage."""
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-01", "CustA", 100, 10000, "GOLD")
    t = datetime(2026, 10, 1, 0, 0)
    t = add_samples_run(engine, "CKT-01", t, 2, reachable=False)  # 2 DOWN (10 mins)
    t = add_samples_run(engine, "CKT-01", t, 10, reachable=True)  # 10 OK

    res = engine.evaluate_circuit("CKT-01")
    assert res.outage_count == 0
    assert res.outage_minutes == 0
    assert res.availability_pct == 100.0


def test_br02_edge_case_exactly_3_down_then_ok_is_15_minutes():
    """
    Explicit Edge Case: Exactly 3 DOWN samples then OK (2 OK samples to close)
    results in an outage of exactly 15 minutes starting at the first DOWN sample.
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-01", "CustA", 100, 10000, "GOLD")
    t0 = datetime(2026, 10, 1, 0, 0)
    t = add_samples_run(engine, "CKT-01", t0, 3, reachable=False)  # 00:00, 00:05, 00:10
    t = add_samples_run(engine, "CKT-01", t, 5, reachable=True)    # 00:15, 00:20, ...

    res = engine.evaluate_circuit("CKT-01")
    assert res.outage_count == 1
    assert res.outage_minutes == 15
    assert res.outage_periods[0].start_time == t0
    assert res.outage_periods[0].end_time == t0 + timedelta(minutes=15)


def test_br02_single_ok_between_downs_does_not_close_outage():
    """
    BR-02 Hysteresis (Flapping protection): Once an outage opens (3 DOWN), a single OK
    followed by another DOWN does NOT close the outage; it stays open until 2 consecutive
    OK or DEGRADED samples occur.
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-01", "CustA", 100, 10000, "SILVER")
    t0 = datetime(2026, 10, 1, 0, 0)
    t = add_samples_run(engine, "CKT-01", t0, 3, reachable=False)  # 3 DOWN (opens outage)
    t = add_samples_run(engine, "CKT-01", t, 1, reachable=True)    # 1 OK (not enough to close)
    t = add_samples_run(engine, "CKT-01", t, 2, reachable=False)   # 2 DOWN (continues outage)
    t = add_samples_run(engine, "CKT-01", t, 2, reachable=True)    # 2 OK (closes outage!)

    res = engine.evaluate_circuit("CKT-01")
    assert res.outage_count == 1
    # Outage spans the 3 DOWN + 1 OK + 2 DOWN = 6 samples = 30 minutes
    assert res.outage_minutes == 30


# =====================================================================
# BR-03: Degraded Time (6+ Consecutive DEGRADED = 30+ mins at 50% Weight)
# =====================================================================

def test_br03_degraded_run_under_and_at_6_samples():
    """
    BR-03: 5 consecutive DEGRADED samples (25 mins) do not count as degraded time;
    6 consecutive DEGRADED samples (30 mins) count at 50% weight (15 mins unavailability).
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-5DEG", "CustA", 100, 10000, "GOLD")
    engine.register_circuit("CKT-6DEG", "CustA", 100, 10000, "GOLD")
    t0 = datetime(2026, 10, 1, 0, 0)

    # 5 DEGRADED + 15 OK = 20 samples (100 mins)
    t = add_samples_run(engine, "CKT-5DEG", t0, 5, latency_ms=35.0, reachable=True)
    add_samples_run(engine, "CKT-5DEG", t, 15, latency_ms=10.0, reachable=True)
    res5 = engine.evaluate_circuit("CKT-5DEG")
    assert res5.degraded_minutes == 0
    assert res5.availability_pct == 100.0

    # 6 DEGRADED (30 mins) + 14 OK (70 mins) = 100 mins total
    t = add_samples_run(engine, "CKT-6DEG", t0, 6, latency_ms=35.0, reachable=True)
    add_samples_run(engine, "CKT-6DEG", t, 14, latency_ms=10.0, reachable=True)
    res6 = engine.evaluate_circuit("CKT-6DEG")
    assert res6.degraded_minutes == 30
    # Availability = (100 - 0 - 0.5 * 30) / 100 = 85.0%
    assert res6.availability_pct == 85.0


# =====================================================================
# BR-04 & Explicit Edge Case: Maintenance Window 48-Hour Advance Notice
# =====================================================================

def test_br04_edge_case_maintenance_notified_exactly_48h_vs_late():
    """
    BR-04 & Edge Case:
    - Window notified exactly 48 hours before start is excluded from monitored_minutes
      and never counts as outage.
    - Window notified < 48 hours (e.g. 47h 59m) is NOT excluded and counts as outage.
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-EXACT48", "CustA", 100, 10000, "GOLD")
    engine.register_circuit("CKT-LATE", "CustA", 100, 10000, "GOLD")

    mw_start = datetime(2026, 10, 5, 2, 0)
    mw_end = datetime(2026, 10, 5, 2, 30)

    # Exactly 48 hours notice
    engine.register_maintenance_window(
        "CKT-EXACT48",
        notified_at=mw_start - timedelta(hours=48),
        start_time=mw_start,
        end_time=mw_end,
    )
    # 47 hours notice (late)
    engine.register_maintenance_window(
        "CKT-LATE",
        notified_at=mw_start - timedelta(hours=47),
        start_time=mw_start,
        end_time=mw_end,
    )

    for cid in ("CKT-EXACT48", "CKT-LATE"):
        # 6 DOWN samples inside the window (02:00 to 02:30) + 14 OK samples after
        t = add_samples_run(engine, cid, mw_start, 6, reachable=False)
        add_samples_run(engine, cid, t, 14, reachable=True)

    res_exact = engine.evaluate_circuit("CKT-EXACT48")
    assert res_exact.monitored_minutes == 70  # 14 samples * 5m; 6 maintenance samples excluded
    assert res_exact.outage_minutes == 0
    assert res_exact.availability_pct == 100.0

    res_late = engine.evaluate_circuit("CKT-LATE")
    assert res_late.monitored_minutes == 100  # All 20 samples included
    assert res_late.outage_minutes == 30
    assert res_late.availability_pct == 70.0


# =====================================================================
# Explicit Edge Case: Missing Samples (Gap in Feed)
# =====================================================================

def test_edge_case_missing_samples_gap_in_feed_not_monitored():
    """
    Explicit Edge Case: Missing samples (gap in the feed) treated as not monitored,
    not as DOWN, and do not bridge across gaps to form false 3-sample outages.
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-GAP", "CustA", 100, 10000, "GOLD")
    t0 = datetime(2026, 10, 1, 0, 0)

    # 2 DOWN samples before a 1-hour feed gap, then 1 DOWN sample after the gap, then OK
    t = add_samples_run(engine, "CKT-GAP", t0, 2, reachable=False)
    t_after_gap = t + timedelta(hours=1)  # 12 missing samples
    t = add_samples_run(engine, "CKT-GAP", t_after_gap, 1, reachable=False)
    add_samples_run(engine, "CKT-GAP", t, 5, reachable=True)

    res = engine.evaluate_circuit("CKT-GAP")
    # Total ingested samples = 2 + 1 + 5 = 8 samples = 40 monitored minutes
    assert res.monitored_minutes == 40
    assert res.outage_count == 0
    assert res.availability_pct == 100.0


# =====================================================================
# BR-05, BR-06 & Explicit Edge Case: Availability 99.9% on GOLD & Slabs
# =====================================================================

def test_br05_br06_edge_case_exactly_99_9_pct_on_gold_no_penalty():
    """
    Explicit Edge Case: Availability of exactly 99.9% on a GOLD circuit incurs 0% penalty.
    Let monitored_minutes = 15,000 (3,000 samples) and outage_minutes = 15 (3 DOWN samples).
    Availability = (15000 - 15) / 15000 = 99.900% -> 0% penalty!
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-GOLD-999", "CustA", 100, 50000, "GOLD")
    t0 = datetime(2026, 10, 1, 0, 0)
    t = add_samples_run(engine, "CKT-GOLD-999", t0, 3, reachable=False)     # 15 mins DOWN
    add_samples_run(engine, "CKT-GOLD-999", t, 2997, reachable=True)        # 14,985 mins OK

    res = engine.evaluate_circuit("CKT-GOLD-999")
    assert res.monitored_minutes == 15000
    assert res.outage_minutes == 15
    assert res.availability_pct == 99.900
    assert res.base_penalty_pct == 0.0
    assert res.penalty_amount_rs == 0.0


# =====================================================================
# BR-07: Chronic Clause (4+ Outages = +5% MRC) and 50% Penalty Cap
# =====================================================================

def test_br07_chronic_clause_and_50_pct_cap():
    """
    BR-07: 4 or more separate outages in a month add 5% of MRC;
    total penalty per circuit is capped at 50% of MRC.
    """
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-CHRONIC", "CustA", 100, 100000, "GOLD")
    t = datetime(2026, 10, 1, 0, 0)

    # Create 4 separate small outages of 15m each (total 60m outage) over 15,000 monitored minutes
    # Availability = (15000 - 60) / 15000 = 99.600% -> GOLD slab < 99.9% = 10% base + 5% chronic = 15%
    for _ in range(4):
        t = add_samples_run(engine, "CKT-CHRONIC", t, 3, reachable=False)
        t = add_samples_run(engine, "CKT-CHRONIC", t, 10, reachable=True)
    remaining_samples = 3000 - (4 * 13)
    add_samples_run(engine, "CKT-CHRONIC", t, remaining_samples, reachable=True)

    res = engine.evaluate_circuit("CKT-CHRONIC")
    assert res.outage_count == 4
    assert res.availability_pct == 99.600
    assert res.base_penalty_pct == 10.0
    assert res.chronic_penalty_pct == 5.0
    assert res.effective_penalty_pct == 15.0
    assert res.cap_applied is False
    assert res.penalty_amount_rs == 15000.0

    # Now test 50% cap: if availability < 99.0% on GOLD (50% base) + 4 outages (+5% chronic) -> capped at 50%
    engine.register_circuit("CKT-CAP", "CustA", 100, 100000, "GOLD")
    t = datetime(2026, 10, 1, 0, 0)
    for _ in range(4):
        t = add_samples_run(engine, "CKT-CAP", t, 10, reachable=False)  # 50 mins each = 200 mins
        t = add_samples_run(engine, "CKT-CAP", t, 10, reachable=True)
    # Total 80 samples = 400 mins, outage = 200 mins -> 50% availability (< 99.0% -> 50% slab + 5% chronic)
    res_cap = engine.evaluate_circuit("CKT-CAP")
    assert res_cap.outage_count == 4
    assert res_cap.base_penalty_pct == 50.0
    assert res_cap.chronic_penalty_pct == 5.0
    assert res_cap.effective_penalty_pct == 50.0
    assert res_cap.cap_applied is True
    assert res_cap.penalty_amount_rs == 50000.0


# =====================================================================
# Input Validation
# =====================================================================

def test_registration_rejects_duplicate_circuits_and_invalid_values():
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-1", "CustA", 100, 10000, "GOLD")

    with pytest.raises(ValueError, match="already registered"):
        engine.register_circuit("CKT-1", "CustA", 100, 10000, "GOLD")
    with pytest.raises(ValueError, match="Bandwidth"):
        engine.register_circuit("CKT-2", "CustA", float("inf"), 10000, "GOLD")
    with pytest.raises(ValueError, match="MRC"):
        engine.register_circuit("CKT-3", "CustA", 100, -1, "GOLD")
    with pytest.raises(ValueError, match="SLA tier"):
        engine.register_circuit("CKT-4", "CustA", 100, 10000, "PLATINUM")


def test_sample_validation_rejects_nonfinite_values_and_duplicate_timestamps():
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-1", "CustA", 100, 10000, "SILVER")
    t0 = datetime(2026, 10, 1, 0, 0)

    with pytest.raises(ValueError, match="finite"):
        engine.ingest_sample("CKT-1", t0, float("nan"), 0.0, True)
    with pytest.raises(ValueError, match="Invalid packet loss"):
        engine.ingest_sample("CKT-1", t0, 10.0, 100.1, True)
    engine.ingest_sample("CKT-1", t0, 10.0, 0.0, True)
    with pytest.raises(ValueError, match="Duplicate sample timestamp"):
        engine.ingest_sample("CKT-1", t0, 11.0, 0.0, True)


def test_maintenance_validation_rejects_empty_or_mixed_timezone_ranges():
    engine = SLACalculatorEngine()
    engine.register_circuit("CKT-1", "CustA", 100, 10000, "SILVER")
    t0 = datetime(2026, 10, 1, 0, 0)

    with pytest.raises(ValueError, match="after start_time"):
        engine.register_maintenance_window("CKT-1", t0, t0, t0)
    with pytest.raises(ValueError, match="same timezone convention"):
        engine.register_maintenance_window(
            "CKT-1", t0, datetime.fromisoformat("2026-10-03T00:00+05:30"),
            datetime.fromisoformat("2026-10-03T00:15+05:30")
        )
