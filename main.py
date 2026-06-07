'''
逻辑无问题 数据库可以正常搜索 集成摄像头重启后以及训练模型后
所有摄像头的重启后 其名称地址都能表示正确 可以设置摄像头使用哪种显示类型
并且可以对指定的用户进行删除操作
可以全彩色显示
'''

from paths import asset_path
from app.services.app_service import AppService

# Build the recognition service before PySide2 installs its import hook; otherwise
# onnxruntime can fail to load its native DLLs on Windows.
APP_SERVICE = AppService()

from PySide2.QtGui import QFont
from PySide2.QtWidgets import QApplication

from app.ui.auth_windows import LogInWindow
from app.ui.monitor_windows import MWindow, configure as configure_monitor_windows

DEFAULT_UI_FONT = QFont('Microsoft YaHei UI', 10)
COMBO_ARROW_ICON = asset_path('combo_arrow_down.svg').replace("\\", "/")
APP_STYLESHEET = """
    QWidget { background: #f5f8fc; color: #213547; font-family: "Microsoft YaHei UI"; font-size: 10pt; }
    QGroupBox { border: 1px solid #c7d5e8; border-radius: 10px; margin-top: 10px; background: #ffffff; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #1c5d99; font-weight: 600; }
    QLineEdit, QComboBox, QDateTimeEdit, QTableWidget {
        border: 1px solid #b8c8dc; border-radius: 6px; padding: 4px 6px; background: #fbfdff;
    }
    QComboBox { padding-right: 28px; }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border-left: 1px solid #c7d5e8;
        background: #eef4ff;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }
    QComboBox::down-arrow {
        image: url("__COMBO_ARROW_ICON__");
        width: 12px;
        height: 8px;
        margin-right: 7px;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #b8c8dc;
        background: #ffffff;
        selection-background-color: #dfeeff;
        selection-color: #1f3f7a;
        outline: none;
    }
    QComboBox:on { border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; }
    QPushButton { border: 1px solid #8fb2d6; border-radius: 8px; padding: 6px 10px; background: #eaf3ff; font-weight: 600; }
    QPushButton:hover { background: #d8eaff; }
    QLabel#display1, QLabel#display2, QLabel#display3, QLabel#display4 { border: 1px solid #c9d7e8; border-radius: 8px; background: #f8fbff; }
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical {
        background: transparent;
        width: 8px;
        margin: 4px 2px 4px 0;
        border: none;
    }
    QScrollBar::handle:vertical {
        background: #b7c8dd;
        min-height: 36px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover { background: #93aac6; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
        background: transparent;
        border: none;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal {
        background: transparent;
        height: 8px;
        margin: 0 4px 2px 4px;
        border: none;
    }
    QScrollBar::handle:horizontal {
        background: #b7c8dd;
        min-width: 36px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal:hover { background: #93aac6; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
        background: transparent;
        border: none;
    }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
""".replace("__COMBO_ARROW_ICON__", COMBO_ARROW_ICON)

configure_monitor_windows(APP_SERVICE, DEFAULT_UI_FONT, APP_STYLESHEET)


def _shutdown_mainwindow():
    target = globals().get('mainwindow')
    if target is None:
        return
    try:
        target.close()
    except Exception as exc:
        print('关闭主窗口资源时出现异常：', exc)


app = QApplication([])
app.setFont(DEFAULT_UI_FONT)
start_login = LogInWindow(APP_SERVICE, DEFAULT_UI_FONT, APP_STYLESHEET)
start_login.ui.show()
app.exec_()

if start_login.StartSignal is True:
    mainwindow = MWindow()
    app.aboutToQuit.connect(_shutdown_mainwindow)
    mainwindow.mui.show()
    app.exec_()

# 临时入口用于调试
# app = QApplication([])
# mainwindow = MWindow()
# mainwindow.mui.show()
# app.exec_()
