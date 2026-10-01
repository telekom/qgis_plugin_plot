# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only
"""Main user interface for managing plot layers, pages, templates, and exports."""

import os
import traceback

import importlib

from pathlib import Path

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsVectorLayer,
    QgsLayoutSize,
    QgsLayoutItemPage,
    QgsLayoutItemLabel,
    QgsLayoutItemPicture,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsApplication,
    Qgis,
    QgsFeatureRequest,
    QgsPointXY,
)

from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QMainWindow,
    QApplication,
    QListWidgetItem,
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QToolButton,
)

from typing import List, Union

from .plot_new_layout import PlotNewLayout
from .plot_layout_menu import PlotLayoutMenu

from ...submodules.base.constants import STYLE_SHEET_ERROR, STYLE_SHEET_WARNING

from ...submodules.base.qgis.plot_layer import PlotLayer, PlotPage
from ...submodules.base.qgis.plot_layout import PlotLayout
from ...submodules.base.qgis.plot_layout_templates import PlotLayoutTemplates
from ...submodules.base.qgis.plot import PrintLayout
from ...submodules.base.qgis.plot_rectangles_from_geometries import PlotRectanglesFromGeometries
from ...submodules.base.qgis.plot_rectangles_from_lines import PlotRectanglesFromLines
from ...submodules.base.qgis.plot_map_tool import PlotPageMapTool

from ...submodules.base.ui.functions import set_label_status
from ...submodules.base.ui.base_class import UiModuleBase
from ...submodules.base.ui.progressbar_extended import DoubleProgressGroup

from ...submodules.base.qgis.geometry import transform_geometry, get_transform
from ...submodules.base.qgis.maptool_digitize_geometry import MapToolDigitizeFeature

FORM_CLASS, _ = UiModuleBase.get_uic_classes(__file__)


