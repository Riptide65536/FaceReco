from __future__ import annotations

import datetime

from PySide2.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)
from PySide2.QtUiTools import QUiLoader

from paths import ui_path


class LogWindow:
    def __init__(self, app_service, default_ui_font, app_stylesheet):
        self.app_service = app_service
        self.default_ui_font = default_ui_font
        self.app_stylesheet = app_stylesheet

        self.ui = QUiLoader().load(ui_path('Log.ui'))
        self.ui.setFont(self.default_ui_font)
        self.ui.setStyleSheet(self.app_stylesheet)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget.setColumnCount(6)
        self.ui.tableWidget.setHorizontalHeaderLabels(['姓名', '地点', '时间', '情绪', '考勤类型', '状态'])
        self._install_extra_filters()
        self.ui.pushButton.clicked.connect(self.inquiryDB)
        self.ui.pushButton2.clicked.connect(self.clearDB)

        nowdatetime = str(datetime.datetime.now()).split('.')[0]
        nowdatetime = datetime.datetime.strptime(nowdatetime, '%Y-%m-%d %H:%M:%S')
        print('datetimeEdit的时间为', nowdatetime, '类型为', type(nowdatetime))
        self.ui.dateTimeEdit1.setDateTime(nowdatetime)
        self.ui.dateTimeEdit2.setDateTime(nowdatetime)

        self.sql_repo = self.app_service.sql_repo

        allname = self.sql_repo.get_all_names()
        for i in allname:
            self.ui.comboBox2.addItem(i[0])
        allplace = self.sql_repo.get_all_places()
        for i in allplace:
            self.ui.comboBox.addItem(i[0])
        self._refresh_attendance_type_filters()
        self.comboStatus.addItems(['任何状态', '正常', '迟到', '早退', '缺勤', '已记录', '异常'])

        default_start = nowdatetime - datetime.timedelta(days=30)
        default_end = nowdatetime
        results = self.sql_repo.query_logs_with_emotion(
            name=None,
            location=None,
            start_time=default_start,
            end_time=default_end,
            attendance_type=None,
            status=None,
        )
        self._fill_table(results)

    def clearDB(self):
        self.sql_repo.reset_logs()
        self.ui.tableWidget.setRowCount(0)

    def _fill_table(self, results):
        self.ui.tableWidget.setRowCount(0)
        for row in results:
            row_count = self.ui.tableWidget.rowCount()
            self.ui.tableWidget.insertRow(row_count)
            values = list(row)
            if len(values) < 6:
                values.extend([''] * (6 - len(values)))
            for col in range(6):
                self.ui.tableWidget.setItem(
                    row_count,
                    col,
                    QTableWidgetItem(str(values[col] if values[col] is not None else '')),
                )

    def _install_extra_filters(self):
        grid = self.ui.layoutWidget.layout()
        self.labelAttendanceType = QLabel('考勤类型：', self.ui.layoutWidget)
        self.labelAttendanceType.setFont(self.default_ui_font)
        self.comboAttendanceType = QComboBox(self.ui.layoutWidget)
        self.comboAttendanceType.setFont(self.default_ui_font)
        self.labelStatus = QLabel('状态：', self.ui.layoutWidget)
        self.labelStatus.setFont(self.default_ui_font)
        self.comboStatus = QComboBox(self.ui.layoutWidget)
        self.comboStatus.setFont(self.default_ui_font)
        self.btnAbsence = QPushButton('当日缺勤', self.ui.layoutWidget)
        self.btnAbsence.setFont(self.default_ui_font)
        self.btnSummary = QPushButton('考勤汇总', self.ui.layoutWidget)
        self.btnSummary.setFont(self.default_ui_font)
        self.btnExport = QPushButton('导出报表', self.ui.layoutWidget)
        self.btnExport.setFont(self.default_ui_font)
        self.btnAbsence.clicked.connect(self.showAbsenceList)
        self.btnSummary.clicked.connect(self.showAttendanceSummary)
        self.btnExport.clicked.connect(self.exportAttendanceReport)
        grid.addWidget(self.labelAttendanceType, 1, 8)
        grid.addWidget(self.comboAttendanceType, 2, 8)
        grid.addWidget(self.labelStatus, 1, 9)
        grid.addWidget(self.comboStatus, 2, 9)
        grid.addWidget(self.btnAbsence, 1, 10)
        grid.addWidget(self.btnSummary, 2, 10)
        grid.addWidget(self.btnExport, 1, 11, 2, 1)

    def _refresh_attendance_type_filters(self):
        defaults = ['任何类型', '上班打卡', '下班打卡', '外出登记', '重复识别', '未识别']
        seen = set()
        self.comboAttendanceType.clear()
        for item in defaults:
            if item in seen:
                continue
            self.comboAttendanceType.addItem(item)
            seen.add(item)
        for row in self.sql_repo.get_all_attendance_types():
            if not row:
                continue
            value = str(row[0] if row[0] is not None else '').strip()
            if (not value) or (value in seen):
                continue
            self.comboAttendanceType.addItem(value)
            seen.add(value)

    def showAbsenceList(self):
        target_day = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd")
        day = datetime.datetime.strptime(target_day, '%Y-%m-%d').date()
        expected_names = sorted(list(set(self.app_service.state.user_dic.values())))
        if not expected_names:
            QMessageBox.about(self.ui, '缺勤名单', '当前没有已登记的人脸用户。')
            return
        absences = self.sql_repo.get_absence_list(expected_names, day=day)
        if not absences:
            text = f'{target_day} 无缺勤人员。'
        else:
            text = f'{target_day} 缺勤人员：\n' + '\n'.join(absences)
        QMessageBox.about(self.ui, '缺勤名单', text)

    def showAttendanceSummary(self):
        starttime = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        endtime = self.ui.dateTimeEdit2.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        start_dt = datetime.datetime.strptime(starttime, '%Y-%m-%d %H:%M:%S')
        end_dt = datetime.datetime.strptime(endtime, '%Y-%m-%d %H:%M:%S')
        summary = self.sql_repo.get_attendance_summary(start_dt, end_dt)
        if not summary:
            QMessageBox.about(self.ui, '考勤汇总', '当前时间范围内没有记录。')
            return
        lines = []
        for name, stat_map in summary.items():
            pairs = [f'{k}:{v}' for k, v in stat_map.items()]
            lines.append(f'{name} -> ' + ' / '.join(pairs))
        QMessageBox.about(self.ui, '考勤汇总', '\n'.join(lines))

    def inquiryDB(self):
        print('日志窗口的查询按钮已经按下')
        peoplename = self.ui.comboBox2.currentText()
        place = self.ui.comboBox.currentText()
        starttime = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        starttime = datetime.datetime.strptime(starttime, '%Y-%m-%d %H:%M:%S')
        endtime = self.ui.dateTimeEdit2.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        endtime = datetime.datetime.strptime(endtime, '%Y-%m-%d %H:%M:%S')

        results = self.sql_repo.query_logs_with_emotion(
            name=peoplename,
            location=place,
            start_time=starttime,
            end_time=endtime,
            attendance_type=self.comboAttendanceType.currentText(),
            status=self.comboStatus.currentText(),
        )
        self._fill_table(results)

    def exportAttendanceReport(self):
        peoplename = self.ui.comboBox2.currentText()
        place = self.ui.comboBox.currentText()
        starttime = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        starttime = datetime.datetime.strptime(starttime, '%Y-%m-%d %H:%M:%S')
        endtime = self.ui.dateTimeEdit2.dateTime().toString("yyyy-MM-dd hh:mm:ss")
        endtime = datetime.datetime.strptime(endtime, '%Y-%m-%d %H:%M:%S')

        default_name = f"attendance_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath, _ = QFileDialog.getSaveFileName(
            self.ui,
            '导出报表',
            default_name,
            'CSV 文件 (*.csv)',
        )
        if not filepath:
            return

        ok, count = self.sql_repo.export_attendance_report(
            output_path=filepath,
            name=peoplename,
            location=place,
            start_time=starttime,
            end_time=endtime,
            attendance_type=self.comboAttendanceType.currentText(),
            status=self.comboStatus.currentText(),
        )
        if ok:
            QMessageBox.about(self.ui, '导出成功', f'已导出 {count} 条记录：\n{filepath}')
        else:
            QMessageBox.about(self.ui, '导出失败', '写入报表文件失败，请检查路径权限。')
