# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only
"""UI for configuring global plot-layout and page-specific options."""

from qgis.PyQt.QtWidgets import (
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QGroupBox,
    QHeaderView,
    QCheckBox,
)
from qgis.PyQt.QtCore import pyqtSignal, Qt, QRegExp
from qgis.PyQt.QtGui import QRegExpValidator

from qgis.core import QgsProject, QgsLayerTree, QgsMapLayer, QgsApplication
from typing import Union, List

from ...submodules.base.qgis.plot_layout import PlotLayout
from ...submodules.base.qgis.plot_layer import PlotLayer, PlotPage
from ...submodules.base.ui.base_class import UiModuleBase

FORM_CLASS, _ = UiModuleBase.get_uic_classes(__file__)


class PlotLayoutMenu(UiModuleBase, QMainWindow, FORM_CLASS):
    """Configure layer visibility, display options, and editable layout fields."""

    saved = pyqtSignal(name="saved")

    def __init__(
        self,
        plot_layout: PlotLayout = None,
        plot_layer: PlotLayer = None,
        edit: Union[PlotLayer, PlotPage] = None,
        **kwargs,
    ):
        """Initialize the menu for either global layout options or one page.

        ``plot_layout`` supplies the layout fields, ``plot_layer`` identifies the
        owning plot layer, and ``edit`` is the layout or page whose options are edited.
        """
        UiModuleBase.__init__(self, **kwargs)
        QMainWindow.__init__(self, kwargs.get("parent"))

        self.setupUi(self)

        self.plot_layout: PlotLayout = plot_layout
        self.plot_layer: PlotLayer = plot_layer
        self.edit_on = edit
        if not self.__is_page_edit:
            # menu for global options
            self.Label_Title.setText(f"{self.plot_layer.layer_pages.name()} - {self.plot_layout.name}")
            self.GroupBox_Layers.setChecked(True)
        else:
            self.Label_Title.setText(
                f"{self.__translate('Page')} {self.edit_on.page} - "
                f"{self.plot_layout.get_parent()[self.edit_on.file].name}"
            )
        if not isinstance(self.plot_layout, PlotLayout):
            raise TypeError(f"plot_layout({self.plot_layout}) is not given")

        self.connect(
            self.GroupBox_Layers.toggled,
            lambda *_: self.__on_layer_option_scope_changed(self.GroupBox_Layers)
        )
        self.connect(self.Table_UserItems.itemClicked, self.__on_user_field_option_clicked)
        self.connect(self.Table_Layers.clicked, lambda *_: self.__sync_layer_visibility_from_table())
        self.connect(
            self.CheckBox_MiniMap.stateChanged,
            lambda *_: self.__on_display_option_changed(self.CheckBox_MiniMap)
        )
        self.connect(
            self.CheckBox_ShowMapTips.stateChanged,
            lambda *_: self.__on_display_option_changed(self.CheckBox_ShowMapTips),
        )
        self.connect(
            self.CheckBox_MiniPageLegend.stateChanged,
            lambda *_: self.__on_display_option_changed(self.CheckBox_MiniPageLegend),
        )

        if self.plot_layout.item_minimap is None:
            self.CheckBox_MiniMap.setEnabled(False)
            self.CheckBox_MiniMap.blockSignals(True)
            self.CheckBox_MiniMap.setText(
                f"{self.CheckBox_MiniMap.text()} {self.__translate('(not available in this layout)')}"
            )

        self.__load_options_into_ui()

        self.initialize_tab_stop_widgets()

    @classmethod
    def __translate(cls, text: str):
        """Translate a user-visible string in the QGIS application context."""
        return QgsApplication.translate("QgsApplication", text)

    def __on_display_option_changed(self, box: QCheckBox):
        """Write a changed display checkbox value to the edited layout or page."""
        if box is self.CheckBox_MiniMap:
            self.edit_on.show_mini_map = Qt.Checked == self.CheckBox_MiniMap.checkState()

        if box is self.CheckBox_ShowMapTips:
            self.edit_on.show_map_tips = Qt.Checked == self.CheckBox_ShowMapTips.checkState()

        if box is self.CheckBox_MiniPageLegend:
            self.edit_on.show_legend_on_page = Qt.Checked == self.CheckBox_MiniPageLegend.checkState()

    def __on_user_field_option_clicked(self, item: QTableWidgetItem):
        """Persist field options when a user toggles a field's local-use checkbox."""
        if item.column() != 0:
            return
        self.__persist_user_field_options()

    def __persist_user_field_options(self):
        """Save every field's displayed text and local-use state to the edited object."""
        for row in range(self.Table_UserItems.rowCount()):
            item_static = self.Table_UserItems.item(row, 0)
            _, user_item, _ = item_static.data(Qt.UserRole)
            self.__save_user_field_option(item_static, user_item.id(), self.Table_UserItems.cellWidget(row, 1).text())

    def __on_layer_option_scope_changed(self, box: QGroupBox, init: bool = False):
        """Update global/page layer-option mode and refresh its visibility table.

        During initialization, restore the mode from the edited object's current
        visibility overrides. Disabling page-specific mode clears those overrides.
        """

        text_global = self.__translate("Use global optios.")
        text_per_page = self.__translate("Page Options")

        if init:
            status = bool(self.edit_on.visibility.visibility)
            box.blockSignals(True)
            box.setChecked(status)
            self.__on_layer_option_scope_changed(box)
            box.blockSignals(False)
            return

        checked = box.isChecked()
        if box is self.GroupBox_Layers:
            if checked:
                self.Label_Layers.setText(text_per_page)
            else:
                self.Label_Layers.setText(text_global)
                self.edit_on.visibility.clear()

        self.refresh_layer_visibility_table()

    def __sync_layer_visibility_from_table(self):
        """Copy table checkbox values to visibility settings and synchronize them."""
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
            self.refresh_layer_visibility_table()

    def refresh_layer_visibility_table(self):
        """Rebuild the layer table and synchronize visibility with the project tree.

        This also removes overrides for layers that are hidden or no longer present.
        """
        table: QTableWidget = self.Table_Layers
        table.clear()

        if self.__is_page_edit and not self.edit_on.visibility.visibility and not self.GroupBox_Layers.isChecked():
            # An empty page override map means that the page inherits global options.
            self.GroupBox_Layers.blockSignals(True)
            self.GroupBox_Layers.setChecked(False)
            self.GroupBox_Layers.blockSignals(False)
            return

        table.setColumnCount(4)

        root: QgsLayerTree = QgsProject.instance().layerTreeRoot()

        layers = self.__get_visible_project_layers(root)
        table.setRowCount(len(layers))

        visibility = self.edit_on.visibility
        self.__remove_hidden_layer_overrides(root)
        self.__set_layer_visibility_headers(table)
        self.__populate_layer_visibility_rows(table, root, layers, visibility)

        table.resizeRowsToContents()
        table.resizeColumnsToContents()

        self.__sync_layer_visibility_from_table()

    def __get_visible_project_layers(self, root: QgsLayerTree) -> List[QgsMapLayer]:
        """Return valid, visible, non-plot project layers, excluding generated legends."""
        layers = root.layerOrder()
        layers = [_ for _ in layers if root.findLayer(_) and not PlotLayer.is_plot_layer(_)]
        layers: List[QgsMapLayer] = [_ for _ in layers if isinstance(_, QgsMapLayer) and _.isValid()]
        layers = [_ for _ in layers if root.findLayer(_).itemVisibilityChecked()]
        return [_ for _ in layers if self.__translate("Legend") not in _.name()]

    def __remove_hidden_layer_overrides(self, root: QgsLayerTree):
        """Remove visibility overrides for valid project layers hidden in the layer tree."""
        hidden_layers = root.layerOrder()
        hidden_layers = [_ for _ in hidden_layers if root.findLayer(_) and not PlotLayer.is_plot_layer(_)]
        hidden_layers: List[QgsMapLayer] = [_ for _ in hidden_layers if isinstance(_, QgsMapLayer) and _.isValid()]
        hidden_layers = [_ for _ in hidden_layers if not root.findLayer(_).itemVisibilityChecked()]
        for layer in hidden_layers:
            self.edit_on.visibility.remove_layer(layer)
        self.edit_on.visibility.sync()

    def __set_layer_visibility_headers(self, table: QTableWidget):
        """Set labels, tooltips, and sizing for the four visibility columns."""
        item = QTableWidgetItem(self.__translate("Overview"))
        item.setData(Qt.ToolTipRole, self.__translate("Plot Layer Option 'overview page' uses this."))
        table.setHorizontalHeaderItem(0, item)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        item = QTableWidgetItem(self.__translate("Legend"))
        item.setData(Qt.ToolTipRole, self.__translate("Plot Layer Option 'legend on page' uses this."))
        table.setHorizontalHeaderItem(1, item)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        item = QTableWidgetItem(self.__translate("Page"))
        item.setData(Qt.ToolTipRole, self.__translate("Show layer in page?"))
        table.setHorizontalHeaderItem(2, item)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        item = QTableWidgetItem("Mini Map")
        item.setData(Qt.ToolTipRole, self.__translate("Show layer on Mini Map?"))
        table.setHorizontalHeaderItem(3, item)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

    def __populate_layer_visibility_rows(
        self, table: QTableWidget, root: QgsLayerTree, layers: List[QgsMapLayer], visibility
    ):
        """Populate one table row per layer with its saved plot visibility settings."""
        table.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for row, layer in enumerate(layers):
            layer_tree_item = root.findLayer(layer)

            # Skip layers hidden by their own checkbox; ancestor visibility is checked below.
            if not layer_tree_item.itemVisibilityChecked():
                continue

            layer_visibility = visibility[layer]

            # A layer can be checked itself but effectively hidden by an unchecked ancestor.
            # In that case disable all of its plot visibility options.
            if not layer_tree_item.isVisible():
                layer_visibility.page = False
                layer_visibility.overview = False
                layer_visibility.legend = False
                layer_visibility.mini_map = False
                layer_visibility.sync()

            # Populate the per-layer plot visibility options from the saved settings.
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
            item_verti.setData(
                Qt.ToolTipRole,
                f"{self.__translate('Layer ID:')} {layer.id()}\n"
                f"{self.__translate('Layer Source:')} {layer.source()}\n"
                f"{self.__translate('Layer visibility has only effect in this QGIS project.')}",
            )
            table.setVerticalHeaderItem(row, item_verti)
            table.verticalHeader().setSectionResizeMode(row, QHeaderView.Interactive)
            table.verticalHeader().setMaximumWidth(175)
            table.verticalHeader().setMinimumWidth(10)

    def __populate_user_fields_table(self):
        """Build the editable-field table from the current layout and saved options."""
        table: QTableWidget = self.Table_UserItems
        table.clear()
        table.setColumnCount(2)
        table.setRowCount(len(self.plot_layout.grouped_items))

        # loads header
        item_hori = QTableWidgetItem(self.__translate("Field"))
        table.setHorizontalHeaderItem(0, item_hori)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        item_hori = QTableWidgetItem(self.__translate("Value"))
        table.setHorizontalHeaderItem(1, item_hori)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

        # Load each item for the user to edit.
        options = self.edit_on.options
        for row, value in enumerate(self.plot_layout.grouped_items.values()):
            self.__populate_user_field_row(table, row, value, options)

        self.__persist_user_field_options()

    def __populate_user_field_row(self, table: QTableWidget, row: int, value, options):
        """Create the label and editor widgets for one user-editable layout field."""
        static_text_item, user_item, option_map = value
        default_active = not self.__is_page_edit
        text, active = options.get(user_item.id(), ("", default_active))

        static_item = QTableWidgetItem(static_text_item.text())
        static_item.setData(Qt.UserRole, value)
        if self.__is_page_edit:
            static_item.setFlags(Qt.NoItemFlags | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            static_item.setCheckState(Qt.Checked if active else Qt.Unchecked)
        else:
            static_item.setFlags(Qt.NoItemFlags | Qt.ItemIsEnabled)
        regex = option_map.get("*", "")
        tooltip = option_map.get("#", "")
        static_item.setFlags(static_item.flags() & ~Qt.ItemIsEditable)
        static_item.setToolTip(
            f"{self.__translate('Layout ID')} ({self.__translate('description')}): "
            f"{static_text_item.id()}\n"
            f"{self.__translate('Layout ID')} ({self.__translate('field')}): "
            f"{user_item.id()}\n"
            f"{self.__translate('pattern')}: {regex or self.__translate('none')}\n\n"
        )
        if tooltip:
            static_item.setToolTip(tooltip + "\n" + static_item.toolTip())

        line_edit = QLineEdit()
        line_edit.setText(str(text))
        line_edit.setClearButtonEnabled(True)
        tooltip_suffix = f", {tooltip}" if tooltip else ""
        if regex:
            line_edit.setValidator(QRegExpValidator(QRegExp(regex)))
            line_edit.setPlaceholderText(
                f"{self.__translate('optional')}{tooltip_suffix}, {self.__translate('pattern')}: {regex}"
            )
        else:
            line_edit.setPlaceholderText(self.__translate("optional") + tooltip_suffix)

        line_edit.setToolTip(static_item.toolTip())
        line_edit.editingFinished.connect(
            lambda edit=line_edit, item_id=user_item.id(), check_item=static_item: self.__save_user_field_option(
                check_item, item_id, edit.text()
            )
        )
        table.setItem(row, 0, static_item)
        table.setCellWidget(row, 1, line_edit)

    def __save_user_field_option(self, check_item: QTableWidgetItem, item_name: str, new_text_value: str):
        """Save a field's text and whether a page overrides the global value."""
        options = self.edit_on.options
        # On pages, the checkbox marks a local override; global values are defaults.
        use_local = self.__is_page_edit and check_item.checkState() == Qt.Checked

        options[item_name] = (new_text_value, use_local)
        self.edit_on.options = options

    def __load_options_into_ui(self):
        """Populate the controls from the current layout or page options."""
        self.__on_layer_option_scope_changed(self.GroupBox_Layers, init=True)
        self.__populate_user_fields_table()

        self.CheckBox_MiniMap.setCheckState(Qt.Checked if self.edit_on.show_mini_map else Qt.Unchecked)

        self.CheckBox_MiniPageLegend.setCheckState(Qt.Checked if self.edit_on.show_legend_on_page else Qt.Unchecked)

        self.CheckBox_ShowMapTips.setCheckState(Qt.Checked if self.edit_on.show_map_tips else Qt.Unchecked)

    def closeEvent(self, event) -> None:
        """Accept the close event and unload this UI module."""
        event.accept()
        self.unload(True)

    def reset_layer_visibility(self):
        """Clear layer overrides and rebuild them from the current project view."""
        self.edit_on.visibility.clear()
        self.edit_on.visibility.sync()
        self.refresh_layer_visibility_table()

    def keyReleaseEvent(self, event):
        """Handle Escape to close the menu and F5 to reset layer visibility."""
        pressed_key = event.key()

        if pressed_key == Qt.Key_Escape:
            self.close()

        if pressed_key == Qt.Key_F5:
            self.reset_layer_visibility()

        event.accept()

    @property
    def __is_page_edit(self) -> bool:
        """Whether this menu edits page-specific rather than global options."""
        return isinstance(self.edit_on, PlotPage)
