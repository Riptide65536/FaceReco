from __future__ import annotations

from PySide2.QtWidgets import QMessageBox, QProgressDialog, QInputDialog, QApplication, QLabel, QComboBox, QPushButton
from PySide2.QtUiTools import QUiLoader
from PySide2.QtGui import QPixmap
from PySide2.QtCore import Qt, QObject, Signal
import cv2, threading, os, shutil, re, time
import ast
from paths import asset_path, ui_path
from app.ui_controller import MainUIController
from app.runtime.camera_stream import Camera
from app.ui.log_window import LogWindow

_CTX = {
    "app_service": None,
    "default_ui_font": None,
    "app_stylesheet": "",
}
_DEBUG_VERBOSE = os.getenv("FACE_RECO_VERBOSE", "0") == "1"

def configure(app_service, default_ui_font, app_stylesheet):
    _CTX["app_service"] = app_service
    _CTX["default_ui_font"] = default_ui_font
    _CTX["app_stylesheet"] = app_stylesheet


def _app_service():
    return _CTX["app_service"]


def _default_ui_font():
    return _CTX["default_ui_font"]


def _app_stylesheet():
    return _CTX["app_stylesheet"]

class _MessageBridge(QObject):
    show_message = Signal(str, str)

    def __init__(self, parent_widget):
        super().__init__()
        self._parent_widget = parent_widget
        self.show_message.connect(self._show_impl, Qt.QueuedConnection)

    def _show_impl(self, title, text):
        QMessageBox.about(self._parent_widget, title, text)


class _StreamEndBridge(QObject):
    stream_end = Signal(int, object)

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self.stream_end.connect(self._owner._handle_camera_stream_end, Qt.QueuedConnection)


class _EnrollBridge(QObject):
    capture_progress = Signal(int, int)
    capture_finished = Signal(bool, int, str)
    train_progress = Signal(int, str)
    train_finished = Signal(bool, int, int, float, str, str)

def _rebuild_face_training_data():
    app_service = _app_service()
    return app_service.pipeline.rebuild_training_data(app_service.data_repo)

