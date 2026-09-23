# -----------------------------------------------------------------------
# Road Centerline Extractor - QGIS Processing algorithm
#
# Copyright (C) 2026 Roberto Geraldes
# Licensed under the GNU General Public License v2 or later.
# -----------------------------------------------------------------------

import json
import os

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsUnitTypes,
    QgsWkbTypes,
)

UNIT_LABELS = ['Meters (m)', 'Kilometers (km)', 'Miles (mi)', 'Feet (ft)']
UNIT_SHORT = ['m', 'km', 'mi', 'ft']
UNIT_FACTOR = [1.0, 0.001, 1.0 / 1609.344, 3.28084]


class ExtractCenterlinesAlgorithm(QgsProcessingAlgorithm):
    """Extracts cleaned, optionally junction-segmented centerlines
    from corridor-shaped polygons."""

    INPUT = 'INPUT'
    SEGMENT_AT_JUNCTIONS = 'SEGMENT_AT_JUNCTIONS'
    MIN_WIDTH = 'MIN_WIDTH'
    SPUR_LENGTH = 'SPUR_LENGTH'
    EXTEND_TO_BOUNDARY = 'EXTEND_TO_BOUNDARY'
    LENGTH_UNIT = 'LENGTH_UNIT'
    OUTPUT = 'OUTPUT'

    # -- boilerplate -----------------------------------------------------

    def tr(self, string):
        return QCoreApplication.translate('ExtractCenterlinesAlgorithm',
                                          string)

    def createInstance(self):
        return ExtractCenterlinesAlgorithm()

    def name(self):
        return 'extractcenterlines'

    def displayName(self):
        return self.tr('Extract Centerlines')

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))

    def shortHelpString(self):
        return self.tr(
            'Extracts centerlines from corridor-shaped polygons (roads, '
            'rivers, or similar elongated networks) using Voronoi-based '
            'skeleton extraction.\n\n'
            '<b>Segment at T-junctions:</b> if enabled, the output is '
            'split into individual features at junctions, so each section '
            'between two nodes can be classified separately. If disabled, '
            'each input polygon produces a single multipart feature.\n\n'
            '<b>Minimum width:</b> sections of the polygon narrower than '
            'this value are excluded from the output. It does not affect '
            'the shape or resolution of the extracted centerline - only '
            'which sections are kept. Set to 0 to disable.\n\n'
            '<b>Spur pruning length:</b> branches shorter than this are '
            'removed (skeleton artefacts near irregular boundaries). '
            'A width-relative safety floor is always applied on top of '
            'this value: a branch shorter than roughly one polygon width '
            'is treated as noise and removed even when longer than this '
            'setting, since genuine branches are typically many widths '
            'long. Set to 0 to rely on that floor alone.\n\n'
            '<b>Extend tips to polygon boundary:</b> if enabled, dead-end '
            'tips are stretched to touch the polygon boundary exactly, '
            'maximizing how much of the network is covered. If disabled '
            '(default), tips are left at the last genuine skeleton point, '
            'which is equidistant from the polygon walls that produced '
            'it - trading a small amount of coverage at each dead end for '
            'centering accuracy that holds all the way to the tip.\n\n'
            'The input layer must use a projected CRS. Width and pruning '
            'parameters are interpreted in the layer\'s map units.'
        )

    # -- parameters ------------------------------------------------------

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT,
            self.tr('Input polygon layer'),
            [QgsProcessing.SourceType.TypeVectorPolygon]))

        self.addParameter(QgsProcessingParameterBoolean(
            self.SEGMENT_AT_JUNCTIONS,
            self.tr('Segment at T-junctions and intersections'),
            defaultValue=True))

        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_WIDTH,
            self.tr('Minimum width (map units, 0 = disabled)'),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=4.0,
            minValue=0.0))

        self.addParameter(QgsProcessingParameterNumber(
            self.SPUR_LENGTH,
            self.tr('Spur pruning length (map units, 0 = disabled)'),
            QgsProcessingParameterNumber.Type.Double,
            defaultValue=9.0,
            minValue=0.0))

        self.addParameter(QgsProcessingParameterBoolean(
            self.EXTEND_TO_BOUNDARY,
            self.tr('Extend tips to polygon boundary '
                    '(maximizes coverage, reduces centering accuracy '
                    'at dead ends)'),
            defaultValue=False))

        self.addParameter(QgsProcessingParameterEnum(
            self.LENGTH_UNIT,
            self.tr('Report length in'),
            options=[self.tr(u) for u in UNIT_LABELS],
            defaultValue=0))

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT,
            self.tr('Centerlines')))

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _check_dependencies():
        missing = []
        try:
            import shapely  # noqa: F401
        except ImportError:
            missing.append('shapely')
        try:
            import networkx  # noqa: F401
        except ImportError:
            missing.append('networkx')
        try:
            import centerline  # noqa: F401
        except ImportError:
            missing.append('centerline')
        if missing:
            raise QgsProcessingException(
                'Missing required Python package(s): {}. Install them in '
                'the QGIS Python environment, e.g.: pip install {}'.format(
                    ', '.join(missing), ' '.join(missing)))

    @staticmethod
    def _validate_crs(source, feedback):
        crs = source.sourceCrs()
        if not crs.isValid():
            raise QgsProcessingException(
                'The input layer has no valid CRS assigned.')
        if crs.isGeographic():
            raise QgsProcessingException(
                'The input layer uses a geographic CRS (degrees). '
                'Reproject it to a projected, metric CRS before running - '
                'width and pruning parameters are interpreted in the '
                'layer\'s map units.')
        if crs.mapUnits() != QgsUnitTypes.DistanceUnit.DistanceMeters:
            feedback.pushWarning(
                'The input CRS units are not meters ({}). Width and '
                'pruning parameters will be interpreted in the layer\'s '
                'map units.'.format(
                    QgsUnitTypes.toString(crs.mapUnits())))

    # -- execution -------------------------------------------------------

    def processAlgorithm(self, parameters, context, feedback):
        self._check_dependencies()

        from shapely.geometry import shape
        from .core import CenterlineCore, ProcessingCanceled

        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.INPUT))

        self._validate_crs(source, feedback)

        segment = self.parameterAsBoolean(
            parameters, self.SEGMENT_AT_JUNCTIONS, context)
        min_width = self.parameterAsDouble(
            parameters, self.MIN_WIDTH, context)
        spur_length = self.parameterAsDouble(
            parameters, self.SPUR_LENGTH, context)
        extend_to_boundary = self.parameterAsBoolean(
            parameters, self.EXTEND_TO_BOUNDARY, context)
        unit_idx = self.parameterAsEnum(
            parameters, self.LENGTH_UNIT, context)

        unit_short = UNIT_SHORT[unit_idx]
        unit_factor = UNIT_FACTOR[unit_idx]

        fields = QgsFields()
        fields.append(QgsField('orig_id', QVariant.LongLong))
        fields.append(QgsField('length_{}'.format(unit_short),
                               QVariant.Double))

        wkb_type = (QgsWkbTypes.Type.LineString if segment
                    else QgsWkbTypes.Type.MultiLineString)
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            wkb_type, source.sourceCrs())
        if sink is None:
            raise QgsProcessingException(
                self.invalidSinkError(parameters, self.OUTPUT))

        core = CenterlineCore(
            spur_min_length=spur_length,
            min_width=min_width,
            extend_to_boundary=extend_to_boundary,
            is_canceled=feedback.isCanceled)

        total = source.featureCount()
        done = 0
        skipped = 0

        feedback.pushInfo('Processing {} polygon(s)...'.format(total))

        for i, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            try:
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    skipped += 1
                    continue

                shapely_geom = shape(json.loads(geom.asJson()))
                parts = core.process_polygon(shapely_geom)

                if not parts:
                    skipped += 1
                    continue

                if segment:
                    for part in parts:
                        out = QgsFeature(fields)
                        qgs_line = QgsGeometry.fromPolylineXY(
                            [QgsPointXY(x, y) for x, y in part.coords])
                        out.setGeometry(qgs_line)
                        out.setAttributes([
                            feat.id(),
                            round(qgs_line.length() * unit_factor, 4)])
                        sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)
                else:
                    out = QgsFeature(fields)
                    qgs_multi = QgsGeometry.fromMultiPolylineXY(
                        [[QgsPointXY(x, y) for x, y in part.coords]
                         for part in parts])
                    out.setGeometry(qgs_multi)
                    out.setAttributes([
                        feat.id(),
                        round(qgs_multi.length() * unit_factor, 4)])
                    sink.addFeature(out, QgsFeatureSink.Flag.FastInsert)

                done += 1

            except ProcessingCanceled:
                break
            except Exception as exc:  # keep going on per-feature errors
                skipped += 1
                feedback.pushWarning(
                    'Skipped feature {}: {}'.format(feat.id(), exc))

            feedback.setProgress(int((i + 1) / total * 100))

        feedback.pushInfo(
            'Done. Processed: {}, skipped: {}.'.format(done, skipped))
        return {self.OUTPUT: dest_id}
