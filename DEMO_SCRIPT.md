# Five Minute Demo Script

This is a recording outline for the required screen-recorded demonstration. Show the terminal and the project files; keep the command and output visible while explaining each step.

## 0:00–0:30 — Introduce the project

“We are Team E043. This Python command-line tool processes five-minute leased-line samples, identifies outages and degraded periods, and calculates SLA availability and penalty credits.” Show `README.md` and the top of `sla_calculator.py`.

## 0:30–1:00 — Show the input format

Open `sample_commands.txt`. Point out circuit registration, the exactly-48-hour maintenance example, and `SAMPLE`, `PRINT_OUTAGES`, and `PRINT_SLA_REPORT` commands.

## 1:00–2:00 — Run the sample

In the repository root run:

```powershell
python sla_calculator.py sample_commands.txt
```

Show the event report and the customer SLA report. Explain the reported start, end, duration, availability, penalty, and cap flag.

## 2:00–3:15 — Explain outage hysteresis

Point to three consecutive DOWN samples and the following two recovery samples. Explain that the outage opens only after the third DOWN reading but is backdated to the first, while the recovery pair is excluded from outage time. Show the test `test_br02_edge_case_exactly_3_down_then_ok_is_15_minutes`.

## 3:15–4:15 — Show two edge cases

Show the GOLD/SILVER threshold boundary test for exactly 40 ms, and the maintenance test for exactly 48 hours versus late notice. Explain that missing feed samples split the stream and are not treated as DOWN.

## 4:15–5:00 — Run the tests and close

Run:

```powershell
python -m pytest -v
```

Show the passing test summary. Close by summarizing the seven rules, the 50% MRC cap, and the team's key design choice: separate contiguous feed segments and use hysteresis for outage detection.