class MWindow():

    def __init__(self):
        self._closing = False
        self.mui = QUiLoader().load(ui_path('MUi.ui'))
        self._msg_bridge = _MessageBridge(self.mui)
        self._stream_end_bridge = _StreamEndBridge(self)
        self.mui.setFont(_default_ui_font())
        self.mui.setStyleSheet(_app_stylesheet())
        self.mui.setFixedSize(self.mui.width(), self.mui.height())
        self.mui.closeEvent = self._on_close_event
        self.mui.pushButton1.clicked.connect(self.start)
        self.mui.pushButton2.clicked.connect(self.close)
        self.mui.addButton.clicked.connect(self.addcam)
        self.mui.delButton.clicked.connect(self.delcam)
        self.mui.luruButton.clicked.connect(self.luru)
        self.mui.logButton.clicked.connect(self.log)
        self.mui.pushButtonSaveConfig.clicked.connect(self.saveconfig)
        self.ui_controller = MainUIController(self)
        self._main_pending_label = None
        self._backend_mode_label = None
        self._pending_notice_shown = False
        self._operation_group_title_base = self.mui.groupBox.title() if hasattr(self.mui, 'groupBox') else '操作区'
        self._luru_button_base_text = self.mui.luruButton.text()
        self._luru_button_base_style = self.mui.luruButton.styleSheet()

        self.busy1, self.busy2, self.busy3, self.busy4 = False, False, False, False
        self.cameraList = [] # 记录已经获取的摄像头 避免同一个摄像头重复获取

        ######### ↓↓↓以下代码为人脸识别数据初始化过程 ########
        app_service = _app_service()
        app_service.initialize_state()
        print('totaluser:', app_service.state.total_user, type(app_service.state.total_user))
        print('idlists:', app_service.state.id_lists, type(app_service.state.id_lists))
        print('userdic:', app_service.state.user_dic, type(app_service.state.user_dic))
        print('rebuild face samples:', len(app_service.state.face_samples), 'labels:', len(app_service.state.id_lists))
        ######### ↑↑↑以上代码为人脸识别数据初始化过程 ########

        ######### ↓↓↓以下代码为显示初始化过程 ########
        if not self._initialize_display_configs():
            return

        ######### ↑↑↑以上代码为显示初始化过程 ########
        self._init_main_pending_hint()
        self._init_backend_mode_hint()
        self._ensure_runtime_mode_widget()
        self.refresh_model_pending_hint()
        self.refresh_backend_mode_hint()
        self._show_pending_startup_notice()

    def _refresh_runtime_mode_on_all_cameras(self):
        mode = _app_service().state.realtime_mode
        for slot in (1, 2, 3, 4):
            cam = getattr(self, f'cam{slot}', None)
            if cam is not None:
                try:
                    cam.set_runtime_mode(mode)
                except Exception:
                    pass

    def _refresh_fps_overlay_on_all_cameras(self):
        enabled = bool(getattr(_app_service().state, 'show_fps_overlay', False))
        for slot in (1, 2, 3, 4):
            cam = getattr(self, f'cam{slot}', None)
            if cam is not None:
                try:
                    cam.set_show_fps_overlay(enabled)
                except Exception:
                    pass

    def _runtime_mode_text(self, mode):
        return {
            'realtime': '实时优先',
            'balanced': '平衡模式',
            'accurate': '高精度',
        }.get(str(mode).strip().lower(), '平衡模式')

    def _ensure_runtime_mode_widget(self):
        if hasattr(self, '_runtime_mode_label') and self._runtime_mode_label is not None:
            return
        parent = self.mui.groupBox if hasattr(self.mui, 'groupBox') else self.mui
        layout = parent.layout() if hasattr(parent, 'layout') else None
        self._runtime_mode_label = QLabel(parent)
        self._runtime_mode_label.setObjectName('runtimeModeHintLabel')
        self._runtime_mode_label.setAlignment(Qt.AlignCenter)
        self._runtime_mode_label.setStyleSheet(
            'QLabel#runtimeModeHintLabel {'
            'background:#f4fbf6; color:#0d5b2f; border:1px solid #bee8cf; border-radius:8px; padding:5px 8px; font-weight:600; }'
        )
        self._runtime_mode_label.setText('识别策略：' + self._runtime_mode_text(_app_service().state.realtime_mode))
        self._runtime_mode_label.show()
        self._runtime_mode_combo = QComboBox(parent)
        self._runtime_mode_combo.addItems(['实时优先', '平衡模式', '高精度'])
        self._runtime_mode_combo.currentIndexChanged.connect(self._on_runtime_mode_changed)
        self._sync_runtime_mode_combo()
        self._runtime_mode_combo.show()
        if layout is not None:
            try:
                layout.insertWidget(0, self._runtime_mode_label)
                layout.insertWidget(1, self._runtime_mode_combo)
            except Exception:
                pass
        self._ensure_fps_toggle_widget(parent, layout)

    def _ensure_fps_toggle_widget(self, parent, layout):
        if hasattr(self, '_fps_toggle_button') and self._fps_toggle_button is not None:
            return
        self._fps_toggle_button = QPushButton(parent)
        self._fps_toggle_button.setObjectName('fpsToggleButton')
        self._fps_toggle_button.setCheckable(True)
        self._fps_toggle_button.setCursor(Qt.PointingHandCursor)
        self._fps_toggle_button.setStyleSheet(
            'QPushButton#fpsToggleButton {'
            'background:#f3f8ff; color:#1f3f7a; border:1px solid #c9dafc; border-radius:8px; padding:6px 10px; font-weight:600; }'
            'QPushButton#fpsToggleButton:checked {'
            'background:#e1f7e9; color:#116234; border:1px solid #9fd6af; }'
        )
        self._fps_toggle_button.clicked.connect(self._on_toggle_fps_overlay)
        self._sync_fps_toggle_button()
        self._fps_toggle_button.show()
        if layout is not None:
            try:
                layout.insertWidget(2, self._fps_toggle_button)
            except Exception:
                pass

    def _sync_fps_toggle_button(self):
        button = getattr(self, '_fps_toggle_button', None)
        if button is None:
            return
        enabled = bool(getattr(_app_service().state, 'show_fps_overlay', False))
        button.blockSignals(True)
        button.setChecked(enabled)
        button.setText('隐藏 FPS' if enabled else '显示 FPS')
        button.setToolTip('切换每个视频窗口左下角的 FPS 显示')
        button.blockSignals(False)

    def _sync_runtime_mode_combo(self):
        combo = getattr(self, '_runtime_mode_combo', None)
        if combo is None:
            return
        mapping = {'realtime': 0, 'balanced': 1, 'accurate': 2}
        idx = mapping.get(_app_service().state.realtime_mode, 1)
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _on_runtime_mode_changed(self, index):
        modes = {0: 'realtime', 1: 'balanced', 2: 'accurate'}
        mode = modes.get(int(index), 'balanced')
        _app_service().state.realtime_mode = mode
        label = getattr(self, '_runtime_mode_label', None)
        if label is not None:
            label.setText('识别策略：' + self._runtime_mode_text(mode))
        self._refresh_runtime_mode_on_all_cameras()
        self.refresh_backend_mode_hint()

    def _on_toggle_fps_overlay(self, checked):
        _app_service().state.show_fps_overlay = bool(checked)
        self._sync_fps_toggle_button()
        self._refresh_fps_overlay_on_all_cameras()

    def _init_main_pending_hint(self):
        if hasattr(self.mui, 'mainPendingHint'):
            self._main_pending_label = self.mui.mainPendingHint
            self._main_pending_label.hide()
            return
        parent = self.mui
        self._main_pending_label = QLabel(parent)
        self._main_pending_label.setObjectName('mainPendingHint')
        self._main_pending_label.setText('模型待更新：请进入“录入人脸及管理”，点击“更新模型”。')
        self._main_pending_label.setAlignment(Qt.AlignCenter)
        self._main_pending_label.setWordWrap(True)
        self._main_pending_label.setStyleSheet(
            'QLabel#mainPendingHint {'
            'background:#fff5f5; color:#a61b1b; border:1px solid #f2b8b8; border-radius:8px; padding:6px 10px; font-weight:600; }'
        )
        self._main_pending_label.setGeometry(420, 850, 1440, 26)
        self._main_pending_label.hide()

    def _init_backend_mode_hint(self):
        if hasattr(self.mui, 'mainBackendHint'):
            self._backend_mode_label = self.mui.mainBackendHint
            print('backend hint widget loaded from ui:', self._backend_mode_label is not None)
            self._backend_mode_label.show()
            return
        parent = self.mui.groupBox if hasattr(self.mui, 'groupBox') else self.mui
        self._backend_mode_label = QLabel(parent)
        self._backend_mode_label.setObjectName('mainBackendHint')
        self._backend_mode_label.setAlignment(Qt.AlignCenter)
        self._backend_mode_label.setStyleSheet(
            'QLabel#mainBackendHint {'
            'background:#eef4ff; color:#1f3f7a; border:1px solid #c9dafc; border-radius:8px; padding:6px 10px; font-weight:600; }'
        )
        if parent is self.mui:
            self._backend_mode_label.setGeometry(420, 820, 480, 26)
        else:
            self._backend_mode_label.setGeometry(18, 24, max(260, parent.width() - 36), 24)
        self._backend_mode_label.show()
        self._backend_mode_label.raise_()

    def refresh_backend_mode_hint(self):
        if self._backend_mode_label is None:
            return
        if self._backend_mode_label.parent() is self.mui.groupBox and self._backend_mode_label.objectName() != 'mainBackendHint':
            self._backend_mode_label.setGeometry(18, 24, max(260, self.mui.groupBox.width() - 36), 24)
        mode = _app_service().pipeline.current_backend_mode()
        provider_text = _app_service().pipeline.current_provider_text()
        mode_map = {
            'deep': '深度模型',
            'lbph': 'LBPH（降级）',
            'lite': 'Lite（应急降级）',
            'unavailable': '不可用',
            'unknown': '未知',
        }
        text = mode_map.get(mode, str(mode))
        strategy_text = self._runtime_mode_text(_app_service().state.realtime_mode)
        if mode == 'deep':
            self._backend_mode_label.setText(f'当前识别后端：{text} [{provider_text}] | 策略：{strategy_text}')
        else:
            self._backend_mode_label.setText(f'当前识别后端：{text} | 策略：{strategy_text}')
        self._backend_mode_label.show()
        self._backend_mode_label.raise_()

    def refresh_model_pending_hint(self):
        if self._main_pending_label is None:
            return
        is_pending = _app_service().is_model_pending()
        print('model pending status:', is_pending)
        if is_pending:
            self._main_pending_label.show()
            self._main_pending_label.raise_()
            if hasattr(self.mui, 'groupBox'):
                self.mui.groupBox.setTitle(f'{self._operation_group_title_base}（模型待更新）')
            self.mui.luruButton.setText('⚠ 录入人脸及管理')
            self.mui.luruButton.setToolTip('模型待更新：请进入录入窗口后点击“更新模型”。')
            self.mui.luruButton.setStyleSheet(
                self._luru_button_base_style
                + 'QPushButton{border:1px solid #e2a4a4; background:#fff5f5; color:#8a1f1f; font-weight:700;}'
                + 'QPushButton:hover{background:#ffeaea;}'
            )
        else:
            self._main_pending_label.hide()
            if hasattr(self.mui, 'groupBox'):
                self.mui.groupBox.setTitle(self._operation_group_title_base)
            self.mui.luruButton.setText(self._luru_button_base_text)
            self.mui.luruButton.setToolTip('')
            self.mui.luruButton.setStyleSheet(self._luru_button_base_style)

    def _show_pending_startup_notice(self):
        if self._pending_notice_shown:
            return
        if _app_service().is_model_pending():
            self._pending_notice_shown = True
            QMessageBox.about(
                self.mui,
                '模型待更新',
                '当前模型不是最新状态。\n请进入“录入人脸及管理”，点击“更新模型”。',
            )

    def _initialize_display_configs(self):
        for slot in (1, 2, 3, 4):
            config_lines = _app_service().config_repo.load_camera_slot(slot)
            if not self._apply_slot_config(slot, config_lines):
                return False
        return True

    def _apply_slot_config(self, slot, config_lines):
        if not config_lines:
            return True

        nameandplace = config_lines[0] if len(config_lines) > 0 else ''
        try:
            displaymode = int(config_lines[1]) if len(config_lines) > 1 else 0
        except ValueError:
            displaymode = 0
        url = config_lines[2] if len(config_lines) > 2 else ''

        if isinstance(url, str) and url.isdigit():
            url = int(url)

        line_name = getattr(self.mui, f'lineEdit{slot}1')
        combo_display = getattr(self.mui, f'comboBox{slot}')
        line_url = getattr(self.mui, f'lineEdit{slot}2')
        line_name.setText(nameandplace)
        combo_display.setCurrentIndex(displaymode)
        line_url.setText(str(url))

        if url == '':
            return True
        return self.start_slot(slot, url, nameandplace, displaymode)

    def _on_close_event(self, event):
        self._closing = True
        try:
            self.close()
        finally:
            event.accept()

    def saveconfig(self):  # 保存显示配置文件的函数
        for slot in (1, 2, 3, 4):
            _app_service().config_repo.save_camera_slot(
                slot,
                getattr(self.mui, f'lineEdit{slot}1').text(),
                getattr(self.mui, f'comboBox{slot}').currentIndex(),
                getattr(self.mui, f'lineEdit{slot}2').text(),
            )

        QMessageBox.about(self.mui, '保存成功', '下次启动时会采用此次配置')

    def delcam(self):
        if _DEBUG_VERBOSE:
            print('function of del camera'
                  '显示删除摄像头的界面 显示需要删除的摄像头的链接')
        self.addwin = DelWindow(self)
        self.addwin.ui.show()

    def addcam(self):
        if _DEBUG_VERBOSE:
            print('function of add camera'
                  '显示添加摄像头的界面 显示需要添加的摄像头的链接')
        self.addwin = AddWindow(self)
        self.addwin.ui.show()

    def luru(self):
        if _DEBUG_VERBOSE:
            print('function of luru face'
                  '显示人脸录入界面 这里需要系统锁 人脸录入的优先级比display的优先级高')
        self.luruwin = LuruWindow(self)
        self.luruwin.ui.setWindowFlags(Qt.CustomizeWindowHint)
        self.luruwin.ui.show()
        self.luruwin.ui.destroyed.connect(lambda *_: self.refresh_model_pending_hint())
        self.luruwin.ui.destroyed.connect(lambda *_: self.refresh_backend_mode_hint())

    def log(self):
        print('function of inquiry log')
        self.logwin = LogWindow(_app_service(), _default_ui_font(), _app_stylesheet())
        self.logwin.ui.show()

    def start(self):
        for slot in (1, 2, 3, 4):
            self.start_slot(slot, '1 Danny MacAskill’s Wee Day Out.flv', '', 0, allow_duplicate_source=True)

    def start1(self, url, cameraNamePlace = '', displaymode = 0):
        self.start_slot(1, url, cameraNamePlace, displaymode)

    def start2(self, url, cameraNamePlace = '', displaymode = 0):
        self.start_slot(2, url, cameraNamePlace, displaymode)

    def start3(self, url, cameraNamePlace = '', displaymode = 0):
        self.start_slot(3, url, cameraNamePlace, displaymode)

    def start4(self, url, cameraNamePlace = '', displaymode = 0):
        self.start_slot(4, url, cameraNamePlace, displaymode)

    def _get_system_lock(self):
        return _app_service().state.system_lock_slot

    def _set_system_lock(self, slot):
        _app_service().state.system_lock_slot = int(slot)

    def start_slot(self, slot, url, cameraNamePlace='', displaymode=0, allow_duplicate_source=False):
        runtime = self.ui_controller.get_slot_runtime(int(slot))
        if getattr(self, runtime.busy_attr, False):
            QMessageBox.about(self.mui, '错误', f'窗口{slot}忙碌，不可以添加视频流')
            return False
        if (not allow_duplicate_source) and (url in self.cameraList):
            QMessageBox.about(self.mui, '错误', f'摄像头{url}忙碌，不可以重复使用')
            return False
        if url == 0:
            current_lock = self._get_system_lock()
            if current_lock not in (0, int(slot)):
                QMessageBox.about(self.mui, '错误', '集成摄像头被占用！')
                return False
            self._set_system_lock(int(slot))
        label = getattr(self.mui, runtime.label_name)
        camera = Camera(url, label, _app_service(), on_stream_end=lambda cam: self._on_camera_stream_end(int(slot), cam))
        camera.displayMode = int(displaymode)
        camera.set_show_fps_overlay(bool(getattr(_app_service().state, 'show_fps_overlay', False)))
        if cameraNamePlace != '':
            camera.nameAndLocation = cameraNamePlace
        setattr(self, runtime.camera_attr, camera)
        if int(displaymode) == 1:
            target = camera.displaySimpleBrand
        elif int(displaymode) == 2:
            target = camera.displayJustdisplayBrand
        else:
            target = camera.display
        threading.Thread(target=target, daemon=True).start()
        if camera.cap.isOpened():
            setattr(self, runtime.busy_attr, True)
            self.cameraList.append(url)
            return True
        return False

    def close(self):
        self._closing = True
        for slot in (1, 2, 3, 4):
            self.close_slot(slot, show_message_when_idle=False)

    def close1(self):
        self.close_slot(1)

    def close2(self):
        self.close_slot(2)

    def close3(self):
        self.close_slot(3)

    def close4(self):
        self.close_slot(4)

    def close_slot(self, slot, show_message_when_idle=True):
        runtime = self.ui_controller.get_slot_runtime(int(slot))
        if getattr(self, runtime.busy_attr, False):
            cam = getattr(self, runtime.camera_attr, None)
            if cam is not None:
                if cam.url in self.cameraList:
                    self.cameraList.remove(cam.url)
                cam.close()
            label = getattr(self.mui, runtime.label_name, None)
            if label is not None:
                label.setPixmap(QPixmap(asset_path('nosignal.png')))
            setattr(self, runtime.busy_attr, False)
            print(f'{slot}close')
            return True
        if show_message_when_idle:
            QMessageBox.about(self.mui, '错误', f'窗口{slot}并没有打开')
        return False

    def capture_busy_slots(self):
        snapshots = []
        for slot in (1, 2, 3, 4):
            if getattr(self, f'busy{slot}', False):
                cam = getattr(self, f'cam{slot}', None)
                if cam is not None:
                    snapshots.append((slot, cam.url, cam.nameAndLocation, cam.displayMode))
        return snapshots

    def close_slots_from_snapshots(self, snapshots):
        for slot, _, _, _ in snapshots:
            getattr(self, f'close{slot}')()

    def restore_slots_from_snapshots(self, snapshots):
        for slot, url, name_place, display_mode in snapshots:
            self.start_slot(slot, url, name_place, display_mode, allow_duplicate_source=True)

    def _on_camera_stream_end(self, slot, cam_obj):
        # Camera stream callback can come from worker threads.
        # Always marshal to UI thread before touching any widgets.
        self._stream_end_bridge.stream_end.emit(int(slot), cam_obj)

    def _handle_camera_stream_end(self, slot, cam_obj):
        """
        回调：摄像头流异常/结束时自动回收主窗口状态，避免“假忙碌”。
        注意：该函数运行在UI线程。
        """
        if self._closing:
            return
        if self.mui is None:
            return
        runtime = self.ui_controller.get_slot_runtime(int(slot))
        current_cam = getattr(self, runtime.camera_attr, None)
        if current_cam is not cam_obj:
            return
        if cam_obj.url in self.cameraList:
            self.cameraList.remove(cam_obj.url)
        setattr(self, runtime.busy_attr, False)
        try:
            label = getattr(self.mui, runtime.label_name, None)
            if label is not None:
                label.setPixmap(QPixmap(asset_path('nosignal.png')))
        except RuntimeError:
            # Main window may already be in teardown.
            return
        if cam_obj.url == 0 and self._get_system_lock() == int(slot):
            self._set_system_lock(0)
        self._msg_bridge.show_message.emit(
            '摄像头已断开',
            f'窗口{slot}的视频流读取失败，系统已自动释放该摄像头。',
        )

