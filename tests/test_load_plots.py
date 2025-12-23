# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2025 Deutsche Telekom Technik GmbH <f.vonstudsinske@telekom.de>
# SPDX-License-Identifier: GPL-3.0-only

from pathlib import Path

from ..submodules.base.qgis.plot_layout_templates import PlotLayoutTemplates


def test_load_plots():

    # load the basic template from the "test_plot" folder
    templates = PlotLayoutTemplates()
    templates.plots.append(Path(__file__).parent.parent / "templates/plots/public")
    templates.load_plots()
    templates.load_layouts()

    # test, if all templates are loaded
    templates["public/A4_Landscape.qpt"]
    templates["public/A4_Portrait.qpt"]
