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

    def __init__(self, entries, destination, max_workers=4):
        super().__init__()
        self.entries = entries
        self.destination = destination
        self.max_workers = max(1, min(max_workers, len(entries), 8))

    def run(self):
        succeeded = 0
        failed = 0

        def download(index, entry):
            return download_package(
                entry,
                self.destination,
                lambda done, total: self.package_progress.emit(index, done, total),
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


class DownloadProgressDialog(QDialog):
    all_finished = pyqtSignal(object)

    def __init__(self, entries, destination, parent=None, max_workers=4):
        super().__init__(parent, Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.entries = entries
        self.destination = destination
        self.completed = 0
        self.setWindowTitle("包下载进度")
        self.resize(760, 420)
        self.setModal(False)
        self._build_ui()

        self.worker = DownloadBatchWorker(entries, destination, max_workers)
        self.worker.package_progress.connect(self._update_progress)
        self.worker.package_finished.connect(self._package_finished)
        self.worker.package_failed.connect(self._package_failed)
        self.worker.batch_finished.connect(self._batch_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.summary = QLabel(
            f"正在使用最多 4 个线程下载 {len(self.entries)} 个软件包。关闭窗口不会中断下载。"
        )
        layout.addWidget(self.summary)
        self.table = QTableWidget(len(self.entries), 3)
        self.table.setHorizontalHeaderLabels(["软件包", "进度", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, entry in enumerate(self.entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.nevra))
            progress = QProgressBar()
            progress.setRange(0, 100)
            self.table.setCellWidget(row, 1, progress)
            self.table.setItem(row, 2, QTableWidgetItem("等待下载"))
        layout.addWidget(self.table)
        footer = QHBoxLayout()
        self.overall = QProgressBar()
        self.overall.setRange(0, len(self.entries))
        close_button = QPushButton("关闭并返回主界面")
        close_button.clicked.connect(self.close)
        footer.addWidget(self.overall)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def _update_progress(self, row, done, total):
        progress = self.table.cellWidget(row, 1)
        if total:
            progress.setRange(0, 100)
            progress.setValue(min(100, int(done * 100 / total)))
        else:
            progress.setRange(0, 0)
        self.table.item(row, 2).setText("下载中")

    def _package_finished(self, row, path):
        progress = self.table.cellWidget(row, 1)
        progress.setRange(0, 100)
        progress.setValue(100)
        self.table.item(row, 2).setText("完成：" + path)
        self.completed += 1
        self.overall.setValue(self.completed)

    def _package_failed(self, row, message):
        self.table.item(row, 2).setText("失败：" + message)
        self.completed += 1
        self.overall.setValue(self.completed)

    def _batch_finished(self, succeeded, failed):
        self.summary.setText(f"下载任务完成：成功 {succeeded} 个，失败 {failed} 个。")
        self.all_finished.emit(self)