class AddWindow():

    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = QUiLoader().load(ui_path('Add.ui'))
        self.ui.setFont(_default_ui_font())
        self.ui.setStyleSheet(_app_stylesheet())
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)

    def _start_slot(self, slot, url, displaymode_index, name_place_text):
        busy = getattr(self.main_window, f'busy{slot}')
        if busy:
            QMessageBox.about(self.ui, '错误', f'窗口{slot}忙碌，不可以添加视频流')
            return
        if url in self.main_window.cameraList:
            QMessageBox.about(self.ui, '错误', f'摄像头{url}忙碌，不可以重复使用')
            return
        started = self.main_window.start_slot(slot, url, displaymode=displaymode_index)
        if not started:
            return
        cam = getattr(self.main_window, f'cam{slot}', None)
        if cam is not None:
            cam.displayMode = displaymode_index
            cam.nameAndLocation = name_place_text or 'Test Camera, Test Location'

    def ok(self):
        if _DEBUG_VERBOSE:
            print('push the ok button')
            print(self.ui.comboBox.currentText())

        if self.ui.comboBox.currentText() == '':
            QMessageBox.about(self.ui, '错误', '请在组合选择框中选择内容')

        else:
            slot_text = self.ui.comboBox.currentText()
            slot_map = {'win1': 1, 'win2': 2, 'win3': 3, 'win4': 4}
            if slot_text not in slot_map:
                QMessageBox.about(self.ui, '错误', '无效的窗口选择')
                return
            if self.ui.lineEdit.text() == '':
                QMessageBox.about(self.ui, '错误', '请输入在文本框中输入内容')
                return

            cam_url = self.ui.lineEdit.text()
            if _DEBUG_VERBOSE:
                print(type(cam_url))
            if cam_url.isdigit():
                cam_url = int(cam_url)
            else:
                if _DEBUG_VERBOSE:
                    print(type(cam_url))
            self._start_slot(
                slot_map[slot_text],
                cam_url,
                self.ui.comboBox2.currentIndex(),
                self.ui.lineEdit2.text(),
            )

    def cancel(self):
        if _DEBUG_VERBOSE:
            print('push the cancel button')


