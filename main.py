'''
逻辑无问题 数据库可以正常搜索 集成摄像头重启后以及训练模型后
所有摄像头的重启后 其名称地址都能表示正确 可以设置摄像头使用哪种显示类型
并且可以对指定的用户进行删除操作
可以全彩色显示
'''

from PySide2.QtWidgets import QApplication, QMessageBox, QTableWidgetItem, QHeaderView, QLabel, QComboBox, QPushButton, QFileDialog
from PySide2.QtUiTools import QUiLoader
from PySide2.QtGui import QImage, QPixmap, QFont
from PySide2.QtCore import Qt, QObject, Signal
import numpy as np
import cv2, threading, os, shutil
from PIL import Image, ImageDraw, ImageFont
import ast
import datetime
from services.emotion_service import EmotionRecognitionService
from paths import asset_path, ui_path
import sqls # sqls是自己写的模块

DEFAULT_UI_FONT = QFont('Microsoft YaHei UI', 10)
APP_STYLESHEET = """
    QWidget { background: #f5f8fc; color: #213547; font-family: \"Microsoft YaHei UI\"; font-size: 10pt; }
    QGroupBox { border: 1px solid #c7d5e8; border-radius: 10px; margin-top: 10px; background: #ffffff; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #1c5d99; font-weight: 600; }
    QLineEdit, QComboBox, QDateTimeEdit, QTableWidget {
        border: 1px solid #b8c8dc; border-radius: 6px; padding: 4px 6px; background: #fbfdff;
    }
    QPushButton { border: 1px solid #8fb2d6; border-radius: 8px; padding: 6px 10px; background: #eaf3ff; font-weight: 600; }
    QPushButton:hover { background: #d8eaff; }
    QLabel#display1, QLabel#display2, QLabel#display3, QLabel#display4 { border: 1px solid #c9d7e8; border-radius: 8px; background: #f8fbff; }
"""

systemLock = 0
totalUser = 0
faceSamples = []
idlists = []
userdic = {}


class _LabelBridge(QObject):
    pixmap_ready = Signal(QPixmap)

    def __init__(self, label):
        super().__init__()
        self._label = label
        self.pixmap_ready.connect(self._label.setPixmap, Qt.QueuedConnection)

def _resolve_user_data_dir(user_id, username):
    id_dir = os.path.join('data', str(user_id))
    name_dir = os.path.join('data', str(username))
    if os.path.isdir(id_dir):
        return id_dir
    if os.path.isdir(name_dir):
        return name_dir
    return None


def _rebuild_face_training_data():
    detector = cv2.CascadeClassifier(asset_path('haarcascade_frontalface_default.xml'))
    samples = []
    labels = []
    if detector.empty():
        print('警告：人脸检测器加载失败，无法重建训练集')
        return samples, labels

    for user_id in sorted(userdic.keys()):
        username = userdic[user_id]
        user_dir = _resolve_user_data_dir(user_id, username)
        if not user_dir:
            continue
        for filename in os.listdir(user_dir):
            image_path = os.path.join(user_dir, filename)
            if not os.path.isfile(image_path):
                continue
            try:
                img = Image.open(image_path).convert('L')
            except Exception as exc:
                print('跳过损坏图片:', image_path, exc)
                continue
            img_np = np.array(img)
            faces = detector.detectMultiScale(img_np)
            for (x, y, w, h) in faces:
                samples.append(img_np[y:y + h, x:x + w])
                labels.append(int(user_id))
    return samples, labels


def _persist_user_training_config():
    with open('config/idlists.txt', 'w') as f:
        for label in idlists:
            f.write(str(label))
            f.write('\n')
    with open('config/totalUser.txt', 'w') as f:
        f.write(str(totalUser))
    with open('config/userdic.txt', 'w') as f:
        f.write(str(userdic))

