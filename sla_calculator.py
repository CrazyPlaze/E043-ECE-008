#!/usr/bin/env python3
"""
ECE-008: Leased Line Uptime SLA and Penalty Calculator
Team ID: E043
Team Members:
  - Vishnu Krishna
  - Vishrutha L
Section: ECM B

Description:
Command-file driven back-end engine for an enterprise connectivity provider.
Processes 5-minute latency and packet-loss samples per circuit into outage and
degraded periods, excludes approved maintenance windows notified >= 48 hours
in advance, computes monthly availability %, and derives SLA penalties against
each circuit's Monthly Recurring Charge (MRC) with chronic outage clauses and
50% penalty caps.
"""

from __future__ import annotations
import sys
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple


class SLATier(str, Enum):
    GOLD = "GOLD"
    SILVER = "SILVER"


class SampleStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass
class MaintenanceWindow:
    circuit_id: str
    notified_at: datetime
    start_time: datetime
    end_time: datetime

    @property
    def is_approved_48h(self) -> bool:
        """
        BR-04: Maintenance windows notified at least 48 hours in advance are excluded
        from the denominator and never count as outage; windows notified late are not excluded.
        Edge case: Maintenance window notified exactly 48 hours before start is approved (>= 48h).
        """
        return (self.start_time - self.notified_at) >= timedelta(hours=48)

    def contains(self, timestamp: datetime) -> bool:
        """Checks if a 5-minute sample timestamp falls inside [start_time, end_time)."""
        return self.start_time <= timestamp < self.end_time


@dataclass
class Sample:
    circuit_id: str
    timestamp: datetime
    latency_ms: float
    packet_loss_pct: float
    reachable: bool
    jitter_ms: float = 0.0  # Optional stretch goal support


@dataclass
class PeriodEvent:
    circuit_id: str
    period_type: str  # "OUTAGE" or "DEGRADED"
    start_time: datetime
    end_time: datetime  # Exclusive end timestamp (last sample + 5 minutes)
    duration_minutes: int
    cause: str


@dataclass
class Circuit:
    circuit_id: str
    customer: str
    bandwidth_mbps: float
    mrc_rs: float
    sla_tier: SLATier
    maintenance_windows: List[MaintenanceWindow] = field(default_factory=list)
    samples: List[Sample] = field(default_factory=list)


@dataclass
class CircuitMonthlyResult:
    circuit_id: str
    customer: str
    sla_tier: SLATier
    mrc_rs: float
    monitored_minutes: int
    outage_minutes: int
    degraded_minutes: int
    outage_count: int
    availability_pct: float
    base_penalty_pct: float
    chronic_penalty_pct: float
    effective_penalty_pct: float
    penalty_amount_rs: float
    cap_applied: bool
    outage_periods: List[PeriodEvent]
    degraded_periods: List[PeriodEvent]


