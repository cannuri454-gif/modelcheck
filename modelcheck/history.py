"""Local aggregate experiment history. No models or dataset bytes are stored."""
from __future__ import annotations

import json
import os
import sqlite3
import math
from pathlib import Path


def validate_saved_report(report):
    """Reject damaged local records before the UI adopts their contents."""
    try:
        if report['schema_version'] != 1 or not isinstance(report['results'], list) or not 1 <= len(report['results']) <= 9:
            raise ValueError()
        if not isinstance(report['dataset']['name'], str) or not isinstance(report['config']['positive_label'], str):
            raise ValueError()
        if not isinstance(report['dataset']['rows'], int) or not 20 <= report['dataset']['rows'] <= 50000:
            raise ValueError()
        for key in ('warnings', 'notes'):
            if not isinstance(report[key], list) or not all(isinstance(value, str) for value in report[key]):
                raise ValueError()
        config = report['config']
        for key in ('target', 'features', 'group', 'time', 'strategies', 'models', 'seed', 'test_size'):
            if key not in config:
                raise ValueError()
        if not isinstance(config['target'], str) or any(value is not None and not isinstance(value, str) for value in (config['group'], config['time'])):
            raise ValueError()
        if not isinstance(config['features'], list) or not 1 <= len(config['features']) <= 200 or not all(isinstance(value, str) for value in config['features']):
            raise ValueError()
        for key, allowed in (('strategies', {'random', 'group', 'time'}), ('models', {'logistic', 'forest'})):
            values = config[key]
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or value not in allowed for value in values):
                raise ValueError()
        if type(config['seed']) is not int or not 0 <= config['seed'] <= 2**31 - 1:
            raise ValueError()
        if not isinstance(config['test_size'], (int, float)) or not .1 <= config['test_size'] <= .4:
            raise ValueError()
        for result in report['results']:
            if result['strategy'] not in {'random', 'group', 'time'} or result['model'] not in {'baseline', 'logistic', 'forest'}:
                raise ValueError()
            m = result['metrics']
            for key in ('accuracy', 'balanced_accuracy', 'roc_auc', 'f1', 'precision', 'recall'):
                if not isinstance(m[key], (int, float)) or not math.isfinite(m[key]) or not 0 <= m[key] <= 1:
                    raise ValueError()
            matrix = m['confusion_matrix']
            if len(matrix) != 2 or any(len(row) != 2 or any(not isinstance(n, int) or n < 0 for n in row) for row in matrix):
                raise ValueError()
            interval = m['accuracy_interval']
            if len(interval) != 2 or not 0 <= interval[0] <= interval[1] <= 1:
                raise ValueError()
            audit = result['audit']
            for key in ('train_records', 'test_records', 'duplicate_test_records'):
                if not isinstance(audit[key], int) or not 0 <= audit[key] <= 50000:
                    raise ValueError()
            if not isinstance(audit['unseen_category_values'], dict) or audit['shared_groups'] is not None and not isinstance(audit['shared_groups'], int):
                raise ValueError()
            if not isinstance(result['groups'], list) or len(result['groups']) > 100:
                raise ValueError()
            for group in result['groups']:
                if not isinstance(group['group'], str) or not isinstance(group['n'], int) or not 0 <= group['accuracy'] <= 1:
                    raise ValueError()
        if not isinstance(report['versions'], dict) or not isinstance(report['dataset']['sha256'], str):
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError('This saved report is damaged or uses an unsupported format.') from error


def default_history_path() -> Path:
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
    return root / 'ModelCheck' / 'experiments.sqlite3'


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or default_history_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute('CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, report TEXT NOT NULL)')
        self.connection.commit()

    def save(self, name: str, report: dict) -> int:
        payload = json.dumps(report, allow_nan=False, ensure_ascii=False)
        with self.connection:
            cursor = self.connection.execute('INSERT INTO experiments (name, created_at, report) VALUES (?, ?, ?)',
                                             (name.strip() or 'Untitled experiment', report['created_at'], payload))
        return int(cursor.lastrowid)

    def list(self) -> list[tuple]:
        return self.connection.execute('SELECT id, name, created_at FROM experiments ORDER BY id DESC LIMIT 200').fetchall()

    def load(self, identifier: int) -> dict:
        row = self.connection.execute('SELECT CASE WHEN length(report)<=? THEN report ELSE NULL END FROM experiments WHERE id = ?',
                                      (100 * 1024**2, identifier)).fetchone()
        if row is None:
            raise ValueError('This experiment is no longer available.')
        if not isinstance(row[0], str):
            raise ValueError('This saved report is damaged or too large to open.')
        report = json.loads(row[0])
        validate_saved_report(report)
        return report

    def close(self):
        self.connection.close()
