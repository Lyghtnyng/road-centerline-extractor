# -----------------------------------------------------------------------
# Road Centerline Extractor - plugin entry point (Processing-only plugin
# from v2.0.0 onward; the interactive dialog has been retired in favour
# of a Processing Toolbox algorithm - see README for details)
#
# Copyright (C) 2026 Roberto Geraldes
# Licensed under the GNU General Public License v2 or later.
# -----------------------------------------------------------------------

from qgis.core import QgsApplication

from .provider import RoadCenterlineExtractorProvider


class RoadCenterlineExtractorPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        self.provider = RoadCenterlineExtractorProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()

    def unload(self):
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
