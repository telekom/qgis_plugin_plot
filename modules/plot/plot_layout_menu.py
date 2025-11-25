# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only

from qgis.PyQt.QtWidgets import (QMainWindow, QTableWidget, QTableWidgetItem,
                             QLineEdit, QGroupBox, QHeaderView,
                             QCheckBox)
from qgis.PyQt.QtCore import pyqtSignal, Qt, QRegExp
from qgis.PyQt.QtGui import QRegExpValidator

from qgis.core import QgsProject, QgsLayerTree, QgsMapLayer, QgsApplication
from typing import Union, List

from ...submodules.base.qgis.plot_layout import PlotLayout
from ...submodules.base.qgis.plot_layer import PlotLayer, PlotPage
from ...submodules.base.ui.base_class import UiModuleBase

FORM_CLASS, _ = UiModuleBase.get_uic_classes(__file__)


class PlotLayoutMenu(UiModuleBase, QMainWindow, FORM_CLASS):
    saved = pyqtSignal(name="saved")

    def __init__(self, plot_layout: PlotLayout = None, plot_layer: PlotLayer = None,
                 edit: Union[PlotLayer, PlotPage] = None, **kwargs):
        UiModuleBase.__init__(self, **kwargs)
        QMainWindow.__init__(self, kwargs.get('parent', None))

        self.setupUi(self)

        self.plot_layout: PlotLayout = plot_layout
        self.plot_layer: PlotLayer = plot_layer
        self.edit_on = edit
        if not self.is_page_edit:
            # menu for global options
            self.Label_Title.setText(f"{self.plot_layer.layer_pages.name()} - {self.plot_layout.name}")
            self.GroupBox_Layers.setChecked(True)
        else:
            self.Label_Title.setText(f"{self.tr_('Page')} {self.edit_on.page} - "
                                     f"{self.plot_layout.get_parent()[self.edit_on.file].name}")
        if not isinstance(self.plot_layout, PlotLayout):
            raise TypeError(f"plot_layout({self.plot_layout}) is not given")

        self.connect(self.GroupBox_Layers.toggled, lambda x=0: self.group_box_toggled(self.GroupBox_Layers))
        self.connect(self.Table_UserItems.itemClicked, self.user_item_clicked)
        self.connect(self.Table_Layers.clicked, self.check_box_layers_clicked)
        self.connect(self.CheckBox_MiniMap.stateChanged,
                     lambda x: self.check_box_state_changed(self.CheckBox_MiniMap))
        self.connect(self.CheckBox_ShowMapTips.stateChanged,
                     lambda x: self.check_box_state_changed(self.CheckBox_ShowMapTips))
        self.connect(self.CheckBox_MiniPageLegend.stateChanged,
                     lambda x: self.check_box_state_changed(self.CheckBox_MiniPageLegend))

        if self.plot_layout.item_minimap is None:
            self.CheckBox_MiniMap.setEnabled(False)
            self.CheckBox_MiniMap.blockSignals(True)
            self.CheckBox_MiniMap.setText(f"{self.CheckBox_MiniMap.text()} {self.tr_('(not available in this layout)')}")

        self.reset_ui()

        self.initialize_tab_stop_widgets()

    @classmethod
    def tr_(cls, text: str):
        result = QgsApplication.translate("QgsApplication", text)
        return result

    def check_box_state_changed(self, box: QCheckBox):
        """ Checkbox option changed for layout or page """
        if box is self.CheckBox_MiniMap:
            self.edit_on.show_mini_map = Qt.Checked == self.CheckBox_MiniMap.checkState()

        if box is self.CheckBox_ShowMapTips:
            self.edit_on.show_map_tips = Qt.Checked == self.CheckBox_ShowMapTips.checkState()

        if box is self.CheckBox_MiniPageLegend:
            self.edit_on.show_legend_on_page = Qt.Checked == self.CheckBox_MiniPageLegend.checkState()

    def user_item_clicked(self, item: QTableWidgetItem):
        if item.column() != 0:
            return
        self.save_user_items()

    def save_user_items(self):
        for row in range(self.Table_UserItems.rowCount()):
            item_static = self.Table_UserItems.item(row, 0)
            static_text_item, user_item, regex = item_static.data(Qt.UserRole)
            self.text_changed(item_static,
                              user_item.id(),
                              self.Table_UserItems.cellWidget(row, 1).text())

    def group_box_toggled(self, box: QGroupBox, init: bool = False):

        text_global = self.tr_("Use global optios.")
        text_per_page = self.tr_("Page Options")

        if init:
            status = bool(self.edit_on.visibility.visibility)
            box.blockSignals(True)
            box.setChecked(status)
            self.group_box_toggled(box)
            box.blockSignals(False)
            return

        checked = box.isChecked()
        if box is self.GroupBox_Layers:
            if checked:
                self.Label_Layers.setText(text_per_page)
            else:
                self.Label_Layers.setText(text_global)
                self.edit_on.visibility.clear()

        self.reset_layer_view()

    def check_box_layers_clicked(self, model):
        """ a clickable checkbox clicked """
        table: QTableWidget = self.Table_Layers

        visibility = self.edit_on.visibility
        removed = False

        for row in range(table.rowCount()):

            # read current states from table
            item_overview = table.item(row, 0)
            item_legend = table.item(row, 1)
            item_page = table.item(row, 2)
            item_mini_map = table.item(row, 3)

            item_verti = table.verticalHeaderItem(row)
            layer_id = item_verti.data(Qt.UserRole)
            visibility[layer_id].overview = item_overview.checkState() == Qt.Checked
            visibility[layer_id].legend = item_legend.checkState() == Qt.Checked
            visibility[layer_id].page = item_page.checkState() == Qt.Checked
            visibility[layer_id].mini_map = item_mini_map.checkState() == Qt.Checked

        # remove no more available layers
        for layer_id in list(visibility.visibility):
            if QgsProject.instance().mapLayer(layer_id) is None:
                visibility.remove_layer(layer_id)
                removed = True

        # save changes
        visibility.sync()

        if removed:
            self.reset_layer_view()

    def reset_layer_view(self):
        table: QTableWidget = self.Table_Layers
        table.clear()

        if self.is_page_edit:
            if not self.edit_on.visibility.visibility and not self.GroupBox_Layers.isChecked():
                # resets to default empty dict to use global options
                self.GroupBox_Layers.blockSignals(True)
                self.GroupBox_Layers.setChecked(False)
                self.GroupBox_Layers.blockSignals(False)
                return

        table.setColumnCount(4)

        root: QgsLayerTree = QgsProject.instance().layerTreeRoot()

        # get all layers from current instance are visible in layer tree root and is not a plot layer
        # layers must be a valid map layer (connected source)
        layers = root.layerOrder()
        layers = [_ for _ in layers if root.findLayer(_) and not PlotLayer.is_plot_layer(_)]
        layers: List[QgsMapLayer] = [_ for _ in layers if isinstance(_, QgsMapLayer) and _.isValid()]
        layers: List[QgsMapLayer] = [_ for _ in layers if root.findLayer(_).itemVisibilityChecked()]
        layers: List[QgsMapLayer] = [_ for _ in layers if self.tr_("Legend") not in _.name()]
        table.setRowCount(len(layers))

        # clean up layers, wich are no more visible
        # hidden layers will be removed from visibility
        not_visible_layers = root.layerOrder()
        not_visible_layers = [_ for _ in not_visible_layers
                              if root.findLayer(_) and not PlotLayer.is_plot_layer(_)]
        not_visible_layers: List[QgsMapLayer] = [_ for _ in not_visible_layers
                                                 if isinstance(_, QgsMapLayer) and _.isValid()]
        not_visible_layers: List[QgsMapLayer] = [_ for _ in not_visible_layers
                                                 if not root.findLayer(_).itemVisibilityChecked()]
        for layer in not_visible_layers:
            self.edit_on.visibility.remove_layer(layer)
        self.edit_on.visibility.sync()

        visibility = self.edit_on.visibility

        # load headers
        item = QTableWidgetItem(self.tr_("Overview"))
        item.setData(Qt.ToolTipRole,
                     self.tr_("Plot Layer Option 'overview page' uses this."))
        table.setHorizontalHeaderItem(0, item)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        item = QTableWidgetItem(self.tr_("Legend"))
        item.setData(Qt.ToolTipRole,
                     self.tr_("Plot Layer Option 'legend on page' uses this."))
        table.setHorizontalHeaderItem(1, item)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        item = QTableWidgetItem(self.tr_("Page"))
        item.setData(Qt.ToolTipRole,
                     self.tr_("Show layer in page?"))
        table.setHorizontalHeaderItem(2, item)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        item = QTableWidgetItem("Mini Map")
        item.setData(Qt.ToolTipRole,
                     self.tr_("Show layer on Mini Map?"))
        table.setHorizontalHeaderItem(3, item)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        # loads layers to table widget
        table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for row, layer in enumerate(layers):
            layer_tree_item = root.findLayer(layer)

            # skip layer, completely hidden
            if not layer_tree_item.itemVisibilityChecked():
                continue

            layer_visibility = visibility[layer]

            # is child checked depending on parents?
            # if not, disable page in pages
            if not layer_tree_item.isVisible():
                layer_visibility.page = False
                layer_visibility.overview = False
                layer_visibility.legend = False
                layer_visibility.mini_map = False
                layer_visibility.sync()

            # use states from Visibility to check/uncheck layer specific settings
            item_overview = QTableWidgetItem()
            item_overview.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_overview.setCheckState(Qt.Checked if layer_visibility.overview else Qt.Unchecked)
            table.setItem(row, 0, item_overview)

            item_legend = QTableWidgetItem()
            item_legend.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_legend.setCheckState(Qt.Checked if layer_visibility.legend else Qt.Unchecked)
            table.setItem(row, 1, item_legend)

            item_page = QTableWidgetItem()
            item_page.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_page.setCheckState(Qt.Checked if layer_visibility.page else Qt.Unchecked)
            table.setItem(row, 2, item_page)

            item_mini_map = QTableWidgetItem()
            item_mini_map.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_mini_map.setCheckState(Qt.Checked if layer_visibility.mini_map else Qt.Unchecked)
            table.setItem(row, 3, item_mini_map)

            # vertical header item
            item_verti = QTableWidgetItem(layer.name())
            item_verti.setData(Qt.UserRole, layer.id())
            item_verti.setData(Qt.ToolTipRole,
                               f"{self.tr_('Layer ID:')} {layer.id()}\n"
                               f"{self.tr_('Layer Source:')} {layer.source()}\n"
                               f"{self.tr_('Layer visibility has only effect in this QGIS project.')}")
            table.setVerticalHeaderItem(row, item_verti)
            table.verticalHeader().setSectionResizeMode(row, QHeaderView.Interactive)
            table.verticalHeader().setMaximumWidth(175)
            table.verticalHeader().setMinimumWidth(10)

        table.resizeRowsToContents()
        table.resizeColumnsToContents()

        self.check_box_layers_clicked(None)

    def reset_user_item_view(self):
        """ resets table widget with all user editable fields """
        table: QTableWidget = self.Table_UserItems
        table.clear()
        table.setColumnCount(2)
        table.setRowCount(len(self.plot_layout.grouped_items))

        # loads header
        item_hori = QTableWidgetItem(self.tr_("Field"))
        table.setHorizontalHeaderItem(0, item_hori)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        item_hori = QTableWidgetItem(self.tr_("Value"))
        table.setHorizontalHeaderItem(1, item_hori)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

        # load each item for the user to edit
        options = self.edit_on.options
        for row, pair in enumerate(self.plot_layout.grouped_items.items()):
            key, value = pair

            static_text_item, user_item, option_map = value
            if self.is_page_edit:
                default_boolean = False
            else:
                default_boolean = True
            text, active = options.get(user_item.id(), ("", default_boolean))

            static_item = QTableWidgetItem(static_text_item.text())
            static_item.setData(Qt.UserRole, value)
            if self.is_page_edit:
                static_item.setFlags(Qt.NoItemFlags | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                static_item.setCheckState(Qt.Unchecked if not active else Qt.Checked)
            else:
                static_item.setFlags(Qt.NoItemFlags | Qt.ItemIsEnabled)
            regex = option_map.get("*", "")
            tooltip = option_map.get("#", "")
            static_item.setFlags(static_item.flags() & ~Qt.ItemIsEditable)
            static_item.setToolTip(f"{self.tr_('Layout ID')} ({self.tr_('description')}): {static_text_item.id()}\n"
                                   f"{self.tr_('Layout ID')} ({self.tr_('field')}): {user_item.id()}\n"
                                   f"{self.tr_('pattern')}: {regex if regex else {self.tr_('none')}}\n\n")
            if tooltip:
                static_item.setToolTip(tooltip + "\n" + static_item.toolTip())

            line_edit = QLineEdit()
            line_edit.setText(str(text))
            line_edit.setClearButtonEnabled(True)
            if regex:
                qre = QRegExp(regex)
                validator = QRegExpValidator(qre)
                line_edit.setValidator(validator)
                ttip = f", {tooltip}" if tooltip else ""
                line_edit.setPlaceholderText(f"{self.tr_('optional')}{ttip}, {self.tr_('pattern')}: {regex}")
            else:
                ttip = f", {tooltip}" if tooltip else ""
                line_edit.setPlaceholderText(self.tr_('optional') + ttip)

            line_edit.setToolTip(static_item.toolTip())
            line_edit.editingFinished.connect(lambda edit=line_edit, item_id=user_item.id(), check_item=static_item:
                                              self.text_changed(check_item, item_id, edit.text()))

            table.setItem(row, 0, static_item)
            table.setCellWidget(row, 1, line_edit)

        self.save_user_items()

    def text_changed(self, check_item: QTableWidgetItem, item_name: str, new_text_value: str):
        """ change text value on page or global """
        options = self.edit_on.options
        if self.is_page_edit:
            # page options
            use_local = check_item.checkState() == Qt.Checked
        else:
            # global options
            use_local = False

        options[item_name] = (new_text_value, use_local)
        self.edit_on.options = options

    def reset_ui(self):
        self.group_box_toggled(self.GroupBox_Layers, init=True)
        self.reset_user_item_view()

        self.CheckBox_MiniMap.setCheckState(Qt.Checked if self.edit_on.show_mini_map
                                            else Qt.Unchecked)

        self.CheckBox_MiniPageLegend.setCheckState(Qt.Checked if self.edit_on.show_legend_on_page
                                                   else Qt.Unchecked)

        self.CheckBox_ShowMapTips.setCheckState(Qt.Checked if self.edit_on.show_map_tips
                                                else Qt.Unchecked)

    def close(self, *args, **kwargs):
        QMainWindow.close(self)

    def closeEvent(self, event) -> None:
        event.accept()
        self.unload(True)

    def key_f5_reset(self):
        # reset to current view
        self.edit_on.visibility.clear()
        self.edit_on.visibility.sync()
        self.reset_layer_view()

    def keyReleaseEvent(self, event):
        """ user presses button """
        pressed_key = event.key()

        if pressed_key == Qt.Key_Escape:
            self.close()

        if pressed_key == Qt.Key_F5:
            self.key_f5_reset()

        event.accept()

    @property
    def is_page_edit(self) -> bool:
        """ True, if current layout menu is to edit page options """
        return isinstance(self.edit_on, PlotPage)
