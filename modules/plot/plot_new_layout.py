# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only
"""Dialog for creating a plot layer from a selected print-layout template."""

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
    """Create a plot layer using a selected print-layout template."""

    def __init__(self, **kwargs: dict):
        """Initialize the dialog, available templates, and coordinate systems."""
        UiModuleBase.__init__(self, **kwargs)
        QMainWindow.__init__(self, kwargs.get("parent"))

        self.setupUi(self)
        self.replace_widget_with_class(self.FileEdit, QgsFileWidget)

        self.show()

        # Qt Connection
        self.connect(self.But_Cancel.clicked, lambda *_: self.close())
        self.connect(self.But_Create.clicked, lambda *_: self.__create_plot_layer())
        self.connect(self.CheckBox_Temporary.stateChanged, self.__on_temporary_mode_changed)

        self.__on_temporary_mode_changed(self.CheckBox_Temporary.checkState())
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

            self.DrD_Templates.setItemData(
                self.DrD_Templates.count() - 1, f"{layout.path}\n{layout.filepath}", Qt.ToolTipRole
            )

        set_label_status(self.Label_Status, "")

    def __get_temporary_layer_path(self, path: str):
        """Build a unique temporary GeoPackage path based on the template name."""
        base = os.path.basename(path).split(".")[0]
        base += f" ({self.__tr('memory')}).qpt"
        return os.path.join(
            self.get_plugin().temp_files, base + datetime.now().strftime("_%Y-%m-%d_%H-%M-%S_%f") + ".gpkg"
        )

    def __on_temporary_mode_changed(self, state: Qt.CheckState):
        """Enable or disable the output path and update its placeholder text."""
        self.FileEdit.setEnabled(state == Qt.Unchecked)

        if self.CheckBox_Temporary.checkState() == Qt.Checked:
            self.FileEdit.lineEdit().setPlaceholderText(self.__tr("memory"))
        else:
            self.FileEdit.lineEdit().setPlaceholderText(self.__tr("Select save location"))

    @classmethod
    def __tr(cls, text: str):
        """Translate a user-visible string in the QGIS application context."""
        return QgsApplication.translate("QgsApplication", text)

    def __create_plot_layer(self):
        """Create the plot layer after validating the selected template, path, and CRS."""
        set_label_status(self.Label_Status, "")

        layout: PlotLayout = self.DrD_Templates.currentData()
        if layout is None:
            set_label_status(self.Label_Status, self.__tr("No Print Layout template selected."), STYLE_SHEET_ERROR)
            return

        if self.CheckBox_Temporary.isChecked():
            path = self.__get_temporary_layer_path(layout.path)
        else:
            path = self.FileEdit.filePath()
            if not path:
                set_label_status(self.Label_Status, self.__tr("No save location set."), STYLE_SHEET_ERROR)
                return
            if not Path(path).parent.is_dir():
                set_label_status(self.Label_Status, self.__tr("Save location invalid."), STYLE_SHEET_ERROR)
                return
            if not Path(path).name.casefold().endswith(".gpkg"):
                set_label_status(self.Label_Status, self.__tr("Save location invalid."), STYLE_SHEET_ERROR)
                return
            if Path(path).is_file():
                set_label_status(
                    self.Label_Status, self.__tr("File '%s' already exists.") % Path(path).name, STYLE_SHEET_ERROR
                )
                return

        crs: QgsCoordinateReferenceSystem = self.DrD_Crs.crs()
        if not crs.isValid():
            set_label_status(self.Label_Status, self.__tr("CRS '%s' is invalid.") % crs.authid(), STYLE_SHEET_ERROR)
            return

        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            plot_layer = PlotLayer.create_new(path, crs)
            plot_layer.file = layout.path

            self.get_parent().set_layer(plot_layer.layer_pages)
            self.unload(True)

        except TypeError:
            self.log(str(traceback.format_exc()))
            set_label_status(
                self.Label_Status, self.__tr("Layout could not be created. Unknown error."), STYLE_SHEET_ERROR
            )

    def unload(self, self_unload: bool = False):
        """Unload this module and release its UI resources.

        :param self_unload: Whether only this module should unload; defaults to False.
        """

        super().unload(self_unload)
        self.close()

        del self

    def keyReleaseEvent(self, event):
        """Close the dialog when Escape is released."""
        pressed_key = event.key()

        if pressed_key == Qt.Key_Escape:
            self.close()

        event.accept()

    def closeEvent(self, event) -> None:
        """Accept the close event and unload this dialog."""
        event.accept()
        self.unload(True)
