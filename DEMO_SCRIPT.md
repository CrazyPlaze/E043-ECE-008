# Five Minute Demo Recording Script

This is a timed narration and screen plan for recording the project. Keep the terminal visible for commands and output. Speak at a steady pace and pause briefly when changing files.

## Before recording

1. Open PowerShell in the project folder.
2. Activate the project environment: `& .\.venv\Scripts\Activate.ps1`.
3. Confirm the sample file is in the folder. The demo commands below have already been checked locally.
4. Start a screen recording with the Windows screen recorder available on your computer. Choose the project window or screen, and enable your microphone if you want narration in the recording. Do not record private notifications or unrelated windows.

## 0:00–0:35 — Introduction

**Show:** `README.md` and the repository file list.

**Say:** “Hello, we are Team E043 from Section ECM B. Our project is a leased-line SLA calculator. It reads five-minute network measurements, detects outages and degraded service, then calculates monthly availability and SLA penalty credits. The project includes the Python implementation, sample input, automated tests, a design document, and a decision log.”

## 0:35–1:15 — Input and setup

**Show:** `sample_commands.txt`, then the README setup and command format.

**Say:** “The input file registers circuits and their SLA tiers, adds scheduled maintenance, and supplies timestamped latency, packet-loss, and reachability measurements. The same command file can request an outage report or a monthly SLA report. To set up the project, create and activate a Python virtual environment, install the requirements, and run the sample command shown in the README.”

## 1:15–2:15 — Run the application

**Run:**

```powershell
python sla_calculator.py sample_commands.txt
```

**Show:** The outage/degraded period reports and monthly reports.

**Say:** “The program reports a 15-minute outage for each sample circuit and a 30-minute degraded period for the GOLD circuit. The monthly reports show availability, outage count, penalty percentage, penalty amount, and whether the 50 percent monthly recurring charge cap applied. These numbers come directly from the bundled sample input.”

## 2:15–3:15 — Explain the event rules

**Show:** The relevant business-rule section in `DESIGN_DOCUMENT.md`, then the matching tests in `test_sla_calculator.py`.

**Say:** “An unreachable measurement is classified as DOWN. For reachable samples, the latency and packet-loss thresholds depend on whether the circuit is GOLD or SILVER. An outage is confirmed by three consecutive DOWN samples and is backdated to the first one. Two consecutive OK or DEGRADED samples close it, with those recovery samples excluded from outage duration. Six consecutive degraded samples form a degraded period. Approved maintenance requires at least 48 hours’ notice, and missing feed samples are not counted as downtime.”

## 3:15–4:10 — Run the tests

**Run:**

```powershell
python -m pytest -v
```

**Show:** The passing test summary.

**Say:** “The automated suite checks the business rules and boundary cases, including exact tier thresholds, outage confirmation and recovery, maintenance notice timing, feed gaps, degraded-period handling, penalty slabs, the chronic-outage clause, and the penalty cap. All 12 tests pass in this run.”

## 4:10–5:00 — Design and close

**Show:** `DECISION_LOG.md`, then the repository file list.

**Say:** “The decision log explains choices such as strict threshold comparisons, treating exactly 48 hours’ notice as qualifying, splitting the feed at missing samples, and applying only the highest base penalty slab before the chronic clause and cap. The design document maps the seven assignment rules to the implementation. This concludes our demonstration of the E043 leased-line SLA calculator. Thank you.”

## Final recording check

- Confirm the recording is about five minutes long and includes both commands and their results.
- Make sure narration is audible if enabled, and that the video contains no private notifications or unrelated content.
- Save the final video, upload it to the agreed video or cloud service, and add its share link to the repository README before final submission.