class MWindow():

    def __init__(self):
        self._closing = False
        self.mui = QUiLoader().load(ui_path('MUi.ui'))
        self.mui.setFont(DEFAULT_UI_FONT)
        self.mui.setStyleSheet(APP_STYLESHEET)
        self.mui.setFixedSize(self.mui.width(), self.mui.height())
        self.mui.closeEvent = self._on_close_event
        self.mui.pushButton1.clicked.connect(self.start)
        self.mui.pushButton2.clicked.connect(self.close)
        self.mui.addButton.clicked.connect(self.addcam)
        self.mui.delButton.clicked.connect(self.delcam)
        self.mui.luruButton.clicked.connect(self.luru)
        self.mui.logButton.clicked.connect(self.log)
        self.mui.pushButtonSaveConfig.clicked.connect(self.saveconfig)

        self.busy1, self.busy2, self.busy3, self.busy4 = False, False, False, False
        self.cameraList = [] # 记录已经获取的摄像头 避免同一个摄像头重复获取

        ######### ↓↓↓以下代码为人脸识别数据初始化过程 ########
        global totalUser, faceSamples, idlists, userdic

        f = open('config/totalUser.txt')
        config_totalUser = f.read()
        totalUser = int(config_totalUser)
        f.close()
        print('totaluser:', totalUser, type(totalUser))

        f = open('config/idlists.txt')
        for line in f.readlines():
            line = line.strip('\n')
            idlists.append(int(line))
        f.close()
        print('idlists:', idlists, type(idlists))

        if os.path.getsize('config/userdic.txt') > 0:
            f = open('config/userdic.txt')
            config_userdic = f.read()
            userdic = ast.literal_eval(config_userdic)
            f.close()
            print('userdic:', userdic, type(userdic))

        if userdic:
            max_user_id = max([int(i) for i in userdic.keys()])
            if totalUser < max_user_id:
                totalUser = max_user_id

        faceSamples, rebuilt_labels = _rebuild_face_training_data()
        idlists = rebuilt_labels
        print('rebuild face samples:', len(faceSamples), 'labels:', len(idlists))
        ######### ↑↑↑以上代码为人脸识别数据初始化过程 ########

        ######### ↓↓↓以下代码为显示初始化过程 ########
        global systemLock
        f = open('config/configwin1.txt')
        result1 = []
        for line in f.readlines():
            line = line.strip('\n')
            result1.append(line)
        f.close()

        f = open('config/configwin2.txt')
        result2 = []
        for line in f.readlines():
            line =  line.strip('\n')
            result2.append(line)
        f.close()

        f = open('config/configwin3.txt')
        result3 = []
        for line in f.readlines():
            line = line.strip('\n')
            result3.append(line)
        f.close()

        f = open('config/configwin4.txt')
        result4 = []
        for line in f.readlines():
            line = line.strip('\n')
            result4.append(line)
        f.close()

        if result1 == []:
            pass
        else:
            nameandplace = result1[0]
            displaymode = int(result1[1])
            url = result1[2]
            if url.isdigit():
                # 如果是摄像头id
                url = int(url)
                if url == 0:
                    if systemLock != 0:
                        QMessageBox.about(self.mui, '错误', '集成摄像头被占用！')
                        return
                    elif systemLock == 0:
                        systemLock = 1
            else:
                # 如果不是摄像头id
                pass
            self.mui.lineEdit11.setText(nameandplace)
            self.mui.comboBox1.setCurrentIndex(displaymode)
            self.mui.lineEdit12.setText(str(url))
            if url != '':
                self.start1(url, nameandplace, displaymode)

        if result2 == []:
            pass
        else:
            nameandplace = result2[0]
            displaymode = int(result2[1])
            url = result2[2]
            if url.isdigit():
                # 如果是摄像头id
                url = int(url)
                if url == 0:
                    if systemLock != 0:
                        QMessageBox.about(self.mui, '错误', '集成摄像头被占用！')
                        return
                    elif systemLock == 0:
                        systemLock = 2
            else:
                # 如果不是摄像头id
                pass
            self.mui.lineEdit21.setText(nameandplace)
            self.mui.comboBox2.setCurrentIndex(displaymode)
            self.mui.lineEdit22.setText(str(url))
            if url != '':
                self.start2(url, nameandplace, displaymode)

        if result3 == []:
            pass
        else:
            nameandplace = result3[0]
            displaymode = int(result3[1])
            url = result3[2]
            if url.isdigit():
                # 如果是摄像头id
                url = int(url)
                if url == 0:
                    if systemLock != 0:
                        QMessageBox.about(self.mui, '错误', '集成摄像头被占用！')
                        return
                    elif systemLock == 0:
                        systemLock = 3
            else:
                # 如果不是摄像头id
                pass
            self.mui.lineEdit31.setText(nameandplace)
            self.mui.comboBox3.setCurrentIndex(displaymode)
            self.mui.lineEdit32.setText(str(url))
            if url != '':
                self.start3(url, nameandplace, displaymode)

        if result4 == []:
            pass
        else:
            nameandplace = result4[0]
            displaymode = int(result4[1])
            url = result4[2]
            if url.isdigit():
                # 如果是摄像头id
                url = int(url)
                if url == 0:
                    if systemLock != 0:
                        QMessageBox.about(self.mui, '错误', '集成摄像头被占用！')
                        return
                    elif systemLock == 0:
                        systemLock = 4
            else:
                # 如果不是摄像头id
                pass
            self.mui.lineEdit41.setText(nameandplace)
            self.mui.comboBox4.setCurrentIndex(displaymode)
            self.mui.lineEdit42.setText(str(url))
            if url != '':
                self.start4(url, nameandplace, displaymode)

        ######### ↑↑↑以上代码为显示初始化过程 ########

    def _on_close_event(self, event):
        self._closing = True
        try:
            self.close()
        finally:
            event.accept()

    def saveconfig(self):  # 保存显示配置文件的函数
        f = open('config/configwin1.txt', 'w')
        nameAndLocation = self.mui.lineEdit11.text()
        displaymode = self.mui.comboBox1.currentIndex()
        url = self.mui.lineEdit12.text()
        result1 = nameAndLocation + '\n' + str(displaymode) + '\n' + url + '\n'
        f.write(result1)
        f.close()
        f = open('config/configwin2.txt', 'w')
        nameAndLocation = self.mui.lineEdit21.text()
        displaymode = self.mui.comboBox2.currentIndex()
        url = self.mui.lineEdit22.text()
        result2 = nameAndLocation + '\n' + str(displaymode) + '\n' + url + '\n'
        f.write(result2)
        f.close()
        f = open('config/configwin3.txt', 'w')
        nameAndLocation = self.mui.lineEdit31.text()
        displaymode = self.mui.comboBox3.currentIndex()
        url = self.mui.lineEdit32.text()
        result3 = nameAndLocation + '\n' + str(displaymode) + '\n' + url + '\n'
        f.write(result3)
        f.close()
        f = open('config/configwin4.txt', 'w')
        nameAndLocation = self.mui.lineEdit41.text()
        displaymode = self.mui.comboBox4.currentIndex()
        url = self.mui.lineEdit42.text()
        result4 = nameAndLocation + '\n' + str(displaymode) + '\n' + url + '\n'
        f.write(result4)
        f.close()

        QMessageBox.about(self.mui, '保存成功', '下次启动时会采用此次配置')

    def delcam(self):
        print('function of del camera'
              '显示删除摄像头的界面 显示需要删除的摄像头的链接')
        self.addwin = DelWindow()
        self.addwin.ui.show()

    def addcam(self):
        print('function of add camera'
              '显示添加摄像头的界面 显示需要添加的摄像头的链接')
        self.addwin = AddWindow()
        self.addwin.ui.show()

    def luru(self):
        print('function of luru face'
              '显示人脸录入界面 这里需要系统锁 人脸录入的优先级比display的优先级高')
        self.luruwin = LuruWindow()
        self.luruwin.ui.setWindowFlags(Qt.CustomizeWindowHint)
        self.luruwin.ui.show()

    def log(self):
        print('function of inquiry log')
        self.logwin = LogWindow()
        self.logwin.ui.show()

    def start(self):
        if self.busy1 == True:
            QMessageBox.about(self.mui, '错误', '窗口1忙碌，不可以添加视频流')
        else:
            self.cam1 = Camera('1 Danny MacAskill’s Wee Day Out.flv', self.mui.display1)
            threading.Thread(target=self.cam1.display, daemon=True).start()
            if self.cam1.cap.isOpened():
                self.busy1 = True

        if self.busy2 == True:
            QMessageBox.about(self.mui, '错误', '窗口2忙碌，不可以添加视频流')
        else:
            self.cam2 = Camera('1 Danny MacAskill’s Wee Day Out.flv', self.mui.display2)
            threading.Thread(target=self.cam2.display, daemon=True).start()
            if self.cam2.cap.isOpened():
                self.busy2 = True

        if self.busy3 == True:
            QMessageBox.about(self.mui, '错误', '窗口3忙碌，不可以添加视频流')
        else:
            self.cam3 = Camera('1 Danny MacAskill’s Wee Day Out.flv', self.mui.display3)
            threading.Thread(target=self.cam3.display, daemon=True).start()
            if self.cam3.cap.isOpened():
                self.busy3 = True

        if self.busy4 == True:
            QMessageBox.about(self.mui, '错误', '窗口4忙碌，不可以添加视频流')
        else:
            self.cam4 = Camera('1 Danny MacAskill’s Wee Day Out.flv', self.mui.display4)
            threading.Thread(target=self.cam4.display, daemon=True).start()
            if self.cam4.cap.isOpened():
                self.busy4 = True

    def start1(self, url, cameraNamePlace = '', displaymode = 0):
        global systemLock
        if self.busy1 == True:
            QMessageBox.about(self.mui, '错误', '窗口1忙碌，不可以添加视频流')
        elif url in self.cameraList:
            QMessageBox.about(self.mui, '错误', f'摄像头{url}忙碌，不可以重复使用')
        else:
            if url == 0:
                systemLock = 1  # 上锁
            self.cam1 = Camera(url, self.mui.display1)
            self.cam1.displayMode = displaymode
            if cameraNamePlace != '':
                self.cam1.nameAndLocation = cameraNamePlace
            if displaymode == 0:
                threading.Thread(target=self.cam1.display, daemon=True).start()
            elif displaymode == 1:
                threading.Thread(target=self.cam1.displaySimpleBrand, daemon=True).start()
            elif displaymode == 2:
                threading.Thread(target=self.cam1.displayJustdisplayBrand, daemon=True).start()
            if self.cam1.cap.isOpened():
                self.busy1 = True
                self.cameraList.append(url)

    def start2(self, url, cameraNamePlace = '', displaymode = 0):
        global systemLock
        if self.busy2 == True:
            QMessageBox.about(self.mui, '错误', '窗口2忙碌，不可以添加视频流')
        elif url in self.cameraList:
            QMessageBox.about(self.mui, '错误', f'摄像头{url}忙碌，不可以重复使用')
        else:
            if url == 0:
                systemLock = 2  # 上锁
            self.cam2 = Camera(url, self.mui.display2)
            self.cam2.displayMode = displaymode
            if cameraNamePlace != '':
                self.cam2.nameAndLocation = cameraNamePlace
            if displaymode == 0:
                threading.Thread(target=self.cam2.display, daemon=True).start()
            elif displaymode == 1:
                threading.Thread(target=self.cam2.displaySimpleBrand, daemon=True).start()
            elif displaymode == 2:
                threading.Thread(target=self.cam2.displayJustdisplayBrand, daemon=True).start()
            if self.cam2.cap.isOpened():
                self.busy2 = True
                self.cameraList.append(url)

    def start3(self, url, cameraNamePlace = '', displaymode = 0):
        global systemLock
        if self.busy3 == True:
            QMessageBox.about(self.mui, '错误', '窗口3忙碌，不可以添加视频流')
        elif url in self.cameraList:
            QMessageBox.about(self.mui, '错误', f'摄像头{url}忙碌，不可以重复使用')
        else:
            if url == 0:
                systemLock = 3  # 上锁
            self.cam3 = Camera(url, self.mui.display3)
            self.cam3.displayMode = displaymode
            if cameraNamePlace != '':
                self.cam3.nameAndLocation = cameraNamePlace
            if displaymode == 0:
                threading.Thread(target=self.cam3.display, daemon=True).start()
            elif displaymode == 1:
                threading.Thread(target=self.cam3.displaySimpleBrand, daemon=True).start()
            elif displaymode == 2:
                threading.Thread(target=self.cam3.displayJustdisplayBrand, daemon=True).start()
            if self.cam3.cap.isOpened():
                self.busy3 = True
                self.cameraList.append(url)

    def start4(self, url, cameraNamePlace = '', displaymode = 0):
        global systemLock
        if self.busy4 == True:
            QMessageBox.about(self.mui, '错误', '窗口4忙碌，不可以添加视频流')
        elif url in self.cameraList:
            QMessageBox.about(self.mui, '错误', f'摄像头{url}忙碌，不可以重复使用')
        else:
            if url == 0:
                systemLock = 4  # 上锁
            self.cam4 = Camera(url, self.mui.display4)
            self.cam4.displayMode = displaymode
            if cameraNamePlace != '':
                self.cam4.nameAndLocation = cameraNamePlace
            if displaymode == 0:
                threading.Thread(target=self.cam4.display, daemon=True).start()
            if displaymode == 1:
                threading.Thread(target=self.cam4.displaySimpleBrand, daemon=True).start()
            if displaymode == 2:
                threading.Thread(target=self.cam4.displayJustdisplayBrand, daemon=True).start()
            if self.cam4.cap.isOpened():
                self.busy4 = True
                self.cameraList.append(url)

    def close(self):
        slots = [
            ('busy1', 'cam1', self.mui.display1, '1close'),
            ('busy2', 'cam2', self.mui.display2, '2close'),
            ('busy3', 'cam3', self.mui.display3, '3close'),
            ('busy4', 'cam4', self.mui.display4, '4close'),
        ]
        for busy_attr, cam_attr, label, msg in slots:
            if getattr(self, busy_attr, False):
                cam = getattr(self, cam_attr, None)
                if cam is not None:
                    if cam.url in self.cameraList:
                        self.cameraList.remove(cam.url)
                    cam.close()
                label.setPixmap(QPixmap(asset_path('nosignal.png')))
                print(msg)
                setattr(self, busy_attr, False)

    def close1(self):
        if self.busy1 == True:
            if self.cam1.url in self.cameraList:
                self.cameraList.remove(self.cam1.url)
            self.cam1.close()
            print('1close')
            self.busy1 = False
            self.mui.display1.setPixmap(QPixmap(asset_path('nosignal.png')))
        else:
            QMessageBox.about(self.mui, '错误', '窗口1并没有打开')

    def close2(self):
        if self.busy2 == True:
            if self.cam2.url in self.cameraList:
                self.cameraList.remove(self.cam2.url)
            self.cam2.close()
            print('2close')
            self.busy2 = False
            self.mui.display2.setPixmap(QPixmap(asset_path('nosignal.png')))
        else:
            QMessageBox.about(self.mui, '错误', '窗口2并没有打开')

    def close3(self):
        if self.busy3 == True:
            if self.cam3.url in self.cameraList:
                self.cameraList.remove(self.cam3.url)
            self.cam3.close()
            print('3close')
            self.busy3 = False
            self.mui.display3.setPixmap(QPixmap(asset_path('nosignal.png')))
        else:
            QMessageBox.about(self.mui, '错误', '窗口3并没有打开')

    def close4(self):
        if self.busy4 == True:
            if self.cam4.url in self.cameraList:
                self.cameraList.remove(self.cam4.url)
            self.cam4.close()
            print('4close')
            self.busy4 = False
            self.mui.display4.setPixmap(QPixmap(asset_path('nosignal.png')))
        else:
            QMessageBox.about(self.mui, '错误', '窗口4并没有打开')

