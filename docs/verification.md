# Verification

Checked locally on Windows 11 with Python 3.12.14 on 2 October 2026.

- `python -m pytest -q`: 26 tests passed in the initial complete test run.
- `python -m bandit -r modelcheck run.py`: no flagged issues.
- `python -m pip_audit -r requirements.txt -r requirements-dev.txt`: no known vulnerabilities found at the time of the audit.
- Opened the actual Qt application, ran the synthetic demonstration, and captured the setup and results views directly from the real widgets without a cursor overlay.
- Default synthetic demo: logistic regression balanced accuracy 1.000 (random), approximately 0.503 (new groups), and 1.000 (future records). These fictional data deliberately contain an alternative customer identifier; they are not a real-world performance claim.

Tests verify training-only preprocessing, group separation, chronological boundaries and date ties, deterministic random membership, known confusion matrices/metrics, duplicate counts, input validation, cancellation, persistence, report escaping, the background Qt worker and restoration of saved experiment settings.

Current limits: only binary classification and one holdout per testing method; no imported models, regression tasks, combined group/time split, cross-validation or tuning. Cross-platform behavior, maximum-size datasets and independently reviewed real-world use have not been validated. No completed malware scan, code signing or stable release is claimed.