class PlotMenu(UiModuleBase, FORM_CLASS, QMainWindow):
    """Main plot menu coordinating plot layers, pages, and related UI modules."""

    def __init__(self, **kwargs: dict):
        """Initialize the plot menu and connect its controls to plugin actions."""
        UiModuleBase.__init__(self, **kwargs)
        QMainWindow.__init__(self, kwargs.get("parent"))

        self.setupUi(self)
        self.global_layout_menu = None
        self.plot_layer = None
        self.page_layout_menu = None
        self.layouts = None
        self.__layout = None
        icon = QIcon(self.get_plugin().get_icon_path("icon.svg"))
        self.setWindowIcon(icon)
        self.But_Create_PDF.setIcon(icon)
        self.But_Create_PDF_QGIS.setIcon(icon)
        self.But_Create_PrintLayout.setIcon(self.getThemeIcon("mActionShowAllLayers.svg"))

        self.But_CreateOverview.setIcon(self.getThemeIcon("mActionShowSelectedLayers.svg"))
        self.But_CreateFromLine.setIcon(self.getThemeIcon("mActionStreamingDigitize.svg"))

        self.But_NewLayout.setIcon(self.getThemeIcon("symbologyAdd.svg"))
        self.But_AddFile.setIcon(self.getThemeIcon("mActionFileOpen.svg"))

        icon = QIcon(self.get_plugin().getThemeIcon("symbologyAdd.svg"))
        self.But_AddPage.setIcon(icon)
        self.But_AddPage.setIconSize(QSize(32, 32))
        self.But_AddPage.setText("")
        icon_portrait = QIcon(self.get_plugin().get_icon_path("add_page_portrait.svg"))
        self.But_AddPage_Portrait.setIcon(icon_portrait)
        self.But_AddPage_Portrait.setIconSize(QSize(32, 32))
        icon_landscape = QIcon(self.get_plugin().get_icon_path("add_page_landscape.svg"))
        self.But_AddPage_Landscape.setIcon(icon_landscape)
        self.But_AddPage_Landscape.setIconSize(QSize(32, 32))

        icon = QIcon(self.get_plugin().getThemeIcon("symbologyRemove.svg"))
        self.But_DeletePage.setIcon(icon)
        self.But_DeletePage.setIconSize(QSize(32, 32))
        self.But_DeletePage.setText("")

        # add ui modules
        self.progress: DoubleProgressGroup = self.add_ui_module(
            "DoubleProgressGroup", self.Frame_Progress, DoubleProgressGroup
        )
        self.progress.hide()
        self.progress.Group_Progress.setTitle(self.__tr("Progress-Container"))
        self.List_Pages.setDragEnabled(True)
        self.List_Pages.setAcceptDrops(True)

        # add some Qt connections
        self.connect(self.But_NewLayout.clicked, lambda *_: self.__add_new_layout())
        self.connect(self.But_Create_PDF.clicked, lambda *_: self.__create_pdf())
        self.connect(self.But_Create_PDF_QGIS.clicked, lambda *_: self.__create_pdf_qgis())
        self.connect(self.But_AddFile.clicked, lambda *_: self.__add_file())
        self.connect(self.But_Create_PrintLayout.clicked, lambda *_: self.__create_qgs_print_layout())
        self.connect(self.But_AddPage.clicked, lambda *_: self.__add_new_page())
        self.connect(self.But_AddPage_Portrait.clicked, lambda *_: self.__add_new_page_portrait())
        self.connect(self.But_AddPage_Landscape.clicked, lambda *_: self.__add_new_page_landscape())
        self.connect(self.But_CreateOverview.clicked, lambda *_: self.__add_over_view_pages())
        self.connect(self.But_CreateFromLine.clicked, lambda *_: self.__start_digitize_map_tool())
        self.connect(self.But_DeletePage.clicked, lambda *_: self.__delete_page())
        self.connect(self.DrD_PrintLayoutsGpkg.currentIndexChanged, lambda *_: self.__layout_selected())
        self.connect(QgsProject.instance().layersAdded, self.__layers_added)
        self.connect(QgsProject.instance().legendLayersAdded, self.__layers_added)
        self.connect(QgsProject.instance().layersRemoved, self.__layers_removed)
        self.connect(self.SpinBox_Dpi.valueChanged, self.__dpi_changed)
        self.connect(self.SpinBox_Scale.valueChanged, self.__scale_changed)
        self.SpinBox_Page_Scale.setValue(self.SpinBox_Scale.value())
        self.connect(self.List_Pages.model().rowsMoved, self.__page_moved)
        self.connect(self.List_Pages.itemDoubleClicked, self.__open_page_item)
        self.connect(self.List_Pages.itemSelectionChanged, self.__page_item_changed)
        self.connect(
            self.CheckBox_Legend_Extra.stateChanged,
            lambda x: self.__check_box_state_changed(self.CheckBox_Legend_Extra),
        )
        self.connect(
            self.CheckBox_Overview.stateChanged, lambda x: self.__check_box_state_changed(self.CheckBox_Overview)
        )

        # other Qt Connections
        self.connect(self.get_plugin().versionRead, lambda plugin: self.set_ui_version_info(self.Label_Version_Nr))

        # load existing plot layers to drd
        self.DrD_PrintLayoutsGpkg.clear()
        self.DrD_PrintLayoutsGpkg.addItem(f"-- {self.__tr('choose or create')} --", None)
        self.__layers_added(QgsProject.instance().mapLayers().values())

        self.__page_item_changed()

        self.initialize_tab_stop_widgets()

    def __init_layouts(self):
        """Load layout templates once and report loading progress in the menu."""
        if self.layouts is not None:
            # already initialized
            return

        self.progress.start_progressbars(
            0, 100, use_subbar=False, can_cancel=False, hide_widgets=[self.ScrollArea], auto_restore=False
        )
        self.layouts = PlotLayoutTemplates(plot_plugin_plots_dir=[self.get_plugin().plots_dir])
        self.layouts.progressChanged.connect(self.__show_progress_main)
        self.layouts.load_default_paths()
        self.layouts.load_plots()
        self.layouts.load_layouts()
        self.progress.restore()

    def __show_progress_main(self, current_value: int, max_value: int, message: str):
        # helper inner function to show connect preparation with progress ui
        self.progress.reset_main_bar(0, max_value, value=current_value)
        self.progress.set_text_main(message)

    @classmethod
    def __tr(cls, text: str):
        """Translate a user-visible string in the QGIS application context."""
        result = QgsApplication.translate("QgsApplication", text)
        return result

    def keyReleaseEvent(self, event):
        """Handle F5 to refresh pages and Escape to close the menu."""
        pressed_key = event.key()
        if pressed_key == Qt.Key_F5:
            self.global_layout_menu.reset_layer_visibility()
            self.__reload_pages()

        if pressed_key == Qt.Key_Escape:
            self.close()

        event.accept()

    def __create_qgs_print_layout(self):
        """Create a print layout and add it to the current QGIS project."""
        self.__layout = None

        self.progress.start_progressbars(
            0, 100, use_subbar=False, can_cancel=False, hide_widgets=[self.ScrollArea], auto_restore=False
        )
        try:
            self.__layout = PrintLayout(self.plot_layer, self.layouts)
            self.__layout.progressChanged.connect(self.__show_progress_main)
            self.__layout.init()
            self.__layout.add_to_instance()
        except Exception as e:
            self.log(traceback.format_exc(), level=self.CRITICAL)
            set_label_status(self.Label_Status, str(e), STYLE_SHEET_ERROR)
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), str(e))
        self.progress.restore()

    def __create_pdf(self):
        """Export the current plot layout to a PDF file selected by the user."""
        self.__layout = None

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            self.__tr("Save file"),
            os.path.join(QgsProject.instance().absolutePath(), self.plot_layer.source.replace(".gpkg", ".pdf")),
            "PDF (*.pdf)",
        )
        if not save_path:
            return

        if not PrintLayout.is_file_overwritable(save_path):
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), self.__tr("Write access to file blocked."))
            self.warning(self.__tr("Print Menu"), self.__tr("Write access to file blocked."))
            return

        self.progress.start_progressbars(0, 100, use_subbar=False, hide_widgets=[self.ScrollArea], auto_restore=False)
        try:
            self.__layout = PrintLayout(self.plot_layer, self.layouts)
            self.__layout.progressChanged.connect(self.__show_progress_main)
            self.__layout.init()

        except AssertionError as e:
            set_label_status(self.Label_Status, str(e), STYLE_SHEET_ERROR)
            self.log(traceback.format_exc(), level=self.WARNING)
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), str(e))

            if "FileError" in str(e) and Path(save_path).is_file():
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    self._tr("Error"),
                    self.__tr("File %s could not be saved.<br/>Please close needed applications.") % save_path,
                )
            self.progress.restore()
            self.__layout = None
            return

        except Exception as e:
            self.log(traceback.format_exc(), level=self.CRITICAL)
            set_label_status(self.Label_Status, str(e), STYLE_SHEET_ERROR)
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), str(e))
            self.progress.restore()
            self.__layout = None
            return

        for _ in range(100):
            self.__show_progress_main(
                self.progress.get_mainbar().value() + 1,
                self.progress.get_mainbar().maximum() + 1,
                self.__tr(
                    "Preparing writing PDF %s.<br/>"
                    "Depending on your layers, network connection, layout size "
                    "and more this process can take a moment."
                )
                % save_path,
            )

        error = self.__layout.create_pdf(save_path)
        self.progress.restore()

        if error:
            QMessageBox.information(
                self.iface.mainWindow(), self.__tr("Error"), self.__tr("PDF print finished with errors.") + "\n" + error
            )

        else:
            QMessageBox.information(
                self.iface.mainWindow(), self.__tr("Print Menu"), self.__tr("PDF print finished without errors.")
            )

        self.__layout = None

    def __create_pdf_qgis(self):
        """Open the QGIS layout designer and trigger its built-in PDF export."""
        self.__layout = None

        self.progress.start_progressbars(0, 100, use_subbar=False, hide_widgets=[self.ScrollArea], auto_restore=False)
        try:
            self.__layout = PrintLayout(self.plot_layer, self.layouts)
            self.__layout.progressChanged.connect(self.__show_progress_main)
            self.__layout.init()
            self.__layout.add_to_instance()

        except AssertionError as e:
            set_label_status(self.Label_Status, str(e), STYLE_SHEET_ERROR)
            self.log(traceback.format_exc(), level=self.WARNING)
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), str(e))
            self.progress.restore()
            self.__layout = None
            return

        except Exception as e:
            self.log(traceback.format_exc(), level=self.CRITICAL)
            set_label_status(self.Label_Status, str(e), STYLE_SHEET_ERROR)
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), str(e))
            self.progress.restore()
            self.__layout = None
            return

        # get the real layout from the layout module
        print_layout = self.__layout.layout

        # apply default render settings
        self.__layout.apply_default_render_context_settings()

        # set some default export settings in the layout (see PdfExportSettings from plot.py get_pdf_export_settings)
        # from cpp code
        #   > QGIS\src\app\layout\qgslayoutdesignerdialog.cpp
        print_layout.setCustomProperty("forceVector", 0)
        print_layout.setCustomProperty("pdfAppendGeoreference", 0)
        print_layout.setCustomProperty("pdfIncludeMetadata", 0)
        print_layout.setCustomProperty("pdfDisableRasterTiles", 0)
        print_layout.setCustomProperty("rasterize", 0)
        print_layout.setCustomProperty("pdfTextFormat", int(Qgis.TextRenderFormat.AlwaysText))
        print_layout.setCustomProperty("pdfSimplify", 1)
        print_layout.setCustomProperty("pdfCreateGeoPdf", 0)
        print_layout.setCustomProperty("pdfOgcBestPracticeFormat", 1)
        print_layout.setCustomProperty("pdfExportThemes", "")
        print_layout.setCustomProperty("pdfLayerOrder", "")
        print_layout.setCustomProperty("pdfLosslessImages", 0)

        # open the layout in the designer window
        designer = self.iface.openLayoutDesigner(print_layout)
        # get the toolbar from the designer
        toolbar = designer.layoutToolbar()
        # get the expected display text, depends on the current language/locale
        # EN = "Export as PDF…", DE = "Als PDF exportieren…"
        # \u2026 is the horizontal ellipsis "..."
        display_text = QgsApplication.translate("QgsModelDesignerDialogBase", "Export as PDF\u2026")

        button = None
        for child in toolbar.findChildren(QToolButton):
            if child.text() == display_text:
                button = child
                break

        if not button:
            set_label_status(self.Label_Status, "Button für PDF-Export nicht gefunden.", STYLE_SHEET_ERROR)
            self.iface.messageBar().pushWarning(self.__tr("Print Menu"), "Button für PDF-Export nicht gefunden.")
            self.progress.restore()
            # close the dialog immediately (objects stay accessible)
            designer.close()
            self.__layout = None
            return

        # triggers the PDF-Export
        #   1. ask for save file name
        #   2. show "PDF Export Options"
        button.click()

        # close the designer window
        designer.close()

        self.progress.restore()

        QMessageBox.information(
            self.iface.mainWindow(), self.__tr("Print Menu"), self.__tr("Advanced PDF export finished.")
        )

        self.__layout.remove_from_instance()
        self.__layout = None

    def __delete_page(self):
        """Delete the selected plot page or pages after confirming a multi-delete."""
        items = self.List_Pages.selectedItems()

        if not items:
            return

        if len(items) > 1:
            reply = QMessageBox.question(
                self.iface.mainWindow(),
                self.__tr("Print Menu"),
                self.__tr("You are about to delete %s pages. Continue?") % len(items),
            )
            if reply != QMessageBox.Yes:
                return

        self.plot_layer.delete_fids([item.data(Qt.UserRole) for item in items])
        self.__reload_pages()
        self.__page_moved()  # triggers page recalculation

        if len(items) == 1:
            row = self.List_Pages.currentRow()
            if row > self.List_Pages.count() - 1:
                self.List_Pages.setCurrentRow(row - 1)
            else:
                self.List_Pages.setCurrentRow(row)

    def __add_new_page_landscape(self, bring_to_front: bool = True):
        """Select a landscape template and start the new-page map tool."""
        for row in range(self.DrD_Page_Templates.count()):
            layout = self.DrD_Page_Templates.itemData(row, Qt.UserRole)
            if layout is not None and layout.page.orientation() == QgsLayoutItemPage.Landscape:
                self.DrD_Page_Templates.setCurrentIndex(row)
                self.__add_new_page(bring_to_front=bring_to_front)
                break
        else:
            set_label_status(self.Label_Status, self.__tr("Something went wrong. No landscape layout found."))

    def __add_new_page_portrait(self, bring_to_front: bool = True):
        """Select a portrait template and start the new-page map tool."""
        for row in range(self.DrD_Page_Templates.count()):
            layout = self.DrD_Page_Templates.itemData(row, Qt.UserRole)
            if layout is not None and layout.page.orientation() == QgsLayoutItemPage.Portrait:
                self.DrD_Page_Templates.setCurrentIndex(row)
                self.__add_new_page(bring_to_front=bring_to_front)
                break
        else:
            set_label_status(self.Label_Status, self.__tr("Something went wrong. No portrait layout found."))

    def __add_new_page(self, bring_to_front: bool = True):
        """Activate the map tool used to draw and create a page."""
        layout: PlotLayout = self.DrD_Page_Templates.currentData()

        if self.DrD_Page_Templates.count() < 0:
            raise ValueError("no layouts found")

        # nothing selected in combobox
        # select matching layout from plot layer and call it again
        if layout is None:
            file = self.plot_layer.file
            self.__select_page_layout_template(file)

            self.__add_new_page()
            return

        scale = self.SpinBox_Page_Scale.value()

        iface = self.get_plugin().iface
        self.__initialize_defaults(self.plot_layer, layout)

        map_tool = PlotPageMapTool(
            iface, iface.mapCanvas().mapTool(), layout, scale, self.plot_layer, drawings=self.get_plugin().drawings
        )
        map_tool.pageAdded.connect(lambda x=0: self.__reload_pages())
        if bring_to_front:
            map_tool.finished.connect(lambda x=0: self.showNormal() if self.isMinimized() else self.show())
        self.get_plugin().iface.mapCanvas().setMapTool(map_tool)
        self.showMinimized()

    def __select_page_layout_template(self, file: str):
        """Select the template matching ``file``, or the first template if not found."""

        for row in range(self.DrD_Page_Templates.count()):
            layout: PlotLayout = self.DrD_Page_Templates.itemData(row, Qt.UserRole)
            if layout.path.endswith(file):
                self.DrD_Page_Templates.setCurrentIndex(row)
                break
        else:
            self.DrD_Page_Templates.setCurrentIndex(0)
            self.log(f"{file} not found in dropdown layouts")

    def __page_item_changed(self):
        """Update the delete control and map selection for selected page items."""
        items = self.List_Pages.selectedItems()
        if not items:
            self.Frame_DeletePage.hide()
            if self.plot_layer is not None:
                self.plot_layer.select_features([])
            return

        if self.plot_layer is not None:
            fids = [item.data(Qt.UserRole) for item in items]
            self.plot_layer.select_features(fids)
        self.Frame_DeletePage.show()

    def __check_box_state_changed(self, box: QCheckBox):
        """Store the changed overview or extra-legend setting on the current plot layer."""
        if box is self.CheckBox_Legend_Extra:
            # save state for extra legend
            self.plot_layer.legend_on_extra_page = Qt.Checked == self.CheckBox_Legend_Extra.checkState()

        if box is self.CheckBox_Overview:
            # save state for overview page
            self.plot_layer.create_overview_page = Qt.Checked == self.CheckBox_Overview.checkState()

    def __page_moved(self, *args, **kwargs):
        """Update page numbering and repaint the plot layer after a reorder."""
        for row in range(self.List_Pages.count()):
            page: PlotPage = self.plot_layer.get_page_from_fid(self.List_Pages.item(row).data(Qt.UserRole))
            page.page = row + 1

        self.__reload_pages()
        self.plot_layer.layer_pages.triggerRepaint()

    def __open_page_item(self, current):
        """Open the options menu for the activated page item."""

        item: QListWidgetItem = self.List_Pages.currentItem()
        if item is None or item is not current:
            return

        fid: int = current.data(Qt.UserRole)
        page: PlotPage = self.plot_layer.get_page_from_fid(fid)
        layout = self.layouts[page.file]

        self.page_layout_menu = self.add_module(
            "PagePlotLayoutMenu", PlotLayoutMenu, parent=self, plot_layout=layout, plot_layer=self.plot_layer, edit=page
        )
        self.page_layout_menu.show()
        self.page_layout_menu.setWindowTitle(item.text())
        self.page_layout_menu.setWindowModality(Qt.WindowModal)

    def __initialize_defaults(self, plot_layer: PlotLayer, layout: PlotLayout = None):
        """Initialize missing plot-layer field values and available layout icons."""
        try:
            options = plot_layer.options
            if layout is None:
                layout = self.layouts[plot_layer.file]
        except KeyError:
            QMessageBox.warning(self, self.__tr("Error"), self.__tr("No layout found with path '%s'") % plot_layer.file)
            self.DrD_PrintLayoutsGpkg.setCurrentIndex(0)
            return

        if plot_layer.file != layout.path:
            return

        for item_id, value_pair in layout.defaults.items():
            type_, value = value_pair

            current_value = options.get(item_id, ("", False))[0]
            if current_value:
                continue

            value_to_set = ""
            item = layout.layout.itemById(item_id)
            if type_ == "function":
                # call something from defined function with importlib
                try:
                    path = Path(self.get_plugin().plugin_dir)
                    if not path.name:
                        path = path.parent
                    parents = []
                    while path.name != "plugins":
                        parents.append(path.name)
                        path = path.parent
                    parents = ".".join(reversed(parents))
                    import_path = f"{parents}.templates.plots.{value}"

                    *import_path, attribute = import_path.split(".")
                    module = importlib.import_module(".".join(import_path))
                    value_to_set = getattr(module, attribute)(self.get_plugin(), layout, item)
                except Exception:
                    self.log(str(traceback.format_exc()), "plot-function-call")
                    value_to_set = ""
                if not isinstance(value_to_set, str):
                    raise TypeError(
                        f"returned value from plot_functions.{value} is not a string, "
                        f"got '{value_to_set}' with type {type(value_to_set)}"
                    )

            if type_ == "value":
                value_to_set = value

            if item is not None and value_to_set is not None and isinstance(item, QgsLayoutItemLabel):
                # item.setText(value_to_set)
                options[item_id] = (value_to_set, False)
        plot_layer.options = options

        # load icons, e.g. company icon
        for item_id, icon_str in layout.icons.items():
            item = layout.layout.itemById(item_id)

            if isinstance(item, QgsLayoutItemPicture) and Path(icon_str).is_file():
                # apply the icon if the file path exists as file
                item.setPicturePath(icon_str)

    def __load_page_templates(self, selected_layout: PlotLayout):
        """Populate page-template choices compatible with the selected layout."""

        def is_layout_loadable(layout: PlotLayout):
            """Check whether a candidate layout has compatible dimensions and group."""

            size: QgsLayoutSize = layout.page.pageSize()
            size_swapped = QgsLayoutSize(size.height(), size.width(), size.units())

            if selected_layout.group != layout.group and selected_layout.group:
                # only layouts with same group name or empty group name
                return False

            return selected_layout.page.pageSize() == size or selected_layout.page.pageSize() == size_swapped

        # loads available print templates to dropdown
        self.DrD_Page_Templates.clear()
        self.GroupBox_Template.show()
        self.But_AddPage.show()
        self.But_AddPage_Portrait.hide()
        self.But_AddPage_Landscape.hide()
        count_landscape = 0
        count_portrait = 0
        for i, layout in enumerate(self.layouts):
            if is_layout_loadable(layout):
                if layout.group:
                    self.DrD_Page_Templates.addItem(f"{layout.name} [{layout.group}]", layout)
                else:
                    self.DrD_Page_Templates.addItem(f"{layout.name}", layout)

                self.DrD_Page_Templates.setItemData(
                    self.DrD_Page_Templates.count() - 1, f"{layout.path}\n{layout.filepath}", Qt.ToolTipRole
                )

                orientation = layout.page.orientation()
                if orientation == QgsLayoutItemPage.Landscape:
                    count_landscape += 1
                if orientation == QgsLayoutItemPage.Portrait:
                    count_portrait += 1

        self.__select_page_layout_template(selected_layout.path)

        if count_portrait == 1 and count_landscape == 1:
            # hides normal page add button when only 1 portrait page and only 1 landscape page is there
            self.GroupBox_Template.hide()
            self.But_AddPage.hide()
            self.But_AddPage_Portrait.show()
            self.But_AddPage_Landscape.show()

            self.add_action(
                f"{self.__tr('Add new page (portrait)')} - {self.plot_layer.layer_pages.name()}",
                QIcon(self.get_plugin().get_icon_path("add_page_portrait.svg")),
                lambda *_: self.__add_new_page_portrait(False),
                toolbar_name="qgis_plot_plugin",
                toolbar_displayname=self.__tr("Print Menu"),
                to_plugin_menu=False,
            )

            self.add_action(
                f"{self.__tr('Add new page (landscape)')} - {self.plot_layer.layer_pages.name()}",
                QIcon(self.get_plugin().get_icon_path("add_page_landscape.svg")),
                lambda *_: self.__add_new_page_landscape(False),
                toolbar_name="qgis_plot_plugin",
                toolbar_displayname=self.__tr("Print Menu"),
                to_plugin_menu=False,
            )

    def __dpi_changed(self, value: int):
        """Update the current plot layer's export resolution."""
        self.global_layout_menu.plot_layer.dpi = value

    def __scale_changed(self, value: int):
        """Update the current plot scale and synchronize the page-scale control."""
        self.global_layout_menu.plot_layer.scale = value
        self.SpinBox_Page_Scale.setValue(value)

    def __get_layer_index(self, layer: Union[str, QgsMapLayer]):
        """Return the dropdown index for ``layer``, or ``-1`` when it is absent."""
        for row in range(self.DrD_PrintLayoutsGpkg.count()):
            data = self.DrD_PrintLayoutsGpkg.itemData(row, Qt.UserRole)

            if isinstance(layer, QgsVectorLayer) and data == layer.id():
                return row
            if isinstance(layer, str) and data == layer:
                return row

        return -1

    def __layers_removed(self, layers: List[str]):
        """Remove deleted project layers from the plot-layer dropdown."""
        for layer_id in layers:
            index = self.__get_layer_index(layer_id)
            if index > -1 and index == self.DrD_PrintLayoutsGpkg.currentIndex():
                # Do this because upcoming plot layout menus depend on the selected layer.
                self.DrD_PrintLayoutsGpkg.setCurrentIndex(0)
            if index > -1:
                self.DrD_PrintLayoutsGpkg.removeItem(index)

        if self.global_layout_menu is not None:
            self.global_layout_menu.refresh_layer_visibility_table()

    def __layers_added(self, layers: List[QgsMapLayer]):
        """Add newly available plot layers to the plot-layer dropdown."""
        for layer in layers:
            index = self.__get_layer_index(layer)
            is_vector = isinstance(layer, QgsVectorLayer)
            is_plot = PlotLayer.is_plot_layer(layer)

            if index == -1 and is_vector and is_plot:
                self.DrD_PrintLayoutsGpkg.addItem(layer.name(), layer.id())

        if self.global_layout_menu is not None:
            self.global_layout_menu.refresh_layer_visibility_table()

    def set_layer(self, layer: QgsVectorLayer):
        """Select ``layer`` in the plot-layer dropdown."""
        index = self.__get_layer_index(layer)
        self.DrD_PrintLayoutsGpkg.setCurrentIndex(index)

    def __layout_selected(self):
        """Load the selected plot layer and initialize its layout and page controls."""
        data: str = self.DrD_PrintLayoutsGpkg.currentData()
        layer: QgsVectorLayer = QgsProject.instance().mapLayer(data)

        self.List_Pages.clear()
        set_label_status(self.Label_Status, "")

        self.remove_actions()

        if self.global_layout_menu is not None:
            self.Frame_Layout_Menu_Global._ui_module_base.replace_with_empty_frame()
            self.global_layout_menu.unload(True)
            self.global_layout_menu.hide()
            self.global_layout_menu.close()
            self.global_layout_menu = None
            self.plot_layer = None

        try:
            self["PlotLayoutMenu"].unload(True)
            self["PlotLayoutMenu"].hide()
            self["PlotLayoutMenu"].close()
            self.global_layout_menu = None
            self.plot_layer = None
        except KeyError:
            pass

        if layer is None:
            self.Frame_Plotlayer.setEnabled(False)
            set_label_status(self.Label_Status, self.__tr("No Print Layer selected."), STYLE_SHEET_ERROR)
        else:
            self.Frame_Plotlayer.setEnabled(True)
            layer.loadNamedStyle(
                os.path.join(self.get_plugin().plugin_dir, "templates", "plots", "plot_layer_stil.qml"), True
            )
            self.plot_layer = PlotLayer(layer)
            layer.updateExtents(force=True)
            layer.dataProvider().updateExtents()
            self.__initialize_defaults(self.plot_layer)
            for layout in self.layouts:
                if layout.path != self.plot_layer.file:
                    continue
                self.__initialize_defaults(self.plot_layer, layout)

            try:
                layout = self.layouts[self.plot_layer.file]
            except KeyError:
                self.DrD_PrintLayoutsGpkg.setCurrentIndex(0)
                return

            self.__load_page_templates(layout)

            self.global_layout_menu = self.add_ui_module(
                "PlotLayoutMenu",
                self.Frame_Layout_Menu_Global,
                PlotLayoutMenu,
                plot_layout=layout,
                plot_layer=self.plot_layer,
                edit=self.plot_layer,
            )
            self.global_layout_menu.GroupBox_Layers.setCheckable(False)
            self.global_layout_menu.Label_Layers.hide()
            self.global_layout_menu.Label_Field_Info.hide()
            self.insert_tab_stop_widgets_behind(self.SpinBox_Scale, self.global_layout_menu.tab_order_widgets)
            self.reload_tab_stop_order()

            self.Frame_Plotlayer.setEnabled(True)

            # load values to window
            self.CheckBox_Legend_Extra.setCheckState(
                Qt.Checked if self.plot_layer.legend_on_extra_page else Qt.Unchecked
            )
            self.CheckBox_Overview.setCheckState(Qt.Checked if self.plot_layer.create_overview_page else Qt.Unchecked)
            self.SpinBox_Dpi.setValue(self.plot_layer.dpi)
            self.SpinBox_Scale.setValue(self.plot_layer.scale)

            self.__reload_pages()
            self.List_Pages.setCurrentItem(None)

            # check if plot layer crs is different to current QgsProject projection
            if self.plot_layer.get_crs().authid().lower() != QgsProject.instance().crs().authid().lower():
                set_label_status(
                    self.Label_Status,
                    self.__tr(
                        "Coordinate Reference System from Print Layer and current QGIS Project are different. "
                        "Maybe the page rectangles will have mystery orientations."
                    ),
                    STYLE_SHEET_WARNING,
                )

    def __reload_pages(self):
        """Rebuild the page list from the currently selected plot layer."""
        self.List_Pages.clear()
        for page in self.plot_layer:
            self.__add_page_feature(page)

    def __add_page_feature(self, page: PlotPage):
        """Add one plot page to the page list with its orientation and feature ID."""
        orientation = self.layouts.get_orientation(page.file)
        if orientation == QgsLayoutItemPage.Portrait:
            orientation = self.__tr("portrait")
        elif orientation == QgsLayoutItemPage.Landscape:
            orientation = self.__tr("landscape")
        else:
            orientation = "unknown"

        item = QListWidgetItem(f"#{page.page} ({orientation})")
        item.setData(Qt.UserRole, page.fid)

        self.List_Pages.addItem(item)

    def __add_new_layout(self):
        """Open the dialog for creating a new plot layout."""
        self.add_module("PlotNewLayout", PlotNewLayout, parent=self)

    def __add_file(self):
        """Add an existing compatible plot GeoPackage to the current project."""
        set_label_status(self.Label_Status, "")
        file, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Wählen Sie eine GeoPackage:",
            QgsProject.instance().absolutePath(),
            "GeoPackage (*.gpkg)",
        )

        if not file:
            return

        ok = PlotLayer.is_plot_file(file)
        if not ok:
            set_label_status(
                self.Label_Status, self.__tr("File '%s' not compatible.") % os.path.basename(file), STYLE_SHEET_ERROR
            )
            return

        layer = QgsVectorLayer(PlotLayer.get_plot_uri(file), os.path.basename(file).split(".")[0])
        if not layer.isValid():
            set_label_status(
                self.Label_Status,
                self.__tr("File '%s' could not be opened.") % os.path.basename(file),
                STYLE_SHEET_ERROR,
            )
            return

        layer = QgsProject.instance().addMapLayer(layer, False)
        root = QgsProject.instance().layerTreeRoot()
        root.insertLayer(0, layer)
        self.set_layer(layer)

    def __start_digitize_map_tool(self):
        """Start digitizing a line that will be converted into plot pages."""

        authid = self.plot_layer.layer_pages.dataProvider().crs().authid()
        self.__map_tool = MapToolDigitizeFeature.start_from_layer(
            QgsVectorLayer(f"LineString?crs={authid}", "temp line layer", "memory"),
            self.iface,
            warn_disabled_snapping=False,
            previous_layer_id=self.iface.activeLayer().id() if self.iface.activeLayer() else None,
        )
        self.__map_tool.drawingFinished.connect(self.__create_new_pages_from_line)

    def __create_new_pages_from_line(self, geometry: QgsGeometry):
        """Create plot pages along the supplied line geometry."""
        self.progress.start_progressbars(0, 100, hide_widgets=[self.ScrollArea], use_subbar=True, auto_restore=False)
        self.progress.set_text_main("")
        overview = None
        overlap = self.SpinBox_Overlapping.value() / 100
        try:
            # Get the available layouts from the template dropdown.
            scale = self.SpinBox_Page_Scale.value()
            crs = self.plot_layer.layer_pages.dataProvider().crs()
            layouts = []
            for row in range(self.DrD_Page_Templates.count()):
                layout = self.DrD_Page_Templates.itemData(row, Qt.UserRole)
                if layout is not None:
                    layout.item_map.setCrs(crs)
                    layouts.append(layout)

            rectangles = [
                self.layouts.get_layout_extent(layout.path, QgsPointXY(100, 100), scale) for layout in layouts
            ]

            overview = PlotRectanglesFromLines([geometry.asPolyline()], rectangles, overlap=overlap)
            overview.progressChanged.connect(self.__update_main_progress)
            overview.subProgressChanged.connect(self.__update_sub_progress)
            rectangles = overview.run()

            self.progress.set_text_main(self.__tr("Adding pages"))
            self.progress.reset_main_bar(0, max(1, len(rectangles)))
            for index, rectangle in enumerate(rectangles):
                layout = layouts[overview.rectangle_template_indices[index]]
                self.plot_layer.add_page(layout, QgsGeometry.fromRect(rectangle), scale)
                self.progress.add_main()

            self.__reload_pages()
        finally:
            if overview is not None:
                overview.progressChanged.disconnect(self.__update_main_progress)
                overview.subProgressChanged.disconnect(self.__update_sub_progress)
            self.progress.restore()

    def __add_over_view_pages(self):
        """Create plot pages around selected features from visible project layers."""
        self.progress.start_progressbars(0, 100, hide_widgets=[self.ScrollArea], use_subbar=True, auto_restore=False)
        self.progress.set_text_main(self.__tr("Collecting selected features"))
        overview = None
        overlap = self.SpinBox_Overlapping.value() / 100
        try:
            layers = QgsProject.instance().mapLayers().values()
            layers = [
                layer for layer in layers if isinstance(layer, QgsVectorLayer) and not PlotLayer.is_plot_layer(layer)
            ]

            layout: PlotLayout = self.DrD_Page_Templates.currentData()

            crs: QgsCoordinateReferenceSystem = self.plot_layer.layer_pages.dataProvider().crs()
            bbox = transform_geometry(
                QgsGeometry.fromRect(crs.bounds()), QgsCoordinateReferenceSystem("EPSG:4326"), crs
            ).boundingBox()
            center = bbox.center()

            # Workaround for CRS bounds whose center is (0, 0), e.g. EPSG:4326.
            center.setX(center.x() + (bbox.width() / 4))
            center.setY(center.y() + (bbox.height() / 4))

            layout.item_map.setCrs(crs)
            scale = self.SpinBox_Page_Scale.value()
            rectangle = self.layouts.get_layout_extent(layout.path, center, scale)

            geometries = []
            target_crs = self.plot_layer.layer_pages.dataProvider().crs()
            selected_feature_count = sum(layer.selectedFeatureCount() for layer in layers)
            self.progress.reset_main_bar(0, max(1, len(layers)))
            self.progress.reset_sub_bar(0, max(1, selected_feature_count))
            for layer in layers:
                if layer.selectedFeatureCount():
                    transform = get_transform(layer.crs(), target_crs)
                    request = QgsFeatureRequest().setCoordinateTransform(transform)
                    for feature in layer.getSelectedFeatures(request):
                        geometries.append(feature.geometry())
                        self.progress.add_sub()
                self.progress.add_main()

            overview = PlotRectanglesFromGeometries(geometries, [rectangle], overlap=overlap)
            overview.progressChanged.connect(self.__update_main_progress)
            overview.subProgressChanged.connect(self.__update_sub_progress)
            rectangles = overview.run()

            if not rectangles:
                QMessageBox.information(
                    self.iface.mainWindow(), self.__tr("Plot Menu (Overview)"), self.__tr("No pages calculated.")
                )
                return

            self.progress.set_text_main(self.__tr("Adding pages"))
            self.progress.reset_main_bar(0, max(1, len(rectangles)))
            for rectangle in rectangles:
                self.plot_layer.add_page(layout, QgsGeometry.fromRect(rectangle), scale)
                self.progress.add_main()

            self.__reload_pages()
        finally:
            if overview is not None:
                overview.progressChanged.disconnect(self.__update_main_progress)
                overview.subProgressChanged.disconnect(self.__update_sub_progress)
            self.progress.restore()

    def __update_main_progress(self, current: int, maximum: int, message: str):
        """Display a calculation phase and its progress in the main progress bar."""
        self.progress.reset_main_bar(0, maximum, value=current)
        self.progress.set_text_main(message)

    def __update_sub_progress(self, current: int, maximum: int, message: str):
        """Display the current input or grouping step in the secondary progress bar."""
        self.progress.reset_sub_bar(0, maximum, value=current)
        self.progress.set_text_single(message)

    def unload(self, self_unload: bool = False):
        """Release loaded layout resources and unload this UI module.

        :param self_unload: Whether only this module should unload; defaults to False.
        """

        # clear loaded layouts (remove all pages and items)
        for plot_layout in self.layouts.layouts:
            plot_layout.layout.clear()

        super().unload(self_unload)
        self.__layout = None
        self.__map_tool = None
        self.close()

        del self

    @classmethod
    def load(cls, parent_module: UiModuleBase):
        """Show an existing menu or load this menu as a standalone UI module.

        :param parent_module: UI module that owns or will contain this menu.
        """

        if cls.__name__ in parent_module:
            module = parent_module[cls.__name__]
            module.show()
            module.activateWindow()
        else:
            module = parent_module.add_module(cls.__name__, cls)
            module.show()
            module.get_plugin().iface.messageBar().pushMessage(
                cls.__tr("Plot Menu"), cls.__tr("Templates loading. Please wait.")
            )
            module.setEnabled(False)
            QApplication.setOverrideCursor(Qt.BusyCursor)
            module.__init_layouts()
            module.setEnabled(True)
            QApplication.restoreOverrideCursor()

            if module.layouts.exceptions:
                error = cls.__tr("Errors occured while loading QGIS Printlayout Templates") + (
                    "\n".join(module.layouts.exceptions)
                )
                module.get_plugin().iface.messageBar().pushWarning(
                    cls.__tr("Print Menu"), cls.__tr("Errors occured while loading QGIS Printlayout Templates")
                )
            else:
                error = ""
            set_label_status(module.Label_Status, error, STYLE_SHEET_ERROR)

        if hasattr(parent_module, "load_version_info"):
            parent_module.load_version_info()

        return module
