# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only

import os
from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication as QgisApp  # Alias to prevent import error below ...

from ..plugin import PluginPlot
from ..modules.plot.plot_menu import PlotMenu


def load_tool_bar(plugin: PluginPlot):
    """ loads default action for your plugin """

    # load translation
    language = QgisApp.instance().locale()

    plugin.install_translator(str(Path(__file__).parent.parent / "i18n" / f"translation_{language}.qm"))
    plugin.install_translator(str(Path(__file__).parent.parent / "i18n" / f"messages_{language}.qm"))

    tr_ = lambda text: QgisApp.translate("QgsApplication", text)
    icon = QIcon(plugin.get_icon_path("icon.svg"))
    plugin.add_action(tr_("Open Print Menu"),
                      icon,
                      lambda x=1: PlotMenu.load(plugin),
                      toolbar_name="qgis_plot_plugin",
                      toolbar_displayname=tr_("Print Menu"))

    # create composer_templates directory, if not exists
    composer_templates = QgisApp.instance().qgisSettingsDirPath() + "/composer_templates"
    Path(composer_templates).mkdir(parents=True, exist_ok=True)

    if os.name == "posix":
        path = Path(plugin.plugin_dir) / "templates" / "plots"
        plugin.add_action(tr_("Open templates folder") + " (QGIS Plot Plugin, 'plots')",
                          QIcon(),
                          lambda x=1: os.system(f'xdg-open "{path}"'))

        plugin.add_action(tr_("Open templates folder") + " (QGIS profile, 'composer_templates')",
                          QIcon(),
                          lambda x=1: os.system(f'xdg-open "{composer_templates}"'))

    if os.name == "nt":
        # Windows
        from subprocess import Popen

        path = Path(plugin.plugin_dir) / "templates" / "plots"
        plugin.add_action(tr_("Open templates folder") + " (QGIS Plot Plugin, 'plots')",
                          QIcon(),
                          lambda x=1: Popen(r'explorer /select,"{}"'.format(path)))

        # convert the composer path to a Windows path ...
        path_qgis = Path(composer_templates).as_posix()
        path_qgis = path_qgis.replace("/", "\\")
        plugin.add_action(tr_("Open templates folder") + " (QGIS Benutzerprofil, 'composer_templates')",
                          QIcon(),
                          lambda x=1: Popen(r'explorer /select,"{}"'.format(path_qgis)))


def init_plugin(plugin: PluginPlot):
    """ Loads/calls some function in plugins class __init__-method.
        Maybe no ui is active from qgis (e.g. start process).

        WARNING: Do not setup UI elements or interact with them here! Use `load_tool_bar` instead.
    """
    # Plot
    plugin.plots_dir = str(Path(plugin.plugin_dir) / "templates" / "plots")


def init_plugin_gui(plugin: PluginPlot):
    """ Run code, when the QGIS ui is guaranteed available. """
    pass
