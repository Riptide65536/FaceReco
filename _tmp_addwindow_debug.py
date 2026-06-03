# -*- coding: utf-8 -*-
import traceback
from PySide2.QtWidgets import QApplication, QMessageBox
from PySide2.QtGui import QFont
from app.ui import monitor_windows
from app.ui.monitor_windows import AddWindow, configure

QMessageBox.about = staticmethod(lambda parent, title, text: print('MSGBOX:', title, text))

class FakeMainWindow:
    def __init__(self):
        self._camera_source_items = [
            {'label': 'Integrated Camera (cam 0)', 'value': '0'},
            {'label': 'OBS Virtual Camera (cam 1)', 'value': '1'},
        ]
        self.cameraList = []
        self.busy1 = self.busy2 = self.busy3 = self.busy4 = False
    def _discover_camera_sources(self):
        return list(self._camera_source_items)
    def _configure_source_combo(self, combo, items, select_first_camera=False):
        return monitor_windows.MWindow._configure_source_combo(self, combo, items, select_first_camera=select_first_camera)
    def _parse_source_input(self, raw_value):
        return monitor_windows.MWindow._parse_source_input(raw_value)
    def _extract_source_combo_value(self, combo):
        return monitor_windows.MWindow._extract_source_combo_value(combo)
    def start_slot(self, slot, url, cameraNamePlace='', displaymode=0, allow_duplicate_source=False):
        print('start_slot called:', slot, repr(url), repr(cameraNamePlace), displaymode)
        return True

try:
    app = QApplication.instance() or QApplication([])
    configure(None, QFont('Microsoft YaHei UI', 10), '')
    fake = FakeMainWindow()
    aw = AddWindow(fake)
    aw.ui.comboBox.setCurrentText('win1')
    aw.ui.lineEdit2.setText('0')
    source = aw.ui.comboBoxSource
    print('count=', source.count())
    for i in range(source.count()):
        print('item', i, repr(source.itemText(i)), repr(source.itemData(i)))
    print('before:', source.currentIndex(), repr(source.currentText()), repr(source.lineEdit().text()), repr(fake._extract_source_combo_value(source)))
    source.setCurrentIndex(1)
    print('after setCurrentIndex(1):', source.currentIndex(), repr(source.currentText()), repr(source.lineEdit().text()), repr(fake._extract_source_combo_value(source)))
    aw.ok()
    print('done')
except Exception:
    traceback.print_exc()
    raise
