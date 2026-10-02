"""Evaluation rules independent of the desktop interface.

All preprocessing is fitted on training records only. Test data is never
used for tuning. Scores from different splits answer different questions.
"""
from __future__ import annotations

import csv
import hashlib
import io
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from . import __version__

MAX_BYTES = 100 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 200
MAX_CATEGORY_LEVELS = 300


class CheckError(ValueError):
    """An actionable problem with the dataset or experiment settings."""


class Cancelled(Exception):
    """A cancellation requested between experiment stages."""


@dataclass
class Dataset:
    frame: pd.DataFrame
    name: str
    sha256: str
    source_path: Path | None = None


@dataclass(frozen=True)
class Config:
    target: str
    features: tuple[str, ...]
    positive_label: str
    group: str | None = None
    time: str | None = None
    strategies: tuple[str, ...] = ('random',)
    models: tuple[str, ...] = ('logistic', 'forest')
    test_size: float = 0.25
    seed: int = 42


def load_csv(path: str | Path) -> Dataset:
    path = Path(path)
    with path.open('rb') as source:
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise CheckError('This version supports CSV files up to 100 MB.')
    try:
        text = raw.decode('utf-8-sig')
        if '\x00' in text:
            raise CheckError('CSV text must not contain null bytes.')
        reader = csv.reader(io.StringIO(text), strict=True)
        header = next(reader)
        if not header or any(not c.strip() for c in header):
            raise CheckError('Every column needs a non-empty name.')
        if len(set(header)) != len(header):
            raise CheckError('Column names must be unique. Rename duplicate columns first.')
        if len(header) > MAX_COLUMNS:
            raise CheckError('This version supports up to 200 columns.')
        count = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise CheckError(f'Data record {count + 1} has a different number of fields from the header.')
            count += 1
            if count > MAX_ROWS:
                raise CheckError('This version supports up to 50,000 data records.')
        frame = pd.read_csv(io.StringIO(text), low_memory=False)
    except (UnicodeDecodeError, csv.Error, StopIteration, pd.errors.ParserError,
            pd.errors.EmptyDataError) as exc:
        raise CheckError('Use a non-empty, comma-separated UTF-8 CSV with a header.') from exc
    if len(frame) < 20:
        raise CheckError('Use at least 20 records so the train/test checks have enough data.')
    return Dataset(frame, path.name, hashlib.sha256(raw).hexdigest(), path.resolve())


def demo_dataset() -> Dataset:
    """Fictional repeated customers; signatures permit memorisation.

    This deliberately illustrates a different prediction task: known
    customers in a random split versus entirely unseen customers.
    """
    rng = np.random.default_rng(17)
    records = []
    for customer in range(80):
        buys = int(rng.integers(0, 2))
        for visit in range(8):
            records.append({
                'customer_id': f'C{customer:03d}',
                'visit_date': (pd.Timestamp('2025-01-01') + pd.Timedelta(days=visit * 14)).strftime('%Y-%m-%d'),
                'account_signature': f'S{customer:03d}',
                'visits_last_month': int(rng.integers(0, 12)),
                'basket_value': round(float(rng.uniform(5, 150)), 2),
                'channel': ['Web', 'Store'][int(rng.integers(0, 2))],
                'purchased': buys,
            })
    frame = pd.DataFrame(records)
    raw = frame.to_csv(index=False).encode('utf-8')
    return Dataset(frame, 'Repeated customers (synthetic)', hashlib.sha256(raw).hexdigest())


def wilson_interval(correct: int, n: int) -> list[float]:
    """Descriptive 95% Wilson interval; assumes independent observations."""
    z = 1.959963984540054
    p = correct / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [float(max(0, center - margin)), float(min(1, center + margin))]


