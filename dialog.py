# Copyright (C) 2026 Roberto Geraldes <rob.filipe007@hotmail.com>
# Road Centerline Extractor - QGIS Plugin
# Licensed under GNU GPL v2 or later
import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFileDialog, QLineEdit, QProgressBar,
    QTextEdit, QGroupBox, QDoubleSpinBox, QCheckBox,
    QSizePolicy, QMessageBox
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.core import QgsProject, QgsMapLayer, QgsVectorLayer, QgsWkbTypes
from .processor import CenterlineProcessor


class WorkerThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, layer, output_path, spur_min_length, road_width, add_to_project, unit_factor, unit_short):
        super().__init__()
        self.layer = layer
        self.output_path = output_path
        self.spur_min_length = spur_min_length
        self.road_width = road_width
        self.add_to_project = add_to_project
        self.unit_factor = unit_factor
        self.unit_short = unit_short

    def run(self):
        try:
            processor = CenterlineProcessor(
                layer=self.layer,
                output_path=self.output_path,
                spur_min_length=self.spur_min_length,
                road_width=self.road_width,
                unit_factor=self.unit_factor,
                unit_short=self.unit_short,
                progress_callback=self.progress.emit
            )
            processor.run()
            self.finished.emit(True, "")
        except Exception as e:
            import traceback
            self.finished.emit(False, traceback.format_exc())


class RoadCenterlineDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.worker = None
        self.setWindowTitle('Road Centerline Extractor')
        self.setMinimumWidth(480)
        self.setMinimumHeight(620)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # --- Title ---
        title = QLabel('Road Centerline Extractor')
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel('Convert road polygons to clean centerlines')
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet('color: gray; margin-bottom: 8px;')
        main_layout.addWidget(subtitle)

        # --- Input group ---
        input_group = QGroupBox('Input')
        input_layout = QVBoxLayout()
        input_layout.setSpacing(8)
        input_layout.addWidget(QLabel('Polygon layer:'))
        self.layer_combo = QComboBox()
        self.layer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        input_layout.addWidget(self.layer_combo)
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)

        # --- Settings group ---
        settings_group = QGroupBox('Settings')
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(10)

        # Road minimum width
        road_width_row = QHBoxLayout()
        road_width_label = QLabel('Minimum road width (meters):')
        road_width_label.setToolTip(
            'The minimum width of your road polygons in meters.\n'
            'Used to control skeleton resolution — a smaller value\n'
            'gives a finer skeleton, a larger value gives a coarser one.\n'
            'Set this to the actual width of your narrowest road.\n'
            'Example: if your narrowest road is 4m wide, enter 4.0'
        )
        road_width_row.addWidget(road_width_label)
        self.road_width_spin = QDoubleSpinBox()
        self.road_width_spin.setRange(0.5, 1000.0)
        self.road_width_spin.setValue(4.0)
        self.road_width_spin.setSingleStep(0.5)
        self.road_width_spin.setDecimals(1)
        self.road_width_spin.setFixedWidth(90)
        self.road_width_spin.setToolTip(road_width_label.toolTip())
        road_width_row.addWidget(self.road_width_spin)
        settings_layout.addLayout(road_width_row)

        road_width_hint = QLabel('Tip: measure the width of your narrowest road in QGIS')
        road_width_hint.setStyleSheet('color: #666; font-size: 10px;')
        road_width_hint.setWordWrap(True)
        settings_layout.addWidget(road_width_hint)

        # Separator line
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet('background-color: #ddd; margin: 2px 0;')
        settings_layout.addWidget(sep)

        # Spur pruning length
        spur_row = QHBoxLayout()
        spur_label = QLabel('Spur pruning length (map units):')
        spur_label.setToolTip(
            'Dead-end branches shorter than this value will be removed.\n'
            'Set to approximately 1.5x your road polygon width.\n'
            'Example: if roads are ~6m wide, use 9.0'
        )
        spur_row.addWidget(spur_label)
        self.spur_spin = QDoubleSpinBox()
        self.spur_spin.setRange(0.1, 10000.0)
        self.spur_spin.setValue(9.0)
        self.spur_spin.setSingleStep(0.5)
        self.spur_spin.setDecimals(1)
        self.spur_spin.setFixedWidth(90)
        self.spur_spin.setToolTip(spur_label.toolTip())
        spur_row.addWidget(self.spur_spin)
        settings_layout.addLayout(spur_row)

        spur_hint = QLabel('Tip: road width x 1.5  (example: 6m road -> use 9.0)')
        spur_hint.setStyleSheet('color: #666; font-size: 10px;')
        spur_hint.setWordWrap(True)
        settings_layout.addWidget(spur_hint)

        # Separator line
        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet('background-color: #ddd; margin: 2px 0;')
        settings_layout.addWidget(sep2)

        # Unit selector
        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel('Report total length in:'))
        self.unit_combo = QComboBox()
        self.unit_combo.addItem('Meters (m)',       1.0)
        self.unit_combo.addItem('Kilometers (km)',  0.001)
        self.unit_combo.addItem('Miles (mi)',        0.000621371)
        self.unit_combo.addItem('Feet (ft)',         3.28084)
        self.unit_combo.setFixedWidth(160)
        self.unit_combo.setCurrentIndex(1)  # default km
        unit_row.addWidget(self.unit_combo)
        unit_row.addStretch()
        settings_layout.addLayout(unit_row)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # --- Output group ---
        output_group = QGroupBox('Output')
        output_layout = QVBoxLayout()
        output_layout.setSpacing(8)
        output_layout.addWidget(QLabel('Save output to:'))
        path_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText('Click Browse to choose output file...')
        path_row.addWidget(self.output_edit)
        browse_btn = QPushButton('Browse')
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_output)
        path_row.addWidget(browse_btn)
        output_layout.addLayout(path_row)
        self.add_to_project_cb = QCheckBox('Add result layer to project')
        self.add_to_project_cb.setChecked(True)
        output_layout.addWidget(self.add_to_project_cb)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)

        # --- Progress ---
        progress_group = QGroupBox('Progress')
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(6)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(130)
        self.log_text.setStyleSheet('font-family: monospace; font-size: 11px;')
        self.log_text.setPlaceholderText('Processing log will appear here...')
        progress_layout.addWidget(self.log_text)
        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.run_btn = QPushButton('Run')
        self.run_btn.setFixedHeight(36)
        self.run_btn.setFixedWidth(110)
        self.run_btn.setStyleSheet(
            'QPushButton { background-color: #2e7d32; color: white; border-radius: 4px; font-weight: bold; }'
            'QPushButton:hover { background-color: #388e3c; }'
            'QPushButton:disabled { background-color: #aaa; }'
        )
        self.run_btn.clicked.connect(self._run)
        btn_row.addWidget(self.run_btn)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.cancel_btn)
        close_btn = QPushButton('Close')
        close_btn.setFixedHeight(36)
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        main_layout.addLayout(btn_row)
        self.setLayout(main_layout)
        self._set_running(False)

    def refresh_layers(self):
        self.layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.type() == QgsMapLayer.VectorLayer and
                    layer.geometryType() == QgsWkbTypes.PolygonGeometry):
                self.layer_combo.addItem(layer.name(), layer.id())
        if self.layer_combo.count() == 0:
            self.layer_combo.addItem('no polygon layers found', None)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Centerlines As', '', 'GeoPackage (*.gpkg);;Shapefile (*.shp)'
        )
        if path:
            if not path.lower().endswith(('.gpkg', '.shp')):
                path += '.gpkg'
            self.output_edit.setText(path)

    def _log(self, msg, color=None):
        if color:
            self.log_text.append(f'<span style="color:{color}">{msg}</span>')
        else:
            self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def _set_running(self, running):
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.layer_combo.setEnabled(not running)
        self.road_width_spin.setEnabled(not running)
        self.spur_spin.setEnabled(not running)
        self.unit_combo.setEnabled(not running)
        self.output_edit.setEnabled(not running)

    def _run(self):
        layer_id = self.layer_combo.currentData()
        if not layer_id:
            QMessageBox.warning(self, 'No Layer', 'Please select a polygon layer.')
            return
        output_path = self.output_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, 'No Output', 'Please choose an output file path.')
            return
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            QMessageBox.warning(self, 'Layer Error', 'Could not find the selected layer.')
            return

        # Check dependencies
        missing = []
        try:
            import centerline
        except ImportError:
            missing.append('centerline')
        try:
            import networkx
        except ImportError:
            missing.append('networkx')
        try:
            import shapely
        except ImportError:
            missing.append('shapely')
        if missing:
            QMessageBox.critical(
                self, 'Missing Libraries',
                f'The following Python libraries are not installed:\n\n'
                f'  {", ".join(missing)}\n\n'
                f'Please install them in the QGIS Python Console:\n\n'
                f'  import subprocess, sys\n'
                f'  subprocess.run([sys.executable, "-m", "pip", "install", '
                f'{", ".join(repr(m) for m in missing)}])'
            )
            return

        unit_factor = self.unit_combo.currentData()
        unit_short = self.unit_combo.currentText().split('(')[1].replace(')', '').strip()

        self.log_text.clear()
        self.progress_bar.setValue(0)
        self._log('Starting processing...', '#1565c0')
        self._log(f'Layer: {layer.name()} ({layer.featureCount()} features)')
        self._log(f'Minimum road width: {self.road_width_spin.value()} m')
        self._log(f'Spur pruning length: {self.spur_spin.value()} map units')
        self._log(f'Length unit: {unit_short}')
        self._log(f'Output: {output_path}')
        self._log('-' * 50)
        self._set_running(True)

        self.worker = WorkerThread(
            layer=layer,
            output_path=output_path,
            spur_min_length=self.spur_spin.value(),
            road_width=self.road_width_spin.value(),
            add_to_project=self.add_to_project_cb.isChecked(),
            unit_factor=unit_factor,
            unit_short=unit_short
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        if message:
            self._log(message)

    def _on_finished(self, success, error_msg):
        self._set_running(False)
        if success:
            output_path = self.output_edit.text().strip()
            unit_factor = self.unit_combo.currentData()
            unit_short = self.unit_combo.currentText().split('(')[1].replace(')', '').strip()
            self.progress_bar.setValue(100)
            self._log('-' * 50)
            self._log('Processing complete!', '#2e7d32')

            result_layer = QgsVectorLayer(output_path, 'Centerlines', 'ogr')
            if self.add_to_project_cb.isChecked() and result_layer.isValid():
                QgsProject.instance().addMapLayer(result_layer)
                self._log('Layer added to project.', '#2e7d32')

            length_msg = ''
            try:
                total_m = sum(f.geometry().length() for f in result_layer.getFeatures())
                total = total_m * unit_factor
                length_msg = f'Total road length: {total:,.2f} {unit_short}'
                self._log(f'Total road length: {total:,.2f} {unit_short}', '#1565c0')
            except Exception:
                pass

            msg = 'Centerline extraction complete!\n\nThe result layer has been added to your project.'
            if length_msg:
                msg += f'\n\n{length_msg}'
            QMessageBox.information(self, 'Done', msg)
        else:
            self._log('Error during processing:', '#c62828')
            self._log(error_msg, '#c62828')
            QMessageBox.critical(self, 'Processing Error',
                f'An error occurred:\n\n{error_msg}\n\nSee the log for details.')

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            self._log('Cancelled by user.', '#e65100')
            self._set_running(False)
            self.progress_bar.setValue(0)