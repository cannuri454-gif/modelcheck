import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import accuracy_score

from modelcheck.engine import (Cancelled, CheckError, Config, Dataset, audit_split,
    build_pipeline, demo_dataset, load_csv, metrics, run_experiment, split_indices, validate)
from modelcheck.history import History
from modelcheck.report import to_html, to_json


@pytest.fixture
def data():
    return demo_dataset()


@pytest.fixture
def config():
    return Config('purchased', ('account_signature', 'visits_last_month', 'basket_value', 'channel'),
                  '1', group='customer_id', time='visit_date', strategies=('random', 'group', 'time'),
                  models=('logistic',))


def test_groups_do_not_cross_split(data, config):
    _, y, _ = validate(data, config)
    train, test = split_indices(data.frame, y, config, 'group')
    assert not set(data.frame.customer_id.iloc[train]) & set(data.frame.customer_id.iloc[test])
    assert not set(train) & set(test)
    assert set(train) | set(test) == set(range(len(data.frame)))


def test_dates_are_strictly_separated_including_ties(data, config):
    _, y, _ = validate(data, config)
    train, test = split_indices(data.frame, y, config, 'time')
    dates = pd.to_datetime(data.frame.visit_date)
    assert dates.iloc[train].max() < dates.iloc[test].min()
    assert set(train) | set(test) == set(range(len(data.frame)))


def test_random_split_repeats_and_is_stratified(data, config):
    _, y, _ = validate(data, config)
    a, b = split_indices(data.frame, y, config, 'random')
    c, d = split_indices(data.frame, y, config, 'random')
    np.testing.assert_array_equal(a, c)
    np.testing.assert_array_equal(b, d)
    assert abs(y.iloc[b].mean() - y.mean()) < 0.01


def test_imputer_and_scaler_fit_training_only():
    x = pd.DataFrame({'number': [1.0, 3.0, np.nan, 10000.0], 'category': ['a', 'b', 'a', 'test-only']})
    pipeline = build_pipeline(x, 'logistic', 42)
    pipeline.fit(x.iloc[:3], [0, 1, 0])
    prepare = pipeline.named_steps['prepare']
    num = prepare.named_transformers_['numeric']
    assert num.named_steps['impute'].statistics_[0] == 2.0
    assert num.named_steps['scale'].mean_[0] == 2.0
    assert 'test-only' not in prepare.named_transformers_['category'].named_steps['encode'].categories_[0]
    assert len(pipeline.predict(x.iloc[3:])) == 1


def test_demo_exposes_memorisation_gap(data, config):
    report = run_experiment(data, config)
    scores = {r['strategy']: r['metrics']['balanced_accuracy'] for r in report['results'] if r['model'] == 'logistic'}
    assert scores['random'] > 0.95
    assert scores['random'] - scores['group'] > 0.30
    for result in report['results']:
        assert sum(map(sum, result['metrics']['confusion_matrix'])) == result['audit']['test_records']
        if result['model'] == 'baseline':
            assert result['metrics']['balanced_accuracy'] == 0.5
    assert report['config']['features'] == config.features
    assert 'Dataset contents' not in to_json(report)  # report has no raw feature rows
    assert 'frame' not in report


def test_metrics_match_known_predictions():
    y = pd.Series([0, 0, 1, 1])
    result = metrics(y, np.array([0, 1, 0, 1]), np.array([0.1, 0.8, 0.2, 0.9]))
    assert result['accuracy'] == accuracy_score(y, [0, 1, 0, 1]) == 0.5
    assert result['confusion_matrix'] == [[1, 1], [1, 1]]
    assert result['precision'] == result['recall'] == 0.5
    assert result['roc_auc'] == 0.75


def test_duplicate_audit_counts_only_test_records(data, config):
    x, _, _ = validate(data, config)
    x.iloc[1] = x.iloc[0]
    x.iloc[2] = x.iloc[0]
    audit = audit_split(data.frame, x, np.array([0, 3]), np.array([1, 2, 4]), config)
    assert audit['duplicate_test_records'] == 2
    assert audit['train_record_ids'] == [1, 4]
    assert audit['test_record_ids'] == [2, 3, 5]


@pytest.mark.parametrize('change', [
    {'features': ('purchased',)}, {'features': ('customer_id',)}, {'features': ()},
    {'strategies': ('group',), 'group': None}, {'strategies': ('time',), 'time': None},
    {'test_size': 0.9}, {'positive_label': 'absent'}, {'seed': -1}])
def test_invalid_settings_rejected(data, config, change):
    with pytest.raises(CheckError):
        validate(data, replace(config, **change))


def test_missing_target_rejected(data, config):
    data.frame.loc[0, 'purchased'] = np.nan
    with pytest.raises(CheckError, match='missing labels'):
        validate(data, config)


def test_single_label_split_rejected(data, config):
    data.frame['purchased'] = [0] * 320 + [1] * 320
    data.frame['visit_date'] = ['2025-01-01'] * 320 + ['2025-02-01'] * 320
    _, y, _ = validate(data, config)
    with pytest.raises(CheckError, match='both labels'):
        split_indices(data.frame, y, config, 'time')


def test_inf_feature_rejected(data, config):
    data.frame.loc[0, 'basket_value'] = np.inf
    with pytest.raises(CheckError, match='infinity'):
        validate(data, config)


def test_cancel_does_not_produce_partial_result(data, config):
    with pytest.raises(Cancelled):
        run_experiment(data, config, cancelled=lambda: True)


def test_csv_roundtrip_hash_and_duplicate_headers(tmp_path, data):
    path = tmp_path / 'data.csv'
    path.write_text(data.frame.to_csv(index=False), encoding='utf-8', newline='')
    loaded = load_csv(path)
    assert loaded.sha256 == data.sha256
    pd.testing.assert_frame_equal(loaded.frame, data.frame)
    path.write_text('label,label\n0,1\n' * 20)
    with pytest.raises(CheckError, match='unique'):
        load_csv(path)


def test_ragged_csv_rejected(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('a,b\n1,2,3\n')
    with pytest.raises(CheckError, match='number of fields'):
        load_csv(path)


def test_history_persists_exact_split_and_escapes_html(tmp_path, data, config):
    report = run_experiment(data, replace(config, strategies=('group',)))
    report['dataset']['name'] = '<script>alert(1)</script>'
    history = History(tmp_path / 'history.sqlite3')
    identifier = history.save("test'); DROP TABLE experiments;--", report)
    history.close()
    reopened = History(tmp_path / 'history.sqlite3')
    saved = reopened.load(identifier)
    assert saved['results'][0]['audit'] == report['results'][0]['audit']
    assert len(reopened.list()) == 1
    rendered = to_html(saved)
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert json.loads(to_json(saved)) == saved
    reopened.close()


def test_all_missing_feature_supported(data, config):
    data.frame['empty'] = np.nan
    config = replace(config, features=('empty',), strategies=('random',))
    report = run_experiment(data, config)
    assert any('every value is missing' in w for w in report['warnings'])
    assert all(np.isfinite(r['metrics']['accuracy']) for r in report['results'])