def validate(dataset: Dataset, config: Config) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    frame = dataset.frame
    chosen = [config.target, *config.features, *([config.group] if config.group else []),
              *([config.time] if config.time else [])]
    if any(col not in frame.columns for col in chosen):
        raise CheckError('A selected column is not in this dataset.')
    if not config.features or len(set(config.features)) != len(config.features):
        raise CheckError('Select at least one feature, with no duplicate selections.')
    if set(config.features) & {config.target, config.group, config.time}:
        raise CheckError('The target, group ID and date columns cannot also be features.')
    if not config.strategies or set(config.strategies) - {'random', 'group', 'time'}:
        raise CheckError('Select a supported testing method.')
    if len(set(config.strategies)) != len(config.strategies):
        raise CheckError('Choose each testing method once.')
    if not config.models or set(config.models) - {'logistic', 'forest'}:
        raise CheckError('Choose logistic regression, random forest, or both.')
    if len(set(config.models)) != len(config.models):
        raise CheckError('Choose each model once.')
    if not 0.1 <= config.test_size <= 0.4 or not 0 <= config.seed <= 2**31 - 1:
        raise CheckError('Use a test fraction from 10% to 40% and a non-negative seed below 2^31.')
    if frame[config.target].isna().any():
        raise CheckError('The prediction column contains missing labels. Resolve them first.')
    labels = frame[config.target].astype(str)
    if labels.nunique() != 2 or config.positive_label not in set(labels):
        raise CheckError('This version needs exactly two target labels and a valid positive label.')
    if labels.value_counts().min() < 4:
        raise CheckError('Each target label needs at least four records.')
    if 'group' in config.strategies and not config.group:
        raise CheckError('Choose a group ID for the group-separated test.')
    if 'time' in config.strategies and not config.time:
        raise CheckError('Choose a date column for the future-data test.')
    if config.group and (frame[config.group].isna().any() or frame[config.group].nunique() < 2):
        raise CheckError('Group IDs must be complete, with at least two different groups.')
    if config.time:
        if pd.api.types.is_numeric_dtype(frame[config.time]):
            raise CheckError('Use written dates such as 2026-10-02, rather than numbers interpreted as timestamps.')
        dates = pd.to_datetime(frame[config.time], errors='coerce', utc=True, format='mixed')
        if dates.isna().any() or dates.nunique() < 2:
            raise CheckError('Dates must all be readable, with at least two different timestamps.')
    x = frame[list(config.features)].copy()
    warnings = []
    for column in x:
        if pd.api.types.is_numeric_dtype(x[column]):
            x[column] = pd.to_numeric(x[column], errors='coerce').astype(float)
            if np.isinf(x[column]).any():
                raise CheckError(f'Feature {column!r} contains infinity. Resolve it first.')
            if (x[column].abs() > 1e100).any():
                raise CheckError(f'Feature {column!r} contains numbers too large for stable calculation.')
        else:
            x[column] = x[column].map(lambda v: str(v) if pd.notna(v) else np.nan).astype(object)
            if x[column].nunique() > MAX_CATEGORY_LEVELS:
                raise CheckError(f'Feature {column!r} has more than 300 categories. Exclude IDs or free text.')
        if x[column].isna().all():
            warnings.append(f'{column}: every value is missing; the training pipeline will use a constant fill.')
        if x[column].nunique() <= 1:
            warnings.append(f'{column}: no useful variation in this dataset.')
        if x[column].astype(str).equals(labels):
            warnings.append(f'{column}: exactly matches the target labels. Review whether it would exist at prediction time.')
    y = (labels == config.positive_label).astype(int)
    return x, y, warnings


def split_indices(frame: pd.DataFrame, y: pd.Series, config: Config, strategy: str) -> tuple[np.ndarray, np.ndarray]:
    indices = np.arange(len(frame))
    if strategy == 'random':
        train, test = train_test_split(indices, test_size=config.test_size, stratify=y, random_state=config.seed)
    elif strategy == 'group':
        train, test = next(GroupShuffleSplit(n_splits=1, test_size=config.test_size,
                                             random_state=config.seed).split(indices, y, frame[config.group].astype(str)))
    elif strategy == 'time':
        dates = pd.to_datetime(frame[config.time], errors='raise', utc=True, format='mixed')
        order = np.argsort(dates.to_numpy(), kind='stable')
        cut = max(1, min(len(frame) - 1, int(np.floor(len(frame) * (1 - config.test_size)))))
        boundary = dates.iloc[order[cut]]
        train = indices[(dates < boundary).to_numpy()]
        test = indices[(dates >= boundary).to_numpy()]
    else:
        raise CheckError('Unknown testing method.')
    if len(train) < 4 or len(test) < 4:
        raise CheckError(f'{strategy}: this split leaves too few training or test records. Choose another fraction.')
    if y.iloc[train].nunique() != 2 or y.iloc[test].nunique() != 2:
        raise CheckError(f'{strategy}: both labels must appear in training and testing. Change the split or dataset.')
    return np.asarray(train), np.asarray(test)


def build_pipeline(x: pd.DataFrame, model: str, seed: int) -> Pipeline:
    numeric = x.select_dtypes(include='number').columns.tolist()
    categorical = [col for col in x if col not in numeric]
    blocks = []
    if numeric:
        blocks.append(('numeric', Pipeline([
            ('impute', SimpleImputer(strategy='median', keep_empty_features=True)),
            ('scale', StandardScaler())]), numeric))
    if categorical:
        blocks.append(('category', Pipeline([
            ('impute', SimpleImputer(strategy='constant', fill_value='(missing)', keep_empty_features=True)),
            ('encode', OneHotEncoder(handle_unknown='ignore', sparse_output=True))]), categorical))
    if model == 'logistic':
        estimator = LogisticRegression(max_iter=1000, random_state=seed)
    elif model == 'forest':
        estimator = RandomForestClassifier(n_estimators=100, min_samples_leaf=2,
                                            random_state=seed, n_jobs=1)
    else:
        estimator = DummyClassifier(strategy='most_frequent')
    return Pipeline([('prepare', ColumnTransformer(blocks, sparse_threshold=1.0)), ('model', estimator)])