class DelWindow():
    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = QUiLoader().load(ui_path('Del.ui'))
        self.ui.setFont(_default_ui_font())
        self.ui.setStyleSheet(_app_stylesheet())
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)

    def ok(self):
        if _DEBUG_VERBOSE:
            print('push the ok button')
            print(self.ui.comboBox.currentText())

        if self.ui.comboBox.currentText() == '':
            QMessageBox.about(self.ui, '错误', '请在组合选择框中选择试图关闭的窗口')

        else:
            slot_map = {'win1': 1, 'win2': 2, 'win3': 3, 'win4': 4}
            slot = slot_map.get(self.ui.comboBox.currentText())
            if slot is None:
                QMessageBox.about(self.ui, '错误', '无效的窗口选择')
                return
            getattr(self.main_window, f'close{slot}')()

    def cancel(self):
        if _DEBUG_VERBOSE:
            print('push the cancel button')

class DelFaceWindow():

    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = QUiLoader().load(ui_path('DelFace.ui'))
        self.ui.setFont(_default_ui_font())
        self.ui.setStyleSheet(_app_stylesheet())
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)
        for _, username in sorted(_app_service().state.user_dic.items(), key=lambda item: int(item[0])):
            self.ui.comboBox.addItem(username)

    def ok(self):
        print('将要对选定的人脸进行删除')
        faceTodel = self.ui.comboBox.currentText()
        print(faceTodel)
        if faceTodel == '':
            QMessageBox.about(self.ui, '错误', '未选择需要删除的人脸')
            return
        if not _app_service().delete_user_only(faceTodel):
            QMessageBox.about(self.ui, '错误', '删除失败，请重试。')
            return
        QMessageBox.about(self.ui, '完成', '已删除目标人脸样本，模型待更新。')
        try:
            if hasattr(self.main_window, 'luruwin') and self.main_window.luruwin is not None:
                self.main_window.luruwin._mark_model_pending_ui()
        except Exception:
            pass

    def cancel(self):
        print('push the cancel button')


