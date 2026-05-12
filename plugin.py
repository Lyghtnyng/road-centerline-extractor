# Copyright (C) 2026 Roberto Geraldes <rob.filipe007@hotmail.com>
# Road Centerline Extractor - QGIS Plugin
# Licensed under GNU GPL v2 or later
import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .dialog import RoadCenterlineDialog


class RoadCenterlinePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        icon = QIcon(icon_path)
        self.action = QAction(icon, 'Road Centerline Extractor', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu('Road Centerline Extractor', self.action)

    def unload(self):
        self.iface.removePluginVectorMenu('Road Centerline Extractor', self.action)
        self.iface.removeToolBarIcon(self.action)
        del self.action

    def run(self):
        if self.dialog is None:
            self.dialog = RoadCenterlineDialog(self.iface)
        self.dialog.refresh_layers()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()