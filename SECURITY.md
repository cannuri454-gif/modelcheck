# Security and release status

ModelCheck 0.1 is an early local desktop tool. It is not a secure sandbox for hostile files and does not certify a model for deployment.

## Data boundaries

- The application makes no network requests, executes no user-supplied code and imports no pickle/joblib model files.
- It reads CSV data as text. Input size, record count, column count and category counts are bounded. These limits reduce resource use, but worst-case data can still take substantial memory and CPU.
- Model fitting and CSV loading run in a background thread. Cancel and close wait for the current stage to finish; the process is not force-killed.
- History uses parameterised SQLite statements. HTML reports escape dataset content and use a restrictive content security policy with no scripts or external resources.
- The database and reports include column/label names, group identifiers, metrics and record positions. They do not contain raw feature rows or trained models, but they can still reveal sensitive information. They are unencrypted and have the same user-account boundary as ordinary files.
- Exporting to a selected path can replace an existing report after the save dialog's overwrite confirmation. Keep report exports separate from source datasets.

## Checks performed

Local tests, Bandit and pip-audit were run on 2 October 2026. See [verification notes](docs/verification.md) for the exact checks. No flagged application issues or known audited dependency vulnerabilities were reported by those tools at that time. These are limited checks, not proof that software is free of vulnerabilities or malware.

The Windows build is unsigned. No completed antivirus verdict or independent security review is claimed. Do not disable your security software to run it. Source and automated workflow results are public; there is no stable public binary release or signed installer yet.

## Reporting

For non-sensitive bugs, open a repository issue with a minimal fictional dataset and reproduction steps. For a sensitive issue, use GitHub private vulnerability reporting if it is enabled. Do not post credentials, real customer records, medical data or private history databases in public issues.
