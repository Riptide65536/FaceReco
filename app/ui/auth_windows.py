from __future__ import annotations

from PySide2.QtGui import QPixmap
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QMessageBox

from paths import asset_path, ui_path


class RegisterWindow:
    def __init__(self, app_service, default_ui_font, app_stylesheet, on_register_success=None):
        self.app_service = app_service
        self.default_ui_font = default_ui_font
        self.app_stylesheet = app_stylesheet
        self.on_register_success = on_register_success

        self.ui = QUiLoader().load(ui_path('Register.ui'))
        self.ui.setFont(self.default_ui_font)
        self.ui.setStyleSheet(self.app_stylesheet)
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)
        self.sql_repo = self.app_service.sql_repo

    def ok(self):
        accountlist = [i[0] for i in self.sql_repo.get_all_accounts()]
        newaccount = self.ui.lineEdit1.text().strip()
        newpassword = self.ui.lineEdit2.text()
        adminpassword = self.ui.lineEdit3.text()

        if newaccount in accountlist:
            QMessageBox.about(self.ui, '错误', '该账户已经存在！')
            return

        if newpassword == '':
            QMessageBox.about(self.ui, '错误', '密码不能为空！')
            return

        if not self.sql_repo.verify_login('admin', adminpassword):
            QMessageBox.about(self.ui, '错误', '超级管理员密码错误！')
            return

        if self.sql_repo.register(newaccount, newpassword):
            QMessageBox.about(self.ui, '欢迎', '新用户注册成功，请记好账号密码！')
            if callable(self.on_register_success):
                self.on_register_success(newaccount)
        else:
            QMessageBox.about(self.ui, '错误', '注册失败，请稍后重试！')

    def cancel(self):
        print('取消注册新用户')


class LogInWindow:
    def __init__(self, app_service, default_ui_font, app_stylesheet):
        self.app_service = app_service
        self.default_ui_font = default_ui_font
        self.app_stylesheet = app_stylesheet

        self.ui = QUiLoader().load(ui_path('LogIn.ui'))
        self.ui.setFont(self.default_ui_font)
        self.ui.setStyleSheet(self.app_stylesheet)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.label.setPixmap(QPixmap(asset_path('welcome.png')))
        self.ui.pushButton1.clicked.connect(self.loginfunction)
        self.ui.pushButton2.clicked.connect(self.registerfunction)
        self.StartSignal = False
        self.sql_repo = self.app_service.sql_repo
        self.accountlist = []

    def loginfunction(self):
        print('登录按钮已经按下')
        self.sql_repo.refresh_connection()
        self.accountlist = [i[0] for i in self.sql_repo.get_all_accounts()]

        account = self.ui.lineEdit1.text().strip()
        password = self.ui.lineEdit2.text()

        if account == '':
            QMessageBox.about(self.ui, '错误', '您还没有输入账号')
        elif password == '':
            QMessageBox.about(self.ui, '错误', '您还没有输入密码')
        elif account in self.accountlist:
            if self.sql_repo.verify_login(account, password):
                QMessageBox.about(self.ui, '登录成功', '欢迎使用！')
                self.StartSignal = True
                print(self.StartSignal)
                self.ui.close()
            else:
                QMessageBox.about(self.ui, '错误', '账号或密码错误！')
        else:
            print(self.sql_repo.get_all_accounts())
            QMessageBox.about(self.ui, '错误', '账号或密码错误！')

    def registerfunction(self):
        print('注册按钮已经按下')
        self.registerwin = RegisterWindow(
            self.app_service,
            self.default_ui_font,
            self.app_stylesheet,
            on_register_success=self._on_register_success,
        )
        self.registerwin.ui.show()

    def _on_register_success(self, newaccount):
        if newaccount and newaccount not in self.accountlist:
            self.accountlist.append(newaccount)
