"""Hostile input, split invariants, export and failure regression checks."""
from dataclasses import replace
from html.parser import HTMLParser
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest
from scipy.sparse import issparse

from modelcheck import engine
from modelcheck.engine import CheckError, Config, Dataset, demo_dataset, load_csv, run_experiment, split_indices, validate
from modelcheck.history import History
from modelcheck.history import validate_saved_report
from modelcheck.report import to_html, to_json, write_report


@pytest.fixture
def sample():
    return demo_dataset(), Config('purchased', ('account_signature', 'basket_value', 'channel'), '1',
                                 group='customer_id', time='visit_date', models=('logistic',))


@pytest.mark.parametrize('contents', [b'', b'\xff', b'a,b\n"unfinished', b'a,\n1,2', b'a,b\n1', b'a\x00b,c\n1,2'])
def test_bad_csv_is_rejected_with_clear_error(tmp_path, contents):
    path = tmp_path / 'bad.csv'
    path.write_bytes(contents)
    with pytest.raises(CheckError):
        load_csv(path)


def test_csv_bom_quotes_multiline_and_unicode_record_positions(tmp_path):
    frame = pd.DataFrame({'notes': ['café, "quoted"\nsecond line'] * 20, 'label': [0, 1] * 10})
    path = tmp_path / 'résumé.csv'
    path.write_text(frame.to_csv(index=False), encoding='utf-8-sig', newline='')
    loaded = load_csv(path)
    pd.testing.assert_frame_equal(loaded.frame, frame)
    assert loaded.source_path == path.resolve()


@pytest.mark.parametrize('limit', ['MAX_BYTES', 'MAX_ROWS', 'MAX_COLUMNS'])
def test_csv_size_row_and_column_limits(tmp_path, monkeypatch, limit):
    path = tmp_path / 'data.csv'
    path.write_text('feature,label\n' + '1,0\n2,1\n' * 10)
    monkeypatch.setattr(engine, limit, {'MAX_BYTES': 10, 'MAX_ROWS': 19, 'MAX_COLUMNS': 1}[limit])
    with pytest.raises(CheckError):
        load_csv(path)


@pytest.mark.parametrize('seed,fraction', [(0, .1), (42, .25), (2147483647, .4)])
def test_split_membership_and_group_boundaries(sample, seed, fraction):
    data, config = sample
    config = replace(config, seed=seed, test_size=fraction)
    _, y, _ = validate(data, config)
    for strategy in ('random', 'group', 'time'):
        train, test = split_indices(data.frame, y, config, strategy)
        assert len(train) + len(test) == len(data.frame)
        assert set(train).isdisjoint(test)
        assert len(set(train)) == len(train) and len(set(test)) == len(test)
        if strategy == 'group':
            assert set(data.frame.customer_id.iloc[train]).isdisjoint(data.frame.customer_id.iloc[test])
        if strategy == 'time':
            assert data.frame.visit_date.iloc[train].max() < data.frame.visit_date.iloc[test].min()


@pytest.mark.parametrize('column,value,match', [('visit_date', 'bad date', 'Dates'), ('visit_date', 123, 'written dates'),
    ('customer_id', None, 'Group IDs'), ('purchased', None, 'missing labels'), ('basket_value', 1e308, 'too large')])
def test_unusable_values_rejected(sample, column, value, match):
    data, config = sample
    data.frame[column] = value
    with pytest.raises(CheckError, match=match):
        validate(data, config)


def test_category_limit_and_duplicate_models(sample):
    data, config = sample
    data.frame['account_signature'] = [f'id-{i}' for i in range(len(data.frame))]
    with pytest.raises(CheckError, match='300 categories'):
        validate(data, config)
    with pytest.raises(CheckError, match='each model once'):
        validate(demo_dataset(), replace(config, models=('logistic', 'logistic')))


def test_many_categories_remain_sparse():
    x = pd.DataFrame({'category': [f'c{i % 100}' for i in range(200)], 'number': np.arange(200)})
    pipeline = engine.build_pipeline(x, 'logistic', 42)
    pipeline.fit(x, [0, 1] * 100)
    assert issparse(pipeline.named_steps['prepare'].transform(x))


