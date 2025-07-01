import sys
import numpy as np
import imagingcontrol4 as ic4
import imagingcontrol4.pyside6 as ic4ui
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QWidget, QHBoxLayout, QFileDialog
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen
from PySide6.QtCore import QTimer
import pyqtgraph as pg


class CameraApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live RGB Histograms - ImagingControl4")

        # === UI Elements ===
        self.display_widget = ic4.pyside6.DisplayWidget()
        self.display = self.display_widget.as_display()
        self.display.set_render_position(ic4.DisplayRenderPosition.STRETCH_TOPLEFT)


        self.image_label = QLabel()
        self.image_label.setFixedSize(640, 480)
        self.image_label.mousePressEvent = self.on_click

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

        # Buttons
        self.open_cam_btn = QPushButton("Open Camera")
        self.open_cam_btn.clicked.connect(self.select_camera)

        self.prop_btn = QPushButton("Adjust Properties")
        self.prop_btn.clicked.connect(self.open_properties)

        self.reset_btn = QPushButton("Reset Points")
        self.reset_btn.clicked.connect(self.reset_points)

        self.save_btn = QPushButton("Save Histogram Snapshot")
        self.save_btn.clicked.connect(self.save_histogram)

        # Layout
        button_layout = QHBoxLayout()
        for btn in [self.open_cam_btn, self.prop_btn, self.reset_btn, self.save_btn]:
            button_layout.addWidget(btn)

        layout = QVBoxLayout()
        layout.addLayout(button_layout)
        layout.addWidget(self.display_widget)
        layout.addWidget(self.hist_r)
        layout.addWidget(self.hist_g)
        layout.addWidget(self.hist_b)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # App state
        self.grabber = ic4.Grabber()
        self.points = []

        # Timer for updating camera feed
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(100)

    def select_camera(self):
        dialog = ic4ui.DeviceSelectionDialog(self.grabber, parent=self)
        if dialog.exec():
            if self.grabber.is_streaming:
                self.grabber.stream_stop()
            # self.grabber.stream_format = self.grabber.stream_formats[0]  # RGB24 by default
            self.grabber.stream_setup(None, self.display)

    def open_properties(self):
        if self.grabber:
            ic4ui.PropertyDialog(self.grabber).exec()

    def reset_points(self):
        self.points.clear()

    def on_click(self, event):
        if len(self.points) < 3:
            pt = event.position().toPoint()
            self.points.append(pt)
        else:
            self.reset_points()

    def update_frame(self):
        if not self.grabber or not self.grabber.is_streaming:
            return

        frame = self.grabber.snap_image(timeout=1000)
        if frame is None:
            return

        img = frame.to_numpy()
        if img.ndim != 3:
            return

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

    def closeEvent(self, event):
        if self.grabber:
            self.grabber.stream_stop()
            self.grabber.close()
        super().closeEvent(event)


if __name__ == "__main__":
    # This is just the default Qt main function template, with added call to Library.init_context()
    from sys import argv

    app = QApplication(argv)
    app.setStyle("fusion")

    with ic4.Library.init_context():

        window = CameraApp()
        window.resize(800, 900)
        window.show()

        app.exec()
    
        sys.exit(app.exec())
