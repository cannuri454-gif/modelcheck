"""Real Qt widget + background task integration, without external UI drivers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import time
import threading
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication
from modelcheck.app import MainWindow
from modelcheck.engine import demo_dataset, Config, run_experiment, load_csv
from modelcheck.history import History


@pytest.fixture(scope='module')
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(application, tmp_path):
    result = MainWindow(History(tmp_path / 'history.sqlite3'))
    yield result
    if result.task:
        result.task.requestInterruption()
        result.task.wait(30000)
        application.processEvents()
    result.close()
    application.processEvents()


def test_demo_worker_result_history_restore(application, window):
    window.load_demo()
    config = window.get_config()
    assert 'customer_id' not in config.features
    assert 'visit_date' not in config.features
    assert 'purchased' not in config.features
    assert set(config.strategies) == {'random', 'group', 'time'}
    window.model_boxes['forest'].setChecked(False)
    window.run_checks()
    assert not window.load_button.isEnabled()
    deadline = time.monotonic() + 30
    while window.task and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.01)
    assert window.task is None
    assert window.current_report is not None
    assert window.result_table.rowCount() == 6
    assert window.pages.currentIndex() == 1
    assert window.export_button.isEnabled()
    window.navigate(2)
    assert window.history_table.rowCount() == 1
    window.history_table.selectRow(0)
    window.open_history()
    original_seed = window.current_report['config']['seed']
    window.seed.setValue(99)
    window.restore_settings()
    assert window.seed.value() == original_seed
    assert window.pages.currentIndex() == 0


def test_new_dataset_resets_feature_selection(application, window):
    window.load_demo()
    changed = demo_dataset()
    changed.frame = changed.frame.rename(columns={'basket_value': 'new_feature'})
    window.set_dataset(changed)
    assert any(box.text() == 'new_feature' and box.isChecked() for box in window.feature_boxes)


def test_selecting_role_removes_feature(application, window):
    window.set_dataset(demo_dataset())
    window.group.setCurrentText('customer_id')
    assert 'customer_id' not in window.get_config().features


def test_reserved_placeholder_is_valid_feature_and_group(application, window):
    dataset = demo_dataset()
    dataset.frame = dataset.frame.rename(columns={'customer_id': '(none)'})
    window.set_dataset(dataset)
    assert '(none)' in window.get_config().features
    window.group.setCurrentIndex(1)
    assert window.get_config().group == '(none)'
    assert '(none)' not in window.get_config().features


def test_cancelled_background_task_does_not_save(application, window):
    entered = threading.Event()
    resume = threading.Event()
    def blocked(progress, cancelled):
        entered.set()
        assert resume.wait(5)
        from modelcheck.engine import Cancelled
        if cancelled():
            raise Cancelled()
        raise AssertionError('Cancellation flag was not delivered')
    window.start_task(blocked, window.receive_report, 'Test cancellation')
    assert entered.wait(5)
    window.cancel_task()
    resume.set()
    deadline = time.monotonic() + 5
    while window.task and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(.01)
    assert window.task is None
    assert window.history.list() == []
    assert window.current_report is None


def test_failed_history_save_keeps_computed_result(application, window):
    window.load_demo()
    report = run_experiment(window.dataset, Config('purchased', ('basket_value',), '1', models=('logistic',)))
    with patch.object(window.history, 'save', side_effect=OSError('disk full')):
        window.receive_report(report)
    assert window.current_report == report
    assert window.result_table.rowCount() == 2
    assert 'could not be saved' in window.status.text()


def test_export_blocks_dataset_and_history_aliases(application, window, tmp_path):
    source = tmp_path / 'dataset.html'
    source.write_text(demo_dataset().frame.to_csv(index=False), encoding='utf-8', newline='')
    window.set_dataset(load_csv(source))
    window.current_report = run_experiment(window.dataset, Config('purchased', ('basket_value',), '1', models=('logistic',)))
    original = source.read_bytes()
    for target in (source, window.history.path, tmp_path / 'oops.csv'):
        with patch('modelcheck.app.QFileDialog.getSaveFileName', return_value=(str(target), 'HTML report (*.html)')), patch('modelcheck.app.QMessageBox.warning') as warning:
            window.export_report()
            warning.assert_called_once()
    assert source.read_bytes() == original
    assert window.history.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_export_writes_valid_json_and_html(application, window, tmp_path):
    window.load_demo()
    window.current_report = run_experiment(window.dataset, Config('purchased', ('basket_value',), '1', models=('logistic',)))
    import json
    for extension, selected in (('json', 'JSON report (*.json)'), ('html', 'HTML report (*.html)')):
        target = tmp_path / f'report.{extension}'
        with patch('modelcheck.app.QFileDialog.getSaveFileName', return_value=(str(target), selected)):
            window.export_report()
        if extension == 'json':
            assert json.loads(target.read_text(encoding='utf-8'))['dataset']['sha256'] == window.dataset.sha256
        else:
            assert '<!doctype html>' in target.read_text(encoding='utf-8')


def test_queued_result_after_cancel_is_not_saved(application, window):
    window.start_task(lambda progress, cancelled: {'not': 'a report'}, window.receive_report, 'Queued result')
    assert window.task.wait(5000)
    # The worker has emitted ready, but the main thread has not processed it.
    window.cancel_task()
    application.processEvents()
    assert window.task is None
    assert window.current_report is None
    assert window.history.list() == []


def test_close_during_work_waits_for_worker_without_saving(application, window):
    entered, resume = threading.Event(), threading.Event()
    def blocked(progress, cancelled):
        entered.set()
        assert resume.wait(5)
        return {'unused': True}
    window.start_task(blocked, window.receive_report, 'Close test')
    assert entered.wait(5)
    window.close()
    assert window.close_pending
    assert window.task is not None
    resume.set()
    deadline = time.monotonic() + 5
    while window.task and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(.01)
    assert window.task is None
    assert window.current_report is None


def test_render_results_at_small_window_size(application, window):
    window.load_demo()
    report = run_experiment(window.dataset, Config('purchased', ('basket_value',), '1', models=('logistic',)))
    window.show_report(report)
    window.resize(980, 700)
    window.show()
    application.processEvents()
    capture = window.grab()
    assert not capture.isNull()
    assert window.chart.width() > 100
