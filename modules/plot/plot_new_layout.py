# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only

import os

from datetime import datetime
import traceback

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsApplication
from qgis.gui import QgsFileWidget

from ...submodules.base.constants import STYLE_SHEET_ERROR
from ...submodules.base.qgis.plot_layer import PlotLayer
from ...submodules.base.qgis.plot_layout import PlotLayout
from ...submodules.base.ui.base_class import UiModuleBase
from ...submodules.base.ui.functions import set_label_status

FORM_CLASS, _ = UiModuleBase.get_uic_classes(__file__)


class PlotNewLayout(UiModuleBase, FORM_CLASS, QMainWindow):
    """ Creates new plot layout
    """

    def __init__(self, **kwargs: dict):

        UiModuleBase.__init__(self, **kwargs)
        QMainWindow.__init__(self, kwargs.get('parent', None))

        self.setupUi(self)
        self.replace_widget_with_class(self.FileEdit, QgsFileWidget)

        self.show()

        # Qt Connection
        self.connect(self.But_Cancel.clicked, self.close)
        self.connect(self.But_Create.clicked, self.create_new_layout)
        self.connect(self.CheckBox_Temporary.stateChanged, self.temporary_state_changed)

        self.temporary_state_changed(self.CheckBox_Temporary.checkState())
        self.layouts = self.get_parent().layouts

        self.post_checks()

        self.FileEdit.setFilter("GeoPackage (*.gpkg)")
        self.FileEdit.setStorageMode(QgsFileWidget.SaveFile)

        # loads available CRS to the dropdown
        default_crs = QgsProject.instance().crs()
        default_crs = QgsCoordinateReferenceSystem("EPSG:25832") if not default_crs.isValid() else default_crs
        self.DrD_Crs.setLayerCrs(default_crs)
        self.DrD_Crs.setCrs(default_crs)
        self.DrD_Crs.setLayerCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        self.DrD_Crs.setLayerCrs(QgsCoordinateReferenceSystem("EPSG:4258"))
        self.DrD_Crs.setLayerCrs(QgsCoordinateReferenceSystem("EPSG:25833"))
        self.DrD_Crs.setLayerCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

        # loads available print templates to dropdown
        self.DrD_Templates.clear()
        for layout in self.layouts:
            if layout.group:
                self.DrD_Templates.addItem(f"[{layout.group}] {layout.name}", layout)
            else:
                self.DrD_Templates.addItem(f"{layout.name}", layout)

            self.DrD_Templates.setItemData(self.DrD_Templates.count() - 1,
                                           f"{layout.path}\n{layout.filepath}",
                                           Qt.ToolTipRole)

        set_label_status(self.Label_Status, "")

    def get_temp_path(self, path: str):
        base = os.path.basename(path).split(".")[0]
        base = base + f" ({self.tr_('memory')}).qpt"
        path = os.path.join(self.get_plugin().temp_files,
                            base + datetime.now().strftime("_%Y-%m-%d_%H-%M-%S_%f") + ".gpkg")
        return path

    def temporary_state_changed(self, state: Qt.CheckState):
        self.FileEdit.setEnabled(state == Qt.Unchecked)

        if self.CheckBox_Temporary.checkState() == Qt.Checked:
            self.FileEdit.lineEdit().setPlaceholderText(self.tr_('memory'))
        else:
            self.FileEdit.lineEdit().setPlaceholderText(self.tr_('Select save location'))

    @classmethod
    def tr_(cls, text: str):
        result = QgsApplication.translate("QgsApplication", text)
        return result

    def create_new_layout(self, checked: bool):
        """ try to create new plot layer """
        set_label_status(self.Label_Status, "")

        layout: PlotLayout = self.DrD_Templates.currentData()
        if layout is None:
            set_label_status(self.Label_Status,
                             self.tr_("No Print Layout template selected."),
                             STYLE_SHEET_ERROR)
            return

        if self.CheckBox_Temporary.isChecked():
            path = self.get_temp_path(layout.path)
        else:
            path = self.FileEdit.filePath()
            if not path:
                set_label_status(self.Label_Status, self.tr_("No save location set."), STYLE_SHEET_ERROR)
                return
            if not Path(path).parent.is_dir():
                set_label_status(self.Label_Status, self.tr_("Save location invalid."), STYLE_SHEET_ERROR)
                return
            if not Path(path).name.casefold().endswith(".gpkg"):
                set_label_status(self.Label_Status, self.tr_("Save location invalid."), STYLE_SHEET_ERROR)
                return
            if Path(path).is_file():
                set_label_status(self.Label_Status,
                                 self.tr_("File '%s' already exists.") % Path(path).name,
                                 STYLE_SHEET_ERROR)
                return

        crs: QgsCoordinateReferenceSystem = self.DrD_Crs.crs()
        if not crs.isValid():
            set_label_status(self.Label_Status,
                             self.tr_("CRS '%s' is invalid.") % crs.authid(),
                             STYLE_SHEET_ERROR)
            return

        try:
            if not os.path.exists(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            plot_layer = PlotLayer.create_new(path, crs)
            plot_layer.file = layout.path

            self.get_parent().set_layer(plot_layer.layer_pages)
            self.unload(True)

        except TypeError as e:
            self.log(str(traceback.format_exc()))
            set_label_status(self.Label_Status,
                             self.tr_("Layout could not be created. Unknown error."),
                             STYLE_SHEET_ERROR)

    def unload(self, self_unload: bool = False):
        """ will be called, when module will be unloaded

            :param self_unload: only self unload, defaults to False
        """

        super().unload(self_unload)
        self.close()

        del self

    def keyReleaseEvent(self, event):
        """ user presses button """
        pressed_key = event.key()

        if pressed_key == Qt.Key_Escape:
            self.close()

        event.accept()

    def close(self, *args, **kwargs):
        QMainWindow.close(self)

    def closeEvent(self, event) -> None:
        event.accept()
        self.unload(True)
