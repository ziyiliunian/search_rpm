from pathlib import Path
from urllib.parse import urlsplit

from PyQt5.QtCore import QSettings, QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .cache import clear_cache
from .download_dialog import DownloadManagerDialog
from .repository import load_packages, parse_package_names, search_packages

SYSTEM_BASE_URL = "https://update.cs2c.com.cn/NS/"
EPKL_BASE_URL = "https://eps-server.openkylin.top/NS/"
CS_BASE_URL = "https://update.cs2c.com.cn/CS/"

SOURCE_SYSTEM_VERSIONS = {
    "SYSTEM": ["V10", "V11"],
    "EPKL": ["V10", "V11"],
    "CS": ["V10"],
}
RELEASES = {
    ("SYSTEM", "V10"): ["V10SP1", "V10SP2", "V10SP3", "V10SP3-2403"],
    ("SYSTEM", "V11"): ["2503", "V11SP1-2603"],
    ("EPKL", "V10"): ["V10SP1", "V10SP2", "V10SP3", "V10SP3-2403", "HPC", "V10.4-HPC", "V10AIPLUS"],
    ("EPKL", "V11"): ["2503"],
    ("CS", "V10"): ["V10SP3", "V10SP3-2403"],
}
SYSTEM_COMPONENTS = {
    ("V10", "V10SP3"): [("os", "os") , ("sm-os", "sm-os")],
}
CS_COMPONENTS = {
    ("V10", "V10SP3"): [("os（hwy）", "hwy/os", "standard")],
    ("V10", "V10SP3-2403"): [
        ("os（aiplus）", "aiplus/os", "standard"),
        ("os（ccw）", "ccw/os", "standard"),
        ("os（gazb）", "gazb/os", "standard"),
        ("os（lowlatency）", "lowlatency/os", "standard"),
        ("kernel-4k", "kernel-4k", "direct"),
    ],
}
EPKL_MULTI_COMPONENTS = {
    ("V10", "V10SP3"): ["Compiler", "DB", "Storage"],
    ("V10", "V10SP3-2403"): ["Compiler", "DB", "Storage"],
    ("V11", "2503"): ["AI"],
}
EPKL_REPOSITORIES = {
    ("V10", "V10.4-HPC"): [("main", "main")],
    ("V10", "V10AIPLUS"): [("main", "main")],
}
ARCHES = {
    ("SYSTEM", "V10", "V10SP1"): ["aarch64", "x86_64"],
    ("SYSTEM", "V10", "V10SP2"): ["aarch64", "x86_64"],
    ("SYSTEM", "V10", "V10SP3"): ["aarch64", "x86_64", "loongarch64"],
    ("SYSTEM", "V10", "V10SP3-2403"): ["aarch64", "x86_64", "loongarch64"],
    ("SYSTEM", "V11", "2503"): ["aarch64", "x86_64", "loongarch64"],
    ("SYSTEM", "V11", "V11SP1-2603"): ["aarch64", "x86_64", "loongarch64", "sw_64"],
    ("EPKL", "V10", "V10SP1"): ["aarch64", "x86_64"],
    ("EPKL", "V10", "V10SP2"): ["aarch64", "x86_64"],
    ("EPKL", "V10", "V10SP3"): ["aarch64", "x86_64", "loongarch64"],
    ("EPKL", "V10", "V10SP3-2403"): ["aarch64", "x86_64", "loongarch64"],
    ("EPKL", "V10", "HPC"): ["aarch64", "x86_64"],
    ("EPKL", "V10", "V10.4-HPC"): ["aarch64", "x86_64"],
    ("EPKL", "V10", "V10AIPLUS"): ["aarch64", "x86_64"],
    ("EPKL", "V11", "2503"): ["aarch64", "x86_64", "loongarch64"],
    ("CS", "V10", "V10SP3"): ["aarch64", "x86_64"],
    ("CS", "V10", "V10SP3-2403"): ["aarch64", "x86_64"],
}
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
        self.active_download_targets = set()
        self.download_manager = DownloadManagerDialog(self)
        self.download_manager.batch_finished.connect(self._download_finished)
        self.setWindowTitle("银河麒麟服务器多架构包下载工具")
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(1240, 820)
        self._build_ui()
        self._initialize_options()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        workflow = QGroupBox(
            "工作流程：选择产品源 → 系统版本 → 发行版本号 → EPKL 仓库分类 → 系统维护与补丁组件 → 芯片架构 → 软件仓库 → 搜索 → 开始下载 → 下载内容"
        )
        form = QFormLayout(workflow)
        self.source = QComboBox()
        self.source.addItem("系统源（update.cs2c.com.cn/NS）", "SYSTEM")
        self.source.addItem("EPKL 源（eps-server.openkylin.top/NS）", "EPKL")
        self.source.addItem("CS 源（update.cs2c.com.cn/CS）", "CS")
        self.source.currentIndexChanged.connect(self._source_changed)
        self.system_version = QComboBox()
        self.system_version.currentTextChanged.connect(self._system_version_changed)
        self.release = QComboBox()
        self.release.currentTextChanged.connect(self._release_changed)
        self.epkl_category = QComboBox()
        self.epkl_category.currentIndexChanged.connect(self._epkl_category_changed)
        self.component = QComboBox()
        self.component.currentIndexChanged.connect(self._component_changed)
        self.arch = QComboBox()
        self.repo = QListWidget()
        self.repo.setMaximumHeight(104)
        self.repo.setSelectionMode(QAbstractItemView.MultiSelection)
        form.addRow("产品源", self.source)
        form.addRow("系统版本", self.system_version)
        form.addRow("发行版本号", self.release)
        self.epkl_category_label = QLabel("EPKL 仓库分类")
        form.addRow(self.epkl_category_label, self.epkl_category)
        form.addRow("系统维护与补丁组件", self.component)
        form.addRow("芯片架构", self.arch)
        form.addRow("软件仓库", self.repo)
        top_layout.addWidget(workflow)

        search = QHBoxLayout()
        self.name_query = QLineEdit()
        self.name_query.setPlaceholderText("包名，例如 kernel*；也可从 TXT 导入")
        self.version_query = QLineEdit()
        self.version_query.setPlaceholderText("版本模糊匹配（可选）")
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
        top_layout.addLayout(search)
        splitter.addWidget(top)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["选择", "包名", "版本", "架构", "仓库", "简介", "下载地址"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        bottom_layout.addWidget(self.table)

        actions = QHBoxLayout()
        select_all = QPushButton("全选结果")
        select_all.clicked.connect(self._select_all)
        copy_repo = QPushButton("复制仓库地址")
        copy_repo.clicked.connect(self._copy_repo_urls)
        self.destination = QLineEdit(str(Path.home() / "Downloads"))
        choose = QPushButton("选择目录")
        choose.clicked.connect(self._choose_destination)
        start_download = QPushButton("开始下载")
        start_download.clicked.connect(self._start_download)
        show_downloads = QPushButton("下载内容")
        show_downloads.clicked.connect(self._show_download_manager)
        for widget in (select_all, copy_repo, QLabel("下载目录"), self.destination, choose, start_download, show_downloads):
            actions.addWidget(widget)
        bottom_layout.addLayout(actions)
        splitter.addWidget(bottom)
        splitter.setSizes([330, 490])
        root_layout.addWidget(splitter)

        cache_row = QHBoxLayout()
        self.cache_policy = QComboBox()
        for text, seconds in CACHE_OPTIONS:
            self.cache_policy.addItem(text, seconds)
        saved_cache = self.settings.value("cache_seconds", 86400, type=int)
        self.cache_policy.setCurrentIndex(max(0, self.cache_policy.findData(saved_cache)))
        self.cache_policy.currentIndexChanged.connect(self._save_cache_policy)
        clear_button = QPushButton("清除缓存")
        clear_button.clicked.connect(self._clear_cache)
        cache_row.addWidget(QLabel("仓库索引缓存"))
        cache_row.addWidget(self.cache_policy)
        cache_row.addWidget(clear_button)
        cache_row.addStretch()
        root_layout.addLayout(cache_row)
        self.status = QLabel("就绪")
        root_layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _initialize_options(self):
        self.source.setCurrentIndex(0)
        self._source_changed()
        self.release.setCurrentText("V10SP3")

    @staticmethod
    def _set_combo(combo, values, preferred=""):
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        index = combo.findText(preferred)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _source_key(self):
        return self.source.currentData() or "SYSTEM"

    def _source_changed(self):
        versions = SOURCE_SYSTEM_VERSIONS.get(self._source_key(), ["V10"])
        self._set_combo(self.system_version, versions, "V10")
        self._system_version_changed(self.system_version.currentText())

    def _system_version_changed(self, system_version):
        releases = RELEASES.get((self._source_key(), system_version), [])
        self._set_combo(self.release, releases, "V10SP3" if system_version == "V10" else "2503")
        if releases:
            self._release_changed(self.release.currentText())
        else:
            self.component.clear()
            self.arch.clear()
            self.repo.clear()
            self.status.setText("当前产品源暂未提供该系统版本")

    def _release_changed(self, release):
        source = self._source_key()
        system_version = self.system_version.currentText()
        key = (source, system_version, release)
        is_epkl = source == "EPKL"
        self.epkl_category_label.setVisible(is_epkl)
        self.epkl_category.setVisible(is_epkl)
        self.epkl_category.blockSignals(True)
        self.epkl_category.clear()
        if is_epkl:
            standard_repositories = EPKL_REPOSITORIES.get(
                (system_version, release), [("main", "main"), ("update", "update")]
            )
            for display, repository in standard_repositories:
                self.epkl_category.addItem(display, (repository, "standard"))
            if EPKL_MULTI_COMPONENTS.get((system_version, release)):
                self.epkl_category.addItem("multi_version", ("multi-version", "multi"))
        self.epkl_category.setCurrentIndex(0)
        self.epkl_category.blockSignals(False)
        self._set_combo(self.arch, ARCHES.get(key, ["aarch64", "x86_64"]), "aarch64")
        if is_epkl:
            self._epkl_category_changed()
            return
        self.component.blockSignals(True)
        self.component.clear()
        if source == "SYSTEM":
            components = SYSTEM_COMPONENTS.get((system_version, release), [("os", "os")])
            for display, path in components:
                self.component.addItem(display, (path, "system"))
        else:
            components = CS_COMPONENTS.get((system_version, release), [])
            for display, path, layout in components:
                self.component.addItem(display, (path, layout))
        self.component.setCurrentIndex(0)
        self.component.blockSignals(False)
        self._component_changed()

    def _epkl_category_changed(self):
        if self._source_key() != "EPKL":
            return
        category = self.epkl_category.currentData() or ("main", "standard")
        system_version = self.system_version.currentText()
        release = self.release.currentText()
        self.component.blockSignals(True)
        self.component.clear()
        if category[1] == "multi":
            for component in EPKL_MULTI_COMPONENTS.get((system_version, release), []):
                self.component.addItem(component, (component, "multi"))
        else:
            self.component.addItem("标准软件包", (category[0], "epkl-standard"))
        self.component.setCurrentIndex(0)
        self.component.blockSignals(False)
        self._component_changed()

    def _component_changed(self):
        source = self._source_key()
        system_version = self.system_version.currentText()
        release = self.release.currentText()
        component_data = self.component.currentData() or ("os", "system")
        self.repo.clear()
        if source == "SYSTEM" or (source == "CS" and component_data[1] == "standard"):
            repositories = [("base", "base"), ("update", "updates")]
        elif source == "CS" and component_data[1] == "direct":
            repositories = [("组件仓库", "direct")]
        elif component_data[1] == "multi":
            self._set_combo(self.arch, ["aarch64", "x86_64"], "aarch64")
            repositories = [("multi_version", "multi-version")]
        else:
            release_arches = ARCHES.get(
                (source, system_version, release), ["aarch64", "x86_64"]
            )
            self._set_combo(self.arch, release_arches, "aarch64")
            repository = component_data[0]
            repositories = [(repository, repository)]
        for display, key in repositories:
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, key)
            self.repo.addItem(item)
            item.setSelected(True)

    def _import_package_names(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入包名文件", str(Path.home()), "文本文件 (*.txt);;所有文件 (*)")
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
        self.import_status.setText(f"已导入 {len(self.imported_names)} 个：{Path(path).name}")
        self.import_status.setToolTip("\n".join(self.imported_names))

    def _repo_urls(self):
        source = self._source_key()
        system_version = self.system_version.currentText()
        release = self.release.currentText()
        arch = self.arch.currentText()
        component_path, layout = self.component.currentData() or ("os", "system")
        urls = []
        for item in self.repo.selectedItems():
            repository = item.data(Qt.UserRole)
            if source == "SYSTEM":
                url = (
                    f"{SYSTEM_BASE_URL}{system_version}/{release}/{component_path}"
                    f"/adv/lic/{repository}/{arch}/"
                )
            elif source == "CS" and layout == "standard":
                url = (
                    f"{CS_BASE_URL}{system_version}/{release}/{component_path}"
                    f"/adv/lic/{repository}/{arch}/"
                )
            elif source == "CS" and layout == "direct":
                url = f"{CS_BASE_URL}{system_version}/{release}/{component_path}/{arch}/"
            elif layout == "multi" and repository == "multi-version":
                url = (
                    f"{EPKL_BASE_URL}{system_version}/{release}/EPKL/multi_version/"
                    f"{component_path}/{arch}/"
                )
            elif layout == "epkl-standard" and repository == "main":
                url = f"{EPKL_BASE_URL}{system_version}/{release}/EPKL/main/{arch}/"
            elif layout == "epkl-standard" and repository == "update":
                url = f"{EPKL_BASE_URL}{system_version}/{release}/EPKL/update/main/{arch}/"
            else:
                continue
            urls.append((url, f"{source.lower()}-{repository}"))
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
        results = search_packages(packages, self.name_query.text(), self.version_query.text(), self.imported_names)
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
        self.table.setRowCount(0)
        for entry in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, entry)
            self.table.setItem(row, 0, check)
            values = (entry.name, f"{entry.version}-{entry.release}", entry.arch, entry.repo, entry.summary, entry.url)
            for column, value in enumerate(values, 1):
                self.table.setItem(row, column, QTableWidgetItem(value))

    def _select_all(self):
        state = Qt.Checked if any(self.table.item(row, 0).checkState() == Qt.Unchecked for row in range(self.table.rowCount())) else Qt.Unchecked
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
        for entry in entries:
            filename = Path(urlsplit(entry.url).path).name
            target = (destination_path, filename)
            if not filename or target in self.active_download_targets or target in targets:
                continue
            targets.add(target)
            accepted.append(entry)
        if not accepted:
            QMessageBox.information(self, "提示", "所选软件包已经在下载任务中。")
            return
        self.active_download_targets.update(targets)
        self.download_manager.add_downloads(accepted, destination_path, targets, max_workers=4)
        self.status.setText(f"已开始下载 {len(accepted)} 个软件包；可点击“下载内容”查看进度")

    def _show_download_manager(self):
        self.download_manager.show()
        self.download_manager.raise_()
        self.download_manager.activateWindow()

    def _download_finished(self, targets, destination, succeeded, failed):
        self.active_download_targets.difference_update(targets)
        self.status.setText(f"下载批次完成：成功 {succeeded}，失败 {failed}；目录：{destination}")

    def _save_cache_policy(self):
        self.settings.setValue("cache_seconds", self.cache_policy.currentData())

    def _clear_cache(self):
        try:
            clear_cache()
            self.status.setText("缓存已清除，下次搜索将重新获取仓库索引")
        except OSError as exc:
            QMessageBox.critical(self, "清除缓存失败", str(exc))

    def closeEvent(self, event):
        if self.download_manager.has_active_downloads():
            QMessageBox.information(self, "下载仍在进行", "仍有下载任务在后台运行，请等待完成后再退出。")
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "索引正在加载", "请等待当前仓库索引加载完成后再退出。")
            event.ignore()
            return
        self.download_manager.accept()
        event.accept()
