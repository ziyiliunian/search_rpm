import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from .download import download_package


class DownloadBatchWorker(QThread):
    package_progress = pyqtSignal(int, int, int)
    package_finished = pyqtSignal(int, str)
    package_failed = pyqtSignal(int, str)
    batch_finished = pyqtSignal(int, int)

    def __init__(self, entries, destination, resume_event, max_workers=4):
        super().__init__()
        self.entries = entries
        self.destination = destination
        self.resume_event = resume_event
        self.max_workers = max(1, min(max_workers, len(entries), 8))

    def run(self):
        succeeded = 0
        failed = 0

        def download(index, entry):
            return download_package(
                entry,
                self.destination,
                lambda done, total: self.package_progress.emit(index, done, total),
                self.resume_event,
            )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(download, index, entry): index
                for index, entry in enumerate(self.entries)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    path = future.result()
                    succeeded += 1
                    self.package_finished.emit(index, path)
                except Exception as exc:
                    failed += 1
                    self.package_failed.emit(index, str(exc))
        self.batch_finished.emit(succeeded, failed)


class DownloadManagerDialog(QDialog):
    batch_finished = pyqtSignal(object, str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.resume_event = threading.Event()
        self.resume_event.set()
        self.workers = []
        self.total_completed = 0
        self.setWindowTitle("下载内容")
        self.resize(820, 460)
        self.setModal(False)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.summary = QLabel("尚未创建下载任务。")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["软件包", "保存目录", "进度", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        footer = QHBoxLayout()
        self.overall = QProgressBar()
        self.overall.setRange(0, 0)
        self.pause_button = QPushButton("暂停全部")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self._toggle_pause)
        close_button = QPushButton("关闭并返回主界面")
        close_button.clicked.connect(self.close)
        footer.addWidget(self.overall)
        footer.addWidget(self.pause_button)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def add_downloads(self, entries, destination, targets, max_workers=4):
        start_row = self.table.rowCount()
        self.table.setRowCount(start_row + len(entries))
        for index, entry in enumerate(entries):
            row = start_row + index
            self.table.setItem(row, 0, QTableWidgetItem(entry.nevra))
            self.table.setItem(row, 1, QTableWidgetItem(destination))
            progress = QProgressBar()
            progress.setRange(0, 100)
            self.table.setCellWidget(row, 2, progress)
            self.table.setItem(row, 3, QTableWidgetItem("等待下载"))

        self.overall.setRange(0, self.table.rowCount())
        self.overall.setValue(self.total_completed)
        worker = DownloadBatchWorker(entries, destination, self.resume_event, max_workers)
        worker.package_progress.connect(
            lambda row, done, total, offset=start_row: self._update_progress(offset + row, done, total)
        )
        worker.package_finished.connect(
            lambda row, path, offset=start_row: self._package_finished(offset + row, path)
        )
        worker.package_failed.connect(
            lambda row, message, offset=start_row: self._package_failed(offset + row, message)
        )
        worker.batch_finished.connect(
            lambda succeeded, failed, batch_targets=targets: self._batch_finished(
                batch_targets, destination, succeeded, failed
            )
        )
        worker.finished.connect(lambda current=worker: self._worker_stopped(current))
        self.workers.append(worker)
        self.summary.setText(
            f"正在下载，共 {self.table.rowCount()} 个软件包；最多 {max_workers} 个并发线程。"
        )
        self.pause_button.setEnabled(True)
        worker.start()

    def has_active_downloads(self):
        return any(worker.isRunning() for worker in self.workers)

    def _toggle_pause(self):
        if self.resume_event.is_set():
            self.resume_event.clear()
            self.pause_button.setText("恢复全部")
            self.summary.setText("下载已暂停。正在读取的数据块完成后进入等待。")
        else:
            self.resume_event.set()
            self.pause_button.setText("暂停全部")
            self.summary.setText("下载已恢复。")

    def _update_progress(self, row, done, total):
        progress = self.table.cellWidget(row, 2)
        if total:
            progress.setRange(0, 100)
            progress.setValue(min(100, int(done * 100 / total)))
        else:
            progress.setRange(0, 0)
        self.table.item(row, 3).setText("下载中")

    def _package_finished(self, row, path):
        progress = self.table.cellWidget(row, 2)
        progress.setRange(0, 100)
        progress.setValue(100)
        self.table.item(row, 3).setText("完成：" + path)
        self.total_completed += 1
        self.overall.setValue(self.total_completed)

    def _package_failed(self, row, message):
        self.table.item(row, 3).setText("失败：" + message)
        self.total_completed += 1
        self.overall.setValue(self.total_completed)

    def _batch_finished(self, targets, destination, succeeded, failed):
        self.batch_finished.emit(targets, destination, succeeded, failed)

    def _worker_stopped(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        worker.deleteLater()
        if not self.has_active_downloads():
            self.resume_event.set()
            self.pause_button.setText("暂停全部")
            self.pause_button.setEnabled(False)
            self.summary.setText(
                f"当前任务全部完成：累计处理 {self.total_completed} 个软件包。"
            )

    def closeEvent(self, event):
        self.hide()
        event.ignore()
