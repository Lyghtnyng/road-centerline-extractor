# -----------------------------------------------------------------------
# Road Centerline Extractor - Processing provider
#
# Copyright (C) 2026 Roberto Geraldes
# Licensed under the GNU General Public License v2 or later.
# -----------------------------------------------------------------------

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithm import ExtractCenterlinesAlgorithm


class RoadCenterlineExtractorProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        self.addAlgorithm(ExtractCenterlinesAlgorithm())

    def id(self):
        return 'roadcenterlineextractor'

    def name(self):
        return 'Road Centerline Extractor'

    def longName(self):
        return self.name()

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))