def audit_split(frame: pd.DataFrame, x: pd.DataFrame, train: np.ndarray, test: np.ndarray, config: Config) -> dict:
    # Exact hashes cover selected feature values only, not the target.
    hashes = pd.util.hash_pandas_object(x, index=False)
    duplicate_count = int(hashes.iloc[test].isin(set(hashes.iloc[train])).sum())
    result = {'duplicate_test_records': duplicate_count, 'shared_groups': None, 'unseen_category_values': {},
              'train_records': len(train), 'test_records': len(test),
              'train_record_ids': (train + 1).tolist(), 'test_record_ids': (test + 1).tolist()}
    if config.group:
        groups = frame[config.group].astype(str)
        result['shared_groups'] = len(set(groups.iloc[train]) & set(groups.iloc[test]))
    for column in x.select_dtypes(exclude='number'):
        train_values = set(x[column].iloc[train].dropna())
        result['unseen_category_values'][column] = int((x[column].iloc[test].notna() & ~x[column].iloc[test].isin(train_values)).sum())
    if config.time:
        dates = pd.to_datetime(frame[config.time], utc=True, format='mixed')
        result['train_latest_date'] = dates.iloc[train].max().isoformat()
        result['test_earliest_date'] = dates.iloc[test].min().isoformat()
    return result


def metrics(y: pd.Series, prediction: np.ndarray, probability: np.ndarray) -> dict:
    accuracy = float(accuracy_score(y, prediction))
    return {'accuracy': accuracy, 'balanced_accuracy': float(balanced_accuracy_score(y, prediction)),
            'roc_auc': float(roc_auc_score(y, probability)), 'f1': float(f1_score(y, prediction, zero_division=0)),
            'precision': float(precision_score(y, prediction, zero_division=0)),
            'recall': float(recall_score(y, prediction, zero_division=0)),
            'confusion_matrix': confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
            'accuracy_interval': wilson_interval(int(np.sum(np.asarray(y) == prediction)), len(y))}


def run_experiment(dataset: Dataset, config: Config, progress: Callable[[str], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> dict:
    progress = progress or (lambda message: None)
    cancelled = cancelled or (lambda: False)
    x, y, warnings = validate(dataset, config)
    results = []
    for strategy in config.strategies:
        if cancelled():
            raise Cancelled()
        train, test = split_indices(dataset.frame, y, config, strategy)
        audit = audit_split(dataset.frame, x, train, test, config)
        for model in ('baseline', *config.models):
            if cancelled():
                raise Cancelled()
            progress(f'{strategy.title()} split: fitting {model}...')
            pipeline = build_pipeline(x, model, config.seed)
            with threadpool_limits(limits=1):
                pipeline.fit(x.iloc[train], y.iloc[train])
                prediction = pipeline.predict(x.iloc[test])
                probability = pipeline.predict_proba(x.iloc[test])[:, 1]
            model_metrics = metrics(y.iloc[test], prediction, probability)
            groups = []
            if config.group and model != 'baseline':
                test_groups = dataset.frame[config.group].iloc[test].astype(str)
                for value, count in test_groups.value_counts().head(100).items():
                    if count < 5:
                        continue
                    mask = (test_groups == value).to_numpy()
                    groups.append({'group': value, 'n': int(count),
                                   'accuracy': float(accuracy_score(y.iloc[test].to_numpy()[mask], prediction[mask]))})
            results.append({'strategy': strategy, 'model': model, 'metrics': model_metrics,
                            'audit': audit, 'groups': sorted(groups, key=lambda g: g['accuracy']),
                            'model_parameters': {'strategy': 'most_frequent'} if model == 'baseline'
                            else ({'max_iter': 1000, 'C': 1.0} if model == 'logistic'
                                  else {'n_estimators': 100, 'min_samples_leaf': 2, 'n_jobs': 1})})
    if cancelled():
        raise Cancelled()
    return {'schema_version': 1, 'app_version': __version__,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'dataset': {'name': dataset.name, 'sha256': dataset.sha256, 'rows': len(x), 'columns': len(dataset.frame.columns)},
            'config': asdict(config), 'warnings': warnings, 'results': results,
            'versions': {'python': platform.python_version(), 'pandas': pd.__version__,
                         'numpy': np.__version__, 'scikit_learn': sklearn.__version__},
            'notes': ['One holdout per method; no hyperparameter search or cross-validation.',
                      'Different splits test different populations; a score drop alone does not prove leakage.',
                      'Accuracy intervals assume independent records and can be too narrow for repeated groups.',
                      'Group summaries include up to 100 largest test groups with at least 5 records.',
                      'Scores use a 0.5 probability decision threshold (or the model prediction rule).',
                      'A clean report does not prove that all leakage is absent. Review feature availability yourself.']}
