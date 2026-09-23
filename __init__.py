# -----------------------------------------------------------------------
# Road Centerline Extractor
#
# Copyright (C) 2026 Roberto Geraldes
# Licensed under the GNU General Public License v2 or later.
# -----------------------------------------------------------------------


def classFactory(iface):
    from .plugin import RoadCenterlineExtractorPlugin
    return RoadCenterlineExtractorPlugin(iface)
