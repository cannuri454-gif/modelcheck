"""Portable reports with escaped input and no executable content."""
import html
import json

LABELS = {'random': 'Random split', 'group': 'New groups', 'time': 'Future records',
          'baseline': 'Majority baseline', 'logistic': 'Logistic regression', 'forest': 'Random forest'}


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)


def to_html(report: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in (
        LABELS[r['strategy']], LABELS[r['model']],
        f"{r['metrics']['balanced_accuracy']:.3f}", f"{r['metrics']['roc_auc']:.3f}",
        r['audit']['train_records'], r['audit']['test_records'],
        r['audit']['duplicate_test_records'], r['audit']['shared_groups'])) + '</tr>' for r in report['results'])
    notes = ''.join(f'<li>{esc(note)}</li>' for note in [*report['warnings'], *report['notes']])
    settings = esc(json.dumps(report['config'], indent=2, ensure_ascii=False))
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>ModelCheck report</title><style>
body{{font:16px/1.6 system-ui,sans-serif;color:#172b3a;background:#f5f7fa;margin:40px auto;padding:0 24px;max-width:1100px}}
h1{{font-size:36px}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #dde3eb}}
pre{{white-space:pre-wrap;background:#fff;padding:20px}}.muted{{color:#617185}}li{{margin:8px 0}}code{{overflow-wrap:anywhere}}
</style><h1>ModelCheck</h1><p class="muted">Local classification experiment</p>
<h2>{esc(report['dataset']['name'])}</h2><p>{report['dataset']['rows']:,} records · {esc(report['created_at'])}</p>
<p>Dataset SHA-256: <code>{esc(report['dataset']['sha256'])}</code></p>
<table><thead><tr><th>Method</th><th>Model</th><th>Balanced accuracy</th><th>ROC AUC</th><th>Train</th><th>Test</th><th>Duplicate test records</th><th>Shared groups</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Settings</h2><pre>{settings}</pre><h2>How to read this</h2><ul>{notes}</ul>
<p>Balanced accuracy averages recall for both labels. ROC AUC measures ranking, not calibrated probability.
The majority baseline always predicts the most common training label.</p>
<h2>Software versions</h2><pre>{esc(json.dumps(report['versions'], indent=2))}</pre>
<p>Use the JSON export for exact split membership, confusion matrices and group summaries.
Record IDs are 1-based data record positions, excluding the header; they are not physical CSV line numbers.</p></html>'''
