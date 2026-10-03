import csv
import json
from pathlib import Path

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from .cve import normalize_cve_id, query_cve

MAX_BATCH_CVES = 200
MAX_IMPORT_BYTES = 1024 * 1024


class CveQueryWorker(QThread):
    loaded = pyqtSignal(list, list)

    def __init__(self, cve_ids):
        super().__init__()
        self.cve_ids = cve_ids

    def run(self):
        results = []
        errors = []
        for cve_id in self.cve_ids:
            try:
                results.append(query_cve(cve_id))
            except Exception as exc:
                errors.append(f"{cve_id}: {exc}")
        self.loaded.emit(results, errors)


class CvePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.results = []
        self.current_result = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        query_row = QHBoxLayout()
        query_row.addWidget(QLabel("CVE 编号"))
        self.query_input = QLineEdit("CVE-2026-16389")
        self.query_input.setPlaceholderText("例如 CVE-2026-16389")
        self.query_input.returnPressed.connect(self._query)
        self.import_button = QPushButton("导入 CVE 文件")
        self.import_button.clicked.connect(self._import_cve_file)
        self.query_button = QPushButton("查询")
        self.query_button.clicked.connect(self._query)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self._clear)
        query_row.addWidget(self.query_input, 1)
        query_row.addWidget(self.import_button)
        query_row.addWidget(self.query_button)
        query_row.addWidget(clear_button)
        layout.addLayout(query_row)

        self.summary_table = QTableWidget(0, 7)
        self.summary_table.setHorizontalHeaderLabels([
            "CVE 编号", "风险等级", "CVSS", "发布日期", "更新日期", "涉及架构", "安全公告"
        ])
        self.summary_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.itemSelectionChanged.connect(self._summary_selected)
        self.summary_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QLabel("漏洞概况"))
        layout.addWidget(self.summary_table, 1)

        self.details = QTabWidget()
        self.products_table = QTableWidget(0, 5)
        self.products_table.setHorizontalHeaderLabels(["导出", "受影响产品", "状态", "关联 CVE", "CVE 查询地址"])
        self.products_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.products_table.horizontalHeader().setStretchLastSection(True)
        self.details.addTab(self.products_table, "受影响产品")

        self.description = self._text_view()
        self.solution = self._text_view()
        self.update_information = self._text_view()
        self.details.addTab(self.description, "漏洞描述")
        self.details.addTab(self.solution, "修复方案")
        self.details.addTab(self.update_information, "更新方法")

        component_panel = QWidget()
        component_layout = QVBoxLayout(component_panel)
        component_actions = QHBoxLayout()
        self.select_all_components = QCheckBox("全选当前 CVE 组件")
        self.select_all_components.stateChanged.connect(self._toggle_all_components)
        export_components = QPushButton("导出已选组件版本 TXT")
        export_components.clicked.connect(self._export_component_versions)
        component_actions.addWidget(self.select_all_components)
        component_actions.addStretch()
        component_actions.addWidget(export_components)
        component_layout.addLayout(component_actions)
        self.components_table = QTableWidget(0, 8)
        self.components_table.setHorizontalHeaderLabels([
            "选择", "产品", "组件", "修复版本", "架构", "状态", "安全公告", "发布日期"
        ])
        self.components_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.components_table.horizontalHeader().setStretchLastSection(True)
        component_layout.addWidget(self.components_table)
        self.details.addTab(component_panel, "组件与修复版本")
        layout.addWidget(self.details, 2)

        export_group = QGroupBox("导出字段（仅导出上方已勾选产品关联的全部 CVE）")
        export_layout = QHBoxLayout(export_group)
        self.export_options = {}
        self.select_all_export_fields = QCheckBox("全选导出字段")
        self.select_all_export_fields.setChecked(True)
        self.select_all_export_fields.stateChanged.connect(self._toggle_all_export_fields)
        export_layout.addWidget(self.select_all_export_fields)
        for key, text in (
            ("summary", "漏洞概况"), ("description", "漏洞描述"),
            ("solution", "修复方案"), ("update_information", "更新方法"),
            ("source_url", "CVE 查询地址"), ("components", "组件与修复版本"),
        ):
            checkbox = QCheckBox(text)
            checkbox.setChecked(True)
            self.export_options[key] = checkbox
            export_layout.addWidget(checkbox)
        self.export_button = QPushButton("导出查询结果")
        self.export_button.clicked.connect(self._export)
        export_layout.addWidget(self.export_button)
        layout.addWidget(export_group)

        self.status = QLabel("支持单个查询或导入每行一个 CVE 编号的 TXT/TXTX 文件")
        layout.addWidget(self.status)

    @staticmethod
    def _text_view():
        widget = QTextEdit()
        widget.setReadOnly(True)
        return widget

    def _import_cve_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 CVE 编号文件", str(Path.home()),
            "CVE 文本文件 (*.txt *.txtx *.txxt);;所有文件 (*)",
        )
        if not path:
            return
        try:
            if Path(path).stat().st_size > MAX_IMPORT_BYTES:
                raise ValueError("导入文件不能超过 1 MiB")
            try:
                text = Path(path).read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                text = Path(path).read_text(encoding="gb18030")
            cve_ids = self._parse_cve_lines(text)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.query_input.setText(", ".join(cve_ids))
        self._start_query(cve_ids)

    @staticmethod
    def _parse_cve_lines(text):
        cve_ids = []
        seen = set()
        for line_number, line in enumerate(text.splitlines(), 1):
            value = line.strip()
            if not value:
                continue
            try:
                cve_id = normalize_cve_id(value)
            except ValueError as exc:
                raise ValueError(f"第 {line_number} 行：{exc}") from exc
            if cve_id not in seen:
                seen.add(cve_id)
                cve_ids.append(cve_id)
        if not cve_ids:
            raise ValueError("文件中没有有效的 CVE 编号")
        if len(cve_ids) > MAX_BATCH_CVES:
            raise ValueError(f"单次最多查询 {MAX_BATCH_CVES} 个 CVE")
        return cve_ids

    def _query(self):
        value = self.query_input.text().strip()
        try:
            cve_ids = []
            seen = set()
            for item in value.replace("，", ",").split(","):
                if item.strip():
                    cve_id = normalize_cve_id(item)
                    if cve_id not in seen:
                        seen.add(cve_id)
                        cve_ids.append(cve_id)
            if not cve_ids:
                raise ValueError("请输入有效的 CVE 编号")
        except ValueError as exc:
            QMessageBox.information(self, "输入错误", str(exc))
            return
        self._start_query(cve_ids)

    def _start_query(self, cve_ids):
        if len(cve_ids) > MAX_BATCH_CVES:
            QMessageBox.information(self, "提示", f"单次最多查询 {MAX_BATCH_CVES} 个 CVE。")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "提示", "CVE 正在查询，请稍候。")
            return
        self._reset_results()
        self.query_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.status.setText(f"正在依次查询 {len(cve_ids)} 个 CVE…")
        self.worker = CveQueryWorker(cve_ids)
        self.worker.loaded.connect(self._loaded)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _loaded(self, results, errors):
        self.results = results
        self.current_result = None
        self._show_summaries()
        self._show_aggregated_products()
        if results:
            self.summary_table.selectRow(0)
        if errors:
            self.status.setText(f"查询完成：成功 {len(results)}，失败 {len(errors)}；" + "；".join(errors))
        else:
            self.status.setText(f"查询完成：成功获取 {len(results)} 个 CVE")
        if not results and errors:
            QMessageBox.warning(self, "CVE 查询失败", "\n".join(errors))

    def _show_summaries(self):
        self.summary_table.setRowCount(0)
        for result in self.results:
            score = (result.get("scores") or [{}])[0]
            values = (
                result.get("cve_id", ""), result.get("severity", ""), score.get("score", ""),
                result.get("published", ""), result.get("updated", ""),
                "、".join(result.get("architectures") or []),
                "、".join(result.get("security_advisories") or []),
            )
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, result)
                self.summary_table.setItem(row, column, item)
        self.summary_table.resizeColumnsToContents()

    def _show_aggregated_products(self):
        products = {}
        for result in self.results:
            cve_id = result.get("cve_id", "")
            for product in result.get("products", []):
                name = product.get("product_name", "")
                if not name:
                    continue
                item = products.setdefault(name, {"states": set(), "cves": set(), "urls": set()})
                item["states"].add(product.get("state", ""))
                item["cves"].add(cve_id)
                item["urls"].add(result.get("source_url", ""))
        self.products_table.setRowCount(1)
        self.select_all_products = QCheckBox("全选")
        self.select_all_products.stateChanged.connect(self._toggle_all_products)
        self.products_table.setCellWidget(0, 0, self.select_all_products)
        self.product_filter = QComboBox()
        self.product_filter.addItem("全部受影响产品", "")
        self.product_filter.addItems(sorted(products))
        self.product_filter.currentIndexChanged.connect(self._filter_products)
        self.products_table.setCellWidget(0, 1, self.product_filter)
        self.products_table.setItem(0, 2, QTableWidgetItem("筛选条件"))
        self.cve_filter = QComboBox()
        self.cve_filter.addItem("全部关联 CVE", "")
        self.cve_filter.addItems(sorted({cve for item in products.values() for cve in item["cves"]}))
        self.cve_filter.currentIndexChanged.connect(self._filter_products)
        self.products_table.setCellWidget(0, 3, self.cve_filter)
        self.products_table.setItem(0, 4, QTableWidgetItem("查询地址随结果显示"))
        for name in sorted(products):
            row = self.products_table.rowCount()
            self.products_table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, name)
            self.products_table.setItem(row, 0, check)
            self.products_table.setItem(row, 1, QTableWidgetItem(name))
            self.products_table.setItem(row, 2, QTableWidgetItem("、".join(sorted(products[name]["states"]))))
            self.products_table.setItem(row, 3, QTableWidgetItem("、".join(sorted(products[name]["cves"]))))
            self.products_table.setItem(row, 4, QTableWidgetItem("\n".join(sorted(products[name]["urls"]))))
        self.products_table.resizeColumnsToContents()

    def _filter_products(self):
        product_name = self.product_filter.currentText() if self.product_filter.currentIndex() > 0 else ""
        cve_id = self.cve_filter.currentText() if self.cve_filter.currentIndex() > 0 else ""
        for row in range(1, self.products_table.rowCount()):
            product = self.products_table.item(row, 1).text()
            cves = self.products_table.item(row, 3).text().split("、")
            self.products_table.setRowHidden(
                row,
                bool(product_name and product_name != product)
                or bool(cve_id and cve_id not in cves),
            )

    def _toggle_all_products(self, state):
        check_state = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        for row in range(1, self.products_table.rowCount()):
            if not self.products_table.isRowHidden(row):
                self.products_table.item(row, 0).setCheckState(check_state)

    def _toggle_all_export_fields(self, state):
        checked = state == Qt.Checked
        for checkbox in self.export_options.values():
            checkbox.setChecked(checked)

    def _summary_selected(self):
        row = self.summary_table.currentRow()
        if row < 0 or not self.summary_table.item(row, 0):
            return
        result = self.summary_table.item(row, 0).data(Qt.UserRole)
        if not result:
            return
        self.current_result = result
        self.description.setPlainText(result.get("description", ""))
        self.solution.setPlainText(result.get("solution", ""))
        self.update_information.setPlainText(result.get("update_information", ""))
        self._fill_components(result)

    def _fill_components(self, result):
        self.select_all_components.blockSignals(True)
        self.select_all_components.setChecked(False)
        self.select_all_components.blockSignals(False)
        self.components_table.setRowCount(0)
        for component in result.get("components", []):
            row = self.components_table.rowCount()
            self.components_table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, {"cve_id": result.get("cve_id", ""), **component})
            self.components_table.setItem(row, 0, check)
            values = (
                component.get("product", ""), component.get("component", ""),
                component.get("version", ""), component.get("architecture", ""),
                component.get("status", ""), component.get("security_advisory", ""),
                component.get("release_date", ""),
            )
            for column, value in enumerate(values, 1):
                self.components_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.components_table.resizeColumnsToContents()

    @staticmethod
    def _fill_table(table, rows):
        table.setRowCount(0)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _toggle_all_components(self, state):
        check_state = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        for row in range(self.components_table.rowCount()):
            self.components_table.item(row, 0).setCheckState(check_state)

    def _selected_components(self):
        selected = []
        for row in range(self.components_table.rowCount()):
            item = self.components_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected

    def _export_component_versions(self):
        components = self._selected_components()
        if not components:
            QMessageBox.information(self, "提示", "请先勾选要导出的组件版本。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出组件版本", str(Path.home() / "cve-components.txt"),
            "文本文件 (*.txt)",
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path += ".txt"
        try:
            with open(path, "w", encoding="utf-8") as stream:
                for item in components:
                    stream.write(f"{item.get('component', '')}\t{item.get('version', '')}\n")
            self.status.setText(f"已导出 {len(components)} 个组件版本：{path}")
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _selected_products(self):
        products = []
        for row in range(1, self.products_table.rowCount()):
            item = self.products_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                products.append(item.data(Qt.UserRole))
        return products

    def _reset_results(self):
        self.results = []
        self.current_result = None
        self.summary_table.setRowCount(0)
        self.products_table.setRowCount(0)
        self.components_table.setRowCount(0)
        self.description.clear()
        self.solution.clear()
        self.update_information.clear()

    def _clear(self):
        self._reset_results()
        self.query_input.clear()
        self.status.setText("查询结果已清空")

    def _export_rows(self):
        selected_products = set(self._selected_products())
        rows = []
        for result in self.results:
            score = (result.get("scores") or [{}])[0]
            products = {}
            for item in result.get("products", []):
                name = item.get("product_name", "")
                if name in selected_products:
                    products.setdefault(name, set()).add(item.get("state", ""))
            components = [
                item for item in result.get("components", [])
                if item.get("product", "") in selected_products
            ]
            for product_name, product_states in products.items():
                related = (
                    [item for item in components if item.get("product") == product_name] or [{}]
                    if self.export_options["components"].isChecked() else [{}]
                )
                for component in related:
                    row = {
                        "受影响产品": product_name,
                        "产品状态": "、".join(sorted(product_states)),
                        "CVE编号": result.get("cve_id", ""),
                        "CVE查询结果": "查询成功",
                    }
                    if self.export_options["source_url"].isChecked():
                        row["CVE查询地址"] = result.get("source_url", "")
                    if self.export_options["summary"].isChecked():
                        row.update({
                            "风险等级": result.get("severity", ""),
                            "CVSS评分": score.get("score", ""),
                            "CVSS向量": score.get("vector", ""),
                            "发布日期": result.get("published", ""),
                            "更新日期": result.get("updated", ""),
                            "涉及架构": "、".join(result.get("architectures") or []),
                            "安全公告": "、".join(result.get("security_advisories") or []),
                        })
                    if self.export_options["description"].isChecked():
                        row["漏洞描述"] = result.get("description", "")
                    if self.export_options["solution"].isChecked():
                        row["修复方案"] = result.get("solution", "")
                    if self.export_options["update_information"].isChecked():
                        row["更新方法"] = result.get("update_information", "")
                    if self.export_options["components"].isChecked():
                        row.update({
                            "组件": component.get("component", ""),
                            "修复版本": component.get("version", ""),
                            "组件架构": component.get("architecture", ""),
                            "组件状态": component.get("status", ""),
                            "组件安全公告": component.get("security_advisory", ""),
                            "组件发布日期": component.get("release_date", ""),
                        })
                    rows.append(row)
        return rows

    def _export(self):
        if not self.results:
            QMessageBox.information(self, "提示", "请先查询 CVE 信息。")
            return
        if not self._selected_products():
            QMessageBox.information(self, "提示", "请至少勾选一个受影响产品。")
            return
        if not any(item.isChecked() for item in self.export_options.values()):
            QMessageBox.information(self, "提示", "请至少勾选一个导出字段。")
            return
        rows = self._export_rows()
        if not rows:
            QMessageBox.information(self, "提示", "所选产品没有可导出的 CVE 记录。")
            return
        default_name = "cve-query-results.csv"
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "导出 CVE 查询结果", str(Path.home() / default_name),
            "CSV 文件 (*.csv);;JSON 文件 (*.json);;文本文件 (*.txt)",
            "CSV 文件 (*.csv)",
        )
        if not path:
            return
        try:
            if selected_filter.startswith("JSON") or path.lower().endswith(".json"):
                if not path.lower().endswith(".json"):
                    path += ".json"
                with open(path, "w", encoding="utf-8") as stream:
                    json.dump(rows, stream, ensure_ascii=False, indent=2)
            elif selected_filter.startswith("文本") or path.lower().endswith(".txt"):
                if not path.lower().endswith(".txt"):
                    path += ".txt"
                with open(path, "w", encoding="utf-8") as stream:
                    for row in rows:
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                self._write_csv(path, rows)
            self.status.setText(f"已导出 {len(rows)} 条产品 CVE 记录：{path}")
        except OSError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    @staticmethod
    def _csv_safe(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    @classmethod
    def _write_csv(cls, path, rows):
        headers = []
        for row in rows:
            for key in row:
                if key not in headers:
                    headers.append(key)
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows([
                {key: cls._csv_safe(value) for key, value in row.items()}
                for row in rows
            ])

    def _finished(self):
        self.query_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.export_button.setEnabled(bool(self.results))
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def has_active_query(self):
        return bool(self.worker and self.worker.isRunning())