class LuruWindow():

    def __init__(self, main_window):
        self.main_window = main_window
        self.ui = QUiLoader().load(ui_path('Luru.ui'))
        self.ui.setFont(_default_ui_font())
        self.ui.setStyleSheet(_app_stylesheet())
        self.ui.setFixedSize(self.ui.width(), self.ui.height())

        self.ui.lurudisplay2.setPixmap(QPixmap(asset_path('avatar.png')))
        self.ui.pushButton3.setText('更新模型')

        self.ui.pushButton2.clicked.connect(self.closeQuit)
        self.ui.pushButton.clicked.connect(self.snap)
        self.ui.pushButton3.clicked.connect(self.trainModel)
        self.ui.pushButton4.clicked.connect(self.delAll)
        # 点击按钮四会执行模型重置操作，跳出弹窗
        self.ui.pushButton5.clicked.connect(self.delFace)

        self.integratedNamePlace = '' # 记录集成摄像头的名称和地点 以便于后续重启的设置
        self.integratedDisplaymode = 0 # 记录集成摄像头的显示模式
        self._restore_done = False
        self.sampleNum = 0
        self.maxSampleNum = 20
        self._capture_running = False
        self._is_training = False
        self._model_pending = _app_service().is_model_pending()
        self.current_username = ''
        self._pending_status_base_text = '请不要遮挡人脸(•̀ ω •́ )\n录入完成会自行退出^_^ \n耐心等待'
        self._capture_write_index = 1
        self._train_progress_dialog = None
        self._train_snapshots = []
        self._enroll_bridge = _EnrollBridge()
        self._enroll_bridge.capture_progress.connect(self._on_capture_progress, Qt.QueuedConnection)
        self._enroll_bridge.capture_finished.connect(self._on_capture_finished, Qt.QueuedConnection)
        self._enroll_bridge.train_progress.connect(self._on_train_progress, Qt.QueuedConnection)
        self._enroll_bridge.train_finished.connect(self._on_train_finished, Qt.QueuedConnection)
        self._pending_label = QLabel(self.ui)
        self._pending_label.setObjectName('luruPendingHint')
        self._pending_label.setStyleSheet(
            'QLabel#luruPendingHint {'
            'background:#fff5f5; color:#a61b1b; border:1px solid #f2b8b8; border-radius:8px; padding:4px 10px; font-weight:600; }'
        )
        self._pending_label.setAlignment(Qt.AlignCenter)
        self._pending_label.setWordWrap(True)
        self._pending_label.setText('⚠ 模型待更新')
        self._pending_label.setGeometry(360, 396, 290, 38)
        self._pending_label.hide()

        current_lock = _app_service().state.system_lock_slot
        if current_lock != 0:
            QMessageBox.about(self.ui, '警告', '集成相机被占用，即将解锁，监控将暂时中断，人脸录入结束后可自行恢复')
            if current_lock == 1:
                self.integratedNamePlace = self.main_window.cam1.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam1.displayMode
                self.main_window.close1()
                _app_service().state.system_lock_slot = 1
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif current_lock == 2:
                self.integratedNamePlace = self.main_window.cam2.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam2.displayMode
                self.main_window.close2()
                _app_service().state.system_lock_slot = 2
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif current_lock == 3:
                self.integratedNamePlace = self.main_window.cam3.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam3.displayMode
                self.main_window.close3()
                _app_service().state.system_lock_slot = 3
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif current_lock == 4:
                self.integratedNamePlace = self.main_window.cam4.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam4.displayMode
                self.main_window.close4()
                _app_service().state.system_lock_slot = 4
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()

        if _app_service().state.system_lock_slot == 0:
            _app_service().state.system_lock_slot = 55
            self.lurucam = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
            self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
            # self.luruThread.setDaemon(True)
            self.luruThread.start()
        self._refresh_capture_status_label()

    def delFace(self):
        self.delfacewin = DelFaceWindow(self.main_window)
        self.delfacewin.ui.show()

    def delAll(self):
        self.resetwin = ResetWindow()
        self.resetwin.ui.show()

    def _refresh_capture_status_label(self):
        ready = _app_service().pipeline.ensure_face_service_ready()
        reason = _app_service().pipeline.face_service_error_text()
        backend_mode = _app_service().pipeline.current_backend_mode()
        if ready:
            self.ui.pushButton3.setEnabled(True)
            if backend_mode == 'lbph':
                self.ui.pushButton3.setToolTip('当前为 LBPH 降级模式：可正常更新模型，识别精度低于深度模型。')
            elif backend_mode == 'lite':
                self.ui.pushButton3.setToolTip('当前为 Lite 应急模式：可正常更新模型，识别精度低于深度/LBPH。')
            else:
                self.ui.pushButton3.setToolTip('')
        else:
            self.ui.pushButton3.setEnabled(True)
            self.ui.pushButton3.setToolTip(
                '当前环境不支持更新模型，请先安装 insightface + onnxruntime。'
                + (f'\n原因：{reason}' if reason else '')
            )
        if self._model_pending:
            self.ui.pushButton3.setText('更新模型')
            self.ui.setWindowTitle('录入人脸（模型待更新）')
            self._pending_label.show()
        else:
            self.ui.pushButton3.setText('更新模型')
            self.ui.setWindowTitle('录入人脸')
            self._pending_label.hide()

    def _mark_model_pending_ui(self):
        self._model_pending = True
        _app_service().mark_model_pending()
        self._refresh_capture_status_label()
        self.main_window.refresh_model_pending_hint()

    def _clear_model_pending_ui(self):
        self._model_pending = False
        self._refresh_capture_status_label()
        self.main_window.refresh_model_pending_hint()

    @staticmethod
    def _sanitize_username(raw_name):
        name = str(raw_name).strip()
        if not name:
            return '', '你还没有输入姓名'
        if re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9_]+', name) is None:
            return '', '姓名仅允许中文、英文、数字、下划线'
        return name, ''

    def _resolve_enroll_name(self, name):
        for _, saved_name in _app_service().state.user_dic.items():
            if saved_name == name:
                msg = QMessageBox(self.ui)
                msg.setWindowTitle('同名用户')
                msg.setText(f'已存在用户“{name}”。')
                merge_btn = msg.addButton('合并到已有用户', QMessageBox.YesRole)
                new_btn = msg.addButton('新建ID（改名）', QMessageBox.NoRole)
                cancel_btn = msg.addButton('取消', QMessageBox.RejectRole)
                msg.exec_()
                clicked = msg.clickedButton()
                if clicked == merge_btn:
                    return name, True
                if clicked == new_btn:
                    new_name, ok = QInputDialog.getText(self.ui, '新建ID', '请输入新用户名：')
                    if not ok:
                        return '', False
                    valid_name, reason = self._sanitize_username(new_name)
                    if not valid_name:
                        QMessageBox.about(self.ui, '错误', reason)
                        return '', False
                    return valid_name, False
                if clicked == cancel_btn:
                    return '', False
                return '', False
        return name, False

    @staticmethod
    def _next_sample_index(user_dir):
        max_idx = 0
        for img_path in user_dir.iterdir():
            if not img_path.is_file():
                continue
            stem = img_path.stem
            if stem.isdigit():
                max_idx = max(max_idx, int(stem))
        return max_idx + 1

    def _set_enroll_controls_enabled(self, enabled):
        self.ui.pushButton.setEnabled(enabled)
        self.ui.pushButton2.setEnabled(enabled)
        self.ui.pushButton3.setEnabled(enabled)
        self.ui.pushButton4.setEnabled(enabled)
        self.ui.pushButton5.setEnabled(enabled)
        self.ui.lineEdit.setEnabled(enabled)

    def trainModel(self, exit_after_success=False):
        if self._is_training:
            return False
        if self._capture_running:
            QMessageBox.about(self.ui, '提示', '当前正在采集样本，请稍后再更新模型。')
            return False
        if not self._model_pending:
            QMessageBox.about(self.ui, '提示', '当前模型已是最新状态，无需更新。')
            return True

        self._is_training = True
        self._set_enroll_controls_enabled(False)
        self._train_exit_after_success = bool(exit_after_success)
        self._train_progress_dialog = QProgressDialog('正在更新模型，请稍候...', '', 0, 4, self.ui)
        self._train_progress_dialog.setWindowTitle('模型更新中')
        self._train_progress_dialog.setCancelButton(None)
        self._train_progress_dialog.setWindowModality(Qt.ApplicationModal)
        self._train_progress_dialog.setMinimumDuration(0)
        self._train_progress_dialog.setValue(0)
        self._train_progress_dialog.show()
        QApplication.processEvents()

        snapshots = self.main_window.capture_busy_slots()
        self.main_window.close_slots_from_snapshots(snapshots)
        self._train_snapshots = snapshots
        threading.Thread(
            target=self._train_model_worker,
            daemon=True,
        ).start()
        return True

    def _train_model_worker(self):
        start_ts = time.time()
        sample_count = 0
        user_count = len(_app_service().state.user_dic)
        detail = ''
        ok = False
        try:
            self._enroll_bridge.train_progress.emit(1, '步骤 1/4：检查样本...')
            samples, labels = _rebuild_face_training_data()
            sample_count = len(samples)
            user_count = len(_app_service().state.user_dic)
            if len(samples) != len(labels):
                detail = f'训练数据异常：样本数={len(samples)}，标签数={len(labels)}'
                return

            if not _app_service().pipeline.ensure_face_service_ready():
                detail = _app_service().pipeline.face_service_error_text() or '深度识别依赖未安装'
                return

            backend_mode = _app_service().pipeline.current_backend_mode()
            if backend_mode == 'lbph':
                self._enroll_bridge.train_progress.emit(2, '步骤 2/4：训练并写入模型（LBPH降级模式）...')
            elif backend_mode == 'lite':
                self._enroll_bridge.train_progress.emit(2, '步骤 2/4：训练并写入模型（Lite应急模式）...')
            else:
                self._enroll_bridge.train_progress.emit(2, '步骤 2/4：训练并写入模型...')

            ok = _app_service().train_with_samples(samples, labels)
            if not ok:
                detail = _app_service().pipeline.last_train_error_text() or '模型更新失败，请检查样本和模型环境。'
                return

            _app_service().state.update_user_stats()
            elapsed = max(0.01, time.time() - start_ts)
            self._enroll_bridge.train_progress.emit(3, '步骤 3/4：刷新状态...')
            self._enroll_bridge.train_progress.emit(4, '步骤 4/4：完成')
            self._enroll_bridge.train_finished.emit(True, user_count, sample_count, elapsed, '', '')
        finally:
            if not ok:
                self._enroll_bridge.train_finished.emit(False, user_count, sample_count, max(0.01, time.time() - start_ts), detail, '')

    def _on_train_progress(self, step, message):
        progress = getattr(self, '_train_progress_dialog', None)
        if progress is None:
            return
        try:
            progress.setLabelText(message)
            progress.setValue(int(step))
            QApplication.processEvents()
        except Exception:
            pass

    def _on_train_finished(self, success, user_count, sample_count, elapsed, detail, _reserved):
        progress = getattr(self, '_train_progress_dialog', None)
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass
            self._train_progress_dialog = None
        snapshots = getattr(self, '_train_snapshots', [])
        try:
            self.main_window.restore_slots_from_snapshots(snapshots)
        except Exception:
            pass
        self._train_snapshots = []
        self._set_enroll_controls_enabled(True)
        self._is_training = False
        if not success:
            if detail:
                QMessageBox.about(self.ui, '错误', f'模型更新失败，请检查样本和模型环境。\n\n详细原因：{detail}')
            else:
                QMessageBox.about(self.ui, '错误', '模型更新失败，请检查样本和模型环境。')
            return
        self._clear_model_pending_ui()
        QMessageBox.about(
            self.ui,
            '更新完成',
            f'模型更新成功。\n训练人数：{user_count}\n样本总数：{sample_count}\n耗时：{elapsed:.2f} 秒',
        )
        if getattr(self, '_train_exit_after_success', False):
            self.closeQuit(force=True)
            return
        next_action = QMessageBox.question(
            self.ui,
            '后续操作',
            '模型已更新，是否继续留在录入界面？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if next_action == QMessageBox.No:
            self.closeQuit(force=True)

    def closeQuit(self, force=False):
        if self._is_training:
            QMessageBox.about(self.ui, '提示', '模型更新进行中，请稍候。')
            return
        if self._capture_running:
            reply = QMessageBox.question(
                self.ui,
                '确认退出',
                '当前正在采集样本，确认要中断并退出吗？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        if (not force) and self._model_pending:
            msg = QMessageBox(self.ui)
            msg.setWindowTitle('模型尚未更新')
            msg.setText('模型尚未更新，是否现在更新模型？')
            update_btn = msg.addButton('更新后退出', QMessageBox.YesRole)
            direct_btn = msg.addButton('直接退出', QMessageBox.NoRole)
            cancel_btn = msg.addButton('取消', QMessageBox.RejectRole)
            msg.exec_()
            clicked = msg.clickedButton()
            if clicked == cancel_btn:
                return
            if clicked == update_btn:
                if self.trainModel(exit_after_success=True):
                    return
                return
            if clicked == direct_btn:
                pass

        self._shutdown_enroll_resources()
        self.main_window.refresh_model_pending_hint()
        self.ui.close()

    def _shutdown_enroll_resources(self):
        if hasattr(self, 'lurucam') and self.lurucam is not None:
            self.lurucam.close(release_system_lock=False)
            self.lurucam = None
        if hasattr(self, 'lurucamReal') and self.lurucamReal is not None:
            self.lurucamReal.close(release_system_lock=False)
            self.lurucamReal = None
        self._restore_integrated_camera()

    def _restore_integrated_camera(self):
        if self._restore_done:
            return
        self._restore_done = True
        current_lock = _app_service().state.system_lock_slot
        if current_lock == 1 and self.main_window.busy1 == False:
            self.main_window.start1(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif current_lock == 2 and self.main_window.busy2 == False:
            self.main_window.start2(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif current_lock == 3 and self.main_window.busy3 == False:
            self.main_window.start3(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif current_lock == 4 and self.main_window.busy4 == False:
            self.main_window.start4(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif current_lock == 55:
            _app_service().state.system_lock_slot = 0

    def getNewface(self):
        print('正在从摄像头录入新的人脸信息\n' * 3)
        self.sampleNum = 0
        self._capture_running = True
        self.ui.pushButton.setText(f'正在采集中 0/{self.maxSampleNum}')

        if hasattr(self, 'lurucam') and self.lurucam is not None:
            self.lurucam.close(release_system_lock=False)
            self.lurucam = None

        self.lurucamReal = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
        if not self.lurucamReal.cap.isOpened():
            self._capture_running = False
            self.ui.pushButton.setText('拍摄')
            QMessageBox.about(self.ui, '错误', '摄像头未打开，无法进行拍摄。')
            return
        self.luruThreadReal = threading.Thread(target=self.getNewFaceDisplay, daemon=True)
        self.luruThreadReal.start()

    def getNewFaceDisplay(self):
        print('人脸捕捉新线程已经开启' * 5)
        captured_any = False
        start_ts = time.time()
        last_face_ts = start_ts
        capture_timeout_sec = 20.0
        no_face_timeout_sec = 6.0
        finished_reason = '未检测到人脸，请调整位置后重试。'
        while (
            hasattr(self, 'lurucamReal')
            and self.lurucamReal._running
            and self.lurucamReal.cap.isOpened()
            and self.sampleNum < self.maxSampleNum
        ):
            now_ts = time.time()
            if (now_ts - start_ts) > capture_timeout_sec:
                if captured_any:
                    finished_reason = '采集超时，已保存当前样本，建议补足后更新模型。'
                else:
                    finished_reason = '采集超时且未检测到人脸，请调整位置后重试。'
                break
            if (now_ts - last_face_ts) > no_face_timeout_sec and (not captured_any):
                finished_reason = '长时间未检测到人脸，请调整角度/光照后重试。'
                break

            success, frame = self.lurucamReal.cap.read()
            if not success:
                finished_reason = '摄像头读取失败，请重试。'
                break

            rawframe = cv2.resize(frame, (640, 360))
            frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
            self.faces = self.lurucamReal.detector.detectMultiScale(frame, 1.3, 5)
            if not isinstance(self.faces, list):
                self.faces = list(self.faces)
            if len(self.faces) > 0:
                last_face_ts = time.time()

            for (x, y, w, h) in self.faces:
                if self.sampleNum >= self.maxSampleNum:
                    break
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), thickness=2)
                user_dir = _app_service().data_repo.user_dir_path(self.filepath)
                file_index = self._capture_write_index
                self._capture_write_index += 1
                self.sampleNum += 1
                face_img = frame[y:y + h, x:x + w]
                cv2.imwrite(str(user_dir / f'{file_index}.jpg'), face_img)
                captured_any = True
                self._enroll_bridge.capture_progress.emit(self.sampleNum, self.maxSampleNum)

            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            self.lurucamReal._emit_frame(rawframe)
            time.sleep(0.01)

        if hasattr(self, 'lurucamReal') and self.lurucamReal is not None:
            self.lurucamReal.close(release_system_lock=False)
            self.lurucamReal._emit_no_signal()
            self.lurucamReal = None

        self._capture_write_index = 1
        if self.sampleNum >= self.maxSampleNum:
            self._enroll_bridge.capture_finished.emit(True, self.sampleNum, '采集完成，请更新模型。')
        elif captured_any:
            self._enroll_bridge.capture_finished.emit(True, self.sampleNum, finished_reason)
        else:
            self._enroll_bridge.capture_finished.emit(False, self.sampleNum, finished_reason)

    def _on_capture_progress(self, captured, max_count):
        self.ui.pushButton.setText(f'拍摄中 {captured}/{max_count}')

    def _on_capture_finished(self, success, captured, message):
        self._capture_running = False
        self.ui.pushButton.setText('拍摄')
        if success and captured > 0:
            self._mark_model_pending_ui()
        QMessageBox.about(self.ui, '拍摄结果', f'{message}\n已采集：{captured}/{self.maxSampleNum}')
        self._start_luru_preview()
        self.sampleNum = 0
        self._refresh_capture_status_label()

    def _start_luru_preview(self):
        if hasattr(self, 'lurucam') and self.lurucam is not None and self.lurucam._running:
            return
        self.lurucam = Camera(0, self.ui.lurudisplay, _app_service(), prefer_haar_detector=True)
        if not self.lurucam.cap.isOpened():
            QMessageBox.about(self.ui, '错误', '摄像头预览恢复失败，请检查设备。')
            return
        self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
        self.luruThread.start()

    def snap(self):
        if self._capture_running:
            QMessageBox.about(self.ui, '提示', '正在采集中，请稍候。')
            return
        if self._is_training:
            QMessageBox.about(self.ui, '提示', '模型更新进行中，暂不可拍摄。')
            return

        username, reason = self._sanitize_username(self.ui.lineEdit.text())
        if not username:
            QMessageBox.about(self.ui, '错误', reason)
            return
        final_name, append_mode = self._resolve_enroll_name(username)
        if not final_name:
            return

        self.filepath = final_name
        self.current_username = final_name
        self.ui.lineEdit.setText(final_name)
        print("拍照按钮按下 用户应该保证拍摄效果 \n" * 5)
        if append_mode:
            user_dir = _app_service().data_repo.user_dir_path(self.filepath)
            user_dir.mkdir(parents=True, exist_ok=True)
            self._capture_write_index = self._next_sample_index(user_dir)
        else:
            user_dir = _app_service().data_repo.recreate_user_dir(self.filepath)
            self._capture_write_index = 1
        _app_service().ensure_user_registered(self.filepath)
        self.getNewface()


class ResetWindow():

    def __init__(self):
        self.ui = QUiLoader().load(ui_path('ResetQ.ui'))
        self.ui.setFont(_default_ui_font())
        self.ui.setStyleSheet(_app_stylesheet())
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.buttonBox.accepted.connect(self.yes)
        self.ui.buttonBox.accepted.connect(self.no)

    def yes(self):
        _app_service().reset_face_data()
        print('重置按钮已经按下，会清空人脸样本、模型和配置')
        print('totalUser:', _app_service().state.total_user)


    def no(self):
        print('重置操作没有被确认，重置操作被取消')

