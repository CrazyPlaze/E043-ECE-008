# Viva Preparation

Use these prompts to rehearse the design and code. Explain the underlying rule in your own words, then point to the method or test that demonstrates it.

## Questions and answer points

1. **What problem does the project solve?**
   It converts five-minute telecom probe records into outage/degraded intervals, calculates circuit availability, and derives customer SLA credits from tier rules and MRC.

2. **Why does an outage open after three DOWN samples?**
   Three consecutive five-minute failures confirm a persistent incident and filter one- or two-sample flaps. Once confirmed, the start is backdated so all 15 minutes count.

3. **Why does an outage close after two OK or DEGRADED samples?**
   Two recovery readings provide hysteresis against brief route flaps. The event ends before this recovery pair, so recovery time is not billed as outage.

4. **What happens with two DOWN samples followed by OK?**
   The opening threshold was not reached, so the run is not an outage.

5. **Why are missing samples not treated as DOWN?**
   The provider has no evidence of reachability during a feed gap. The gap is excluded from monitored minutes and splits the state machine into separate segments.

6. **How is a maintenance window approved?**
   Its notice must be at least 48 hours before the start. The boundary is inclusive, so exactly 48 hours qualifies.

7. **How are GOLD and SILVER samples classified?**
   Unreachable is DOWN. Otherwise, thresholds are strict: GOLD uses latency >30 ms or loss >0.2%; SILVER uses >40 ms or >0.5%. Exact 40 ms is OK on SILVER and DEGRADED on GOLD.

8. **When does degraded time affect availability?**
   Only a continuous run of at least six DEGRADED samples qualifies. Its duration is multiplied by 0.5 in the availability formula.

9. **Why are outage detection and degraded detection separate passes?**
   Outage status takes precedence. Marking outage samples first prevents samples inside an outage from also reducing availability as degraded time.

10. **How is availability calculated?**
    `(monitored_minutes - outage_minutes - 0.5 × degraded_minutes) / monitored_minutes × 100`, rounded to three decimals before tier-slab selection.

11. **Are penalty slabs cumulative?**
    No. The engine selects one base slab, the highest threshold crossed. It then adds 5% for four or more outages and caps the final percentage at 50% of MRC.

12. **What does `cap_applied` mean?**
    It is true only when the uncapped base-plus-chronic percentage exceeds 50%. Exactly 50% does not need a cap.

13. **How does the engine avoid counting maintenance or gaps as outages?**
    Qualifying maintenance samples are removed before event detection. The remaining samples are segmented at any timestamp interval other than five minutes.

14. **What validation does the engine perform?**
    It rejects duplicate circuits and sample timestamps, unknown circuit IDs, invalid tiers, non-finite/out-of-range numbers, invalid maintenance ranges, and mixed timezone conventions.

15. **How would you add a new rule safely?**
    Define the boundary and precedence, add a focused test first, implement the rule in the appropriate classification/evaluation stage, run the full suite, then update the design document and decision log.

16. **What would you improve next?**
    Add integration tests using the official sample CSV pack, structured output CSV generation, richer command-line errors with line numbers, and a calendar-month boundary policy if the evaluator requires multi-month data.

## Live-change practice

Be ready to change a threshold or rule in a small, isolated method, add one test that captures the new behavior, and rerun `python -m pytest -v`. Explain the expected result before running it.