class AddWindow():

    def __init__(self):
        self.ui = QUiLoader().load(ui_path('Add.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)

    def ok(self):
        global systemLock
        print('push the ok button')
        print(self.ui.comboBox.currentText())

        if self.ui.comboBox.currentText() == '':
            QMessageBox.about(self.ui, '错误', '请在组合选择框中选择内容')

        else:
            if self.ui.comboBox.currentText() == 'win1':

                # print("我们将要打开窗口1")
                if self.ui.lineEdit.text() == '':
                    QMessageBox.about(self.ui, '错误', '请输入在文本框中输入内容')
                elif mainwindow.busy1 == False:
                    self.textCamUrl = self.ui.lineEdit.text()
                    print(type(self.textCamUrl))
                    if self.textCamUrl.isdigit():
                        self.textCamUrl = int(self.textCamUrl)
                        '''
                        如果不是视频格式 是摄像头的ID 则把他转换成int格式
                        '''
                        print(type(self.textCamUrl))

                        if self.textCamUrl == 0:

                            if systemLock != 0:
                                QMessageBox.about(self.ui, '错误', "集成摄像头被占用！")
                                return
                            elif systemLock == 0:
                                systemLock = 1
                                '''
                                这段代码是针对集成摄像头的占用检测，
                                集成摄像头涉及人脸录入
                                '''
                    else:
                        '''如果不是摄像头的ID
                        则什么都不做
                        '''
                        print(type(self.textCamUrl))
                        pass

                    if self.textCamUrl not in mainwindow.cameraList:
                        displaymodeIndex = self.ui.comboBox2.currentIndex()
                        mainwindow.start1(self.textCamUrl, displaymode=displaymodeIndex)
                        mainwindow.cam1.displayMode = displaymodeIndex
                        if self.ui.lineEdit2.text() == '':
                            # 如果没有输入摄像头的名称地址
                            mainwindow.cam1.nameAndLocation = 'Test Camera, Test Location'
                        else:
                            mainwindow.cam1.nameAndLocation = self.ui.lineEdit2.text()
                    else:
                        QMessageBox.about(self.ui, '错误', f'摄像头{self.textCamUrl}忙碌，不可以重复使用')

                else:
                    QMessageBox.about(self.ui, '错误', '窗口1忙碌，不可以添加视频流')

            if self.ui.comboBox.currentText() == 'win2':

                if self.ui.lineEdit.text() == '':
                    QMessageBox.about(self.ui, '错误', '请输入在文本框中输入内容')
                elif mainwindow.busy2 == False:
                    self.textCamUrl = self.ui.lineEdit.text()
                    print(type(self.textCamUrl))
                    if self.textCamUrl.isdigit():
                        self.textCamUrl = int(self.textCamUrl)
                        '''
                        如果不是视频格式 是摄像头的ID 则把他转换成int格式
                        '''
                        print(type(self.textCamUrl))

                        if self.textCamUrl == 0:

                            if systemLock != 0:
                                QMessageBox.about(self.ui, '错误', "集成摄像头被占用！")
                                return
                            elif systemLock == 0:
                                systemLock = 2
                                '''
                                这段代码是针对集成摄像头的占用检测，
                                集成摄像头涉及人脸录入
                                '''

                    else:
                        '''如果不是摄像头的ID
                        则什么都不做
                        '''
                        print(type(self.textCamUrl))
                        pass

                    if self.textCamUrl not in mainwindow.cameraList:
                        displaymodeIndex = self.ui.comboBox2.currentIndex()
                        mainwindow.start2(self.textCamUrl, displaymode=displaymodeIndex)
                        mainwindow.cam2.displayMode = displaymodeIndex
                        if self.ui.lineEdit2.text() == '':
                            # 如果没有输入摄像头的名称地址
                            mainwindow.cam2.nameAndLocation = 'Test Camera, Test Location'
                        else:
                            mainwindow.cam2.nameAndLocation = self.ui.lineEdit2.text()
                    else:
                        QMessageBox.about(self.ui, '错误', f'摄像头{self.textCamUrl}忙碌，不可以重复使用')

                else:
                    QMessageBox.about(self.ui, '错误', '窗口2忙碌，不可以添加视频流')

            if self.ui.comboBox.currentText() == 'win3':

                if self.ui.lineEdit.text() == '':
                    QMessageBox.about(self.ui, '错误', '请输入在文本框中输入内容')
                elif mainwindow.busy3 == False:
                    self.textCamUrl = self.ui.lineEdit.text()
                    print(type(self.textCamUrl))
                    if self.textCamUrl.isdigit():
                        self.textCamUrl = int(self.textCamUrl)
                        '''
                        如果不是视频格式 是摄像头的ID 则把他转换成int格式
                        '''
                        print(type(self.textCamUrl))

                        if self.textCamUrl == 0:

                            if systemLock != 0:
                                QMessageBox.about(self.ui, '错误', "集成摄像头被占用！")
                                return
                            elif systemLock == 0:
                                systemLock = 3
                                '''
                                这段代码是针对集成摄像头的占用检测，
                                集成摄像头涉及人脸录入
                                '''

                    else:
                        '''如果不是摄像头的ID
                        则什么都不做
                        '''
                        print(type(self.textCamUrl))
                        pass

                    if self.textCamUrl not in mainwindow.cameraList:
                        displaymodeIndex = self.ui.comboBox2.currentIndex()
                        mainwindow.start3(self.textCamUrl, displaymode=displaymodeIndex)
                        mainwindow.cam3.displayMode = displaymodeIndex
                        if self.ui.lineEdit2.text() == '':
                            # 如果没有输入摄像头的名称地址
                            mainwindow.cam3.nameAndLocation = 'Test Camera, Test Location'
                        else:
                            mainwindow.cam3.nameAndLocation = self.ui.lineEdit2.text()
                    else:
                        QMessageBox.about(self.ui, '错误', f'摄像头{self.textCamUrl}忙碌，不可以重复使用')

                else:
                    QMessageBox.about(self.ui, '错误', '窗口3忙碌，不可以添加视频流')

            if self.ui.comboBox.currentText() == 'win4':

                if self.ui.lineEdit.text() == '':
                    QMessageBox.about(self.ui, '错误', '请输入在文本框中输入内容')
                elif mainwindow.busy4 == False:
                    self.textCamUrl = self.ui.lineEdit.text()
                    print(type(self.textCamUrl))
                    if self.textCamUrl.isdigit():
                        self.textCamUrl = int(self.textCamUrl)
                        '''
                        如果不是视频格式 是摄像头的ID 则把他转换成int格式
                        '''
                        print(type(self.textCamUrl))

                        if self.textCamUrl == 0:

                            if systemLock != 0:
                                QMessageBox.about(self.ui, '错误', "集成摄像头被占用！")
                                return
                            elif systemLock == 0:
                                systemLock = 4
                                '''
                                这段代码是针对集成摄像头的占用检测，
                                集成摄像头涉及人脸录入
                                '''

                    else:
                        '''如果不是摄像头的ID
                        则什么都不做
                        '''
                        print(type(self.textCamUrl))
                        pass
                    if self.textCamUrl not in mainwindow.cameraList:
                        displaymodeIndex = self.ui.comboBox2.currentIndex()
                        mainwindow.start4(self.textCamUrl, displaymode=displaymodeIndex)
                        mainwindow.cam4.displayMode = displaymodeIndex
                        if self.ui.lineEdit2.text() == '':
                            # 如果没有输入摄像头的名称地址
                            mainwindow.cam4.nameAndLocation = 'Test Camera, Test Location'
                        else:
                            mainwindow.cam4.nameAndLocation = self.ui.lineEdit2.text()
                    else:
                        QMessageBox.about(self.ui, '错误', f'摄像头{self.textCamUrl}忙碌，不可以重复使用')

                else:
                    QMessageBox.about(self.ui, '错误', '窗口4忙碌，不可以添加视频流')

    def cancel(self):
        print('push the cancel button')


class DelWindow():
    def __init__(self):
        self.ui = QUiLoader().load(ui_path('Del.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)

    def ok(self):
        print('push the ok button')
        print(self.ui.comboBox.currentText())

        if self.ui.comboBox.currentText() == '':
            QMessageBox.about(self.ui, '错误', '请在组合选择框中选择试图关闭的窗口')

        else:
            if self.ui.comboBox.currentText() == 'win1':
                # print("我们将要关闭窗口1")
                mainwindow.close1()

            if self.ui.comboBox.currentText() == 'win2':
                mainwindow.close2()

            if self.ui.comboBox.currentText() == 'win3':
                mainwindow.close3()

            if self.ui.comboBox.currentText() == 'win4':
                mainwindow.close4()

    def cancel(self):
        print('push the cancel button')

class DelFaceWindow():

    def __init__(self):
        self.ui = QUiLoader().load(ui_path('DelFace.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)
        for i in range(1, totalUser+1):
            if i in userdic:
                self.ui.comboBox.addItem(userdic[i])

    def ok(self):
        global totalUser
        global faceSamples
        global idlists
        global userdic
        print('将要对选定的人脸进行删除')
        faceTodel = self.ui.comboBox.currentText()
        print(faceTodel)
        label_of_face = None
        for label, username in list(userdic.items()):
            if username == faceTodel:
                label_of_face = int(label)
                break
        if label_of_face is not None and label_of_face in userdic:
            userdic.pop(label_of_face)

        for candidate in [os.path.join('data', faceTodel), os.path.join('data', str(label_of_face))]:
            if candidate and os.path.isdir(candidate):
                shutil.rmtree(candidate)
        totalUser = max([int(i) for i in userdic.keys()], default=0)
        faceSamples, idlists = _rebuild_face_training_data()

        tag1, tag2, tag3, tag4 = False, False, False, False
        remeurl1, remeurl2, remeurl3, remeurl4 = '', '', '', ''
        remeplace1, remeplace2, remeplace3, remeplace4 = '', '', '', ''
        rememode1, rememode2, rememode3, rememode4 = '', '', '', ''
        if mainwindow.busy1 == True:
            tag1 = True
            remeurl1 = mainwindow.cam1.url
            remeplace1 = mainwindow.cam1.nameAndLocation
            rememode1 = mainwindow.cam1.displayMode
            mainwindow.close1()
            mainwindow.busy1 = False
            # 释放一号窗口 一号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
        if mainwindow.busy2 == True:
            tag2 = True
            remeurl2 = mainwindow.cam2.url
            remeplace2 = mainwindow.cam2.nameAndLocation
            rememode2 = mainwindow.cam2.displayMode
            mainwindow.close2()
            mainwindow.busy2 = False
            # 释放二号窗口 二号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
        if mainwindow.busy3 == True:
            tag3 = True
            remeurl3 = mainwindow.cam3.url
            remeplace3 = mainwindow.cam3.nameAndLocation
            rememode3 = mainwindow.cam3.displayMode
            mainwindow.close3()
            mainwindow.busy3 = False
            # 释放三号窗口 三号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
        if mainwindow.busy4 == True:
            tag4 = True
            remeurl4 = mainwindow.cam4.url
            remeplace4 = mainwindow.cam4.nameAndLocation
            rememode4 = mainwindow.cam4.displayMode
            mainwindow.close4()
            mainwindow.busy4 = False
            # 释放四号窗口 四号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
        try:
            if len(faceSamples) != len(idlists):
                QMessageBox.about(self.ui, '错误', f'训练数据异常：样本数={len(faceSamples)}，标签数={len(idlists)}')
                return
            yml = 'model' + '/' + 'model' + '.yml'
            if len(faceSamples) == 0:
                if os.path.exists(yml):
                    os.remove(yml)
            else:
                self.recog = cv2.face.LBPHFaceRecognizer_create()
                # 初始化人脸识别算法
                self.recog.train(faceSamples, np.array(idlists))
                self.recog.write(yml)
            _persist_user_training_config()
        finally:
            '''
                        下面的代码是以前关闭摄像头的重启操作
                        '''
            if tag1 == True:
                mainwindow.start1(remeurl1, remeplace1, rememode1)
            if tag2 == True:
                mainwindow.start2(remeurl2, remeplace2, rememode2)
            if tag3 == True:
                mainwindow.start3(remeurl3, remeplace3, rememode3)
            if tag4 == True:
                mainwindow.start4(remeurl4, remeplace4, rememode4)

    def cancel(self):
        print('push the cancel button')


class LuruWindow():

    def __init__(self):
        global systemLock
        self.ui = QUiLoader().load(ui_path('Luru.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
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

        if systemLock != 0:
            QMessageBox.about(self.ui, '警告', '集成相机被占用，即将解锁，监控将暂时中断，人脸录入结束后可自行恢复')
            if systemLock == 1:
                self.integratedNamePlace = mainwindow.cam1.nameAndLocation
                self.integratedDisplaymode = mainwindow.cam1.displayMode
                mainwindow.close1()
                systemLock = 1
                self.lurucam = Camera(0, self.ui.lurudisplay)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif systemLock == 2:
                self.integratedNamePlace = mainwindow.cam2.nameAndLocation
                self.integratedDisplaymode = mainwindow.cam2.displayMode
                mainwindow.close2()
                systemLock = 2
                self.lurucam = Camera(0, self.ui.lurudisplay)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif systemLock == 3:
                self.integratedNamePlace = mainwindow.cam3.nameAndLocation
                self.integratedDisplaymode = mainwindow.cam3.displayMode
                mainwindow.close3()
                systemLock = 3
                self.lurucam = Camera(0, self.ui.lurudisplay)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()
            elif systemLock == 4:
                self.integratedNamePlace = mainwindow.cam4.nameAndLocation
                self.integratedDisplaymode = mainwindow.cam4.displayMode
                mainwindow.close4()
                systemLock = 4
                self.lurucam = Camera(0, self.ui.lurudisplay)
                self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
                # self.luruThread.setDaemon(True)
                self.luruThread.start()

        if systemLock == 0:
            systemLock = 55
            self.lurucam = Camera(0, self.ui.lurudisplay)
            self.luruThread = threading.Thread(target=self.lurucam.displayLuruBrand, daemon=True)
            # self.luruThread.setDaemon(True)
            self.luruThread.start()

    def delFace(self):
        self.delfacewin = DelFaceWindow()
        self.delfacewin.ui.show()

    def delAll(self):
        self.resetwin = ResetWindow()
        self.resetwin.ui.show()

    def trainModel(self):
        global totalUser
        global userdic
        global faceSamples
        global idlists

        print('训练模型按钮已经按下')
        tag1, tag2, tag3, tag4 = False, False, False, False
        remeurl1, remeurl2, remeurl3, remeurl4 = '', '', '', ''
        remeplace1, remeplace2, remeplace3, remeplace4 = '', '', '', ''
        rememode1, rememode2, rememode3, rememode4 = '', '', '', ''
        username = self.ui.lineEdit.text().strip()

        if username == '':
            QMessageBox.about(self.ui, '错误', '你还没有输入姓名')
        elif not os.path.exists('data/' + username):
            QMessageBox.about(self.ui, '错误', '该用户不存在或未进行录入')
        else:
            existing_id = None
            for label, saved_name in userdic.items():
                if saved_name == username:
                    existing_id = int(label)
                    break
            if existing_id is None:
                next_id = max([int(i) for i in userdic.keys()], default=0) + 1
                userdic[next_id] = username
                totalUser = max(totalUser, next_id)

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
            if mainwindow.busy1 == True:
                tag1 = True
                remeurl1 = mainwindow.cam1.url
                remeplace1 = mainwindow.cam1.nameAndLocation
                rememode1 = mainwindow.cam1.displayMode
                mainwindow.close1()
                mainwindow.busy1 = False
                # 释放一号窗口 一号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
            if mainwindow.busy2 == True:
                tag2 = True
                remeurl2 = mainwindow.cam2.url
                remeplace2 = mainwindow.cam2.nameAndLocation
                rememode2 = mainwindow.cam2.displayMode
                mainwindow.close2()
                mainwindow.busy2 = False
                # 释放二号窗口 二号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
            if mainwindow.busy3 == True:
                tag3 = True
                remeurl3 = mainwindow.cam3.url
                remeplace3 = mainwindow.cam3.nameAndLocation
                rememode3 = mainwindow.cam3.displayMode
                mainwindow.close3()
                mainwindow.busy3 = False
                # 释放三号窗口 三号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作
            if mainwindow.busy4 == True:
                tag4 = True
                remeurl4 = mainwindow.cam4.url
                remeplace4 = mainwindow.cam4.nameAndLocation
                rememode4 = mainwindow.cam4.displayMode
                mainwindow.close4()
                mainwindow.busy4 = False
                # 释放四号窗口 四号相机 设置为空闲 并保存了它的URL和名称地址、显示模式 以便后续重启操作

            try:
                faceSamples, idlists = _rebuild_face_training_data()
                if len(faceSamples) == 0:
                    QMessageBox.about(self.ui, '错误', '未检测到有效人脸样本，请重新拍摄后再训练。')
                    return
                if len(faceSamples) != len(idlists):
                    QMessageBox.about(self.ui, '错误', f'训练数据异常：样本数={len(faceSamples)}，标签数={len(idlists)}')
                    return

                self.recog = cv2.face.LBPHFaceRecognizer_create()
                self.recog.train(faceSamples, np.array(idlists))
                yml = 'model' + '/' + 'model' + '.yml'
                self.recog.write(yml)
                totalUser = max([int(i) for i in userdic.keys()], default=0)
                _persist_user_training_config()
            finally:
                '''
                下面的代码是以前关闭摄像头的重启操作
                '''
                if tag1 == True:
                    mainwindow.start1(remeurl1, remeplace1, rememode1)
                if tag2 == True:
                    mainwindow.start2(remeurl2, remeplace2, rememode2)
                if tag3 == True:
                    mainwindow.start3(remeurl3, remeplace3, rememode3)
                if tag4 == True:
                    mainwindow.start4(remeurl4, remeplace4, rememode4)

    def closeQuit(self):
        if hasattr(self, 'lurucam') and self.lurucam is not None:
            self.lurucam.close()
        if hasattr(self, 'lurucamReal') and self.lurucamReal is not None:
            self.lurucamReal.close()
        self._restore_integrated_camera()
        self.ui.close()

    def _restore_integrated_camera(self):
        global systemLock
        if self._restore_done:
            return
        self._restore_done = True
        if systemLock == 1 and mainwindow.busy1 == False:
            mainwindow.start1(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif systemLock == 2 and mainwindow.busy2 == False:
            mainwindow.start2(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif systemLock == 3 and mainwindow.busy3 == False:
            mainwindow.start3(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif systemLock == 4 and mainwindow.busy4 == False:
            mainwindow.start4(0, self.integratedNamePlace, self.integratedDisplaymode)
        elif systemLock == 55:
            systemLock = 0

    def getNewface(self):
        print('正在从摄像头录入新的人脸信息\n' * 3)
        self.sampleNum = 0  # 已经获取的样本数量
        self.maxSampleNum = 10

        self.lurucam.cap.release()
        self.ui.lurudisplay.setPixmap(QPixmap(asset_path('nosignal.png')))

        self.lurucamReal = Camera(0, self.ui.lurudisplay)
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
                cv2.imwrite('data' + '/' + self.filepath + '/' + str(self.sampleNum) + '.jpg', frame)

            rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
            self.lurucamReal._emit_frame(rawframe)
            cv2.waitKey(10)

        if hasattr(self, 'lurucamReal') and self.lurucamReal is not None:
            self.lurucamReal.close()
            self.lurucamReal._emit_no_signal()
        self.sampleNum = 0
        self._restore_integrated_camera()

    def snap(self):
        global systemLock
        if self.ui.lineEdit.text() == '':
            QMessageBox.about(self.ui, '错误', '你还没有输入姓名')
        else:
            self.filepath = self.ui.lineEdit.text()
            # 这里需要添加“文件中是否有重复人员的校验操作”
            print("拍照按钮按下 用户应该保证拍摄效果 \n" * 5)
            if not os.path.exists('data' + '/' + self.filepath):
                os.mkdir('data' + '/' + self.filepath)
            else:
                shutil.rmtree('data' + '/' + self.filepath)
                os.mkdir('data' + '/' + self.filepath)
                # 存在用户姓名目录就清空，不存在就创建，确保最后存在空的data目录

            self.getNewface()


class ResetWindow():

    def __init__(self):
        self.ui = QUiLoader().load(ui_path('ResetQ.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.buttonBox.accepted.connect(self.yes)
        self.ui.buttonBox.accepted.connect(self.no)

    def yes(self):
        global totalUser
        global userdic
        global idlists
        global faceSamples
        userdic = {}
        totalUser = 0
        idlists = []
        faceSamples = []

        print('重置按钮已经按下，会清空人脸样本、模型和配置')
        data_dir = 'data'
        if os.path.isdir(data_dir):
            for entry in os.listdir(data_dir):
                entry_path = os.path.join(data_dir, entry)
                if os.path.isdir(entry_path):
                    shutil.rmtree(entry_path, ignore_errors=True)
                elif os.path.isfile(entry_path):
                    # 仅清理常见样本文件，保留 data 目录下的代码文件
                    ext = os.path.splitext(entry)[1].lower()
                    if ext in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
                        try:
                            os.remove(entry_path)
                        except OSError:
                            pass
        else:
            os.mkdir(data_dir)
        shutil.rmtree('model')
        os.mkdir('model')
        print('totalUser:', totalUser)

        # 以下代码是对config文件夹下的文件的操作
        f = open('config/idlists.txt', 'w')
        f.write('')
        f.close()

        f = open('config/totalUser.txt', 'w')
        f.write('0')
        f.close()

        f = open('config/userdic.txt', 'w')
        f.write('')
        f.close()


    def no(self):
        print('重置操作没有被确认，重置操作被取消')

class LogWindow():
    def __init__(self):
        self.ui = QUiLoader().load(ui_path('Log.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget.setColumnCount(6)
        self.ui.tableWidget.setHorizontalHeaderLabels(['姓名', '地点', '时间', '情绪', '考勤类型', '状态'])
        self._install_extra_filters()
        self.ui.pushButton.clicked.connect(self.inquiryDB)
        self.ui.pushButton2.clicked.connect(self.clearDB)

        # 将两个时间编辑框中的时间选定为当下的时间 方便用户进行调整
        nowdatetime = str(datetime.datetime.now()).split('.')[0]
        nowdatetime = datetime.datetime.strptime(nowdatetime, '%Y-%m-%d %H:%M:%S')
        print('datetimeEdit的时间为',nowdatetime,'类型为',type(nowdatetime))
        self.ui.dateTimeEdit1.setDateTime(nowdatetime)
        self.ui.dateTimeEdit2.setDateTime(nowdatetime)

        self.sqlofLog = sqls.SqlF()
        # 从sqls模块中创建一个SqlF()对象

        # 给姓名多选框添加数据
        allname = self.sqlofLog.getAllname()  # sql返回的是一个tuple
        # print('allname:',allname)
        for i in allname:
            self.ui.comboBox2.addItem(i[0])
        # 给地点多选框添加数据
        allplace = self.sqlofLog.getAllplace() # sql返回的是一个tuple
        # print('allplace', allplace)
        for i in allplace:
            self.ui.comboBox.addItem(i[0])
        self.comboAttendanceType.addItems(['任何类型', '上班打卡', '下班打卡', '外出登记', '重复识别', '未识别'])
        self.comboStatus.addItems(['任何状态', '正常', '迟到', '早退', '缺勤', '已记录', '异常'])

        default_start = nowdatetime - datetime.timedelta(days=30)
        default_end = nowdatetime
        results = self.sqlofLog.query_logs_with_emotion(
            name=None,
            location=None,
            start_time=default_start,
            end_time=default_end,
            attendance_type=None,
            status=None,
        )
        self._fill_table(results)

    def clearDB(self):
        # 以下代码是对于数据库的操作
        self.sqlofLog.resetDB()
        # 下面是tableWidget刷新操作
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
                self.ui.tableWidget.setItem(row_count, col, QTableWidgetItem(str(values[col] if values[col] is not None else '')))

    def _install_extra_filters(self):
        grid = self.ui.layoutWidget.layout()
        self.labelAttendanceType = QLabel('考勤类型：', self.ui.layoutWidget)
        self.labelAttendanceType.setFont(DEFAULT_UI_FONT)
        self.comboAttendanceType = QComboBox(self.ui.layoutWidget)
        self.comboAttendanceType.setFont(DEFAULT_UI_FONT)
        self.labelStatus = QLabel('状态：', self.ui.layoutWidget)
        self.labelStatus.setFont(DEFAULT_UI_FONT)
        self.comboStatus = QComboBox(self.ui.layoutWidget)
        self.comboStatus.setFont(DEFAULT_UI_FONT)
        self.btnAbsence = QPushButton('当日缺勤', self.ui.layoutWidget)
        self.btnAbsence.setFont(DEFAULT_UI_FONT)
        self.btnSummary = QPushButton('考勤汇总', self.ui.layoutWidget)
        self.btnSummary.setFont(DEFAULT_UI_FONT)
        self.btnExport = QPushButton('导出报表', self.ui.layoutWidget)
        self.btnExport.setFont(DEFAULT_UI_FONT)
        self.btnAbsence.clicked.connect(self.showAbsenceList)
        self.btnSummary.clicked.connect(self.showAttendanceSummary)
        self.btnExport.clicked.connect(self.exportAttendanceReport)
        # Place to the right side of existing filters, no .ui redesign required.
        grid.addWidget(self.labelAttendanceType, 1, 8)
        grid.addWidget(self.comboAttendanceType, 2, 8)
        grid.addWidget(self.labelStatus, 1, 9)
        grid.addWidget(self.comboStatus, 2, 9)
        grid.addWidget(self.btnAbsence, 1, 10)
        grid.addWidget(self.btnSummary, 2, 10)
        grid.addWidget(self.btnExport, 1, 11, 2, 1)

    def showAbsenceList(self):
        target_day = self.ui.dateTimeEdit1.dateTime().toString("yyyy-MM-dd")
        day = datetime.datetime.strptime(target_day, '%Y-%m-%d').date()
        expected_names = sorted(list(set(userdic.values())))
        if not expected_names:
            QMessageBox.about(self.ui, '缺勤名单', '当前没有已登记的人脸用户。')
            return
        absences = self.sqlofLog.getAbsenceList(expected_names, day=day)
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
        summary = self.sqlofLog.getAttendanceSummary(start_dt, end_dt)
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
        starttime = self.ui.dateTimeEdit1.dateTime()
        starttime = starttime.toString("yyyy-MM-dd hh:mm:ss") # 现在是string格式
        starttime = datetime.datetime.strptime(starttime,'%Y-%m-%d %H:%M:%S') #转为datetime格式
        endtime = self.ui.dateTimeEdit2.dateTime()
        endtime = endtime.toString("yyyy-MM-dd hh:mm:ss") # 现在是string格式
        endtime = datetime.datetime.strptime(endtime,'%Y-%m-%d %H:%M:%S') #转为datetime格式
        # print('starttime', starttime)
        # print('endtime', endtime)

        results = self.sqlofLog.query_logs_with_emotion(
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

        ok, count = self.sqlofLog.exportAttendanceReport(
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


class Camera:
    '''摄像头对象'''

    def __init__(self, url, outLabel):
        self.nameAndLocation = 'Test Video, No Location' # 记录摄像头的名称和地址
        self.displayMode = 0 # 记录摄像头的显示模式
        self.url = url
        self.outLabel = outLabel
        self._bridge = _LabelBridge(outLabel)
        self._running = True
        self.cap = cv2.VideoCapture(self.url)
        self.detector = cv2.CascadeClassifier(asset_path('haarcascade_frontalface_default.xml'))
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._pil_font = self._load_pil_font(28)
        self.emotion = None
        try:
            # The model file may be missing, or TensorFlow may be unavailable.
            # In that case we gracefully fall back to "中性".
            self.emotion = EmotionRecognitionService()
        except Exception as exc:
            print('情绪识别服务不可用，已回退为中性：', exc)

    @staticmethod
    def _load_pil_font(size=28):
        # Prefer common Chinese fonts on Windows, then generic fallbacks.
        candidates = [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
        ]
        for path in candidates:
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _draw_text(self, frame_bgr, text, org, color=(0, 0, 255), font_scale=0.8, thickness=2):
        text = str(text)
        if text == '':
            return frame_bgr
        # ASCII-only text can stay on fast OpenCV renderer.
        if all(ord(ch) < 128 for ch in text) or self._pil_font is None:
            cv2.putText(frame_bgr, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
            return frame_bgr

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil_img)
        # OpenCV color is BGR; PIL expects RGB.
        rgb_color = (int(color[2]), int(color[1]), int(color[0]))
        draw.text((int(org[0]), int(org[1]) - 24), text, fill=rgb_color, font=self._pil_font)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _emit_frame(self, rgb_frame):
        img = QImage(
            rgb_frame.data,
            rgb_frame.shape[1],
            rgb_frame.shape[0],
            rgb_frame.shape[1] * 3,
            QImage.Format_RGB888,
        )
        self._bridge.pixmap_ready.emit(QPixmap.fromImage(img))

    def _emit_no_signal(self):
        self._bridge.pixmap_ready.emit(QPixmap(asset_path('nosignal.png')))

    def display(self):
        sqlofDisplay = sqls.SqlF()
        faceMaxNum = 5 # 人脸重复出现的上限为5 连续5次识别为某个人 则该人员需要留下记录
        facecountDic = {} # 用来记录人脸重复的次数
        faceList = [] # 保存当前帧的人脸数据
        tempfaceList = [] # 人脸存储列表，保存上一帧的人的姓名
        emotion_state = {} # 按姓名做轻量情绪防抖，减少画面文字抖动
        debug_recognition = os.getenv('FACE_RECO_DEBUG', '0') == '1'

        if os.path.exists('model/model.yml'):  # 表示为已经录入过人脸了，可以进行人脸识别操作了
            yml = 'model' + '/' + 'model.yml'
            self.recognizer.read(yml)
        '''
        yml文件比较大，避免反复的读取操作是必须的
        '''
        while self._running and self.cap.isOpened():
            while self._running:
                success, frame = self.cap.read()
                if not self._running:
                    break
                if success:
                    frame_people = []
                    rawframe = cv2.resize(frame, (640, 360))
                    # cv2.imshow('raw', frame)
                    frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
                    # cv2.imshow('raw2', frame)
                    self.faces = self.detector.detectMultiScale(frame, 1.3, 5)
                    rawframe = self._draw_text(
                        rawframe,
                        self.nameAndLocation,
                        (7, 20),
                        color=(0, 0, 255),
                        font_scale=0.6,
                        thickness=2,
                    )
                    # 其中gray为要检测的灰度图像，1.3(scaleFactor)为每次图像尺寸减小的比例，5为minNeighbors
                    #  框选人脸，for循环保证一个能检测的实时动态视频流
                    # for (x, y, w, h) in self.faces:
                    #     # xy为左上角的坐标,w为宽，h为高，用rectangle为人脸标记画框
                    #     cv2.rectangle(frame, (x, y), (x + w, y + w), (255, 0, 0), thickness=2)
                    # 框选人脸，for循环保证一个能检测的实时动态视频流
                    for (x, y, w, h) in self.faces:
                        # xy为左上角的坐标,w为宽，h为高，用rectangle为人脸标记画框
                        cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)

                        if os.path.exists('model/model.yml'):  # 表示为已经录入过人脸了，可以进行人脸识别操作了
                            # yml = 'model' + '/' + 'model.yml'
                            # self.recognizer.read(yml)
                            idum, confidence = self.recognizer.predict(frame[y:y + h, x:x + w])
                            if debug_recognition:
                                print('idum为', idum)
                                print('confidence；', confidence)
                            if confidence < 68:
                                name = userdic.get(idum, str(idum))
                                face_gray = frame[y:y + h, x:x + w]
                                raw_emotion = '中性'
                                if self.emotion is not None:
                                    try:
                                        raw_emotion, _ = self.emotion.predict(face_gray)
                                    except Exception:
                                        raw_emotion = '中性'
                                state = emotion_state.get(name, {'last_raw': '', 'stable': raw_emotion, 'count': 0})
                                if raw_emotion == state['last_raw']:
                                    state['count'] += 1
                                else:
                                    state['last_raw'] = raw_emotion
                                    state['count'] = 1
                                if state['count'] >= 2:
                                    state['stable'] = raw_emotion
                                emotion_state[name] = state
                                emotion_text = state['stable']
                                rawframe = self._draw_text(
                                    rawframe,
                                    f'{name} | {emotion_text}',
                                    (x + 5, y + 15),
                                    color=(0, 0, 255),
                                    font_scale=1,
                                    thickness=2,
                                )
                                frame_people.append(f'{name}({emotion_text})')
                                # 人脸计数代码区--------
                                faceList.append((name, emotion_text))
                                if (name, emotion_text) not in tempfaceList:
                                    facecountDic[(name, emotion_text)] = 1
                                else:
                                    facecountDic[(name, emotion_text)] += 1
                                # 人脸计数代码区--------

                            else:
                                rawframe = self._draw_text(
                                    rawframe,
                                    'unknown',
                                    (x + 5, y + 15),
                                    color=(0, 0, 255),
                                    font_scale=1,
                                    thickness=2,
                                )

                    if frame_people:
                        unique_people = []
                        seen = set()
                        for item in frame_people:
                            if item not in seen:
                                unique_people.append(item)
                                seen.add(item)
                        summary_text = '当前帧识别: ' + ', '.join(unique_people[:3])
                        if len(unique_people) > 3:
                            summary_text += f' ... 共{len(unique_people)}人'
                        rawframe = self._draw_text(
                            rawframe,
                            summary_text,
                            (7, 45),
                            color=(0, 0, 255),
                            font_scale=0.6,
                            thickness=2,
                        )

                    rawframe = cv2.cvtColor(rawframe,cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)

                    # 人脸计数代码区--------
                    for (name, emotion_text), count in facecountDic.items():
                        if count >= faceMaxNum:
                            # 如果出现次数超过faceMaxNum
                            nowdatetime = str(datetime.datetime.now()).split('.')[0]
                            nowdatetime = datetime.datetime.strptime(nowdatetime, '%Y-%m-%d %H:%M:%S')
                            sqlofDisplay.saveNameTimePic(
                                name,
                                self.nameAndLocation,
                                nowdatetime,
                                emotion=emotion_text,
                            )
                            facecountDic[(name, emotion_text)] = 0 # 归零操作
                    tempfaceList = faceList # 当前帧变为上一帧
                    faceList = [] # 当前帧置零等待接收
                    # 人脸计数代码区--------

                    cv2.waitKey(10)
                else:
                    self.cap.release()
                    self._emit_no_signal()
                    print('released!')
                    break
            if not self._running:
                break

    def displaySimpleBrand(self):
        '''
        只进行人脸检测的版本
        '''
        while self._running and self.cap.isOpened():
            while self._running:
                success, frame = self.cap.read()
                if not self._running:
                    break
                if success:
                    rawframe = cv2.resize(frame, (640, 360))
                    # cv2.imshow('raw', frame)
                    frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
                    # cv2.imshow('raw2', frame)
                    faces = self.detector.detectMultiScale(frame, 1.3, 5)
                    # 其中gray为要检测的灰度图像，1.3为每次图像尺寸减小的比例，5为minNeighbors
                    rawframe = self._draw_text(
                        rawframe,
                        self.nameAndLocation,
                        (7, 20),
                        color=(0, 0, 255),
                        font_scale=0.6,
                        thickness=2,
                    )

                    # 框选人脸，for循环保证一个能检测的实时动态视频流
                    for (x, y, w, h) in faces:
                        # xy为左上角的坐标,w为宽，h为高，用rectangle为人脸标记画框
                        cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)

                    rawframe = cv2.cvtColor(rawframe,cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)
                    cv2.waitKey(10)
                else:
                    self.cap.release()
                    self._emit_no_signal()
                    print('released!')
                    break
            if not self._running:
                break

    def displayJustdisplayBrand(self):
        '''
        displayJustdisplayBrand是只进行播放视频帧的版本 没有人脸检测和人脸识别
        '''
        while self._running and self.cap.isOpened():
            while self._running:
                success, frame = self.cap.read()
                if not self._running:
                    break
                if success:
                    rawframe = cv2.resize(frame, (640, 360))
                    rawframe = self._draw_text(
                        rawframe,
                        self.nameAndLocation,
                        (7, 20),
                        color=(0, 0, 255),
                        font_scale=0.6,
                        thickness=2,
                    )
                    rawframe = cv2.cvtColor(rawframe,cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)
                    cv2.waitKey(10)
                else:
                    self.cap.release()
                    self._emit_no_signal()
                    print('released!')
                    break
            if not self._running:
                break

    def displayLuruBrand(self):
        '''
        displayLuruBrand是Camera对象针对录入界面的定制版本，没有实时的人脸识别以及
        识别文字表示功能，更符合录入界面的应用场景需要
        '''
        while self._running and self.cap.isOpened():
            while self._running:
                success, frame = self.cap.read()
                if not self._running:
                    break
                if success:
                    rawframe = cv2.resize(frame, (640, 360))
                    # cv2.imshow('raw', frame)
                    frame = cv2.cvtColor(rawframe, cv2.COLOR_BGR2GRAY)
                    # cv2.imshow('raw2', frame)
                    faces = self.detector.detectMultiScale(frame, 1.3, 5)
                    # 其中gray为要检测的灰度图像，1.3为每次图像尺寸减小的比例，5为minNeighbors
                    rawframe = self._draw_text(
                        rawframe,
                        'enroll in facial recognition',
                        (7, 20),
                        color=(0, 0, 255),
                        font_scale=0.6,
                        thickness=2,
                    )

                    # 框选人脸，for循环保证一个能检测的实时动态视频流
                    for (x, y, w, h) in faces:
                        # xy为左上角的坐标,w为宽，h为高，用rectangle为人脸标记画框
                        cv2.rectangle(rawframe, (x, y), (x + w, y + h), (0, 0, 255), thickness=2)

                    rawframe = cv2.cvtColor(rawframe, cv2.COLOR_BGR2RGB)
                    if not self._running:
                        break
                    self._emit_frame(rawframe)
                    cv2.waitKey(10)
                else:
                    self.cap.release()
                    self._emit_no_signal()
                    print('released!')
                    break
            if not self._running:
                break

    def close(self):
        global systemLock
        self._running = False
        if self.url == 0:
            systemLock = 0  # 解锁
        if self.cap is not None:
            self.cap.release()
        # Ensure the last frame cannot remain visible after stream shutdown.
        self._emit_no_signal()


class LogInWindow():
    def __init__(self):
        self.ui = QUiLoader().load(ui_path('LogIn.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.setFixedSize(self.ui.width(), self.ui.height())
        self.ui.label.setPixmap(QPixmap(asset_path('welcome.png')))
        self.ui.pushButton1.clicked.connect(self.loginfunction)
        self.ui.pushButton2.clicked.connect(self.registerfunction)
        self.StartSignal = False
        self.sqloflogin = sqls.SqlF()

    def loginfunction(self):
        print('登录按钮已经按下')
        self.sqloflogin.dbclose()
        self.sqloflogin.__init__()
        self.accountlist = [i[0] for i in self.sqloflogin.getAllaccount()]

        account = self.ui.lineEdit1.text().strip()
        password = self.ui.lineEdit2.text()

        if account == '':
            QMessageBox.about(self.ui, '错误', '您还没有输入账号')
        elif password == '':
            QMessageBox.about(self.ui, '错误', '您还没有输入密码')
        elif account in self.accountlist:
            if self.sqloflogin.verify_login(account, password):
                QMessageBox.about(self.ui, '登录成功', '欢迎使用！')
                self.StartSignal = True
                print(self.StartSignal)
                self.ui.close()
            else:
                QMessageBox.about(self.ui, '错误', '账号或密码错误！')
        else:
            print(self.sqloflogin.getAllaccount())
            QMessageBox.about(self.ui, '错误', '账号或密码错误！')

    def registerfunction(self):
        print('注册按钮已经按下')
        self.registerwin = RegisterWindow()
        self.registerwin.ui.show()


class RegisterWindow():
    def __init__(self):
        self.ui = QUiLoader().load(ui_path('Register.ui'))
        self.ui.setFont(DEFAULT_UI_FONT)
        self.ui.setStyleSheet(APP_STYLESHEET)
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)
        self.sqlofregister = sqls.SqlF()
    def ok(self):
        accountlist = [i[0] for i in self.sqlofregister.getAllaccount()]
        newaccount = self.ui.lineEdit1.text().strip()
        newpassword = self.ui.lineEdit2.text()
        adminpassword = self.ui.lineEdit3.text()

        if newaccount in accountlist:
            QMessageBox.about(self.ui, '错误', '该账户已经存在！')
            return

        if newpassword == '':
            QMessageBox.about(self.ui, '错误', '密码不能为空！')
            return

        if not self.sqlofregister.verify_login('admin', adminpassword):
            QMessageBox.about(self.ui, '错误', '超级管理员密码错误！')
            return

        if self.sqlofregister.register(newaccount, newpassword):
            QMessageBox.about(self.ui, '欢迎', '新用户注册成功，请记好账号密码！')
            if hasattr(start_login, 'accountlist'):
                start_login.accountlist.append(newaccount)
        else:
            QMessageBox.about(self.ui, '错误', '注册失败，请稍后重试！')

    def cancel(self):
        print('取消注册新用户')


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
start_login = LogInWindow()
start_login.ui.show()
app.exec_()

if start_login.StartSignal == True:
    mainwindow = MWindow()
    app.aboutToQuit.connect(_shutdown_mainwindow)
    mainwindow.mui.show()
    app.exec_()

# 临时入口用于调试
# app = QApplication([])
# mainwindow = MWindow()
# mainwindow.mui.show()
# app.exec_()


