from __future__ import annotations

from PySide2.QtWidgets import QMessageBox
from PySide2.QtUiTools import QUiLoader
from PySide2.QtGui import QPixmap
from PySide2.QtCore import Qt, QObject, Signal
import cv2, threading, os, shutil
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

def _rebuild_face_training_data():
    app_service = _app_service()
    return app_service.pipeline.rebuild_training_data(app_service.data_repo)

class MWindow():

    def __init__(self):
        self._closing = False
        self.mui = QUiLoader().load(ui_path('MUi.ui'))
        self._msg_bridge = _MessageBridge(self.mui)
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
        print('function of del camera'
              '显示删除摄像头的界面 显示需要删除的摄像头的链接')
        self.addwin = DelWindow(self)
        self.addwin.ui.show()

    def addcam(self):
        print('function of add camera'
              '显示添加摄像头的界面 显示需要添加的摄像头的链接')
        self.addwin = AddWindow(self)
        self.addwin.ui.show()

    def luru(self):
        print('function of luru face'
              '显示人脸录入界面 这里需要系统锁 人脸录入的优先级比display的优先级高')
        self.luruwin = LuruWindow(self)
        self.luruwin.ui.setWindowFlags(Qt.CustomizeWindowHint)
        self.luruwin.ui.show()

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
        """
        回调：摄像头流异常/结束时自动回收主窗口状态，避免“假忙碌”。
        注意：这里只做状态回收，不直接操作UI控件，以降低线程边界风险。
        """
        runtime = self.ui_controller.get_slot_runtime(int(slot))
        current_cam = getattr(self, runtime.camera_attr, None)
        if current_cam is not cam_obj:
            return
        if cam_obj.url in self.cameraList:
            self.cameraList.remove(cam_obj.url)
        setattr(self, runtime.busy_attr, False)
        label = getattr(self.mui, runtime.label_name, None)
        if label is not None:
            label.setPixmap(QPixmap(asset_path('nosignal.png')))
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
            print(type(cam_url))
            if cam_url.isdigit():
                cam_url = int(cam_url)
            else:
                print(type(cam_url))
            self._start_slot(
                slot_map[slot_text],
                cam_url,
                self.ui.comboBox2.currentIndex(),
                self.ui.lineEdit2.text(),
            )

    def cancel(self):
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

        snapshots = self.main_window.capture_busy_slots()
        self.main_window.close_slots_from_snapshots(snapshots)
        try:
            if not _app_service().delete_user_and_rebuild(faceTodel):
                QMessageBox.about(self.ui, '错误', '重建训练模型失败，请检查样本。')
                return
        finally:
            self.main_window.restore_slots_from_snapshots(snapshots)

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

        self.ui.pushButton2.clicked.connect(self.closeQuit)
        self.ui.pushButton.clicked.connect(self.snap)
        self.ui.pushButton3.clicked.connect(self.trainModel)
        self.ui.pushButton4.clicked.connect(self.delAll)
        # 点击按钮四会执行模型重置操作，跳出弹窗
        self.ui.pushButton5.clicked.connect(self.delFace)

        self.integratedNamePlace = '' # 记录集成摄像头的名称和地点 以便于后续重启的设置
        self.integratedDisplaymode = 0 # 记录集成摄像头的显示模式
        self._restore_done = False

        current_lock = _app_service().state.system_lock_slot
        if current_lock != 0:
            QMessageBox.about(self.ui, '警告', '集成相机被占用，即将解锁，监控将暂时中断，人脸录入结束后可自行恢复')
            if current_lock == 1:
                self.integratedNamePlace = self.main_window.cam1.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam1.displayMode
                self.main_window.close1()
                _app_service().state.system_lock_slot = 1
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service())
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif current_lock == 2:
                self.integratedNamePlace = self.main_window.cam2.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam2.displayMode
                self.main_window.close2()
                _app_service().state.system_lock_slot = 2
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service())
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif current_lock == 3:
                self.integratedNamePlace = self.main_window.cam3.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam3.displayMode
                self.main_window.close3()
                _app_service().state.system_lock_slot = 3
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service())
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif current_lock == 4:
                self.integratedNamePlace = self.main_window.cam4.nameAndLocation
                self.integratedDisplaymode = self.main_window.cam4.displayMode
                self.main_window.close4()
                _app_service().state.system_lock_slot = 4
                self.lurucam = Camera(0, self.ui.lurudisplay, _app_service())
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()

        if _app_service().state.system_lock_slot == 0:
            _app_service().state.system_lock_slot = 55
            self.lurucam = Camera(0, self.ui.lurudisplay, _app_service())
            self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
            # self.luruThread.setDaemon(True)
            self.luruThread.start()

    def delFace(self):
        self.delfacewin = DelFaceWindow(self.main_window)
        self.delfacewin.ui.show()

    def delAll(self):
        self.resetwin = ResetWindow()
        self.resetwin.ui.show()

    def trainModel(self):
        print('训练模型按钮已经按下')
        username = self.ui.lineEdit.text().strip()

        can_train, reason = _app_service().can_train_user(username)
        if not can_train:
            QMessageBox.about(self.ui, '错误', reason)
        else:
            _app_service().ensure_user_registered(username)

            '''
            因为在按下拍摄按钮后，主界面的display窗口就已经启动 > display()会检测yml文件的存在
            > 存在yml文件就会进行读取操作 > 此时的trainModel()可能刚被按下，模型尚未训练完成
            > 导致Camera.display()中的读取yml文件操作出现报错

            解决方法：
            训练过程中，释放Camera的cap 训练完成后再进行 start操作

            因为本系统为多摄像头的监控管理系统，应用中很有可能不止一个摄像头在使用yml模型进行人脸识别操作
            所以需要对正在忙碌的窗口所对应的Camera对象都进行release操作，并在模型训练完成后
            对应当进行重启的摄像头进行重启操作
            '''
            snapshots = self.main_window.capture_busy_slots()
            self.main_window.close_slots_from_snapshots(snapshots)

            try:
                samples, labels = _rebuild_face_training_data()
                if len(samples) == 0:
                    QMessageBox.about(self.ui, '错误', '未检测到有效人脸样本，请重新拍摄后再训练。')
                    return
                if len(samples) != len(labels):
                    QMessageBox.about(self.ui, '错误', f'训练数据异常：样本数={len(samples)}，标签数={len(labels)}')
                    return

                _app_service().state.face_samples = samples
                _app_service().state.id_lists = labels
                if not _app_service().rebuild_and_train():
                    QMessageBox.about(self.ui, '错误', '训练失败，请检查样本和模型环境。')
                    return
                _app_service().state.update_user_stats()
            finally:
                self.main_window.restore_slots_from_snapshots(snapshots)

    def closeQuit(self):
        if hasattr(self, 'lurucam') and self.lurucam is not None:
            self.lurucam.close()
        if hasattr(self, 'lurucamReal') and self.lurucamReal is not None:
            self.lurucamReal.close()
        self._restore_integrated_camera()
        self.ui.close()

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
        self.sampleNum = 0  # 已经获取的样本数量
        self.maxSampleNum = 10

        self.lurucam.cap.release()
        self.ui.lurudisplay.setPixmap(QPixmap(asset_path('nosignal.png')))

        self.lurucamReal = Camera(0, self.ui.lurudisplay, _app_service())
        self.luruThreadReal = threading.Thread(target=self.getNewFaceDisplay, daemon=True)
        self.luruThreadReal.start()

    def getNewFaceDisplay(self):
        print('人脸捕捉新线程已经开启' * 5)
        while (
            hasattr(self, 'lurucamReal')
            and self.lurucamReal._running
            and self.lurucamReal.cap.isOpened()
            and self.sampleNum < self.maxSampleNum
        ):
            success, frame = self.lurucamReal.cap.read()
            if not success:
                break

            rawframe = cv2.resize(frame, (640, 360))
            frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
            self.faces = self.lurucamReal.detector.detectMultiScale(frame, 1.3, 5)

            for (x, y, w, h) in self.faces:
                if self.sampleNum >= self.maxSampleNum:
                    break
                cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), thickness=2)
                self.sampleNum += 1
                user_dir = _app_service().data_repo.user_dir_path(self.filepath)
                cv2.imwrite(str(user_dir / f'{self.sampleNum}.jpg'), frame)

            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            self.lurucamReal._emit_frame(rawframe)
            cv2.waitKey(10)

        if hasattr(self, 'lurucamReal') and self.lurucamReal is not None:
            self.lurucamReal.close()
            self.lurucamReal._emit_no_signal()
        self.sampleNum = 0
        self._restore_integrated_camera()

    def snap(self):
        if self.ui.lineEdit.text() == '':
            QMessageBox.about(self.ui, '错误', '你还没有输入姓名')
        else:
            self.filepath = self.ui.lineEdit.text()
            # 这里需要添加“文件中是否有重复人员的校验操作”
            print("拍照按钮按下 用户应该保证拍摄效果 \n" * 5)
            _app_service().data_repo.recreate_user_dir(self.filepath)
            # 存在用户姓名目录就清空，不存在就创建，确保最后存在空的data目录

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

