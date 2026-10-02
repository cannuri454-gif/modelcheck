"""Optional deterministic checks with temporary fictional data only."""
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from modelcheck.engine import CheckError, Config, load_csv, run_experiment

with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / 'synthetic.csv'
    rng = np.random.default_rng(712)
    for _ in range(300):
        path.write_bytes(rng.integers(0, 256, size=int(rng.integers(0, 1500)), dtype=np.uint8).tobytes())
        try:
            load_csv(path)
        except CheckError:
            pass
        else:
            raise RuntimeError('Random bytes were unexpectedly accepted.')
    frame = pd.DataFrame({f'x{i}': rng.normal(size=50000) for i in range(8)})
    frame['label'] = (frame.x0 + frame.x1 > 0).astype(int)
    path.write_text(frame.to_csv(index=False), encoding='utf-8', newline='')
    started = time.monotonic()
    with patch('socket.socket.connect', side_effect=RuntimeError('Unexpected network connection')):
        report = run_experiment(load_csv(path), Config('label', tuple(frame.columns[:-1]), '1'))
    if len(report['results']) != 3 or any(r['audit']['train_records'] + r['audit']['test_records'] != 50000 for r in report['results']):
        raise RuntimeError('Large-dataset membership check failed.')
    print(f'Passed 300 random-byte inputs and 50,000-row/both-model test ({time.monotonic()-started:.2f}s).')
