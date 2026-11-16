# E043 ECE-008 Leased Line SLA Calculator

Team E043 built a Python command-line engine that converts five-minute leased-line telemetry into outage and degraded periods, monthly availability, and SLA penalty credits. It implements the seven business rules in the assignment and includes tests for the specified edge cases and input validation.

## Team

- Vishnu Krishna
- Vishrutha L
- Section ECM B

## Requirements

- Python 3.10 or newer
- `pytest` for the test suite

## Setup

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

## Run

```powershell
python sla_calculator.py sample_commands.txt
```

The command file supports circuit registration, maintenance windows, telemetry samples, outage reports, and SLA reports. Lines beginning with `#` are comments. Each command may use `|` separators or whitespace.

```text
REGISTER_CIRCUIT | <circuit_id> | <customer> | <bandwidth_mbps> | <mrc_rs> | <GOLD|SILVER>
MAINTENANCE      | <circuit_id> | <notified_iso> | <start_iso> | <end_iso>
SAMPLE           | <circuit_id> | <timestamp_iso> | <latency_ms> | <packet_loss_pct> | <REACHABLE|UNREACHABLE>
PRINT_OUTAGES    | [optional_circuit_id]
PRINT_SLA_REPORT | [optional_customer]
```

The output includes the event type, start and end times, duration, and cause for each detected period. The SLA report includes availability, outage count, penalty percentage and amount, and whether the 50% MRC cap applied.

## Business rules

1. Unreachable samples are DOWN. Otherwise, latency or packet loss above the tier threshold is DEGRADED. GOLD thresholds are 30 ms and 0.2%; SILVER thresholds are 40 ms and 0.5%. Comparisons are strict.
2. Three consecutive DOWN samples open an outage, backdated to the first sample. Two consecutive OK or DEGRADED samples close it; the recovery samples are not charged as outage time.
3. Six or more consecutive DEGRADED samples form a degraded period and count at half weight toward unavailability.
4. Samples in maintenance windows notified at least 48 hours in advance are excluded. Late-notice windows remain monitored. Exclusions split telemetry into separate contiguous segments.
5. Availability is `(monitored - outage - 0.5 × degraded) / monitored × 100`, rounded to three decimal places. Missing samples are not monitored.
6. GOLD penalties are 10%, 25%, and 50% below 99.9%, 99.5%, and 99.0%. SILVER penalties are 10%, 25%, and 50% below 99.5%, 99.0%, and 98.0%.
7. Four or more separate outages add 5% of MRC. Total penalty is capped at 50% of MRC.

## Validation and tests

The engine rejects duplicate circuit IDs and sample timestamps, unknown circuit references, invalid tier names, non-finite or out-of-range telemetry values, negative bandwidth/MRC values, invalid maintenance ranges, and inconsistent timestamp timezone conventions.

Run the suite with:

```powershell
python -m pytest -v
```

The suite covers the explicit assignment cases: three DOWN samples, tier threshold boundaries, exactly 48-hour maintenance notice, feed gaps, and exactly 99.900% GOLD availability. It also covers outage hysteresis, degraded-period minimum length, chronic penalties, the MRC cap, and input validation.

## Files

- `sla_calculator.py` — engine and command-line entry point.
- `test_sla_calculator.py` — pytest suite.
- `sample_commands.txt` — small runnable demonstration of the command format and core edge cases.
- `DESIGN_DOCUMENT.md` — implementation design and business-rule register.
- `output/pdf/E043_ECE008_Design_Document.pdf` — formatted design document for submission.
- `DECISION_LOG.md` — design decisions and rationale.
- `VIVA_PREPARATION.md` — viva questions with concise answer points.
- `DEMO_SCRIPT.md` — five-minute screen-recording outline.
