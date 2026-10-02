# Verification

Checked locally on Windows 11 with Python 3.12.14 on 2 October 2026.

- `python -m pytest -q`: 70 tests passed, including the final application changes.
- Coverage.py 7.16.2 measured 89% combined statement/branch coverage across the application, including 93% in evaluation and 100% in report generation. Coverage is a measurement, not proof of correctness.
- Additional checks cover malformed/NUL/UTF-8/BOM/multiline CSV input, size limits, split boundary seeds/fractions, numeric dates, extreme numbers, sparse preprocessing, cancellation races, closing during work, protected export paths, atomic export failure, corrupt JSON history and HTML injection attempts.
- 300 deterministic random-byte CSV cases were rejected without an unexpected exception. A fictional 50,000-row, eight-feature dataset completed both models in about six seconds while other checks were running. This does not validate the simultaneous 200-column/100-MB worst case.
- `python -m bandit -r modelcheck run.py`: no flagged issues.
- `python -m pip_audit -r requirements.txt -r requirements-dev.txt`: no known vulnerabilities found at the time of the audit.
- Opened the actual Qt application, ran the synthetic demonstration, and captured the setup and results views directly from the real widgets without a cursor overlay.
- The Windows folder build passed `ModelCheck.exe --self-test` with exit code 0. This starts Qt, runs the demonstration, fills the results table and saves an experiment in a temporary database. The build uses Windows' native ICU library; an incompatible library collected from the development environment is excluded by the checked-in packaging specification.
- Default synthetic demo: logistic regression balanced accuracy 1.000 (random), approximately 0.503 (new groups), and 1.000 (future records). These fictional data deliberately contain an alternative customer identifier; they are not a real-world performance claim.

Tests verify training-only preprocessing, group separation, chronological boundaries and date ties, deterministic random membership, known confusion matrices/metrics, duplicate counts, input validation, cancellation, persistence, report escaping, the background Qt worker and restoration of saved experiment settings.

Current limits: only binary classification and one holdout per testing method; no imported models, regression tasks, combined group/time split, cross-validation or tuning. Cross-platform behavior, the simultaneous maximum-size input and independently reviewed real-world use have not been validated. Code signing and a stable release are not claimed. See the release verification report for artifact-specific antivirus results.