def test_cancel_after_fitting_returns_no_report(sample):
    data, config = sample
    stages = []
    with pytest.raises(engine.Cancelled):
        run_experiment(data, config, progress=stages.append, cancelled=lambda: bool(stages))
    assert len(stages) == 1


def test_html_never_creates_tags_from_input(sample):
    data, config = sample
    report = run_experiment(data, config)
    attack = '<img src="https://example.invalid/track" onerror="alert(1)"><script>bad()</script>'
    report['dataset']['name'] = attack
    report['warnings'] = [attack]
    report['config']['positive_label'] = attack
    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []
            self.csp = None
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            attrs = dict(attrs)
            if attrs.get('http-equiv') == 'Content-Security-Policy':
                self.csp = attrs['content']
    parsed = Tags()
    parsed.feed(to_html(report))
    assert not {'script', 'img', 'iframe', 'a', 'form'} & set(parsed.tags)
    assert "default-src 'none'" in parsed.csp
    assert json.loads(to_json(report))['dataset']['name'] == attack


def test_history_failed_save_is_atomic_and_corrupt_json_rejected(tmp_path, sample):
    data, config = sample
    report = run_experiment(data, config)
    history = History(tmp_path / 'history.sqlite3')
    identifier = history.save('valid', report)
    report['results'][0]['metrics']['accuracy'] = float('nan')
    with pytest.raises(ValueError):
        history.save('invalid', report)
    assert len(history.list()) == 1
    with history.connection:
        history.connection.execute('UPDATE experiments SET report=? WHERE id=?', ('{broken', identifier))
    with pytest.raises(json.JSONDecodeError):
        history.load(identifier)
    assert history.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    history.close()


def test_known_perfect_reversed_and_constant_prediction_metrics():
    y = pd.Series([0, 0, 1, 1])
    for prediction, expected_accuracy, expected_auc in [([0, 0, 1, 1], 1, 1), ([1, 1, 0, 0], 0, 0), ([0, 0, 0, 0], .5, .5)]:
        result = engine.metrics(y, np.array(prediction), np.array(prediction, dtype=float))
        assert result['accuracy'] == expected_accuracy
        assert result['roc_auc'] == expected_auc
        assert sum(map(sum, result['confusion_matrix'])) == 4
        assert 0 <= result['accuracy_interval'][0] <= result['accuracy_interval'][1] <= 1


def test_failed_export_preserves_existing_report_and_cleans_temporary(tmp_path, sample, monkeypatch):
    data, config = sample
    report = run_experiment(data, config)
    destination = tmp_path / 'report.json'
    destination.write_text('keep previous report')
    def failure(*args):
        raise OSError('disk full')
    monkeypatch.setattr('modelcheck.report.os.fsync', failure)
    with pytest.raises(OSError):
        write_report(report, destination, True)
    assert destination.read_text() == 'keep previous report'
    assert list(tmp_path.glob('.modelcheck-*.tmp')) == []


@pytest.mark.parametrize('payload', [None, 'not a report', [], {'schema_version': 9, 'results': []}])
def test_wrong_saved_report_shape_rejected(payload):
    with pytest.raises(ValueError, match='damaged'):
        validate_saved_report(payload)


def test_invalid_saved_metrics_rejected(sample):
    data, config = sample
    report = run_experiment(data, config)
    report['results'][0]['metrics']['accuracy'] = float('nan')
    with pytest.raises(ValueError, match='damaged'):
        validate_saved_report(report)


@pytest.mark.parametrize('key,value', [('target', 123), ('features', None), ('group', {}), ('seed', -1), ('test_size', float('nan')), ('models', ['unknown'])])
def test_invalid_saved_settings_rejected(sample, key, value):
    data, config = sample
    report = json.loads(to_json(run_experiment(data, config)))
    report['config'][key] = value
    with pytest.raises(ValueError, match='damaged'):
        validate_saved_report(report)
