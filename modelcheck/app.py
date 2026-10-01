"""ModelCheck desktop interface. Computation runs outside the UI thread."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget)

from .engine import Cancelled, Config, Dataset, demo_dataset, load_csv, run_experiment
from .history import History
from .report import LABELS, to_html, to_json

INK = '#17332f'
TEAL = '#167d70'
STRATEGY_NAMES = {'random': 'Random split', 'group': 'New groups', 'time': 'Future records'}
STYLE = '''
QWidget { font-family: "Segoe UI"; font-size: 13px; color: #17332f; }
QMainWindow, QWidget#main { background: #f3f6f5; }
QFrame#sidebar { background: #163a34; }
QLabel#brand { color: #eff8f4; font-size: 25px; font-weight: 700; }
QLabel#sideText { color: #accbc1; }
QPushButton#nav { background: transparent; color: #d1e4dc; text-align: left; border: 0; padding: 14px 18px; border-radius: 8px; }
QPushButton#nav:checked { background: #2b544a; color: white; font-weight: 600; }
QPushButton#nav:hover { background: #234b42; }
QPushButton { border: 1px solid #cddbd5; border-radius: 7px; padding: 10px 16px; background: white; font-weight: 600; }
QPushButton:hover { background: #edf5f1; border-color: #93b8a7; }
QPushButton:disabled { color: #91a19a; background: #edf0ee; }
QPushButton#primary { background: #167d70; color: white; border: 1px solid #167d70; }
QPushButton#primary:hover { background: #12685e; }
QPushButton#primary:disabled { background: #9abcb3; border-color: #9abcb3; }
QPushButton#sideButton { background: #2b544a; color: #eff8f4; border: 1px solid #426b60; }
QLabel#eyebrow { color: #688278; font-size: 11px; font-weight: 700; }
QLabel#title { font-size: 29px; font-weight: 700; }
QLabel#sub { color: #62796f; }
QLabel#section { font-size: 17px; font-weight: 600; }
QLabel#number { font-size: 31px; font-weight: 700; }
QLabel#pill { background: #dceee6; color: #236752; border-radius: 12px; padding: 7px 12px; font-size: 11px; font-weight: 700; }
QFrame#card { background: white; border: 1px solid #dce5df; border-radius: 10px; }
QLabel#notice { color: #785c21; background: #fff4d9; padding: 12px; border-radius: 7px; }
QLabel#success { color: #26634f; background: #e4f1ea; padding: 12px; border-radius: 7px; }
QComboBox, QLineEdit, QSpinBox { background: #fff; border: 1px solid #ccdcd3; border-radius: 6px; padding: 8px; min-height: 19px; }
QComboBox::drop-down { border: 0; width: 24px; }
QCheckBox { spacing: 8px; padding: 4px 0; }
QTableWidget { background: white; alternate-background-color: #f4f8f5; border: 0; gridline-color: #e5ede8; selection-background-color: #dceee6; selection-color: #17332f; }
QHeaderView::section { background: #eef4f0; border: 0; border-bottom: 1px solid #dce5df; padding: 9px; color: #567166; font-weight: 600; }
QTabWidget::pane { border: 1px solid #dce5df; background: white; border-radius: 7px; }
QTabBar::tab { padding: 11px 18px; color: #62796f; background: #edf3ef; }
QTabBar::tab:selected { background: white; color: #167d70; font-weight: 700; }
QTextBrowser { border: 0; background: white; padding: 8px; }
QScrollArea { border: 0; background: transparent; }
QProgressBar { background: #dfe9e3; border: 0; border-radius: 3px; max-height: 5px; }
QProgressBar::chunk { background: #167d70; }
'''


def label(text: str, kind: str | None = None, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if kind:
        widget.setObjectName(kind)
    return widget


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName('card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return frame, layout


def table(headers: list[str]) -> QTableWidget:
    result = QTableWidget(0, len(headers))
    result.setHorizontalHeaderLabels(headers)
    result.verticalHeader().hide()
    result.setAlternatingRowColors(True)
    result.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    result.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    result.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    result.verticalHeader().setDefaultSectionSize(36)
    return result


def fill_table(widget: QTableWidget, rows: list[list]) -> None:
    widget.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            widget.setItem(i, j, QTableWidgetItem(str(value)))


class ScoreChart(QWidget):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.setMinimumHeight(185)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        left, right, top, bottom = 45, 12, 28, 36
        plot_w, plot_h = width - left - right, height - top - bottom
        painter.setFont(QFont('Segoe UI', 9))
        for fraction in (0, 0.25, 0.5, 0.75, 1):
            yy = int(top + (1 - fraction) * plot_h)
            painter.setPen(QPen(QColor('#e4ece7')))
            painter.drawLine(left, yy, width - right, yy)
            painter.setPen(QColor('#738b7e'))
            painter.drawText(0, yy - 8, 36, 18, Qt.AlignmentFlag.AlignRight, f'{fraction:.2f}')
        if not self.rows:
            painter.setPen(QColor('#738b7e'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Run an experiment to compare scores')
            return
        step = plot_w / len(self.rows)
        for i, (name, value, color) in enumerate(self.rows):
            bw = min(65, step * 0.48)
            xx = left + step * (i + 0.5) - bw / 2
            yy = top + (1 - value) * plot_h
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(int(xx), int(yy), int(bw), max(1, int(value * plot_h)), 4, 4)
            painter.setPen(QColor(INK))
            painter.drawText(int(xx - 20), int(yy - 23), int(bw + 40), 20, Qt.AlignmentFlag.AlignCenter, f'{value:.3f}')
            painter.setPen(QColor('#61796d'))
            painter.drawText(int(left + step * i), height - 29, int(step), 25, Qt.AlignmentFlag.AlignCenter, name)


class Task(QThread):
    message = Signal(str)
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            result = self.operation(self.message.emit, self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.ready.emit(result)
        except Cancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, history: History | None = None):
        super().__init__()
        self.history = history or History()
        self.dataset: Dataset | None = None
        self.current_report = None
        self.task: Task | None = None
        self.close_pending = False
        self.feature_boxes = []
        self.setWindowTitle('ModelCheck')
        self.resize(1410, 900)
        self.setMinimumSize(1080, 760)
        self.setStyleSheet(STYLE)
        root = QWidget()
        root.setObjectName('main')
        self.setCentralWidget(root)
        body = QHBoxLayout(root)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(224)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 29, 20, 24)
        side.setSpacing(10)
        side.addWidget(label('ModelCheck', 'brand'))
        side.addWidget(label('Evidence behind the score', 'sideText'))
        side.addSpacing(34)
        side.addWidget(label('WORKSPACE', 'sideText'))
        self.nav_buttons = []
        for i, title in enumerate(('01   Dataset & setup', '02   Results', '03   Saved experiments')):
            button = QPushButton(title)
            button.setObjectName('nav')
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=i: self.navigate(page))
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch()
        side.addWidget(label('CURRENT DATASET', 'sideText'))
        self.dataset_side = label('No dataset loaded', 'sideText', True)
        side.addWidget(self.dataset_side)
        side.addSpacing(12)
        self.load_button = QPushButton('Open CSV')
        self.load_button.setObjectName('sideButton')
        self.load_button.clicked.connect(self.choose_csv)
        side.addWidget(self.load_button)
        self.demo_button = QPushButton('Try the demo')
        self.demo_button.setObjectName('sideButton')
        self.demo_button.clicked.connect(self.load_demo)
        side.addWidget(self.demo_button)
        side.addSpacing(18)
        side.addWidget(label('Runs on your computer.\nNo uploads. No API keys.', 'sideText', True))
        body.addWidget(sidebar)
        main = QWidget()
        main.setObjectName('main')
        content = QVBoxLayout(main)
        content.setContentsMargins(30, 26, 30, 18)
        content.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(label('CLASSIFICATION LAB  /  v0.1 alpha', 'eyebrow'))
        top.addStretch()
        top.addWidget(label('LOCAL · NO UPLOADS', 'pill'))
        content.addLayout(top)
        self.pages = QStackedWidget()
        self.setup_page = self.build_setup()
        self.result_page = self.build_results()
        self.history_page = self.build_history()
        for page in (self.setup_page, self.result_page, self.history_page):
            self.pages.addWidget(page)
        content.addWidget(self.pages, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        content.addWidget(self.progress)
        footer = QHBoxLayout()
        self.status = label('Start with a CSV or explore the synthetic demo.', 'sub')
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.cancel_task)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        content.addLayout(footer)
        body.addWidget(main, 1)
        self.navigate(0)
        self.refresh_history()

    def navigate(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index == 2:
            self.refresh_history()

    def build_setup(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label('A good score needs a fair test.', 'title'))
        layout.addWidget(label('Choose the prediction task, then test it against the way the model will actually be used.', 'sub', True))
        layout.addSpacing(6)
        columns = QHBoxLayout()
        left = QVBoxLayout()
        setup_card, setup = card()
        setup.addWidget(label('Define the experiment', 'section'))
        setup.addWidget(label('PREDICTION COLUMN', 'eyebrow'))
        self.target = QComboBox()
        self.target.currentTextChanged.connect(self.target_changed)
        setup.addWidget(self.target)
        grid = QGridLayout()
        grid.addWidget(label('Positive label', 'sub'), 0, 0)
        grid.addWidget(label('Experiment name', 'sub'), 0, 1)
        self.positive = QComboBox()
        self.experiment_name = QLineEdit('Classification check')
        grid.addWidget(self.positive, 1, 0)
        grid.addWidget(self.experiment_name, 1, 1)
        setup.addLayout(grid)
        roles = QGridLayout()
        roles.addWidget(label('Group ID (optional)', 'sub'), 0, 0)
        roles.addWidget(label('Date column (optional)', 'sub'), 0, 1)
        self.group = QComboBox()
        self.time = QComboBox()
        for combo in (self.group, self.time):
            combo.currentTextChanged.connect(self.roles_changed)
        roles.addWidget(self.group, 1, 0)
        roles.addWidget(self.time, 1, 1)
        setup.addLayout(roles)
        setup.addWidget(label('TESTING METHODS', 'eyebrow'))
        self.strategy_boxes = {}
        for key, title in (('random', 'Random: mix records, keep label proportions'),
                           ('group', 'New groups: hold out entire customers or subjects'),
                           ('time', 'Future records: train earlier, test later')):
            box = QCheckBox(title)
            box.setChecked(key == 'random')
            self.strategy_boxes[key] = box
            setup.addWidget(box)
        options = QGridLayout()
        options.addWidget(label('Test fraction', 'sub'), 0, 0)
        options.addWidget(label('Random seed', 'sub'), 0, 1)
        self.test_fraction = QSpinBox()
        self.test_fraction.setRange(10, 40)
        self.test_fraction.setValue(25)
        self.test_fraction.setSuffix('%')
        self.seed = QSpinBox()
        self.seed.setRange(0, 2**31 - 1)
        self.seed.setValue(42)
        options.addWidget(self.test_fraction, 1, 0)
        options.addWidget(self.seed, 1, 1)
        setup.addLayout(options)
        setup.addWidget(label('MODELS', 'eyebrow'))
        model_row = QHBoxLayout()
        self.model_boxes = {}
        for key, title in (('logistic', 'Logistic regression'), ('forest', 'Random forest')):
            box = QCheckBox(title)
            box.setChecked(True)
            self.model_boxes[key] = box
            model_row.addWidget(box)
        setup.addLayout(model_row)
        setup.addWidget(label('A majority-label baseline is included automatically.', 'sub', True))
        self.run_button = QPushButton('Run experiment')
        self.run_button.setObjectName('primary')
        self.run_button.clicked.connect(self.run_checks)
        self.run_button.setEnabled(False)
        setup.addWidget(self.run_button)
        left.addWidget(setup_card)
        left.addStretch()
        columns.addLayout(left, 1)
        right = QVBoxLayout()
        data_card, data = card()
        self.dataset_heading = label('Your dataset', 'section')
        self.dataset_description = label('Open a UTF-8 CSV with a header and two target labels.\nUp to 50,000 records and 100 MB.', 'sub', True)
        data.addWidget(self.dataset_heading)
        data.addWidget(self.dataset_description)
        self.preview_table = table(['Preview'])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.setMaximumHeight(185)
        data.addWidget(self.preview_table)
        right.addWidget(data_card)
        features_card, features = card()
        features.addWidget(label('Choose the input features', 'section'))
        features.addWidget(label('Exclude anything unavailable when making a prediction. Group IDs, dates and the target are excluded automatically.', 'sub', True))
        feature_scroll = QScrollArea()
        feature_scroll.setWidgetResizable(True)
        self.feature_widget = QWidget()
        self.feature_widget.setStyleSheet('background: white;')
        self.feature_layout = QVBoxLayout(self.feature_widget)
        self.feature_layout.setContentsMargins(0, 0, 0, 0)
        self.feature_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        feature_scroll.setWidget(self.feature_widget)
        features.addWidget(feature_scroll, 1)
        right.addWidget(features_card, 1)
        self.setup_notice = label('Results are evidence to review, not a guarantee that a model is ready to deploy.', 'notice', True)
        right.addWidget(self.setup_notice)
        columns.addLayout(right, 1)
        layout.addLayout(columns, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def build_results(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        texts = QVBoxLayout()
        texts.addWidget(label('See what the score is hiding.', 'title'))
        self.result_subtitle = label('Run an experiment to see the comparison.', 'sub', True)
        texts.addWidget(self.result_subtitle)
        header.addLayout(texts, 1)
        self.export_button = QPushButton('Export report')
        self.export_button.clicked.connect(self.export_report)
        self.export_button.setEnabled(False)
        header.addWidget(self.export_button)
        layout.addLayout(header)
        cards = QHBoxLayout()
        self.score_values = {}
        self.score_notes = {}
        for strategy in ('random', 'group', 'time'):
            frame, inside = card()
            inside.addWidget(label(STRATEGY_NAMES[strategy].upper(), 'eyebrow'))
            value = label('—', 'number')
            inside.addWidget(value)
            note = label('Balanced accuracy · not run', 'sub')
            inside.addWidget(note)
            cards.addWidget(frame)
            self.score_values[strategy] = value
            self.score_notes[strategy] = note
        layout.addLayout(cards)
        self.result_notice = label('Compare the same model across testing methods. Different methods answer different questions.', 'notice', True)
        layout.addWidget(self.result_notice)
        middle = QHBoxLayout()
        chart_card, chart_layout = card()
        chart_head = QHBoxLayout()
        chart_head.addWidget(label('Balanced accuracy by testing method', 'section'), 1)
        self.chart_model = QComboBox()
        self.chart_model.addItem('Logistic regression', 'logistic')
        self.chart_model.addItem('Random forest', 'forest')
        self.chart_model.currentIndexChanged.connect(self.update_chart)
        chart_head.addWidget(self.chart_model)
        chart_layout.addLayout(chart_head)
        self.chart = ScoreChart()
        chart_layout.addWidget(self.chart)
        chart_card.setMinimumHeight(265)
        middle.addWidget(chart_card, 3)
        audit_card, audit = card()
        audit.addWidget(label('Split checks', 'section'))
        self.audit_text = QTextBrowser()
        self.audit_text.setOpenExternalLinks(False)
        self.audit_text.setPlainText('Checks will appear here after a run.')
        audit.addWidget(self.audit_text)
        middle.addWidget(audit_card, 2)
        layout.addLayout(middle, 2)
        self.result_table = table(['Testing method', 'Model', 'Balanced acc.', 'ROC AUC', 'F1', 'Train / test'])
        self.result_table.itemSelectionChanged.connect(self.show_detail)
        self.result_table.setMinimumHeight(190)
        layout.addWidget(self.result_table, 2)
        tabs = QTabWidget()
        self.detail_text = QTextBrowser()
        self.detail_text.setPlainText('Select a result to inspect its confusion matrix and split.')
        tabs.addTab(self.detail_text, 'Selected result')
        self.group_table = table(['Group', 'Test records', 'Accuracy'])
        tabs.addTab(self.group_table, 'Group breakdown')
        self.notes_text = QTextBrowser()
        tabs.addTab(self.notes_text, 'Reading the results')
        tabs.setMinimumHeight(155)
        layout.addWidget(tabs, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def build_history(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label('Experiments worth keeping.', 'title'))
        layout.addWidget(label('Completed runs are saved locally with settings, dataset hashes and exact split membership.', 'sub', True))
        frame, inside = card()
        self.history_table = table(['Experiment', 'Completed (UTC)', 'ID'])
        self.history_table.doubleClicked.connect(self.open_history)
        inside.addWidget(self.history_table, 1)
        open_button = QPushButton('Open selected report')
        open_button.clicked.connect(self.open_history)
        inside.addWidget(open_button)
        layout.addWidget(frame, 1)
        restore = QPushButton('Use displayed report settings with the loaded dataset')
        restore.clicked.connect(self.restore_settings)
        layout.addWidget(restore)
        layout.addWidget(label('History includes column names, target labels and group summaries. Dataset contents and trained models are not saved. Keep reports private if those details are sensitive.', 'sub', True))
        return page

    def start_task(self, operation, receive, title: str):
        if self.task is not None:
            return
        self.task = Task(operation, self)
        self.task.message.connect(self.status.setText)
        self.task.ready.connect(receive)
        self.task.failed.connect(self.task_error)
        self.task.finished.connect(self.task_finished)
        self.set_busy(True)
        self.status.setText(title)
        self.task.start()

    def set_busy(self, busy: bool):
        for widget in (self.load_button, self.demo_button, self.setup_page, self.history_page):
            widget.setEnabled(not busy)
        self.run_button.setEnabled(not busy and self.dataset is not None)
        self.export_button.setEnabled(not busy and self.current_report is not None)
        self.progress.setVisible(busy)
        self.cancel_button.setVisible(busy)

    def task_error(self, message: str):
        self.status.setText('Experiment not completed.')
        if not self.close_pending:
            QMessageBox.warning(self, 'Please check these settings', message)

    def task_finished(self):
        was_cancelled = self.task.isInterruptionRequested()
        self.task.deleteLater()
        self.task = None
        self.set_busy(False)
        if was_cancelled:
            self.status.setText('Cancelled. No partial experiment was saved.')
        if self.close_pending:
            self.close()

    def cancel_task(self):
        if self.task:
            self.task.requestInterruption()
            self.status.setText('Stopping after the current loading or model-fitting stage...')

    def choose_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open dataset', '', 'CSV files (*.csv)')
        if path:
            self.start_task(lambda progress, cancelled: load_csv(path), self.set_dataset, 'Reading CSV...')

    def load_demo(self):
        self.set_dataset(demo_dataset())
        self.target.setCurrentText('purchased')
        self.group.setCurrentText('customer_id')
        self.time.setCurrentText('visit_date')
        self.strategy_boxes['group'].setChecked(True)
        self.strategy_boxes['time'].setChecked(True)
        self.experiment_name.setText('Repeated customers: split comparison')
        self.setup_notice.setText('Synthetic demo: account_signature identifies repeated customers. Random splits can reward memorisation; new-group tests ask about unseen customers.')

    def set_dataset(self, dataset: Dataset):
        self.dataset = dataset
        self.feature_boxes = []
        self.dataset_side.setText(dataset.name)
        self.dataset_heading.setText(dataset.name)
        missing = int(dataset.frame.isna().sum().sum())
        self.dataset_description.setText(f'{len(dataset.frame):,} records · {len(dataset.frame.columns)} columns · {missing:,} missing values\nShowing the first 5 records below.')
        for combo in (self.target, self.group, self.time):
            combo.blockSignals(True)
            combo.clear()
            if combo is not self.target:
                combo.addItem('(none)')
            combo.addItems(dataset.frame.columns.tolist())
            combo.blockSignals(False)
        for box in self.strategy_boxes.values():
            box.setChecked(False)
        self.strategy_boxes['random'].setChecked(True)
        self.target.setCurrentIndex(len(dataset.frame.columns) - 1)
        self.target_changed()
        self.preview_table.setColumnCount(min(6, len(dataset.frame.columns)))
        columns = dataset.frame.columns[:6].tolist()
        self.preview_table.setHorizontalHeaderLabels(columns)
        fill_table(self.preview_table, dataset.frame[columns].head(5).fillna('(missing)').values.tolist())
        self.setup_notice.setText('Choose a prediction column with exactly two labels. Review each feature for information that would only become available after the outcome.')
        self.navigate(0)
        self.run_button.setEnabled(self.task is None)
        self.status.setText('Dataset loaded. Choose the experiment settings.')

    def target_changed(self, *_):
        if self.dataset is None:
            return
        name = self.target.currentText()
        self.positive.clear()
        if name in self.dataset.frame:
            values = sorted(self.dataset.frame[name].dropna().astype(str).unique())
            self.positive.addItems(values[:100])
            if len(values) == 2:
                self.positive.setCurrentIndex(1)
        self.roles_changed()

    def roles_changed(self, *_):
        if self.dataset is None:
            return
        checked = {b.text() for b in self.feature_boxes if b.isChecked()}
        first = not self.feature_boxes
        while self.feature_layout.count():
            item = self.feature_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.feature_boxes = []
        excluded = {self.target.currentText(), self.group.currentText(), self.time.currentText()}
        for column in self.dataset.frame:
            if column in excluded:
                continue
            box = QCheckBox(column)
            box.setChecked(first or column in checked)
            self.feature_layout.addWidget(box)
            self.feature_boxes.append(box)

    def get_config(self) -> Config:
        return Config(target=self.target.currentText(),
                      features=tuple(box.text() for box in self.feature_boxes if box.isChecked()),
                      positive_label=self.positive.currentText(),
                      group=None if self.group.currentText() == '(none)' else self.group.currentText(),
                      time=None if self.time.currentText() == '(none)' else self.time.currentText(),
                      strategies=tuple(k for k, box in self.strategy_boxes.items() if box.isChecked()),
                      models=tuple(k for k, box in self.model_boxes.items() if box.isChecked()),
                      test_size=self.test_fraction.value() / 100, seed=self.seed.value())

    def run_checks(self):
        if self.dataset is None:
            return
        config = self.get_config()
        dataset = self.dataset
        self.start_task(lambda progress, cancelled: run_experiment(dataset, config, progress, cancelled),
                        self.receive_report, 'Preparing experiment...')

    def receive_report(self, report):
        try:
            self.history.save(self.experiment_name.text(), report)
            self.status.setText('Completed. Report saved locally.')
        except Exception as exc:
            # Displaying a computed report remains possible if local storage fails.
            self.status.setText(f'Completed, but history could not be saved: {exc}')
        self.show_report(report)

    def show_report(self, report: dict):
        self.current_report = report
        self.result_subtitle.setText(f"{report['dataset']['name']} · {report['dataset']['rows']:,} records · positive label: {report['config']['positive_label']}")
        available_models = list(dict.fromkeys(r['model'] for r in report['results'] if r['model'] != 'baseline'))
        self.chart_model.blockSignals(True)
        self.chart_model.clear()
        for model in available_models:
            self.chart_model.addItem(LABELS[model], model)
        self.chart_model.blockSignals(False)
        fill_table(self.result_table, [[LABELS[r['strategy']], LABELS[r['model']],
            f"{r['metrics']['balanced_accuracy']:.3f}", f"{r['metrics']['roc_auc']:.3f}", f"{r['metrics']['f1']:.3f}",
            f"{r['audit']['train_records']} / {r['audit']['test_records']}"] for r in report['results']])
        self.notes_text.setPlainText('\n\n'.join([
            'Balanced accuracy averages recall for the two labels. A value of 0.5 is the majority baseline for this binary task.',
            'ROC AUC measures how well probabilities rank the two labels. It does not show whether probabilities are calibrated.',
            'New-group splits hold out a fraction of groups, so the record fraction may differ. Future-record splits keep equal timestamps together.',
            *report['warnings'], *report['notes']]))
        self.update_chart()
        if report['results']:
            self.result_table.selectRow(1 if len(report['results']) > 1 else 0)
        self.export_button.setEnabled(self.task is None)
        self.navigate(1)

    def update_chart(self, *_):
        if self.current_report is None:
            return
        model = self.chart_model.currentData()
        chosen = {r['strategy']: r for r in self.current_report['results'] if r['model'] == model}
        colors = {'random': '#167d70', 'group': '#d39b43', 'time': '#708fa7'}
        self.chart.rows = []
        for strategy in ('random', 'group', 'time'):
            result = chosen.get(strategy)
            if result:
                value = result['metrics']['balanced_accuracy']
                self.score_values[strategy].setText(f'{value:.3f}')
                self.score_notes[strategy].setText(f"Balanced accuracy · {result['audit']['test_records']} test records")
                self.chart.rows.append((STRATEGY_NAMES[strategy], value, colors[strategy]))
            else:
                self.score_values[strategy].setText('—')
                self.score_notes[strategy].setText('Balanced accuracy · not run')
        self.chart.update()
        messages = []
        for strategy, result in chosen.items():
            audit = result['audit']
            messages.append(f"{STRATEGY_NAMES[strategy]}\n  Exact feature duplicates in test: {audit['duplicate_test_records']}")
            if audit['shared_groups'] is not None:
                messages[-1] += f"\n  Groups shared with training: {audit['shared_groups']}"
            unseen = sum(audit['unseen_category_values'].values())
            if unseen:
                messages[-1] += f'\n  Unseen categorical values: {unseen} cells'
        self.audit_text.setPlainText('\n\n'.join(messages))
        if 'random' in chosen and 'group' in chosen:
            delta = chosen['random']['metrics']['balanced_accuracy'] - chosen['group']['metrics']['balanced_accuracy']
            self.result_notice.setText(f'Random vs new groups: {delta * 100:+.1f} percentage points. This changes the prediction task; the gap alone does not prove leakage.')
        else:
            self.result_notice.setText('Review feature availability and choose the split that matches the intended use. A clean split check cannot rule out every kind of leakage.')

    def show_detail(self):
        if not self.current_report or self.result_table.currentRow() < 0:
            return
        row = self.result_table.currentRow()
        if row >= len(self.current_report['results']):
            return
        result = self.current_report['results'][row]
        m = result['metrics']
        tn, fp = m['confusion_matrix'][0]
        fn, tp = m['confusion_matrix'][1]
        lo, hi = m['accuracy_interval']
        text = (f"{LABELS[result['strategy']]} · {LABELS[result['model']]}\n"
                f'Confusion matrix: true negative {tn} · false positive {fp} · false negative {fn} · true positive {tp}\n'
                f"Accuracy {m['accuracy']:.3f} · precision {m['precision']:.3f} · recall {m['recall']:.3f}\n"
                f'Accuracy 95% Wilson interval: {lo:.3f}–{hi:.3f} (assumes independent records).\n'
                'Exact train/test record IDs are included in the JSON export.')
        if 'train_latest_date' in result['audit']:
            text += f"\nLatest training date: {result['audit']['train_latest_date']}\nEarliest test date: {result['audit']['test_earliest_date']}"
        self.detail_text.setPlainText(text)
        fill_table(self.group_table, [[g['group'], g['n'], f"{g['accuracy']:.3f}"] for g in result['groups']])

    def refresh_history(self):
        try:
            self.history_rows = self.history.list()
            fill_table(self.history_table, [[name, timestamp[:19].replace('T', ' '), identifier]
                                          for identifier, name, timestamp in self.history_rows])
        except Exception as exc:
            self.status.setText(f'History could not be opened: {exc}')

    def open_history(self, *_):
        row = self.history_table.currentRow()
        if row >= 0:
            try:
                self.show_report(self.history.load(self.history_rows[row][0]))
                self.status.setText('Saved report opened. No models were rerun.')
            except Exception as exc:
                QMessageBox.warning(self, 'Could not open report', str(exc))

    def restore_settings(self):
        if not self.current_report or not self.dataset:
            QMessageBox.information(self, 'Load the dataset first', 'Open a saved report and load its original CSV before restoring the settings.')
            return
        if self.current_report['dataset']['sha256'] != self.dataset.sha256:
            QMessageBox.warning(self, 'Dataset does not match', 'The loaded file hash differs from the report. Load the exact original CSV, or use the same built-in demo.')
            return
        config = self.current_report['config']
        self.target.setCurrentText(config['target'])
        self.group.setCurrentText(config['group'] or '(none)')
        self.time.setCurrentText(config['time'] or '(none)')
        self.positive.setCurrentText(config['positive_label'])
        for box in self.feature_boxes:
            box.setChecked(box.text() in config['features'])
        for key, box in self.strategy_boxes.items():
            box.setChecked(key in config['strategies'])
        for key, box in self.model_boxes.items():
            box.setChecked(key in config['models'])
        self.seed.setValue(config['seed'])
        self.test_fraction.setValue(round(config['test_size'] * 100))
        self.navigate(0)
        self.status.setText('Exact dataset matched. Settings restored; run again to repeat the experiment.')

    def export_report(self):
        if not self.current_report:
            return
        path, selected = QFileDialog.getSaveFileName(self, 'Export experiment report', 'modelcheck-report.html',
                                                    'HTML report (*.html);;JSON report (*.json)')
        if not path:
            return
        destination = Path(path)
        use_json = destination.suffix.lower() == '.json' or 'JSON' in selected
        if not destination.suffix:
            destination = destination.with_suffix('.json' if use_json else '.html')
        try:
            destination.write_text(to_json(self.current_report) if use_json else to_html(self.current_report), encoding='utf-8')
            self.status.setText(f'Report exported: {destination.name}')
        except OSError as exc:
            QMessageBox.warning(self, 'Could not export report', str(exc))

    def closeEvent(self, event):
        if self.task is not None:
            self.close_pending = True
            self.cancel_task()
            event.ignore()
            return
        self.history.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('ModelCheck')
    app.setOrganizationName('ModelCheck')
    window = MainWindow()
    window.show()
    if '--demo' in sys.argv:
        window.load_demo()
    return app.exec()
