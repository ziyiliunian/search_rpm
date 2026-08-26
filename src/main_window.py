from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPushButton, QProgressBar, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget
)

from .download import download_package
from .repository import list_directory, load_packages, search_packages

BASE_URL = "https://update.cs2c.com.cn/NS/V10/"
ARCHES = ["x86_64", "aarch64", "arm64", "loongarch64", "riscv64", "ppc64le", "noarch"]


class LoadWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, urls):
        super().__init__()
        self.urls = urls

    def run(self):
        packages = []
        errors = []
        for url, repo_name in self.urls:
            try:
                packages.extend(load_packages(url, repo_name))
            except Exception as exc:
                errors.append(f"{repo_name}: {exc}")
        if packages:
            self.loaded.emit(packages)
        else:
            self.failed.emit("；".join(errors) or "没有可加载的仓库")


class DownloadWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, entries, destination):
        super().__init__()
        self.entries, self.destination = entries, destination

    def run(self):
        results = []
        try:
            for index, entry in enumerate(self.entries, 1):
                path = download_package(entry, self.destination, lambda done, total: self.progress.emit(done, total, f"{index}/{len(self.entries)} {entry.name}"))
                results.append(path)
            self.finished.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.packages = []
        self.worker = None
        self.download_worker = None
        self.setWindowTitle("Search RPM")
        self.resize(1200, 760)
        self._build_ui()
        self._load_versions()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        filters = QGroupBox("仓库选择")
        form = QFormLayout(filters)
        self.version = QListWidget()
        self.version.setMaximumHeight(92)
        self.version.itemSelectionChanged.connect(self._load_os)
        self.os_type = QListWidget()
        self.os_type.setMaximumHeight(72)
        self.os_type.itemSelectionChanged.connect(self._load_arches)
        self.arch = QListWidget()
        self.arch.setMaximumHeight(72)
        self.repo = QListWidget()
        self.repo.setMaximumHeight(72)
        self.repo.addItems(["base", "updates"])
        for row in (self.version, self.os_type, self.arch):
            row.setSelectionMode(QAbstractItemView.SingleSelection)
        self.repo.setSelectionMode(QAbstractItemView.MultiSelection)
        for index in range(self.repo.count()):
            self.repo.item(index).setSelected(True)
        form.addRow("系统版本", self.version)
        form.addRow("OS 类型", self.os_type)
        form.addRow("芯片架构", self.arch)
        form.addRow("仓库", self.repo)
        layout.addWidget(filters)

        search = QHBoxLayout()
        self.name_query = QLineEdit()
        self.name_query.setPlaceholderText("包名，例如 kernel* 或 openssl")
        self.version_query = QLineEdit()
        self.version_query.setPlaceholderText("版本模糊匹配，例如 89.44")
        self.repo_query = QLineEdit()
        self.repo_query.setPlaceholderText("库名模糊匹配，可选")
        button = QPushButton("搜索")
        button.clicked.connect(self._search)
        for widget in (self.name_query, self.version_query, self.repo_query):
            search.addWidget(widget)
        search.addWidget(button)
        layout.addLayout(search)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["选择", "包名", "版本", "架构", "仓库", "简介", "下载地址"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        self.select_all = QPushButton("全选结果")
        self.select_all.clicked.connect(self._select_all)
        browse = QPushButton("浏览仓库")
        browse.clicked.connect(self._browse_repo)
        download = QPushButton("下载选中包")
        download.clicked.connect(self._download)
        self.destination = QLineEdit(str(Path.home() / "Downloads"))
        choose = QPushButton("选择目录")
        choose.clicked.connect(self._choose_destination)
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        for widget in (self.select_all, browse, download, QLabel("目录"), self.destination, choose, self.progress):
            actions.addWidget(widget)
        layout.addLayout(actions)
        self.status = QLabel("就绪：请选择版本、OS、架构和仓库后搜索")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _add_single(self, widget, value):
        widget.clear()
        widget.addItem(value)
        widget.setCurrentRow(0)

    def _load_versions(self):
        self.status.setText("正在读取系统版本目录…")
        try:
            entries = list_directory(BASE_URL)
            names = [name for name, _ in entries if name]
            self.version.clear()
            self.version.addItems(names)
            if names:
                preferred = names.index("V10SP3") if "V10SP3" in names else 0
                self.version.setCurrentRow(preferred)
        except Exception as exc:
            self._add_single(self.version, "V10SP3")
            self.status.setText(f"版本目录读取失败，可继续手动尝试：{exc}")

    def _selected_path(self):
        values = []
        for widget in (self.version, self.os_type):
            item = widget.currentItem()
            if item:
                values.append(item.text().strip("/"))
        return values

    def _load_os(self):
        item = self.version.currentItem()
        path = [item.text().strip("/")] if item else []
        self._load_children(self.os_type, path, "OS 类型")

    def _load_arches(self):
        path = self._selected_path() + ["adv", "lic", "base"]
        self._load_children(self.arch, path, "芯片架构")

    def _load_children(self, widget, path_parts, label):
        if not path_parts:
            return
        try:
            url = BASE_URL + "/".join(path_parts) + "/"
            entries = list_directory(url)
            names = [name for name, _ in entries]
            widget.clear()
            widget.addItems(names or ["lic"])
            widget.setCurrentRow(0)
            self.status.setText(f"已加载 {label} 候选：{len(names)} 项")
        except Exception as exc:
            self._add_single(widget, "lic")
            self.status.setText(f"{label}目录读取失败：{exc}")

    def _repo_urls(self):
        parts = self._selected_path() + ["adv", "lic"]
        arch_item = self.arch.currentItem()
        if not arch_item:
            return []
        arch = arch_item.text().strip("/")
        selected = [item.text() for item in self.repo.selectedItems()]
        if not selected:
            selected = ["base", "updates"]
        return [(BASE_URL + "/".join(parts + [name, arch]) + "/", name) for name in selected]

    def _repo_url(self):
        return self._repo_urls()[0][0]

    def _search(self):
        self.status.setText("正在加载仓库索引…")
        self.worker = LoadWorker(self._repo_urls())
        self.worker.loaded.connect(self._on_loaded)
        self.worker.failed.connect(lambda msg: self.status.setText(f"索引加载失败：{msg}"))
        self.worker.start()

    def _on_loaded(self, packages):
        self.packages = packages
        self._show_results(search_packages(packages, self.name_query.text(), self.version_query.text(), self.repo_query.text()))
        self.status.setText(f"索引加载完成，共 {len(packages)} 个包")

    def _show_results(self, results):
        self.table.setRowCount(0)
        for entry in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, entry)
            self.table.setItem(row, 0, check)
            for col, value in enumerate((entry.name, entry.version + "-" + entry.release, entry.arch, entry.repo, entry.summary, entry.url), 1):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.status.setText(f"匹配到 {len(results)} 个 RPM 包")

    def _select_all(self):
        state = Qt.Checked if any(self.table.item(row, 0).checkState() == Qt.Unchecked for row in range(self.table.rowCount())) else Qt.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def _choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.destination.text())
        if path:
            self.destination.setText(path)

    def _browse_repo(self):
        QApplication.clipboard().setText(self._repo_url())
        self.status.setText(f"仓库地址已复制：{self._repo_url()}")

    def _download(self):
        entries = [self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount()) if self.table.item(row, 0).checkState() == Qt.Checked]
        if not entries:
            QMessageBox.information(self, "提示", "请先勾选要下载的 RPM 包。")
            return
        self.download_worker = DownloadWorker(entries, self.destination.text())
        self.download_worker.progress.connect(lambda done, total, text: (self.progress.setMaximum(total or 1), self.progress.setValue(done), self.status.setText("下载中：" + text)))
        self.download_worker.finished.connect(lambda paths: self.status.setText(f"下载完成：{len(paths)} 个包，目录：{self.destination.text()}"))
        self.download_worker.failed.connect(lambda msg: QMessageBox.critical(self, "下载失败", msg))
        self.download_worker.start()
