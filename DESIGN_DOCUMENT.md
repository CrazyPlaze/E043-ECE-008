# ECE-008 Leased Line Uptime SLA and Penalty Calculator

## Team and scope

Team E043 (Vishnu Krishna and Vishrutha L), Section ECM B. The program is a file-driven Python engine for registering enterprise circuits, ingesting five-minute probes, finding outage and degraded periods, and calculating monthly SLA availability and penalty credits.

## Glossary

- **Circuit:** A customer leased-line service with an SLA tier and monthly recurring charge (MRC).
- **Sample:** A probe reading for a circuit at a timestamp, containing latency, packet loss, reachability, and optional jitter.
- **DOWN:** A sample for which the circuit is unreachable.
- **DEGRADED:** A reachable sample that exceeds its tier's latency or packet-loss threshold.
- **Maintenance window:** A scheduled interval; it qualifies for exclusion only when it has at least 48 hours of advance notice.
- **Monitored minutes:** Number of usable probe samples multiplied by five, after qualifying maintenance exclusions. Missing samples do not add minutes.
- **Chronic outage:** Four or more distinct outage periods in a month.

## Business rule register

| ID | Rule |
| --- | --- |
| BR-01 | Unreachable means DOWN. Otherwise, latency above 40 ms or loss above 0.5% means DEGRADED; GOLD uses 30 ms and 0.2%. Threshold comparisons are strict. |
| BR-02 | Three consecutive DOWN samples open an outage, backdated to the first DOWN sample. Two consecutive OK or DEGRADED samples close it. The recovery pair is excluded from outage duration. |
| BR-03 | A run of at least six consecutive DEGRADED samples forms a degraded period and counts at 50% weight toward unavailability. |
| BR-04 | Exclude samples in an approved maintenance window notified at least 48 hours before its start. Late notice does not qualify. |
| BR-05 | Availability is `(monitored - outage - 0.5 × degraded) / monitored × 100`, rounded to three decimals. A feed gap is unmonitored. |
| BR-06 | GOLD: below 99.9%, 99.5%, and 99.0% incurs 10%, 25%, and 50%. SILVER: below 99.5%, 99.0%, and 98.0% incurs 10%, 25%, and 50%. |
| BR-07 | Four or more outages add 5% of MRC. Total penalty is capped at 50% of MRC. |

## Domain model

- `SLATier` and `SampleStatus` are enums for tier and probe classification.
- `Circuit` stores customer, bandwidth, MRC, tier, windows, and samples.
- `MaintenanceWindow` validates the 48-hour notice rule and interval membership.
- `Sample` stores the measured probe values.
- `PeriodEvent` records an outage or degraded interval with cause and duration.
- `CircuitMonthlyResult` contains availability, outage totals, penalty components, and cap status.
- `SLACalculatorEngine` validates commands, classifies samples, evaluates periods, and formats reports.

## Processing flow

1. Parse commands and validate circuit, window, and sample inputs.
2. Sort each circuit's samples chronologically and remove samples inside qualifying maintenance windows.
3. Split the remaining samples wherever timestamps are not exactly five minutes apart. This prevents outages from crossing gaps or excluded maintenance.
4. Run the outage state machine on each segment. Three DOWN samples confirm and backdate an outage. Two consecutive OK/DEGRADED samples confirm recovery.
5. Mark outage samples, then identify separate runs of at least six DEGRADED samples outside outages.
6. Calculate monitored minutes and weighted downtime, round availability to three decimals, then apply the tier penalty and chronic clause.
7. Cap the percentage at 50% of MRC and format the event and customer reports.

## State transitions

| State | Input | Next state / action |
| --- | --- | --- |
| Watching | DOWN | Count DOWN run; on the third sample, open an outage from the first DOWN. |
| Watching | OK or DEGRADED | Clear an unconfirmed DOWN run. |
| In outage | DOWN | Continue the outage and clear any recovery count. |
| In outage | OK or DEGRADED | Count recovery; close before the second consecutive recovery sample. |
| Any | Feed gap or excluded maintenance interval | End the current segment; do not bridge the next sample to this one. |

The three-sample opening rule filters short transient failures while preserving the full interval once confirmed. The two-sample recovery rule avoids splitting one incident when a route briefly flaps back to reachable. These choices are reflected in outage duration and outage-count penalties.

## Explicit edge cases

| Case | Expected behavior |
| --- | --- |
| Exactly three DOWN samples then recovery | One 15-minute outage, starting at the first DOWN sample. |
| Latency exactly 40 ms | OK for SILVER; DEGRADED for GOLD. |
| Maintenance notice exactly 48 hours before start | Excluded from monitoring and outage calculations. |
| Missing telemetry samples | Gap is not monitored and splits state-machine segments. |
| GOLD availability exactly 99.900% | No base penalty because the slab uses a strict `< 99.9%` boundary. |

## Input validation

Reject duplicate circuit identifiers and sample timestamps, unknown circuit references, unsupported tiers, non-finite or out-of-range numeric values, negative bandwidth/MRC/latency/jitter, invalid maintenance ranges, and mixed naive/aware timestamps. Maintenance with late notice is valid input; it is simply not excluded.

## Test coverage

`test_sla_calculator.py` tests all seven business rules, the five explicit edge cases, outage hysteresis, degraded-run length, chronic penalties and cap behavior, and input validation. Run with `python -m pytest -v`.
