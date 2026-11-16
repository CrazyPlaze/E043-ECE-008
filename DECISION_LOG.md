# Decision Log

Team E043 — ECE-008 Leased Line Uptime SLA and Penalty Calculator

- **D-01 — Python:** Chose Python 3.10+ and the standard library for straightforward timestamp arithmetic, state transitions, and command-file parsing.
- **D-02 — Strict thresholds:** Used `>` for latency and packet-loss limits so boundary values remain compliant where the brief says “above.”
- **D-03 — Feed gaps:** Split samples into contiguous five-minute segments so gaps are not counted as downtime and do not join separate outage runs.
- **D-04 — Maintenance filtering:** Remove samples in qualifying maintenance windows before event detection so they leave the monitored denominator and cannot start or extend an outage.
- **D-05 — Exact notice boundary:** Treat exactly 48 hours of notice as qualifying by using `>= 48 hours`.
- **D-06 — Outage debounce:** Require three consecutive DOWN samples, then backdate the event to the first sample to filter transient blips while crediting the full confirmed interval.
- **D-07 — Recovery hysteresis:** Require two consecutive OK or DEGRADED samples to close an outage, and exclude those recovery samples from its duration.
- **D-08 — Event precedence:** Detect outages before degraded runs and exclude outage samples from degraded accounting to prevent double counting.
- **D-09 — Degraded minimum:** Require six consecutive DEGRADED samples, matching the 30-minute rule at five-minute sampling intervals.
- **D-10 — Availability precision:** Apply the half-weight degraded deduction and round availability to three decimal places before selecting the penalty slab.
- **D-11 — Strict penalty boundaries:** Use strict less-than comparisons so exactly 99.900% on GOLD receives no penalty.
- **D-12 — Single base slab:** Apply the highest qualifying base penalty only; penalty slabs are not cumulative.
- **D-13 — Chronic clause and cap:** Add the 5% chronic amount to the base percentage, then cap the total at 50% of MRC and report whether that cap changed the result.
- **D-14 — Half-open intervals:** Represent samples and windows as `[start, end)` intervals to make duration and boundary handling consistent.
- **D-15 — Extensible jitter option:** Keep the optional jitter stretch goal behind engine configuration so the required baseline stays unchanged unless explicitly enabled.
- **D-16 — Reject duplicate records:** Reject duplicate circuit IDs and sample timestamps instead of silently replacing or ambiguously counting data.
- **D-17 — Reject invalid numbers and mixed time zones:** Validate finite numeric inputs and require a consistent naive/aware timestamp convention to avoid hidden NaN propagation and comparison errors.
