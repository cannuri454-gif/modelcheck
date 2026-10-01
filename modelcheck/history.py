"""Local aggregate experiment history. No models or dataset bytes are stored."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


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
        row = self.connection.execute('SELECT report FROM experiments WHERE id = ?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('This experiment is no longer available.')
        return json.loads(row[0])

    def close(self):
        self.connection.close()
