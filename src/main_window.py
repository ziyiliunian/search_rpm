from pathlib import Path

from PyQt5.QtCore import QSettings, QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .cache import clear_cache
from .download_dialog import DownloadProgressDialog
from .repository import load_packages, parse_package_names, search_packages

MAIN_BASE_URL = "https://update.cs2c.com.cn/NS/V10/"
EPKL_BASE_URL = "https://eps-server.openkylin.top/NS/V10/"
VERSIONS = ["V10SP3", "V10SP2", "V10SP1"]
OS_TYPES = {"V10SP3": ["os", "sm-os"], "V10SP2": ["os"], "V10SP1": ["os"]}
ARCHES = {
    "V10SP3": ["aarch64", "x86_64", "loongarch64"],
    "V10SP2": ["aarch64", "x86_64"],
    "V10SP1": ["aarch64", "x86_64"],
}
MAIN_REPOS = (("base", "base"), ("update", "updates"))
EPKL_REPOS = (
    ("EPEL 主源（EPKL/main）", "epkl-main"),
    ("EPEL 更新源（EPKL/update）", "epkl-update"),
)
CACHE_OPTIONS = (("不使用缓存", 0), ("缓存 1 小时", 3600), ("缓存 24 小时", 86400), ("缓存 7 天", 604800))


class LoadWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, urls, cache_seconds):
        super().__init__()
        self.urls = urls
        self.cache_seconds = cache_seconds

    def run(self):
        packages = []
        errors = []
        for url, repo_name in self.urls:
            try:
                packages.extend(load_packages(url, repo_name, self.cache_seconds))
            except Exception as exc:
                errors.append(f"{repo_name}: {exc}")
        if packages:
            self.loaded.emit(packages)
        else:
            self.failed.emit("；".join(errors) or "没有可加载的仓库")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ziyiliunian", "kylin-server-rpm-search")
        self.packages = []
        self.imported_names = []
        self.worker = None
        self.download_dialogs = []
        self.active_download_targets = set()
        self.setWindowTitle("银河麒麟服务器多架构包下载工具")
        self.resize(1220, 780)
        self._build_ui()
        self._initialize_options()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        workflow = QGroupBox(
            "工作流程：选择系统版本 → 选择 OS 类型 → 选择芯片架构 → 选择软件仓库 → 输入或导入包名 → 搜索 → 选择目录 → 下载内容"
        )
        form = QFormLayout(workflow)
        self.version = QComboBox()
        self.version.currentTextChanged.connect(self._version_changed)
        self.os_type = QComboBox()
        self.arch = QComboBox()
        self.repo = QListWidget()
        self.repo.setMaximumHeight(104)
        self.repo.setSelectionMode(QAbstractItemView.MultiSelection)
        form.addRow("系统版本", self.version)
        form.addRow("OS 类型", self.os_type)
        form.addRow("芯片架构", self.arch)
        form.addRow("软件仓库", self.repo)
        layout.addWidget(workflow)

        search = QHBoxLayout()
        self.name_query = QLineEdit()
        self.name_query.setPlaceholderText("包名，例如 kernel*；也可从 TXT 导入多个包名")
        self.version_query = QLineEdit()
        self.version_query.setPlaceholderText("版本模糊匹配（可选），例如 89.44")
        import_button = QPushButton("从文件导入")
        import_button.clicked.connect(self._import_package_names)
        self.import_status = QLabel("未导入文件")
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self._search)
        search.addWidget(self.name_query, 3)
        search.addWidget(self.version_query, 2)
        search.addWidget(import_button)
        search.addWidget(self.import_status, 2)
        search.addWidget(self.search_button)
        layout.addLayout(search)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["选择", "包名", "版本", "架构", "仓库", "简介", "下载地址"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        select_all = QPushButton("全选结果")
        select_all.clicked.connect(self._select_all)
        copy_repo = QPushButton("复制仓库地址")
        copy_repo.clicked.connect(self._copy_repo_urls)
        self.destination = QLineEdit(str(Path.home() / "Downloads"))
        choose = QPushButton("选择目录")
        choose.clicked.connect(self._choose_destination)
        download = QPushButton("下载内容")
        download.clicked.connect(self._start_download)
        actions.addWidget(select_all)
        actions.addWidget(copy_repo)
        actions.addWidget(QLabel("下载目录"))
        actions.addWidget(self.destination, 3)
        actions.addWidget(choose)
        actions.addWidget(download)
        layout.addLayout(actions)

        cache_row = QHBoxLayout()
        self.cache_policy = QComboBox()
        for text, seconds in CACHE_OPTIONS:
            self.cache_policy.addItem(text, seconds)
        saved_cache = self.settings.value("cache_seconds", 86400, type=int)
        index = self.cache_policy.findData(saved_cache)
        self.cache_policy.setCurrentIndex(index if index >= 0 else 2)
        self.cache_policy.currentIndexChanged.connect(self._save_cache_policy)
        clear_button = QPushButton("清除缓存")
        clear_button.clicked.connect(self._clear_cache)
        cache_row.addWidget(QLabel("仓库索引缓存"))
        cache_row.addWidget(self.cache_policy)
        cache_row.addWidget(clear_button)
        cache_row.addStretch()
        layout.addLayout(cache_row)

        self.status = QLabel("就绪")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _initialize_options(self):
        self.version.addItems(VERSIONS)
        self.version.setCurrentText("V10SP3")
        self._version_changed("V10SP3")

    @staticmethod
    def _set_combo(combo, values, preferred):
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        index = combo.findText(preferred)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _version_changed(self, version):
        self._set_combo(self.os_type, OS_TYPES.get(version, ["os"]), "os")
        arches = ARCHES.get(version, ["aarch64", "x86_64"])
        self._set_combo(self.arch, arches, "aarch64")
        self.repo.clear()
        for display, key in MAIN_REPOS + EPKL_REPOS:
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, key)
            self.repo.addItem(item)
            item.setSelected(key in {"base", "updates"})

    def _import_package_names(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入包名文件", str(Path.home()), "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = Path(path).read_text(encoding="gb18030")
            except (OSError, UnicodeError) as exc:
                QMessageBox.critical(self, "导入失败", str(exc))
                return
        except OSError as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.imported_names = parse_package_names(text)
        self.import_status.setText(f"已导入 {len(self.imported_names)} 个包名：{Path(path).name}")
        self.import_status.setToolTip("\n".join(self.imported_names))

    def _repo_urls(self):
        version = self.version.currentText()
        os_type = self.os_type.currentText()
        arch = self.arch.currentText()
        urls = []
        for item in self.repo.selectedItems():
            key = item.data(Qt.UserRole)
            if key in {"base", "updates"}:
                url = f"{MAIN_BASE_URL}{version}/{os_type}/adv/lic/{key}/{arch}/"
            elif key == "epkl-main":
                url = f"{EPKL_BASE_URL}{version}/EPKL/main/{arch}/"
            elif key == "epkl-update":
                url = f"{EPKL_BASE_URL}{version}/EPKL/update/main/{arch}/"
            else:
                continue
            urls.append((url, key))
        return urls

    def _search(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "提示", "仓库索引正在加载，请稍候。")
            return
        urls = self._repo_urls()
        if not urls:
            QMessageBox.information(self, "提示", "请至少选择一个软件仓库。")
            return
        self.search_button.setEnabled(False)
        self.status.setText("正在读取仓库索引（优先使用有效缓存）…")
        self.worker = LoadWorker(urls, self.cache_policy.currentData())
        self.worker.loaded.connect(self._on_loaded)
        self.worker.failed.connect(self._on_load_failed)
        self.worker.finished.connect(self._search_finished)
        self.worker.start()

    def _on_loaded(self, packages):
        self.packages = packages
        results = search_packages(
            packages, self.name_query.text(), self.version_query.text(), self.imported_names
        )
        self._show_results(results)
        self.status.setText(f"索引包含 {len(packages)} 个包，匹配 {len(results)} 个")

    def _on_load_failed(self, message):
        self.status.setText("索引加载失败")
        QMessageBox.critical(self, "索引加载失败", message)

    def _search_finished(self):
        self.search_button.setEnabled(True)
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def _show_results(self, results):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for entry in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, entry)
            self.table.setItem(row, 0, check)
            values = (
                entry.name, f"{entry.version}-{entry.release}", entry.arch,
                entry.repo, entry.summary, entry.url,
            )
            for column, value in enumerate(values, 1):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _select_all(self):
        state = Qt.Checked if any(
            self.table.item(row, 0).checkState() == Qt.Unchecked
            for row in range(self.table.rowCount())
        ) else Qt.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def _choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.destination.text())
        if path:
            self.destination.setText(path)

    def _copy_repo_urls(self):
        urls = [url for url, _ in self._repo_urls()]
        if not urls:
            QMessageBox.information(self, "提示", "请至少选择一个软件仓库。")
            return
        QApplication.clipboard().setText("\n".join(urls))
        self.status.setText(f"已复制 {len(urls)} 个仓库地址")

    def _selected_entries(self):
        entries = []
        seen_urls = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                entry = item.data(Qt.UserRole)
                if entry.url not in seen_urls:
                    entries.append(entry)
                    seen_urls.add(entry.url)
        return entries

    def _start_download(self):
        entries = self._selected_entries()
        if not entries:
            QMessageBox.information(self, "提示", "请先勾选要下载的 RPM 包。")
            return
        destination = self.destination.text().strip()
        if not destination:
            QMessageBox.information(self, "提示", "请选择下载目录。")
            return
        destination_path = str(Path(destination).expanduser().resolve())
        accepted = []
        targets = set()
        duplicates = 0
        for entry in entries:
            filename = entry.url.rstrip("/").split("/")[-1].split("?", 1)[0]
            target = (destination_path, filename)
            if target in self.active_download_targets or target in targets:
                duplicates += 1
                continue
            targets.add(target)
            accepted.append(entry)
        if not accepted:
            QMessageBox.information(self, "提示", "所选软件包已经在下载任务中。")
            return
        if duplicates:
            self.status.setText(f"已跳过 {duplicates} 个目标文件重复的软件包")
        self.active_download_targets.update(targets)
        dialog = DownloadProgressDialog(accepted, destination_path, self, max_workers=4)
        dialog.download_targets = targets
        self.download_dialogs.append(dialog)
        dialog.all_finished.connect(self._download_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _download_finished(self, dialog):
        self.active_download_targets.difference_update(dialog.download_targets)
        if dialog in self.download_dialogs:
            self.download_dialogs.remove(dialog)
        self.status.setText(f"一个下载任务已完成，保存目录：{dialog.destination}")

    def _save_cache_policy(self):
        self.settings.setValue("cache_seconds", self.cache_policy.currentData())

    def _clear_cache(self):
        try:
            clear_cache()
            self.status.setText("缓存已清除，下次搜索将重新获取仓库索引")
        except OSError as exc:
            QMessageBox.critical(self, "清除缓存失败", str(exc))

    def closeEvent(self, event):
        if self.active_download_targets:
            QMessageBox.information(
                self, "下载仍在进行",
                "仍有下载任务在后台运行。请等待任务完成后再退出；可关闭下载进度弹窗并继续使用主界面。",
            )
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "索引正在加载", "请等待当前仓库索引加载完成后再退出。")
            event.ignore()
            return
        event.accept()
