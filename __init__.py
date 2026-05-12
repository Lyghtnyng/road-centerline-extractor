# Copyright (C) 2026 Roberto Geraldes <rob.filipe007@hotmail.com>
# Road Centerline Extractor - QGIS Plugin
# Licensed under GNU GPL v2 or later
def classFactory(iface):
    from .plugin import RoadCenterlinePlugin
    return RoadCenterlinePlugin(iface)