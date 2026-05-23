from PySide2.QtWidgets import QApplication, QMessageBox
from PySide2.QtUiTools import QUiLoader
from PySide2.QtGui import QPixmap, QFont
# import main

from paths import asset_path, ui_path

DEFAULT_UI_FONT = QFont('Microsoft YaHei UI', 10)
APP_STYLESHEET = """
    QWidget { background: #f5f8fc; color: #213547; font-family: "Microsoft YaHei UI"; font-size: 10pt; }
    QGroupBox { border: 1px solid #c7d5e8; border-radius: 10px; margin-top: 10px; background: #ffffff; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #1c5d99; font-weight: 600; }
    QLineEdit, QComboBox, QDateTimeEdit, QTableWidget {
        border: 1px solid #b8c8dc; border-radius: 6px; padding: 4px 6px; background: #fbfdff;
    }
    QPushButton { border: 1px solid #8fb2d6; border-radius: 8px; padding: 6px 10px; background: #eaf3ff; font-weight: 600; }
    QPushButton:hover { background: #d8eaff; }
"""
import sqls # sqls鏄嚜宸卞啓鐨勬ā鍧?

class LogInWindow():
    def __init__(self):
        self.ui = QUiLoader().load(ui_path('LogIn.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.label.setPixmap(QPixmap(asset_path('welcome.png')))
        self.ui.pushButton1.clicked.connect(self.loginfunction)
        self.ui.pushButton2.clicked.connect(self.registerfunction)
        self.sqloflogin = sqls.SqlF()

    def loginfunction(self):
        print('登录按钮已经按下')
        accountlist = []
        for i in self.sqloflogin.getAllaccount():
            accountlist.append(i[0])
        if self.ui.lineEdit1.text() == '':
            QMessageBox.about(self.ui, '错误', '您还没有输入账号')
        elif self.ui.lineEdit2.text() == '':
            QMessageBox.about(self.ui, '错误', '您还没有输入密码')
        elif self.ui.lineEdit1.text() in accountlist:
            if self.sqloflogin.verify_login(self.ui.lineEdit1.text(), self.ui.lineEdit2.text()):
                QMessageBox.about(self.ui, '登录成功', '欢迎使用！')

                # mainwindow = main.MWindow()
                # mainwindow.mui.show()

                self.ui.hide()
            else:
                QMessageBox.about(self.ui, '错误', '账号或密码错误！')
        else:
            print(self.sqloflogin.getAllaccount())
            QMessageBox.about(self.ui, '错误', '账号或密码错误！')

    def registerfunction(self):
        print('注册按钮已经按下')


if __name__ == '__main__':
    app = QApplication([])
    app.setFont(DEFAULT_UI_FONT)
    loginwindow = LogInWindow()
    loginwindow.ui.show()
    app.exec_()