class SLACalculatorEngine:
    """
    Core engine implementing Business Rules BR-01 through BR-07 and explicit edge cases.
    """

    SAMPLE_INTERVAL_MINUTES = 5

    def __init__(self, enable_jitter_stretch: bool = False, jitter_threshold_ms: Optional[float] = None):
        self.circuits: Dict[str, Circuit] = {}
        self.enable_jitter_stretch = enable_jitter_stretch
        self.jitter_threshold_ms = jitter_threshold_ms

    def register_circuit(
        self,
        circuit_id: str,
        customer: str,
        bandwidth_mbps: float,
        mrc_rs: float,
        sla_tier: str | SLATier,
    ) -> Circuit:
        """Core Requirement 1: Register circuits."""
        if not circuit_id or not circuit_id.strip() or not customer or not customer.strip():
            raise ValueError("Circuit ID and Customer name must be non-empty.")
        if circuit_id in self.circuits:
            raise ValueError(f"Circuit '{circuit_id}' is already registered.")
        try:
            bandwidth = float(bandwidth_mbps)
            mrc = float(mrc_rs)
        except (TypeError, ValueError) as exc:
            raise ValueError("Bandwidth and MRC must be numeric values.") from exc
        if not math.isfinite(bandwidth) or bandwidth <= 0:
            raise ValueError(f"Bandwidth must be positive for circuit {circuit_id}.")
        if not math.isfinite(mrc) or mrc < 0:
            raise ValueError(f"MRC cannot be negative for circuit {circuit_id}.")

        try:
            tier = SLATier(sla_tier.upper()) if isinstance(sla_tier, str) else SLATier(sla_tier)
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"Unsupported SLA tier {sla_tier!r}; use GOLD or SILVER.") from exc
        circuit = Circuit(
            circuit_id=circuit_id,
            customer=customer,
            bandwidth_mbps=bandwidth,
            mrc_rs=mrc,
            sla_tier=tier,
        )
        self.circuits[circuit_id] = circuit
        return circuit

    def register_maintenance_window(
        self,
        circuit_id: str,
        notified_at: datetime,
        start_time: datetime,
        end_time: datetime,
    ) -> MaintenanceWindow:
        """Core Requirement 1: Register approved maintenance windows."""
        if circuit_id not in self.circuits:
            raise KeyError(f"Unknown circuit '{circuit_id}'.")
        timestamps = (notified_at, start_time, end_time)
        if not all(isinstance(ts, datetime) for ts in timestamps):
            raise ValueError("Maintenance timestamps must be datetime values.")
        aware = [ts.utcoffset() is not None for ts in timestamps]
        if len(set(aware)) != 1:
            raise ValueError("Maintenance timestamps must all use the same timezone convention.")
        if end_time <= start_time:
            raise ValueError("Maintenance window end_time must be after start_time.")

        window = MaintenanceWindow(
            circuit_id=circuit_id,
            notified_at=notified_at,
            start_time=start_time,
            end_time=end_time,
        )
        self.circuits[circuit_id].maintenance_windows.append(window)
        return window

    def ingest_sample(
        self,
        circuit_id: str,
        timestamp: datetime,
        latency_ms: float,
        packet_loss_pct: float,
        reachable: bool,
        jitter_ms: float = 0.0,
    ) -> Sample:
        """Core Requirement 2: Ingest 5-minute monitoring samples."""
        if circuit_id not in self.circuits:
            raise KeyError(f"Unknown circuit '{circuit_id}'.")
        if not isinstance(timestamp, datetime):
            raise ValueError("Sample timestamp must be a datetime value.")
        if not isinstance(reachable, bool):
            raise ValueError("Reachable must be a boolean value.")
        try:
            latency = float(latency_ms)
            packet_loss = float(packet_loss_pct)
            jitter = float(jitter_ms)
        except (TypeError, ValueError) as exc:
            raise ValueError("Latency, packet loss, and jitter must be numeric values.") from exc
        if not all(math.isfinite(value) for value in (latency, packet_loss, jitter)):
            raise ValueError("Latency, packet loss, and jitter must be finite numbers.")
        if packet_loss < 0.0 or packet_loss > 100.0:
            raise ValueError(f"Invalid packet loss {packet_loss_pct}% at {timestamp}.")
        if latency < 0.0:
            raise ValueError(f"Negative latency {latency_ms} ms at {timestamp}.")
        if jitter < 0.0:
            raise ValueError(f"Negative jitter {jitter_ms} ms at {timestamp}.")
        existing = self.circuits[circuit_id].samples
        if any(sample.timestamp == timestamp for sample in existing):
            raise ValueError(f"Duplicate sample timestamp {timestamp} for circuit {circuit_id}.")
        if existing and (existing[0].timestamp.utcoffset() is None) != (timestamp.utcoffset() is None):
            raise ValueError("Sample timestamps for a circuit must use the same timezone convention.")

        sample = Sample(
            circuit_id=circuit_id,
            timestamp=timestamp,
            latency_ms=latency,
            packet_loss_pct=packet_loss,
            reachable=reachable,
            jitter_ms=jitter,
        )
        self.circuits[circuit_id].samples.append(sample)
        return sample

    def classify_sample(self, sample: Sample, tier: SLATier) -> Tuple[SampleStatus, str]:
        """
        BR-01: Sample status:
          - unreachable -> DOWN
          - latency above 40 ms or packet loss above 0.5% -> DEGRADED; otherwise OK
          - GOLD uses 30 ms and 0.2%
        Explicit Edge Case:
          - Latency exactly 40 ms -> OK for SILVER (40.0 is not > 40.0), DEGRADED for GOLD (40.0 > 30.0).
        """
        if not sample.reachable:
            return SampleStatus.DOWN, "UNREACHABLE"

        lat_limit = 30.0 if tier == SLATier.GOLD else 40.0
        loss_limit = 0.2 if tier == SLATier.GOLD else 0.5

        reasons = []
        if sample.latency_ms > lat_limit:
            reasons.append("HIGH_LATENCY")
        if sample.packet_loss_pct > loss_limit:
            reasons.append("PACKET_LOSS")
        if self.enable_jitter_stretch and self.jitter_threshold_ms is not None:
            if sample.jitter_ms > self.jitter_threshold_ms:
                reasons.append("HIGH_JITTER")

        if reasons:
            return SampleStatus.DEGRADED, "+".join(reasons)
        return SampleStatus.OK, "OK"

    def is_in_valid_maintenance(self, circuit: Circuit, timestamp: datetime) -> bool:
        """
        BR-04: Samples inside an approved window notified at least 48 hours in advance
        are excluded from the denominator and never count as outage; windows notified late
        are not excluded.
        """
        for mw in circuit.maintenance_windows:
            if mw.is_approved_48h and mw.contains(timestamp):
                return True
        return False

    def evaluate_circuit(self, circuit_id: str) -> CircuitMonthlyResult:
        """
        Evaluates all business rules BR-01 through BR-07 for a single circuit.
        Handles:
          - BR-01: Sample classification (GOLD vs SILVER thresholds)
          - BR-02: Outage state machine (opens on 3 consecutive DOWN, closes on 2 consecutive OK/DEGRADED)
          - BR-03: Degraded runs (6+ consecutive DEGRADED samples = 30+ mins count at 50% weight)
          - BR-04: Maintenance window exclusion (>= 48h advance notice)
          - BR-05: Availability % = (monitored - outage - 0.5 * degraded) / monitored, rounded to 3 decimals
          - BR-06: Tiered SLA penalty slabs (GOLD: <99.9%->10%, <99.5%->25%, <99.0%->50%;
                   SILVER: <99.5%->10%, <99.0%->25%, <98.0%->50%)
          - BR-07: Chronic clause (4+ outages add 5% MRC; total penalty capped at 50% MRC)
          - Edge Case: Missing samples (gaps > 5 minutes) treated as not monitored, not as DOWN.
        """
        if circuit_id not in self.circuits:
            raise KeyError(f"Unknown circuit '{circuit_id}'.")

        circuit = self.circuits[circuit_id]
        sorted_samples = sorted(circuit.samples, key=lambda s: s.timestamp)

        # Filter out samples that fall inside a valid (>=48h notified) maintenance window (BR-04)
        monitored_samples: List[Tuple[Sample, SampleStatus, str]] = []
        for s in sorted_samples:
            if self.is_in_valid_maintenance(circuit, s.timestamp):
                continue
            status, reason = self.classify_sample(s, circuit.sla_tier)
            monitored_samples.append((s, status, reason))

        monitored_minutes = len(monitored_samples) * self.SAMPLE_INTERVAL_MINUTES

        # Split monitored_samples into contiguous segments separated by feed gaps (> 5 minutes)
        # or valid maintenance exclusions so missing samples are never treated as DOWN.
        segments: List[List[Tuple[Sample, SampleStatus, str]]] = []
        current_segment: List[Tuple[Sample, SampleStatus, str]] = []

        for item in monitored_samples:
            sample = item[0]
            if not current_segment:
                current_segment.append(item)
            else:
                prev_sample = current_segment[-1][0]
                delta = sample.timestamp - prev_sample.timestamp
                if delta == timedelta(minutes=self.SAMPLE_INTERVAL_MINUTES):
                    current_segment.append(item)
                else:
                    # Gap in the feed or maintenance window break -> close current contiguous segment
                    segments.append(current_segment)
                    current_segment = [item]
        if current_segment:
            segments.append(current_segment)

        outage_periods: List[PeriodEvent] = []
        degraded_periods: List[PeriodEvent] = []
        outage_sample_timestamps = set()

        # Pass 1: Outage Detection (BR-02) per contiguous segment
        for seg in segments:
            in_outage = False
            consecutive_down = 0
            consecutive_recovery = 0  # OK or DEGRADED
            outage_start_idx = 0

            for i, (s, status, _) in enumerate(seg):
                if not in_outage:
                    if status == SampleStatus.DOWN:
                        if consecutive_down == 0:
                            outage_start_idx = i
                        consecutive_down += 1
                        if consecutive_down == 3:
                            in_outage = True
                            consecutive_recovery = 0
                    else:
                        consecutive_down = 0
                else:
                    if status in (SampleStatus.OK, SampleStatus.DEGRADED):
                        consecutive_recovery += 1
                        if consecutive_recovery == 2:
                            # Outage closes before the 2 recovery samples (at index i - 1)
                            outage_end_idx = i - 2
                            start_ts = seg[outage_start_idx][0].timestamp
                            end_ts = seg[outage_end_idx][0].timestamp + timedelta(
                                minutes=self.SAMPLE_INTERVAL_MINUTES
                            )
                            dur_mins = (outage_end_idx - outage_start_idx + 1) * self.SAMPLE_INTERVAL_MINUTES
                            outage_periods.append(
                                PeriodEvent(
                                    circuit_id=circuit.circuit_id,
                                    period_type="OUTAGE",
                                    start_time=start_ts,
                                    end_time=end_ts,
                                    duration_minutes=dur_mins,
                                    cause="UNREACHABLE",
                                )
                            )
                            for k in range(outage_start_idx, outage_end_idx + 1):
                                outage_sample_timestamps.add(seg[k][0].timestamp)
                            in_outage = False
                            consecutive_down = 0
                            consecutive_recovery = 0
                    else:
                        # Another DOWN sample resets the recovery counter; outage continues
                        consecutive_recovery = 0

            # If segment ends while still in_outage, close outage at the end of the segment
            if in_outage:
                # If the last sample was a single OK/DEGRADED (consecutive_recovery == 1),
                # the outage did not reach 2 consecutive recovery samples, so it stays open through the segment end
                # OR if trailing recovery sample shouldn't be DOWN: wait - in BR-02, an outage only closes after
                # 2 consecutive OK/DEGRADED samples.
                outage_end_idx = len(seg) - 1
                start_ts = seg[outage_start_idx][0].timestamp
                end_ts = seg[outage_end_idx][0].timestamp + timedelta(
                    minutes=self.SAMPLE_INTERVAL_MINUTES
                )
                dur_mins = (outage_end_idx - outage_start_idx + 1) * self.SAMPLE_INTERVAL_MINUTES
                outage_periods.append(
                    PeriodEvent(
                        circuit_id=circuit.circuit_id,
                        period_type="OUTAGE",
                        start_time=start_ts,
                        end_time=end_ts,
                        duration_minutes=dur_mins,
                        cause="UNREACHABLE",
                    )
                )
                for k in range(outage_start_idx, outage_end_idx + 1):
                    outage_sample_timestamps.add(seg[k][0].timestamp)

        # Pass 2: Degraded Period Detection (BR-03)
        # 6 or more consecutive DEGRADED samples (30 minutes) outside an active outage count as degraded time
        for seg in segments:
            deg_start_idx: Optional[int] = None
            deg_count = 0
            deg_causes: List[str] = []

            for i, (s, status, reason) in enumerate(seg):
                if status == SampleStatus.DEGRADED and s.timestamp not in outage_sample_timestamps:
                    if deg_count == 0:
                        deg_start_idx = i
                        deg_causes = []
                    deg_count += 1
                    if reason not in deg_causes:
                        deg_causes.append(reason)
                else:
                    if deg_count >= 6 and deg_start_idx is not None:
                        start_ts = seg[deg_start_idx][0].timestamp
                        end_ts = seg[i - 1][0].timestamp + timedelta(
                            minutes=self.SAMPLE_INTERVAL_MINUTES
                        )
                        dur_mins = deg_count * self.SAMPLE_INTERVAL_MINUTES
                        degraded_periods.append(
                            PeriodEvent(
                                circuit_id=circuit.circuit_id,
                                period_type="DEGRADED",
                                start_time=start_ts,
                                end_time=end_ts,
                                duration_minutes=dur_mins,
                                cause="/".join(deg_causes),
                            )
                        )
                    deg_start_idx = None
                    deg_count = 0
                    deg_causes = []

            if deg_count >= 6 and deg_start_idx is not None:
                start_ts = seg[deg_start_idx][0].timestamp
                end_ts = seg[-1][0].timestamp + timedelta(minutes=self.SAMPLE_INTERVAL_MINUTES)
                dur_mins = deg_count * self.SAMPLE_INTERVAL_MINUTES
                degraded_periods.append(
                    PeriodEvent(
                        circuit_id=circuit.circuit_id,
                        period_type="DEGRADED",
                        start_time=start_ts,
                        end_time=end_ts,
                        duration_minutes=dur_mins,
                        cause="/".join(deg_causes),
                    )
                )

        outage_minutes = sum(p.duration_minutes for p in outage_periods)
        degraded_minutes = sum(p.duration_minutes for p in degraded_periods)
        outage_count = len(outage_periods)

        # BR-05: Availability = (monitored_minutes - outage_minutes - 0.5 * degraded_minutes) / monitored_minutes
        # as a percentage rounded to 3 decimals
        if monitored_minutes == 0:
            availability_pct = 100.0
        else:
            effective_uptime = monitored_minutes - outage_minutes - (0.5 * degraded_minutes)
            raw_pct = (effective_uptime / monitored_minutes) * 100.0
            availability_pct = round(max(0.0, raw_pct), 3)

        # BR-06: Penalty Slabs
        # GOLD: below 99.9% -> 10%, below 99.5% -> 25%, below 99.0% -> 50%
        # SILVER: below 99.5% -> 10%, below 99.0% -> 25%, below 98.0% -> 50%
        # Explicit Edge Case: Availability of exactly 99.9% on a GOLD circuit -> 0% penalty
        base_penalty_pct = 0.0
        if circuit.sla_tier == SLATier.GOLD:
            if availability_pct < 99.0:
                base_penalty_pct = 50.0
            elif availability_pct < 99.5:
                base_penalty_pct = 25.0
            elif availability_pct < 99.9:
                base_penalty_pct = 10.0
        else:  # SILVER
            if availability_pct < 98.0:
                base_penalty_pct = 50.0
            elif availability_pct < 99.0:
                base_penalty_pct = 25.0
            elif availability_pct < 99.5:
                base_penalty_pct = 10.0

        # BR-07: Chronic clause: 4 or more separate outages in a month add 5% of MRC;
        # total penalty per circuit is capped at 50% of MRC
        chronic_penalty_pct = 5.0 if outage_count >= 4 else 0.0
        unclamped_penalty_pct = base_penalty_pct + chronic_penalty_pct
        cap_applied = unclamped_penalty_pct > 50.0
        effective_penalty_pct = min(50.0, unclamped_penalty_pct)
        penalty_amount_rs = round(circuit.mrc_rs * (effective_penalty_pct / 100.0), 2)

        return CircuitMonthlyResult(
            circuit_id=circuit.circuit_id,
            customer=circuit.customer,
            sla_tier=circuit.sla_tier,
            mrc_rs=circuit.mrc_rs,
            monitored_minutes=monitored_minutes,
            outage_minutes=outage_minutes,
            degraded_minutes=degraded_minutes,
            outage_count=outage_count,
            availability_pct=availability_pct,
            base_penalty_pct=base_penalty_pct,
            chronic_penalty_pct=chronic_penalty_pct,
            effective_penalty_pct=effective_penalty_pct,
            penalty_amount_rs=penalty_amount_rs,
            cap_applied=cap_applied,
            outage_periods=outage_periods,
            degraded_periods=degraded_periods,
        )

    def format_circuit_events_report(self, circuit_id: str) -> str:
        """Core Requirement 3: Detect outage and degraded periods per circuit and print with start, end and cause."""
        res = self.evaluate_circuit(circuit_id)
        lines = [
            f"=== CIRCUIT PERIOD REPORT: {res.circuit_id} ({res.customer} | {res.sla_tier.value}) ==="
        ]
        all_events = sorted(
            res.outage_periods + res.degraded_periods, key=lambda e: e.start_time
        )
        if not all_events:
            lines.append("No outage or degraded periods detected.")
        else:
            for ev in all_events:
                lines.append(
                    f"{ev.period_type:<8} | Start: {ev.start_time.strftime('%Y-%m-%d %H:%M')} | "
                    f"End: {ev.end_time.strftime('%Y-%m-%d %H:%M')} | "
                    f"Duration: {ev.duration_minutes}m | Cause: {ev.cause}"
                )
        return "\n".join(lines)

    def format_customer_sla_report(self, customer: Optional[str] = None) -> str:
        """Core Requirement 4 & 5: Compute monthly availability % per circuit and print SLA report per customer."""
        results = [
            self.evaluate_circuit(cid)
            for cid in sorted(self.circuits.keys())
            if customer is None or self.circuits[cid].customer == customer
        ]
        by_customer: Dict[str, List[CircuitMonthlyResult]] = {}
        for r in results:
            by_customer.setdefault(r.customer, []).append(r)

        output_blocks = []
        for cust_name, cust_results in sorted(by_customer.items()):
            lines = [
                f"=== MONTHLY SLA REPORT: {cust_name} ===",
                f"{'Circuit':<10} | {'Tier':<6} | {'MRC (Rs)':>10} | {'Avail (%)':>9} | "
                f"{'Outages':>7} | {'Penalty (%)':>11} | {'Penalty (Rs)':>12} | {'Cap Applied':<11}",
                "-" * 98,
            ]
            total_mrc = 0.0
            total_penalty = 0.0
            for r in cust_results:
                total_mrc += r.mrc_rs
                total_penalty += r.penalty_amount_rs
                cap_str = "YES" if r.cap_applied else "NO"
                lines.append(
                    f"{r.circuit_id:<10} | {r.sla_tier.value:<6} | {r.mrc_rs:>10.2f} | "
                    f"{r.availability_pct:>8.3f}% | {r.outage_count:>7} | "
                    f"{r.effective_penalty_pct:>10.1f}% | {r.penalty_amount_rs:>12.2f} | {cap_str:<11}"
                )
            lines.append("-" * 98)
            lines.append(
                f"TOTAL MRC: Rs {total_mrc:.2f} | TOTAL SLA PENALTY: Rs {total_penalty:.2f}"
            )
            output_blocks.append("\n".join(lines))
        return "\n\n".join(output_blocks)

    def execute_command_file(self, filepath: str) -> str:
        """
        Parses and executes a command file.
        Supported commands:
          REGISTER_CIRCUIT <circuit_id> <customer> <bandwidth_mbps> <mrc_rs> <GOLD|SILVER>
          MAINTENANCE <circuit_id> <notified_iso> <start_iso> <end_iso>
          SAMPLE <circuit_id> <timestamp_iso> <latency_ms> <packet_loss_pct> <REACHABLE|UNREACHABLE>
          PRINT_OUTAGES [circuit_id]
          PRINT_SLA_REPORT [customer]
        """
        outputs: List[str] = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")] if "|" in line else line.split()
                cmd = parts[0].upper()

                if cmd == "REGISTER_CIRCUIT":
                    # REGISTER_CIRCUIT | CKT-01 | AcmeCorp | 100 | 50000 | GOLD
                    _, cid, cust, bw, mrc, tier = parts[:6]
                    self.register_circuit(cid, cust, float(bw), float(mrc), tier)
                elif cmd == "MAINTENANCE":
                    # MAINTENANCE | CKT-01 | 2026-10-01T00:00 | 2026-10-03T02:00 | 2026-10-03T04:00
                    _, cid, notified_s, start_s, end_s = parts[:5]
                    self.register_maintenance_window(
                        cid,
                        datetime.fromisoformat(notified_s),
                        datetime.fromisoformat(start_s),
                        datetime.fromisoformat(end_s),
                    )
                elif cmd == "SAMPLE":
                    # SAMPLE | CKT-01 | 2026-10-01T00:00 | 12.5 | 0.0 | REACHABLE
                    _, cid, ts_s, lat_s, loss_s, reach_s = parts[:6]
                    reachable = reach_s.upper() in ("REACHABLE", "TRUE", "1", "YES")
                    self.ingest_sample(
                        cid,
                        datetime.fromisoformat(ts_s),
                        float(lat_s),
                        float(loss_s),
                        reachable,
                    )
                elif cmd == "PRINT_OUTAGES":
                    if len(parts) > 1 and parts[1]:
                        outputs.append(self.format_circuit_events_report(parts[1]))
                    else:
                        for cid in sorted(self.circuits.keys()):
                            outputs.append(self.format_circuit_events_report(cid))
                elif cmd == "PRINT_SLA_REPORT":
                    cust = parts[1] if len(parts) > 1 and parts[1] else None
                    outputs.append(self.format_customer_sla_report(cust))
                else:
                    raise ValueError(f"Line {line_no}: Unrecognized command '{cmd}'")

        return "\n\n".join(outputs)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 sla_calculator.py <command_file.txt>")
        sys.exit(1)
    engine = SLACalculatorEngine()
    print(engine.execute_command_file(sys.argv[1]))
