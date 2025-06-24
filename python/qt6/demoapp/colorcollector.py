import PIL.ImageGrab as ImageGrab
import numpy as np

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QLabel, QWidget, QColorDialog, QToolBar, QPushButton

class ColorCollector(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Color Collector")
        self.resize(900, 700)
        self.colors = []

        self.instruction_label = QLabel("Click the buttons below to select colors for the background and flakes.", self)
        
        self.background_label = QLabel("Save last clicked colors", self)
        self.background_label.setAlignment(Qt.AlignCenter)
        
        self.background_button = QPushButton("Select background color", self)
        self.background_button.clicked.connect(self.select_background_color)

        self.first_color_label = QLabel("Save last clicked colors", self)
        self.first_color_label.setAlignment(Qt.AlignCenter)

        self.first_color_button = QPushButton("Select the color of a mono-layer flake", self)
        self.first_color_button.clicked.connect(self.select_first_color)

        self.second_color_label = QLabel("Save last clicked colors", self)
        self.second_color_label.setAlignment(Qt.AlignCenter)

        self.second_color_button = QPushButton("Select the color of a bi-layer flake", self)
        self.second_color_button.clicked.connect(self.select_second_color)
        
        layout = QVBoxLayout()
        layout.addWidget(self.background_label)
        layout.addWidget(self.background_button)
        layout.addWidget(self.first_color_label)
        layout.addWidget(self.first_color_button)
        layout.addWidget(self.second_color_label)
        layout.addWidget(self.second_color_button)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def select_background_color(self):
        self.select_color(self.background_label)

    def select_first_color(self):
        self.select_color(self.first_color_label)

    def select_second_color(self):
        self.select_color(self.second_color_label)
    
    def select_color(self, label):
        # Take a snapshot of the screen, and grab a 20x20 pixel area around the cursor

        if len(self.colors) == 0:
            print("No colors captured. Please click on the screen to capture colors.")
            return
        
        # Calculate the average color from the captured colors using the squared method
        red = 0
        green = 0
        blue = 0
        for color in self.colors:
            red += np.square(color[0])
            green += np.square(color[1])
            blue += np.square(color[2])

        red = int(np.sqrt(red / len(self.colors)))
        green = int(np.sqrt(green / len(self.colors)))
        blue = int(np.sqrt(blue / len(self.colors)))

        label.setText(f"Selected color: RGB({red}, {green}, {blue})")
        label.setStyleSheet(f"background-color: rgb({red}, {green}, {blue});")

        self.colors.clear()

    def get_colors_at_cursor(self, global_pos=None):
        image = ImageGrab.grab(all_screens=True)
        print("Image grabbed")
        pos = global_pos
        if pos is None:
            pos = QPoint(10, 10)
        
        for y in range(pos.y() - 10, pos.y() + 10):
            for x in range(pos.x() - 10, pos.x() + 10):
                color = image.getpixel((x, y))  #TODO: positions aren't adding up. Also I need to adjust this to be continuous
                self.colors.append(color)