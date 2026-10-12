import os
import traceback

import importlib

from pathlib import Path
from qgis.PyQt.QtWidgets import QVBoxLayout

from qgis.core import (QgsProject, QgsMapLayer, QgsVectorLayer,
                       QgsLayoutSize, QgsLayoutItemPage,
                       QgsLayoutItemLabel, QgsLayoutItemPicture,
                       QgsCoordinateReferenceSystem, QgsGeometry,
                       QgsApplication, Qgis, QgsLayoutExporter)

from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (QMainWindow, QWidget, QSizePolicy, QApplication, QListWidgetItem,
                                 QCheckBox, QFileDialog, QMessageBox, QToolButton, QLabel)


from typing import List, Union

from ...submodules.base.ui.base_class import UiModuleBase

FORM_CLASS, _ = UiModuleBase.get_uic_classes(__file__)

### Settings
IMAGE_DPI = 96
MAX_SCALE_IN_FACTOR= 3.5
MAX_SCALE_OUT_FACTOR= 0.25
ZOOM_FACTOR = 1.2

BACKGROUND_COLOR = "#f0f0f0"
BORDER_COLOR = "#ababab"
###

class Preview(UiModuleBase, FORM_CLASS, QMainWindow):
    """ Preview Window
    """
    def __init__(self, **kwargs: dict):
    
        UiModuleBase.__init__(self, **kwargs)
        QMainWindow.__init__(self, None, Qt.Window)
        self._parent = kwargs.get('parent', None)
        self.setupUi(self)
        #self.scrollAreaWidgetContents
        self.scale = 1
        self.page_label_array = []
        self.pixmap_array = []

        #connect slots
        self.zoom_in_action.triggered.connect(self.zoom_in)
        self.zoom_out_action.triggered.connect(self.zoom_out)
        self.zoom_percent_action.triggered.connect(self.zoom_reset)

        #center toolbar
        self.left_spacer = QWidget()
        self.right_spacer = QWidget()
        self.left_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.right_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
  

        self.toolBar.clear()

        self.toolBar.addWidget(self.left_spacer)
        
        self.toolBar.addAction(self.zoom_out_action)
        self.toolBar.addAction(self.zoom_percent_action)
        self.toolBar.addAction(self.zoom_in_action)
        
        self.toolBar.addWidget(self.right_spacer)   

        #window Settings
        self.setWindowTitle("Preview")
        self.resize(1178, 849) 

        #mouse shortcut (zoom in/out)
        self.scrollArea.installEventFilter(self)
        self.scrollAreaWidgetContents.installEventFilter(self)


    def show_preview(self, qgis_layout):

        scroll_widget = self.scrollAreaWidgetContents
        scroll_layout = scroll_widget.layout()

        # If no layout was set in Qt Designer, create one else clear existing
        if scroll_layout is None:
            scroll_layout = QVBoxLayout(scroll_widget)
            scroll_widget.setLayout(scroll_layout)
        else:
            while scroll_layout.count():
                child = scroll_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        exporter = QgsLayoutExporter(qgis_layout)
        pages = qgis_layout.pageCollection()
        
        self.page_label_array = []
        self.pixmap_array = []

        for page_number in range(pages.pageCount()):

            image = exporter.renderPageToImage(page_number, QSize(), IMAGE_DPI)
            pixmap = QPixmap.fromImage(image)

            page_label = QLabel()
            page_label.setPixmap(pixmap)

            page_label.setStyleSheet(f"border: 1px solid {BORDER_COLOR}; margin-bottom: 15px; background-color: {BACKGROUND_COLOR};")

            scroll_layout.addWidget(page_label, alignment=Qt.AlignCenter)

            self.page_label_array.append(page_label)
            self.pixmap_array.append(pixmap)

        self.show()

    def closeEvent(self, event) -> None:
        """ Destroy window """
        self.unload(self_unload=True)
        event.accept()
        self._parent.preview = None

    def unload(self, self_unload):
        super().unload(self_unload)

    def zoom_in(self, factor=2):
        # self.scale *= ZOOM_FACTOR
        self.scale = round(self.scale * ZOOM_FACTOR, 1)
        if self.scale > MAX_SCALE_IN_FACTOR:
            self.scale = MAX_SCALE_IN_FACTOR
        self.update_pixmap()

    def zoom_out(self, factor=2):
        # self.scale /= ZOOM_FACTOR
        self.scale = round(self.scale / ZOOM_FACTOR, 1)
        if self.scale < MAX_SCALE_OUT_FACTOR:
            self.scale = MAX_SCALE_OUT_FACTOR
        self.update_pixmap()

    def zoom_reset(self):
            print("Reset Zoom")
            self.scale = 1
            self.update_pixmap()

    def update_pixmap(self):
        for page_label, pixmap in zip(self.page_label_array, self.pixmap_array):
            size = pixmap.size()
            scaled_pixmap = pixmap.scaled(self.scale * size)
            page_label.setPixmap(scaled_pixmap)
        percent_scale = int(round(100* self.scale, 0))
        self.zoom_percent_action.setText(f"{percent_scale}%")

    #Shortcuts
    def eventFilter(self, source, event) -> bool:
        if event.type() == event.Type.Wheel:
            # check for ctl key
            if event.modifiers() == Qt.ControlModifier:
                # event.angleDelta().y() -> + int fo up / -int for down
                if event.angleDelta().y() > 0:
                    self.zoom_in()
                elif event.angleDelta().y() < 0:
                    self.zoom_out()
                
                return True
        return super().eventFilter(source, event)
