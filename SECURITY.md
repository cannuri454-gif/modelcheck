# Security and release status

ModelCheck 0.1 is an early local desktop tool. It is not a secure sandbox for hostile files and does not certify a model for deployment.

## Data boundaries

- The application makes no network requests, executes no user-supplied code and imports no pickle/joblib model files.
- It reads CSV data as text. Input size, record count, column count and category counts are bounded. These limits reduce resource use, but worst-case data can still take substantial memory and CPU.
- Model fitting and CSV loading run in a background thread. Cancel and close wait for the current stage to finish; the process is not force-killed.
- History uses parameterised SQLite statements. HTML reports escape dataset content and use a restrictive content security policy with no scripts or external resources.
- The database and reports include column/label names, group identifiers, metrics and record positions. They do not contain raw feature rows or trained models, but they can still reveal sensitive information. They are unencrypted and have the same user-account boundary as ordinary files.
- Exports accept only HTML/JSON names and refuse the loaded source dataset, history database and existing aliases of those files. They use a flushed temporary file followed by replacement, so a failed write preserves the previous report. An existing report can still be replaced after the save dialog's overwrite confirmation.

## Checks performed

See the [release verification report](docs/release-verification.md) for test scope, antivirus evidence, exact download hashes and remaining limits.

Local tests, Bandit and pip-audit were run on 2 October 2026. See [verification notes](docs/verification.md) for the exact checks. No flagged application issues or known audited dependency vulnerabilities were reported by those tools at that time. These are limited checks, not proof that software is free of vulnerabilities or malware.

The Windows build is unsigned. See the release verification report for the exact artifact hashes and antivirus results. No independent security review is claimed. Do not disable your security software to run it. Source and automated workflow results are public. Downloadable previews are marked alpha; there is no stable release or signed installer yet.

## Reporting

For non-sensitive bugs, open a repository issue with a minimal fictional dataset and reproduction steps. For a sensitive issue, use GitHub private vulnerability reporting if it is enabled. Do not post credentials, real customer records, medical data or private history databases in public issues.
