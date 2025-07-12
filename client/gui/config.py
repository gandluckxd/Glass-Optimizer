"""
Конфигурация и константы для приложения оптимизации 2D раскроя
"""

import os

# Стили для приложения
DARK_THEME_STYLE = """
    QWidget {
        background-color: #2b2b2b;
        color: #ffffff;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 9pt;
    }
    
    QTabWidget::pane {
        border: 2px solid #555555;
        border-radius: 8px;
        background-color: #2b2b2b;
        padding-top: 5px;
    }
    
    QTabBar::tab {
        background-color: #404040;
        color: #ffffff;
        padding: 10px 20px;
        margin-right: 2px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        font-weight: bold;
    }
    
    QTabBar::tab:selected {
        background-color: #0078d4;
        color: #ffffff;
    }
    
    QTabBar::tab:hover {
        background-color: #555555;
    }
    
    QGroupBox {
        font-weight: bold;
        font-size: 10pt;
        border: 2px solid #555555;
        border-radius: 8px;
        margin-top: 10px;
        padding-top: 15px;
        background-color: #333333;
        color: #ffffff;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 10px 0 10px;
        color: #ffffff;
        background-color: #333333;
    }
    
    QTableWidget {
        background-color: #1e1e1e;
        color: #ffffff;
        gridline-color: #555555;
        border: 2px solid #555555;
        border-radius: 4px;
        selection-background-color: #0078d4;
        alternate-background-color: #262626;
    }
    
    QTableWidget::item {
        padding: 8px;
        border-bottom: 1px solid #444444;
    }
    
    QTableWidget::item:selected {
        background-color: #0078d4;
        color: #ffffff;
    }
    
    QHeaderView::section {
        background-color: #404040;
        color: #ffffff;
        padding: 8px;
        border: none;
        border-right: 1px solid #555555;
        font-weight: bold;
    }
    
    QPushButton {
        background-color: #0078d4;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 4px;
        font-weight: bold;
        min-width: 100px;
    }
    
    QPushButton:hover {
        background-color: #106ebe;
    }
    
    QPushButton:pressed {
        background-color: #005a9e;
    }
    
    QPushButton:disabled {
        background-color: #666666;
        color: #999999;
    }
    
    QLineEdit, QSpinBox, QComboBox {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 2px solid #555555;
        border-radius: 4px;
        padding: 8px;
        font-size: 9pt;
    }
    
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
        border: 2px solid #0078d4;
    }
    
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    
    QComboBox QAbstractItemView {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 2px solid #555555;
        selection-background-color: #0078d4;
    }
    
    QLabel {
        color: #ffffff;
        font-weight: normal;
    }
    
    QCheckBox {
        color: #ffffff;
        spacing: 8px;
    }
    
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 2px solid #555555;
        border-radius: 3px;
        background-color: #1e1e1e;
    }
    
    QCheckBox::indicator:checked {
        background-color: #0078d4;
        border: 2px solid #0078d4;
    }
    
    QSlider::groove:horizontal {
        border: 1px solid #555555;
        height: 8px;
        background: #1e1e1e;
        border-radius: 4px;
    }
    
    QSlider::handle:horizontal {
        background: #0078d4;
        border: 2px solid #0078d4;
        width: 18px;
        height: 18px;
        margin: -7px 0;
        border-radius: 9px;
    }
    
    QSlider::handle:horizontal:hover {
        background: #106ebe;
        border: 2px solid #106ebe;
    }
    
    QGraphicsView {
        background-color: #1e1e1e;
        border: 2px solid #555555;
        border-radius: 4px;
    }
    
    QSplitter::handle {
        background-color: #555555;
        width: 3px;
        height: 3px;
    }
    
    QSplitter::handle:horizontal {
        background-color: #555555;
        width: 3px;
    }
    
    QSplitter::handle:vertical {
        background-color: #555555;
        height: 3px;
    }
"""

# Стили для диалогов
DIALOG_STYLE = """
    QDialog {
        background-color: #2b2b2b;
        color: #ffffff;
        border: 2px solid #555555;
        border-radius: 8px;
    }
    QLabel {
        color: #ffffff;
        font-size: 10pt;
    }
    QTextEdit {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 2px solid #555555;
        border-radius: 4px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 9pt;
        padding: 8px;
    }
    QPushButton {
        background-color: #0078d4;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-weight: bold;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #106ebe;
    }
    QProgressBar {
        background-color: #404040;
        border: 2px solid #555555;
        border-radius: 4px;
        text-align: center;
        color: #ffffff;
        font-weight: bold;
        height: 25px;
    }
    QProgressBar::chunk {
        background-color: #0078d4;
        border-radius: 2px;
    }
"""

# Размеры окна
WINDOW_MIN_WIDTH = 1400
WINDOW_MIN_HEIGHT = 900

# Настройки таблиц
TABLE_HEADERS = {
    'details': ['Наименование изделия', 'Материал', 'Высота, мм', 'Ширина, мм', 'Кол-во'],
    'materials': ['Материал', 'Высота, мм', 'Ширина, мм', 'Кол-во'],
    'remainders': ['Материал', 'Высота, мм', 'Ширина, мм', 'Кол-во'],
    'remnants_result': ['Материал', 'Высота, мм', 'Ширина, мм', 'Кол-во'],
    'waste_results': ['Материал', 'Высота, мм', 'Ширина, мм', 'Кол-во'],
    'waste_result': ['Материал', 'Высота, мм', 'Ширина, мм', 'Кол-во']
}

# Настройки оптимизации
OPTIMIZATION_DEFAULTS = {
    'allowRotation': True,
    'blade_width': 3,
    'min_remainder_width': 100,
    'min_remainder_height': 100
}

# Настройки визуализации
VISUALIZATION_DEFAULTS = {
    'zoom_min': 10,
    'zoom_max': 500,
    'zoom_default': 100,
    'grid_size': 50
}

# Цвета для визуализации
COLORS = {
    'sheet_border': '#ffffff',
    'detail_fill': '#4CAF50',
    'detail_border': '#2E7D32',
    'remainder_fill': '#FF9800',
    'remainder_border': '#F57C00',
    'waste_fill': '#f44336',
    'waste_border': '#d32f2f',
    'grid': '#444444',
    'text': '#ffffff'
}

 