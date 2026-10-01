"""Real Qt widget + background task integration, without external UI drivers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import time

import pytest
from PySide6.QtWidgets import QApplication
from modelcheck.app import MainWindow
from modelcheck.engine import demo_dataset
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
