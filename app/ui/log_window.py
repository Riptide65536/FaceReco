from __future__ import annotations

import datetime
from collections import Counter, defaultdict

from PySide2.QtCore import QSignalBlocker, Qt
from PySide2.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from PySide2.QtUiTools import QUiLoader

from paths import ui_path


class LogWindow:
    def __init__(self, app_service, default_ui_font, app_stylesheet):
        self.app_service = app_service
        self.default_ui_font = default_ui_font
        self.app_stylesheet = app_stylesheet
        self._suspend_auto_query = True

        self.ui = QUiLoader().load(ui_path("Log.ui"))
        self.ui.setFont(self.default_ui_font)
        self.ui.setStyleSheet(self.app_stylesheet)
        self.ui.resize(1380, 860)
        self.ui.setMinimumSize(1240, 820)
        self.ui.setWindowTitle("人员信息日志")

        self.sql_repo = self.app_service.sql_repo

        self._setup_root_layout()
        self._setup_table(self.ui.tableWidget)
        self._install_extra_filters()
        self._apply_runtime_texts()
        self._wire_signals()

        self._populate_base_filters()
        self._refresh_attendance_type_filters()
        self._populate_status_filters()
        self._set_default_time_range()

        self._suspend_auto_query = False
        self.refresh_table()

    def _setup_root_layout(self) -> None:
        table = self.ui.tableWidget
        controls = self.ui.layoutWidget
        table.setParent(None)
        controls.setParent(None)

        root_layout = QVBoxLayout(self.ui)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        controls.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls.setMinimumHeight(120)

        root_layout.addWidget(table, 1)
        root_layout.addWidget(controls, 0)

        grid = controls.layout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for col in range(12):
            grid.setColumnStretch(col, 0)
        for col in (2, 3, 6, 7, 8, 9):
            grid.setColumnStretch(col, 1)

    def _setup_table(self, table: QTableWidget) -> None:
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["姓名", "地点", "时间", "情绪", "考勤类型", "状态"])
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideRight)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)

        header = table.horizontalHeader()
        for idx, width in enumerate([120, 180, 220, 120, 220, 140]):
            header.setSectionResizeMode(idx, QHeaderView.Interactive)
            table.setColumnWidth(idx, width)
        header.setStretchLastSection(True)

    def _apply_runtime_texts(self) -> None:
        if hasattr(self.ui, "label"):
            self.ui.label.setText("请输入查询条件")
        if hasattr(self.ui, "label_2"):
            self.ui.label_2.setText("人员姓名：")
        if hasattr(self.ui, "label_3"):
            self.ui.label_3.setText("摄像地点：")
        if hasattr(self.ui, "label_4"):
            self.ui.label_4.setText("起始时间：")
        if hasattr(self.ui, "label_5"):
            self.ui.label_5.setText("结束时间：")
        if hasattr(self.ui, "pushButton"):
            self.ui.pushButton.setText("查询")
            self.ui.pushButton.setMinimumHeight(36)
        if hasattr(self.ui, "pushButton2"):
            self.ui.pushButton2.setText("清空数据库")
            self.ui.pushButton2.setMinimumHeight(36)

    def _populate_base_filters(self) -> None:
        blockers = [
            QSignalBlocker(self.ui.comboBox),
            QSignalBlocker(self.ui.comboBox2),
        ]
        _ = blockers

        self.ui.comboBox.clear()
        self.ui.comboBox.addItem("任何地点")
        for row in self.sql_repo.get_all_places():
            value = str(row[0] if row and row[0] is not None else "").strip()
            if value:
                self.ui.comboBox.addItem(value)

        self.ui.comboBox2.clear()
        self.ui.comboBox2.addItem("任何人员")
        for row in self.sql_repo.get_all_names():
            value = str(row[0] if row and row[0] is not None else "").strip()
            if value:
                self.ui.comboBox2.addItem(value)

    def _populate_status_filters(self) -> None:
        blocker = QSignalBlocker(self.comboStatus)
        _ = blocker
        self.comboStatus.clear()
        self.comboStatus.addItems(["任何状态", "正常", "迟到", "早退", "缺勤", "已记录", "异常"])

    def _set_default_time_range(self) -> None:
        now_dt = datetime.datetime.now().replace(microsecond=0)
        start_dt = now_dt - datetime.timedelta(days=30)

        blockers = [
            QSignalBlocker(self.ui.dateTimeEdit1),
            QSignalBlocker(self.ui.dateTimeEdit2),
        ]
        _ = blockers
        self.ui.dateTimeEdit1.setCalendarPopup(True)
        self.ui.dateTimeEdit2.setCalendarPopup(True)
        self.ui.dateTimeEdit1.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.ui.dateTimeEdit2.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.ui.dateTimeEdit1.setDateTime(start_dt)
        self.ui.dateTimeEdit2.setDateTime(now_dt)

    def _wire_signals(self) -> None:
        self.ui.pushButton.clicked.connect(self.inquiryDB)
        self.ui.pushButton2.clicked.connect(self.clearDB)

        self.ui.comboBox.currentTextChanged.connect(self._auto_query)
        self.ui.comboBox2.currentTextChanged.connect(self._auto_query)
        self.ui.dateTimeEdit1.dateTimeChanged.connect(self._auto_query)
        self.ui.dateTimeEdit2.dateTimeChanged.connect(self._auto_query)

    def _auto_query(self, *_args) -> None:
        if self._suspend_auto_query:
            return
        self.refresh_table()

    def _current_start_end(self) -> tuple[datetime.datetime, datetime.datetime]:
        start_text = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        end_text = self.ui.dateTimeEdit2.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        start_dt = datetime.datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.datetime.strptime(end_text, "%Y-%m-%d %H:%M:%S")
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
            blockers = [
                QSignalBlocker(self.ui.dateTimeEdit1),
                QSignalBlocker(self.ui.dateTimeEdit2),
            ]
            _ = blockers
            self.ui.dateTimeEdit1.setDateTime(start_dt)
            self.ui.dateTimeEdit2.setDateTime(end_dt)
        return start_dt, end_dt

    def _current_filters(self) -> dict[str, object]:
        start_dt, end_dt = self._current_start_end()
        return {
            "name": self.ui.comboBox2.currentText(),
            "location": self.ui.comboBox.currentText(),
            "start_time": start_dt,
            "end_time": end_dt,
            "attendance_type": self.comboAttendanceType.currentText(),
            "status": self.comboStatus.currentText(),
        }

    def _query_current_logs(self):
        return self.sql_repo.query_logs_with_emotion(**self._current_filters())

    def refresh_table(self) -> None:
        self._fill_table(self._query_current_logs())

    def clearDB(self) -> None:
        if not self.sql_repo.reset_logs():
            QMessageBox.about(self.ui, "清空失败", "日志数据库清空失败，请稍后重试。")
            return

        self._suspend_auto_query = True
        try:
            self._populate_base_filters()
            self._refresh_attendance_type_filters()
            self._populate_status_filters()
        finally:
            self._suspend_auto_query = False
        self.ui.tableWidget.setRowCount(0)

    def _fill_table(self, results) -> None:
        self.ui.tableWidget.setRowCount(0)
        for row in results:
            row_count = self.ui.tableWidget.rowCount()
            self.ui.tableWidget.insertRow(row_count)
            values = list(row)
            if len(values) < 6:
                values.extend([""] * (6 - len(values)))
            for col in range(6):
                item = QTableWidgetItem(str(values[col] if values[col] is not None else ""))
                item.setToolTip(item.text())
                self.ui.tableWidget.setItem(row_count, col, item)
        self.ui.tableWidget.resizeRowsToContents()

    def _install_extra_filters(self) -> None:
        grid = self.ui.layoutWidget.layout()
        self.labelAttendanceType = QLabel("考勤类型：", self.ui.layoutWidget)
        self.labelAttendanceType.setFont(self.default_ui_font)
        self.comboAttendanceType = QComboBox(self.ui.layoutWidget)
        self.comboAttendanceType.setFont(self.default_ui_font)

        self.labelStatus = QLabel("状态：", self.ui.layoutWidget)
        self.labelStatus.setFont(self.default_ui_font)
        self.comboStatus = QComboBox(self.ui.layoutWidget)
        self.comboStatus.setFont(self.default_ui_font)

        self.btnAbsence = QPushButton("当日缺勤", self.ui.layoutWidget)
        self.btnAbsence.setFont(self.default_ui_font)
        self.btnSummary = QPushButton("考勤汇总", self.ui.layoutWidget)
        self.btnSummary.setFont(self.default_ui_font)
        self.btnExport = QPushButton("导出报表", self.ui.layoutWidget)
        self.btnExport.setFont(self.default_ui_font)

        for widget in (
            self.ui.comboBox,
            self.ui.comboBox2,
            self.ui.dateTimeEdit1,
            self.ui.dateTimeEdit2,
            self.comboAttendanceType,
            self.comboStatus,
            self.ui.pushButton,
            self.ui.pushButton2,
            self.btnAbsence,
            self.btnSummary,
            self.btnExport,
        ):
            widget.setMinimumHeight(36)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.comboAttendanceType.setMinimumWidth(150)
        self.comboStatus.setMinimumWidth(120)
        self.btnAbsence.setMinimumWidth(120)
        self.btnSummary.setMinimumWidth(120)
        self.btnExport.setMinimumWidth(120)
        self.btnExport.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.btnAbsence.clicked.connect(self.showAbsenceList)
        self.btnSummary.clicked.connect(self.showAttendanceSummary)
        self.btnExport.clicked.connect(self.exportAttendanceReport)
        self.comboAttendanceType.currentTextChanged.connect(self._auto_query)
        self.comboStatus.currentTextChanged.connect(self._auto_query)

        grid.addWidget(self.labelAttendanceType, 1, 8)
        grid.addWidget(self.comboAttendanceType, 2, 8)
        grid.addWidget(self.labelStatus, 1, 9)
        grid.addWidget(self.comboStatus, 2, 9)
        grid.addWidget(self.btnAbsence, 1, 10)
        grid.addWidget(self.btnSummary, 2, 10)
        grid.addWidget(self.btnExport, 1, 11, 2, 1)

    def _refresh_attendance_type_filters(self) -> None:
        defaults = ["任何类型", "上班打卡", "下班打卡", "外出登记", "重复识别", "未识别"]
        seen = set()
        blocker = QSignalBlocker(self.comboAttendanceType)
        _ = blocker

        self.comboAttendanceType.clear()
        for item in defaults:
            if item in seen:
                continue
            self.comboAttendanceType.addItem(item)
            seen.add(item)
        for row in self.sql_repo.get_all_attendance_types():
            if not row:
                continue
            value = str(row[0] if row[0] is not None else "").strip()
            if (not value) or (value in seen):
                continue
            self.comboAttendanceType.addItem(value)
            seen.add(value)

    def showAbsenceList(self) -> None:
        target_day = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd")
        day = datetime.datetime.strptime(target_day, "%Y-%m-%d").date()
        expected_names = sorted(list(set(self.app_service.state.user_dic.values())))
        if not expected_names:
            QMessageBox.about(self.ui, "缺勤名单", "当前没有已登记的人脸用户。")
            return

        absences = self.sql_repo.get_absence_list(expected_names, day=day)
        if not absences:
            text = f"{target_day} 无缺勤人员。"
        else:
            text = f"{target_day} 缺勤人员：\n" + "\n".join(absences)
        QMessageBox.about(self.ui, "缺勤名单", text)

    def showAttendanceSummary(self) -> None:
        rows = self._query_current_logs()
        if not rows:
            QMessageBox.about(self.ui, "考勤汇总", "当前筛选范围内没有记录。")
            return

        total_rows = len(rows)
        per_person_types: dict[str, Counter] = defaultdict(Counter)
        per_person_status: dict[str, Counter] = defaultdict(Counter)

        for row in rows:
            name = str(row[0] if row[0] else "未知人员")
            attendance_type = str(row[4] if len(row) > 4 and row[4] else "未分类")
            status = str(row[5] if len(row) > 5 and row[5] else "未分类")
            per_person_types[name][attendance_type] += 1
            per_person_status[name][status] += 1

        lines = [
            f"当前筛选范围共 {total_rows} 条记录。",
            "统计口径：按当前筛选结果，汇总每个人的考勤类型与状态次数。",
            "",
        ]

        for name in sorted(per_person_types.keys()):
            type_text = "，".join(f"{key} {value} 次" for key, value in per_person_types[name].items())
            status_text = "，".join(f"{key} {value} 次" for key, value in per_person_status[name].items())
            lines.append(f"{name}")
            lines.append(f"考勤类型：{type_text}")
            lines.append(f"状态统计：{status_text}")
            lines.append("")

        QMessageBox.about(self.ui, "考勤汇总", "\n".join(lines).strip())

    def inquiryDB(self) -> None:
        print("日志窗口的查询按钮已经按下")
        self.refresh_table()

    def exportAttendanceReport(self) -> None:
        filters = self._current_filters()

        default_name = f"attendance_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath, _ = QFileDialog.getSaveFileName(
            self.ui,
            "导出报表",
            default_name,
            "CSV 文件 (*.csv)",
        )
        if not filepath:
            return

        ok, count = self.sql_repo.export_attendance_report(output_path=filepath, **filters)
        if ok:
            QMessageBox.about(self.ui, "导出成功", f"已导出 {count} 条记录：\n{filepath}")
        else:
            QMessageBox.about(self.ui, "导出失败", "写入报表文件失败，请检查路径权限。")
