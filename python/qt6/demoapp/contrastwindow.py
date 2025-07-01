
from threading import Lock

from PySide6.QtCore import QTimer, QEvent, Qt
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QImage, QPixmap, QPainter, QPen
from PySide6.QtWidgets import QMainWindow, QMessageBox, QLabel, QApplication, QFileDialog, QToolBar, QVBoxLayout, QWidget

import imagingcontrol4 as ic4
import pyqtgraph as pg
import numpy as np

from resourceselector import ResourceSelector

DEVICE_LOST_EVENT = QEvent.Type(QEvent.Type.User + 2)

class ClickableDisplayWidget(ic4.pyside6.DisplayWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_width = self.width()
        self.image_height = self.height()
    
    def mousePressEvent(self, event):
        # Get mouse position relative to the widget
        pos = event.position().toPoint()

        # Get widget size
        widget_width = self.width()
        widget_height = self.height()

        # Convert to relative (normalized) coordinates (0.0–1.0)
        rel_x = pos.x() / widget_width
        rel_y = pos.y() / widget_height

        img_x = int(rel_x * self.image_width)
        img_y = int(rel_y * self.image_height)
        print(f"Image pixel coordinates: ({img_x}, {img_y})")

        super().mousePressEvent(event)  # Pass the event to base class

class MainWindow(QMainWindow):
    curr_image_array = None

    def __init__(self):
        QMainWindow.__init__(self)

        self.grabber = ic4.Grabber()
        self.grabber.event_add_device_lost(lambda g: QApplication.postEvent(self, QEvent(DEVICE_LOST_EVENT)))

        class Listener(ic4.QueueSinkListener):
            def sink_connected(self, sink: ic4.QueueSink, image_type: ic4.ImageType, min_buffers_required: int) -> bool:
                # Allocate more buffers than suggested, because we temporarily take some buffers
                # out of circulation when saving an image or video files.
                sink.alloc_and_queue_buffers(min_buffers_required + 2)
                return True

            def sink_disconnected(self, sink: ic4.QueueSink):
                pass

            def frames_queued(listener, sink: ic4.QueueSink):
                buf = sink.pop_output_buffer()

                self.curr_image_array = buf.numpy_copy()

                # Connect the buffer's chunk data to the device's property map
                # This allows for properties backed by chunk data to be updated
                self.device_property_map.connect_chunkdata(buf)


        self.sink = ic4.QueueSink(Listener())

        self.property_dialog = None
        self.points = []

        self.createUI()

        try:
            self.display = self.video_widget.as_display()
            self.display.set_render_position(ic4.DisplayRenderPosition.STRETCH_TOPLEFT)
        except Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)


        self.updateControls()

    def createUI(self):
        self.resize(1024, 900)

        selector = ResourceSelector()

        self.device_select_act = QAction(selector.loadIcon("images/camera.png"), "&Select", self)
        self.device_select_act.setStatusTip("Select a video capture device")
        self.device_select_act.setShortcut(QKeySequence.Open)
        self.device_select_act.triggered.connect(self.onSelectDevice)

        self.device_properties_act = QAction(selector.loadIcon("images/imgset.png"), "&Properties", self)
        self.device_properties_act.setStatusTip("Show device property dialog")
        self.device_properties_act.triggered.connect(self.onDeviceProperties)

        self.device_driver_properties_act = QAction("&Driver Properties", self)
        self.device_driver_properties_act.setStatusTip("Show device driver property dialog")
        self.device_driver_properties_act.triggered.connect(self.onDeviceDriverProperties)

        self.trigger_mode_act = QAction(selector.loadIcon("images/triggermode.png"), "&Trigger Mode", self)
        self.trigger_mode_act.setStatusTip("Enable and disable trigger mode")
        self.trigger_mode_act.setCheckable(True)
        self.trigger_mode_act.triggered.connect(self.onToggleTriggerMode)

        self.start_live_act = QAction(selector.loadIcon("images/livestream.png"), "&Live Stream", self)
        self.start_live_act.setStatusTip("Start and stop the live stream")
        self.start_live_act.setCheckable(True)
        self.start_live_act.triggered.connect(self.startStopStream)

        self.reset_btn = QAction("&Reset Points", self)
        self.reset_btn.setStatusTip("Resest the selected points")
        self.reset_btn.triggered.connect(self.reset_points)

        self.save_btn = QAction("&Save Graphs", self)
        self.save_btn.setStatusTip("Save the histogram graphs as images")
        self.save_btn.triggered.connect(self.save_histogram)

        self.close_device_act = QAction("Close", self)
        self.close_device_act.setStatusTip("Close the currently opened device")
        self.close_device_act.setShortcuts(QKeySequence.Close)
        self.close_device_act.triggered.connect(self.onCloseDevice)

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.setStatusTip("Exit program")
        exit_act.triggered.connect(self.close)

        # Create 3 stacked histogram widgets
        self.hist_r = pg.PlotWidget(title="Red Channel")
        self.hist_g = pg.PlotWidget(title="Green Channel")
        self.hist_b = pg.PlotWidget(title="Blue Channel")
        self.curve_r = self.hist_r.plot(pen='r')
        self.curve_g = self.hist_g.plot(pen='g')
        self.curve_b = self.hist_b.plot(pen='b')

        for hist in (self.hist_r, self.hist_g, self.hist_b):
            hist.setYRange(0, 1000)
            hist.setXRange(0, 255)

        toolbar = QToolBar(self)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        toolbar.addAction(self.device_select_act)
        toolbar.addAction(self.device_properties_act)
        toolbar.addSeparator()
        toolbar.addAction(self.trigger_mode_act)
        toolbar.addSeparator()
        toolbar.addAction(self.start_live_act)
        toolbar.addSeparator()
        toolbar.addAction(self.reset_btn)
        toolbar.addAction(self.save_btn)

        self.video_widget = ClickableDisplayWidget()
        self.video_widget.setMinimumSize(640, 480)
        self.video_widget.mousePressEvent = self.on_click

        self.statusBar().showMessage("Ready")
        self.statistics_label = QLabel("", self.statusBar())
        self.statusBar().addPermanentWidget(self.statistics_label)
        self.statusBar().addPermanentWidget(QLabel("  "))
        self.camera_label = QLabel(self.statusBar())
        self.statusBar().addPermanentWidget(self.camera_label)

        self.update_statistics_timer = QTimer()
        self.update_statistics_timer.timeout.connect(self.onUpdateStatisticsTimer)
        self.update_statistics_timer.timeout.connect(self.update_frame)
        self.update_statistics_timer.start()

        layout = QVBoxLayout()
        layout.addWidget(self.video_widget)
        # layout.addWidget(self.hist_r)
        # layout.addWidget(self.hist_g)
        # layout.addWidget(self.hist_b)

        # container = QWidget()
        # container.setLayout(layout)
        # self.setCentralWidget(container)
        self.setCentralWidget(self.video_widget)


    def onCloseDevice(self):
        if self.grabber.is_streaming:
            self.startStopStream()
        
        try:
            self.grabber.device_close()
        except:
            pass

        self.device_property_map = None
        self.display.display_buffer(None)

        self.updateControls()

    def closeEvent(self, ev: QCloseEvent):
        if self.grabber.is_streaming:
            self.grabber.stream_stop()

    def customEvent(self, ev: QEvent):
        if ev.type() == DEVICE_LOST_EVENT:
            self.onDeviceLost()

    def onSelectDevice(self):
        dlg = ic4.pyside6.DeviceSelectionDialog(self.grabber, parent=self)
        if dlg.exec() == 1:
            if not self.property_dialog is None:
                self.property_dialog.update_grabber(self.grabber)
            
            self.onDeviceOpened()
        self.updateControls()

    def onDeviceProperties(self):
        if self.property_dialog is None:
            self.property_dialog = ic4.pyside6.PropertyDialog(self.grabber, parent=self, title="Device Properties")
            # set default vis
        
        self.property_dialog.show()

    def onDeviceDriverProperties(self):
        dlg = ic4.pyside6.PropertyDialog(self.grabber.driver_property_map, parent=self, title="Device Driver Properties")
        # set default vis

        dlg.exec()

        self.updateControls()

    def onToggleTriggerMode(self):
        try:
            self.device_property_map.set_value(ic4.PropId.TRIGGER_MODE, self.trigger_mode_act.isChecked())
        except ic4.IC4Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

    def onUpdateStatisticsTimer(self):
        if not self.grabber.is_device_valid:
            return
        
        try:
            stats = self.grabber.stream_statistics
            text = f"Frames Delivered: {stats.sink_delivered} Dropped: {stats.device_transmission_error}/{stats.device_underrun}/{stats.transform_underrun}/{stats.sink_underrun}"
            self.statistics_label.setText(text)
            tooltip = (
                f"Frames Delivered: {stats.sink_delivered}"
                f"Frames Dropped:"
                f"  Device Transmission Error: {stats.device_transmission_error}"
                f"  Device Underrun: {stats.device_underrun}"
                f"  Transform Underrun: {stats.transform_underrun}"
                f"  Sink Underrun: {stats.sink_underrun}"
            )
            self.statistics_label.setToolTip(tooltip)
        except ic4.IC4Exception:
            pass

    def onDeviceLost(self):
        QMessageBox.warning(self, "", f"The video capture device is lost!", QMessageBox.StandardButton.Ok)

        # stop video

        self.updateCameraLabel()
        self.updateControls()

    def onDeviceOpened(self):
        self.device_property_map = self.grabber.device_property_map

        trigger_mode = self.device_property_map.find(ic4.PropId.TRIGGER_MODE)
        trigger_mode.event_add_notification(self.updateTriggerControl)

        self.updateCameraLabel()

        # if start_stream_on_open
        self.startStopStream()

    def updateTriggerControl(self, p: ic4.Property):
        if not self.grabber.is_device_valid:
            self.trigger_mode_act.setChecked(False)
            self.trigger_mode_act.setEnabled(False)
        else:
            try:
                self.trigger_mode_act.setChecked(self.device_property_map.get_value_str(ic4.PropId.TRIGGER_MODE) == "On")
                self.trigger_mode_act.setEnabled(True)
            except ic4.IC4Exception:
                self.trigger_mode_act.setChecked(False)
                self.trigger_mode_act.setEnabled(False)

    def updateControls(self):
        if not self.grabber.is_device_open:
            self.statistics_label.clear()

        self.device_properties_act.setEnabled(self.grabber.is_device_valid)
        self.device_driver_properties_act.setEnabled(self.grabber.is_device_valid)
        self.start_live_act.setEnabled(self.grabber.is_device_valid)
        self.start_live_act.setChecked(self.grabber.is_streaming)
        self.close_device_act.setEnabled(self.grabber.is_device_open)

        self.updateTriggerControl(None)

    def updateCameraLabel(self):
        try:
            info = self.grabber.device_info
            self.camera_label.setText(f"{info.model_name} {info.serial}")
        except ic4.IC4Exception:
            self.camera_label.setText("No Device")

    def startStopStream(self):
        try:
            if self.grabber.is_device_valid:
                if self.grabber.is_streaming:
                    self.grabber.stream_stop()
                else:
                    self.grabber.stream_setup(self.sink, self.display)

        except ic4.IC4Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

        self.updateControls()

    def on_click(self, event):
        if len(self.points) < 3:
            pt = event.position().toPoint()
            self.points.append(pt)
        else:
            self.reset_points()
        pass

    def reset_points(self):
        self.points.clear()

    def save_histogram(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Histogram Image", "", "PNG Images (*.png);;All Files (*)"
        )
        if not filename:
            return

        export_layout = pg.GraphicsLayout()
        export_layout.addItem(self.hist_r.plotItem)
        export_layout.nextRow()
        export_layout.addItem(self.hist_g.plotItem)
        export_layout.nextRow()
        export_layout.addItem(self.hist_b.plotItem)

        exporter = pg.exporters.ImageExporter(export_layout)
        exporter.export(filename)
        print(f"Histogram saved to: {filename}")

    def update_frame(self):
        if not self.grabber or not self.grabber.is_streaming:
            return

        # frame = self.sink.snap_single(timeout=1000)
        # if frame is None:
        #     return
        buf = self.sink.pop_output_buffer()
        self.curr_image_array = buf.numpy_copy()

        img = self.curr_image_array
        if img.ndim != 3:
            return

        buf.release()

        h, w, _ = img.shape
        qimg = QImage(img.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(self.image_label.size())

        painter = QPainter(pix)
        pen = QPen(pg.mkColor('y'))
        pen.setWidth(3)
        painter.setPen(pen)
        for pt in self.points:
            painter.drawEllipse(pt, 5, 5)
        painter.end()

        self.image_label.setPixmap(pix)

        if len(self.points) == 3:
            self.update_histogram(img)

    def update_histogram(self, img):
        region_size = 5
        chans = {'r': [], 'g': [], 'b': []}

        for pt in self.points:
            x, y = pt.x(), pt.y()
            region = img[max(0, y - region_size):y + region_size,
                         max(0, x - region_size):x + region_size]
            chans['r'].extend(region[:, :, 0].flatten())
            chans['g'].extend(region[:, :, 1].flatten())
            chans['b'].extend(region[:, :, 2].flatten())

        r_hist, _ = np.histogram(chans['r'], bins=256, range=(0, 255))
        g_hist, _ = np.histogram(chans['g'], bins=256, range=(0, 255))
        b_hist, _ = np.histogram(chans['b'], bins=256, range=(0, 255))

        self.curve_r.setData(r_hist)
        self.curve_g.setData(g_hist)
        self.curve_b.setData(b_hist)

if __name__ == "__main__":
    with ic4.Library.init_context():
        app = QApplication()
        app.setApplicationName("ic4-demoapp")
        app.setApplicationDisplayName("IC4 Demo Application")
        app.setStyle("fusion")

        w = MainWindow()
        w.show()

        app.exec()
