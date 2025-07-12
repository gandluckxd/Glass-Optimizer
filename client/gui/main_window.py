"""
Главное окно приложения оптимизации 2D раскроя
Профессиональная система с современным интерфейсом
"""

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, 
    QTableWidget, QTableWidgetItem, QCheckBox, QSpinBox, QGroupBox, 
    QPushButton, QGraphicsView, QGraphicsScene, QFormLayout, QLineEdit, 
    QTabWidget, QComboBox, QDialog, QProgressBar, QMessageBox, QHeaderView,
    QSplitter, QFrame, QTextEdit, QSlider
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QPen, QBrush, QColor, QPainter, QTransform, QShowEvent
import sys
import threading
from datetime import datetime
# Исправленные импорты для модульной архитектуры
from core.api_client import get_details_raw, get_warehouse_main_material, get_warehouse_remainders, check_api_connection
from core.optimizer_core import optimize, OptimizationResult
from .table_widgets import (_create_text_item, _create_numeric_item,
                           fill_details_table, fill_materials_table, fill_remainders_table,
                           update_remnants_result_table, update_waste_results_table)
import functools
import requests
import os
import json
import logging
from .dialogs import DebugDialog, ProgressDialog

# Настройка логирования
logger = logging.getLogger(__name__)


class ZoomableGraphicsView(QGraphicsView):
    """Кастомный класс для поддержки зума колесиком мыши"""
    def __init__(self, scene, parent=None):
        super().__init__(scene)
        self.parent_window = parent
        
    def wheelEvent(self, event):
        if self.parent_window:
            self.parent_window.wheel_zoom(event)

class OptimizerWindow(QWidget):
    """Главное окно приложения"""
    
    # Сигналы для thread-safe коммуникации
    debug_step_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str, str, str)  # title, message, icon
    success_signal = pyqtSignal()
    data_loaded_signal = pyqtSignal(dict, list, list)  # details_data, remainders, materials
    restore_button_signal = pyqtSignal()
    
    # Сигналы для оптимизации
    optimization_result_signal = pyqtSignal(object)  # OptimizationResult
    optimization_error_signal = pyqtSignal(str)
    close_progress_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        # Инициализация данных
        self.current_details = []
        self.current_materials = []
        self.current_remainders = []
        self.optimization_result = None
        self.current_sheet_index = 0
        self.auto_load_debug = False
        
        # Инициализация диалогов
        self.debug_dialog = None
        self.progress_dialog = None
        
        # Настройка UI
        self.init_ui()
        
        # Настройка размера окна
        self.setWindowTitle("Оптимизатор 2D Раскроя")
        self.setMinimumSize(1400, 900)  # Минимальный размер окна
        

        
        # Подключение сигналов для thread-safe коммуникации
        self.debug_step_signal.connect(self._add_debug_step_safe)
        self.error_signal.connect(self._show_error_safe)
        self.success_signal.connect(self._show_success_safe)
        self.data_loaded_signal.connect(self._update_tables_safe)
        self.restore_button_signal.connect(self._restore_button_safe)
        
        # Сигналы для оптимизации
        self.optimization_result_signal.connect(self._handle_optimization_result)
        self.optimization_error_signal.connect(self._handle_optimization_error)
        self.close_progress_signal.connect(self._close_progress_dialog)
        
        print("🔧 DEBUG: Главное окно инициализировано")

    def showEvent(self, event):
        """Переопределение showEvent для настройки темного заголовка"""
        super().showEvent(event)
        
        # Настройка темного заголовка окна (для Windows)
        try:
            import ctypes
            from ctypes import wintypes
            import platform
            
            # Получаем handle окна
            hwnd = int(self.winId())
            
            # Определяем версию Windows и используем соответствующую константу
            version = platform.version()
            version_parts = version.split('.')
            build_number = int(version_parts[2]) if len(version_parts) > 2 else 0
            
            # Для Windows 10 1903+ (build 18362+) и Windows 11
            if build_number >= 18362:
                # Пробуем новую константу (Windows 11)
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                value = ctypes.c_int(1)
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 
                    ctypes.byref(value), ctypes.sizeof(value)
                )
                
                # Если не сработало, пробуем старую константу
                if result != 0:
                    DWMWA_USE_IMMERSIVE_DARK_MODE = 19
                    result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 
                        ctypes.byref(value), ctypes.sizeof(value)
                    )
                
                if result == 0:
                    print(f"🔧 DEBUG: Темный заголовок окна установлен (константа {DWMWA_USE_IMMERSIVE_DARK_MODE})")
                else:
                    print(f"🔧 DEBUG: Не удалось установить темный заголовок (код ошибки: {result})")
            else:
                print("🔧 DEBUG: Версия Windows не поддерживает темные заголовки окон")
                
        except Exception as e:
            # Если не получилось (не Windows или ошибка), продолжаем без темного заголовка
            print(f"🔧 DEBUG: Не удалось установить темный заголовок: {e}")
            pass

    def init_ui(self):
        """Инициализация интерфейса"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Применение темной темы ко всему приложению
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
            }
            
            QGroupBox {
                background-color: #3c3c3c;
                border: 2px solid #555555;
                border-radius: 8px;
                margin: 5px;
                padding-top: 15px;
                font-weight: bold;
                color: #ffffff;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #ffffff;
                background-color: #3c3c3c;
            }
            
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
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
                background-color: #555555;
                color: #888888;
            }
            
            QLineEdit {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            
            QLineEdit:focus {
                border-color: #0078d4;
            }
            
            QTableWidget {
                background-color: #404040;
                alternate-background-color: #4a4a4a;
                gridline-color: #555555;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #ffffff;
            }
            
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #555555;
            }
            
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
            
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 8px;
                border: 1px solid #555555;
                font-weight: bold;
            }
            
            QLabel {
                color: #ffffff;
                background-color: transparent;
            }
            
            QSpinBox, QComboBox {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                min-width: 80px;
            }
            
            QSpinBox:focus, QComboBox:focus {
                border-color: #0078d4;
            }
            
            QComboBox::drop-down {
                border: none;
                background-color: #555555;
                width: 20px;
            }
            
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
                margin: 5px;
            }
            
            QMessageBox {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            
            QMessageBox QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            
            QMessageBox QPushButton:hover {
                background-color: #106ebe;
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
                background-color: #404040;
            }
            
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
                image: none;
            }
            
            QProgressBar {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 4px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
            }
            
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 2px;
            }
            
            QGraphicsView {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 4px;
            }
            
            QSplitter::handle {
                background-color: #555555;
                width: 3px;
                height: 3px;
            }
            
            QSplitter::handle:hover {
                background-color: #0078d4;
            }
        """)
        
        # Создание вкладок
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #555555;
                background-color: #3c3c3c;
                border-radius: 8px;
            }
            
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 10px 20px;
                margin-right: 3px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border: 2px solid #555555;
                border-bottom: none;
                font-weight: bold;
                font-size: 9pt;
                min-width: 260px;
                max-width: 380px;
            }
            
            QTabBar::tab:selected {
                background-color: #3c3c3c;
                border-bottom: 2px solid #0078d4;
                color: #ffffff;
                font-size: 9pt;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #404040;
            }
        """)
        
        # Вкладка 1: Информация о сменном задании
        self.create_info_tab()
        
        # Вкладка 2: Результаты оптимизации
        self.create_results_tab()
        
        # Вкладка 3: Визуализация раскроя
        vis_tab = self.create_visualization_tab()
        self.tabs.addTab(vis_tab, "🎨 Визуализация раскроя")
        
        main_layout.addWidget(self.tabs)

    def create_info_tab(self):
        """Создание вкладки информации о задании"""
        info_tab = QWidget()
        layout = QVBoxLayout(info_tab)

        # Верхняя часть - информация о задании и склад
        top_splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - информация о задании
        left_group = self.create_task_info_group()
        top_splitter.addWidget(left_group)
        
        # Правая часть - склад
        right_group = self.create_warehouse_group()
        top_splitter.addWidget(right_group)
        
        top_splitter.setSizes([700, 700])
        layout.addWidget(top_splitter)
        
        # Нижняя часть - параметры оптимизации
        params_group = self.create_optimization_params_group()
        layout.addWidget(params_group)
        
        self.tabs.addTab(info_tab, "Информация о сменном задании")

    def create_task_info_group(self):
        """Создание группы информации о задании"""
        group = QGroupBox("Информация о сменном задании")
        layout = QVBoxLayout(group)

        # Поля ввода и загрузки
        input_layout = QHBoxLayout()
        
        input_layout.addWidget(QLabel("Идентификатор сменного задания:"))
        self.grorderid_input = QLineEdit()
        self.grorderid_input.setPlaceholderText("Введите номер сменного задания")
        input_layout.addWidget(self.grorderid_input)
        
        self.load_data_button = QPushButton("Загрузить данные")
        self.load_data_button.clicked.connect(self.on_load_data_clicked)
        input_layout.addWidget(self.load_data_button)
        
        layout.addLayout(input_layout)

        # Информационные поля
        info_layout = QFormLayout()
        
        self.task_name_label = QLabel("<не загружено>")
        self.task_name_label.setStyleSheet("font-weight: bold; color: #ffffff; background-color: transparent;")
        info_layout.addRow("Наименование:", self.task_name_label)
        
        self.task_date_label = QLabel("<не загружено>")
        self.task_date_label.setStyleSheet("color: #ffffff; background-color: transparent;")
        info_layout.addRow("Дата:", self.task_date_label)
        
        self.task_orders_label = QLabel("<не загружено>")
        self.task_orders_label.setStyleSheet("color: #ffffff; background-color: transparent;")
        info_layout.addRow("Заказы:", self.task_orders_label)
        
        layout.addLayout(info_layout)
        
        # Таблица стекол
        layout.addWidget(QLabel("Список стекол для оптимизации:"))
        self.details_table = QTableWidget(0, 5)
        self.details_table.setHorizontalHeaderLabels([
            'Элемент', 'Материал', 
            'Высота', 'Ширина', 'Кол-во'
        ])
        # Умная настройка ширины столбцов: автоматически по содержимому + ручная корректировка
        header = self.details_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)  # Ручная корректировка
        header.setStretchLastSection(True)  # Последний столбец заполняет оставшееся место
        # Автоматическое определение ширины по содержимому при заполнении данных
        for i in range(self.details_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        # После определения оптимальной ширины, разрешаем ручное изменение
        QTimer.singleShot(100, lambda: self._set_interactive_mode(self.details_table))
        layout.addWidget(self.details_table)
        
        return group

    def create_warehouse_group(self):
        """Создание группы склада"""
        group = QGroupBox("Склад")
        layout = QVBoxLayout(group)
        
        # Склад остатков
        layout.addWidget(QLabel("Склад остатков:"))
        self.remainders_table = QTableWidget(0, 4)
        self.remainders_table.setHorizontalHeaderLabels([
            'Наименование', 'Высота', 'Ширина', 'Кол-во'
        ])
        # Умная настройка ширины столбцов: автоматически по содержимому + ручная корректировка
        header = self.remainders_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for i in range(self.remainders_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        QTimer.singleShot(100, lambda: self._set_interactive_mode(self.remainders_table))
        layout.addWidget(self.remainders_table)
        
        # Склад материалов
        layout.addWidget(QLabel("Склад материалов:"))
        self.materials_table = QTableWidget(0, 4)
        self.materials_table.setHorizontalHeaderLabels([
            'Наименование', 'Высота', 'Ширина', 'Кол-во'
        ])
        # Умная настройка ширины столбцов: автоматически по содержимому + ручная корректировка
        header = self.materials_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for i in range(self.materials_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        QTimer.singleShot(100, lambda: self._set_interactive_mode(self.materials_table))
        layout.addWidget(self.materials_table)
        
        return group

    def create_optimization_params_group(self):
        """Создание группы параметров оптимизации"""
        params_group = QGroupBox("Параметры оптимизации")
        layout = QFormLayout()
        
        # Минимальная ширина остатка
        self.min_remnant_width = QSpinBox()
        self.min_remnant_width.setRange(10, 1000)
        self.min_remnant_width.setValue(180)  # Установлено согласно требованиям Артема
        self.min_remnant_width.setSuffix(" мм")
        layout.addRow("Мин. ширина остатка:", self.min_remnant_width)
        
        # Минимальная высота остатка
        self.min_remnant_height = QSpinBox()
        self.min_remnant_height.setRange(10, 1000)
        self.min_remnant_height.setValue(100)  # Установлено согласно требованиям Артема
        self.min_remnant_height.setSuffix(" мм")
        layout.addRow("Мин. высота остатка:", self.min_remnant_height)
        
        # Целевой процент отходов
        self.target_waste_percent = QSpinBox()
        self.target_waste_percent.setRange(1, 20)
        self.target_waste_percent.setValue(5)  # ИЗМЕНЕНО: Увеличено с 3% до 5% для реальных данных
        self.target_waste_percent.setSuffix(" %")
        self.target_waste_percent.setStyleSheet("""
            QSpinBox {
                background-color: #404040;
                color: #00ff00;
                font-weight: bold;
                font-size: 12pt;
            }
        """)
        layout.addRow("🎯 Целевой % отходов:", self.target_waste_percent)
        
        # Минимальная сторона обрезка
        self.min_cut_size = QSpinBox()
        self.min_cut_size.setRange(5, 50)
        self.min_cut_size.setValue(10)
        self.min_cut_size.setSuffix(" мм")
        layout.addRow("Минимальная сторона обрезка:", self.min_cut_size)
        
        # Использование остатков
        self.use_remainders = QCheckBox("Использовать остатки со склада")
        self.use_remainders.setChecked(True)
        layout.addRow(self.use_remainders)
        
        # Поворот деталей
        self.allow_rotation = QCheckBox("Разрешить поворот деталей")
        self.allow_rotation.setChecked(True)
        layout.addRow(self.allow_rotation)
        
        # Кнопка оптимизации
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.optimize_button = QPushButton("🚀 Запустить оптимизацию")
        self.optimize_button.clicked.connect(self.on_optimize_clicked)
        self.optimize_button.setEnabled(False)
        self.optimize_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                font-size: 11pt;
                padding: 10px 20px;
                min-width: 200px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        button_layout.addWidget(self.optimize_button)
        
        layout.addRow(button_layout)
        
        params_group.setLayout(layout)
        return params_group

    def create_results_tab(self):
        """Создание вкладки результатов оптимизации"""
        results_tab = QWidget()
        layout = QVBoxLayout(results_tab)
        
        # Статистика вверху
        stats_group = self.create_statistics_group()
        layout.addWidget(stats_group)
        
        # Горизонтальное разделение: остатки слева, отходы справа
        tables_splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - деловые остатки
        remnants_group = QGroupBox("Список деловых остатков")
        remnants_layout = QVBoxLayout(remnants_group)
        
        self.remnants_result_table = QTableWidget(0, 4)
        self.remnants_result_table.setHorizontalHeaderLabels([
            'Наименование', 'Высота', 'Ширина', 'Кол-во'
        ])
        # Умная настройка ширины столбцов: автоматически по содержимому + ручная корректировка
        header = self.remnants_result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for i in range(self.remnants_result_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        QTimer.singleShot(100, lambda: self._set_interactive_mode(self.remnants_result_table))
        # Включаем сортировку
        self.remnants_result_table.setSortingEnabled(True)
        self.remnants_result_table.setMinimumHeight(400)
        remnants_layout.addWidget(self.remnants_result_table)
        
        tables_splitter.addWidget(remnants_group)
        
        # Правая часть - отходы
        waste_group = QGroupBox("Список обрезков (отходов)")
        waste_layout = QVBoxLayout(waste_group)
        
        self.waste_results_table = QTableWidget(0, 4)
        self.waste_results_table.setHorizontalHeaderLabels([
            'Наименование', 'Высота', 'Ширина', 'Кол-во'
        ])
        # Умная настройка ширины столбцов: автоматически по содержимому + ручная корректировка
        header = self.waste_results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for i in range(self.waste_results_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        QTimer.singleShot(100, lambda: self._set_interactive_mode(self.waste_results_table))
        # Включаем сортировку
        self.waste_results_table.setSortingEnabled(True)
        self.waste_results_table.setMinimumHeight(400)
        waste_layout.addWidget(self.waste_results_table)
        
        tables_splitter.addWidget(waste_group)
        
        # Равные размеры для обеих таблиц
        tables_splitter.setSizes([500, 500])
        layout.addWidget(tables_splitter)
        
        self.tabs.addTab(results_tab, "Результаты оптимизации")
    
    def create_visualization_tab(self):
        """Создание отдельной вкладки для визуализации"""
        vis_tab = QWidget()
        layout = QVBoxLayout(vis_tab)
        
        # Верхний блок с контролами и информацией
        controls_group = QGroupBox("Навигация и настройки")
        controls_layout = QVBoxLayout()
        
        # Первая строка - навигация и контролы
        top_controls_layout = QHBoxLayout()
        
        # Выбор листа
        self.sheets_combo = QComboBox()
        self.sheets_combo.setMinimumWidth(800)  # Увеличиваем с 600 до 800 для длинных названий листов
        self.sheets_combo.currentIndexChanged.connect(self.on_sheet_selected)
        top_controls_layout.addWidget(QLabel("Лист для просмотра:"))
        top_controls_layout.addWidget(self.sheets_combo)
        
        top_controls_layout.addStretch()
        
        # Кнопки навигации
        nav_group = QGroupBox("Навигация")
        nav_layout = QHBoxLayout()
        
        self.prev_sheet_btn = QPushButton("◀ Предыдущий")
        self.prev_sheet_btn.clicked.connect(self.on_prev_sheet)
        self.prev_sheet_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_sheet_btn)
        
        self.next_sheet_btn = QPushButton("Следующий ▶")
        self.next_sheet_btn.clicked.connect(self.on_next_sheet)
        self.next_sheet_btn.setEnabled(False)
        nav_layout.addWidget(self.next_sheet_btn)
        
        nav_group.setLayout(nav_layout)
        top_controls_layout.addWidget(nav_group)
        
        # Масштаб
        zoom_group = QGroupBox("Масштаб")
        zoom_layout = QHBoxLayout()
        
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 500)  # Увеличиваем диапазон зума до 500%
        self.zoom_slider.setValue(100)
        self.zoom_slider.setTickInterval(25)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.setMinimumWidth(150)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        zoom_layout.addWidget(self.zoom_slider)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(50)
        self.zoom_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        zoom_layout.addWidget(self.zoom_label)
        
        self.reset_zoom_btn = QPushButton("🔍 Вписать в окно")
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        zoom_layout.addWidget(self.reset_zoom_btn)
        
        zoom_group.setLayout(zoom_layout)
        top_controls_layout.addWidget(zoom_group)
        
        # Настройки отображения
        display_group = QGroupBox("Отображение")
        display_layout = QVBoxLayout()
        
        # Убираем галочку сетки - она больше не нужна
        # self.show_grid_cb = QCheckBox("Показать сетку (100мм)")
        # self.show_grid_cb.setChecked(True)
        # self.show_grid_cb.toggled.connect(self.refresh_visualization)
        # display_layout.addWidget(self.show_grid_cb)
        
        self.show_dimensions_cb = QCheckBox("Показать размеры")
        self.show_dimensions_cb.setChecked(True)
        self.show_dimensions_cb.toggled.connect(self.refresh_visualization)
        display_layout.addWidget(self.show_dimensions_cb)
        
        self.show_names_cb = QCheckBox("Показать названия")
        self.show_names_cb.setChecked(True)
        self.show_names_cb.toggled.connect(self.refresh_visualization)
        display_layout.addWidget(self.show_names_cb)
        
        display_group.setLayout(display_layout)
        top_controls_layout.addWidget(display_group)
        
        controls_layout.addLayout(top_controls_layout)
        
        # Вторая строка - информация о текущем листе
        info_layout = QHBoxLayout()
        
        self.sheet_info_label = QLabel("Выберите лист для просмотра информации")
        self.sheet_info_label.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                padding: 12px;
                background-color: #404040;
                border-radius: 6px;
                border: 2px solid #555555;
            }
        """)
        self.sheet_info_label.setMinimumHeight(60)
        self.sheet_info_label.setMaximumHeight(60)
        self.sheet_info_label.setWordWrap(True)
        info_layout.addWidget(self.sheet_info_label)
        
        controls_layout.addLayout(info_layout)
        
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)
        
        # Основная область: визуализация слева, таблица отходов справа
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - визуализация
        vis_main_group = QGroupBox("Раскрой листа")
        vis_main_layout = QVBoxLayout()
        
        # Графическая сцена
        self.graphics_scene = QGraphicsScene()
        
        # Используем кастомный вид с поддержкой зума
        self.graphics_view = ZoomableGraphicsView(self.graphics_scene, self)
        self.graphics_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graphics_view.setMinimumHeight(600)
        self.graphics_view.setMinimumWidth(600)
        
        # ИСПРАВЛЕНО: Улучшенные настройки прокрутки и зума
        self.graphics_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.graphics_view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.graphics_view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Полная свобода прокрутки
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Дополнительные настройки для улучшенной производительности
        self.graphics_view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.graphics_view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        
        # Включаем обновление сцены только при необходимости
        self.graphics_view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        
        vis_main_layout.addWidget(self.graphics_view)
        vis_main_group.setLayout(vis_main_layout)
        main_splitter.addWidget(vis_main_group)
        
        # Правая часть - таблицы текущего листа
        right_group = QGroupBox("Анализ текущего листа")
        right_layout = QVBoxLayout(right_group)
        
        # Вертикальный сплиттер для двух таблиц
        tables_splitter = QSplitter(Qt.Vertical)
        
        # Таблица деловых остатков текущего листа
        remnants_group = QGroupBox("Деловые остатки текущего листа")
        remnants_layout = QVBoxLayout(remnants_group)
        
        self.current_remnants_table = QTableWidget(0, 4)
        self.current_remnants_table.setHorizontalHeaderLabels([
            'Артикул', 'Высота', 'Ширина', 'Кол-во'
        ])
        # Простая автоматическая настройка ширины столбцов
        header = self.current_remnants_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)  # Последний столбец растягивается
        self.current_remnants_table.setSortingEnabled(True)
        self.current_remnants_table.setMinimumHeight(200)
        remnants_layout.addWidget(self.current_remnants_table)
        
        tables_splitter.addWidget(remnants_group)
        
        # Таблица отходов текущего листа
        waste_group = QGroupBox("Отходы текущего листа")
        waste_layout = QVBoxLayout(waste_group)
        
        self.waste_result_table = QTableWidget(0, 4)
        self.waste_result_table.setHorizontalHeaderLabels([
            'Артикул', 'Высота', 'Ширина', 'Кол-во'
        ])
        # Простая автоматическая настройка ширины столбцов
        header = self.waste_result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)  # Последний столбец растягивается
        self.waste_result_table.setSortingEnabled(True)
        self.waste_result_table.setMinimumHeight(200)
        waste_layout.addWidget(self.waste_result_table)
        
        tables_splitter.addWidget(waste_group)
        
        # Равные размеры для обеих таблиц
        tables_splitter.setSizes([200, 200])
        right_layout.addWidget(tables_splitter)
        
        main_splitter.addWidget(right_group)
        
        # Пропорции: визуализация 55%, анализ текущего листа 45%
        main_splitter.setSizes([550, 450])
        layout.addWidget(main_splitter)
        
        # Добавляем вкладку в интерфейс
        return vis_tab

    def create_statistics_group(self):
        """Создание группы статистики"""
        group = QGroupBox("Общая информация о результатах оптимизации")
        layout = QVBoxLayout(group)
        
        # Основные статистики
        stats_layout = QHBoxLayout()
        
        # Левая колонка - общая информация
        left_layout = QFormLayout()
        
        # Стиль для значений статистики
        stats_style = "color: #ffffff; font-weight: bold; background-color: transparent; font-size: 11pt;"
        
        self.stats_materials_used = QLabel("0")
        self.stats_materials_used.setStyleSheet(stats_style)
        left_layout.addRow("Использовано заготовок (склад материалов):", self.stats_materials_used)
        
        self.stats_remainders_used = QLabel("0")
        self.stats_remainders_used.setStyleSheet(stats_style)
        left_layout.addRow("Использовано заготовок (склад остатков):", self.stats_remainders_used)
        
        self.stats_total_sheets = QLabel("0")
        self.stats_total_sheets.setStyleSheet(stats_style)
        left_layout.addRow("Количество листов (всего):", self.stats_total_sheets)
        
        self.stats_total_details = QLabel("0")
        self.stats_total_details.setStyleSheet(stats_style)
        left_layout.addRow("Количество заготовок (всего):", self.stats_total_details)
        
        # НОВОЕ ПОЛЕ: Распределение элементов
        self.stats_distributed_elements = QLabel("0/0")
        self.stats_distributed_elements.setStyleSheet(stats_style)
        left_layout.addRow("Распределено элементов:", self.stats_distributed_elements)
        
        # ПЕРЕМЕЩЕНО: Общая площадь заготовок теперь в левой колонке
        self.stats_details_area = QLabel("0.00 м²")
        self.stats_details_area.setStyleSheet(stats_style)
        left_layout.addRow("Общая площадь заготовок:", self.stats_details_area)
        
        stats_layout.addLayout(left_layout)
        
        # Правая часть - два столбца: деловые остатки и отходы
        right_section = QHBoxLayout()
        
        # Первый столбец - деловые остатки (зеленый)
        remnants_layout = QFormLayout()
        
        # Стиль для деловых остатков (зеленый)
        remnants_style = "color: #4ecdc4; font-weight: bold; background-color: transparent; font-size: 11pt;"
        
        self.stats_remnants_area = QLabel("0.00 м²")
        self.stats_remnants_area.setStyleSheet(remnants_style)
        remnants_layout.addRow("Площадь деловых остатков:", self.stats_remnants_area)
        
        self.stats_remnants_count = QLabel("0")
        self.stats_remnants_count.setStyleSheet(remnants_style)
        remnants_layout.addRow("Количество деловых остатков:", self.stats_remnants_count)
        
        self.stats_remnants_percent = QLabel("0.00 %")
        self.stats_remnants_percent.setStyleSheet(remnants_style)
        remnants_layout.addRow("Процент деловых остатков:", self.stats_remnants_percent)
        
        right_section.addLayout(remnants_layout)
        
        # Второй столбец - отходы (красный)
        waste_layout = QFormLayout()
        
        # Стиль для отходов (красный)
        waste_style = "color: #ff6b6b; font-weight: bold; background-color: transparent; font-size: 11pt;"
        
        self.stats_waste_area = QLabel("0.00 м²")
        self.stats_waste_area.setStyleSheet(waste_style)
        waste_layout.addRow("Площадь отхода:", self.stats_waste_area)
        
        self.stats_waste_count = QLabel("0")
        self.stats_waste_count.setStyleSheet(waste_style)
        waste_layout.addRow("Количество отхода:", self.stats_waste_count)
        
        self.stats_waste_percent = QLabel("0.00 %")
        self.stats_waste_percent.setStyleSheet(waste_style)
        waste_layout.addRow("Процент отхода:", self.stats_waste_percent)
        
        right_section.addLayout(waste_layout)
        
        stats_layout.addLayout(right_section)
        layout.addLayout(stats_layout)
        
        # Кнопка загрузки данных в Altawin
        upload_layout = QHBoxLayout()
        upload_layout.addStretch()  # Выравнивание по центру
        
        self.upload_to_altawin_button = QPushButton("📤 Загрузить данные оптимизации в Altawin")
        self.upload_to_altawin_button.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                font-size: 12pt;
                margin: 10px 0px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #666666;
                color: #cccccc;
            }
        """)
        self.upload_to_altawin_button.clicked.connect(self.on_upload_to_altawin)
        self.upload_to_altawin_button.setEnabled(False)  # Изначально отключена
        self.upload_to_altawin_button.setToolTip("Загрузить результаты оптимизации обратно в базу данных Altawin")
        
        upload_layout.addWidget(self.upload_to_altawin_button)
        upload_layout.addStretch()  # Выравнивание по центру
        
        layout.addLayout(upload_layout)
        
        return group

    def create_visualization_group(self):
        """Создание группы визуализации"""
        vis_group = QGroupBox("Визуализация раскроя")
        layout = QVBoxLayout()
        
        # Контролы навигации
        controls_layout = QHBoxLayout()
        
        # Выбор листа
        self.sheets_combo = QComboBox()
        self.sheets_combo.setMinimumWidth(350)
        self.sheets_combo.currentIndexChanged.connect(self.on_sheet_selected)
        controls_layout.addWidget(QLabel("Лист:"))
        controls_layout.addWidget(self.sheets_combo)
        
        # Кнопки навигации
        self.prev_sheet_btn = QPushButton("◀ Предыдущий")
        self.prev_sheet_btn.clicked.connect(self.on_prev_sheet)
        self.prev_sheet_btn.setEnabled(False)
        self.next_sheet_btn = QPushButton("Следующий ▶")
        self.next_sheet_btn.clicked.connect(self.on_next_sheet)
        self.next_sheet_btn.setEnabled(False)
        
        controls_layout.addWidget(self.prev_sheet_btn)
        controls_layout.addWidget(self.next_sheet_btn)
        
        controls_layout.addStretch()
        
        # Контроль масштаба
        controls_layout.addWidget(QLabel("Масштаб:"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 500)  # ИСПРАВЛЕНО: 10% - 500%
        self.zoom_slider.setValue(100)  # 100% по умолчанию
        self.zoom_slider.setTickInterval(50)
        self.zoom_slider.setTickPosition(QSlider.TicksBelow)
        self.zoom_slider.setMinimumWidth(150)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        self.zoom_slider.setToolTip("Масштаб: 10% (обзор) - 500% (детальный просмотр)\nИспользуйте колесико мыши для плавного зума")
        controls_layout.addWidget(self.zoom_slider)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(50)
        self.zoom_label.setToolTip("Текущий масштаб отображения")
        controls_layout.addWidget(self.zoom_label)
        
        # Кнопка сброса зума
        self.reset_zoom_btn = QPushButton("🔍 Вписать")
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        self.reset_zoom_btn.setToolTip("Автоматически подобрать масштаб для отображения всего листа")
        controls_layout.addWidget(self.reset_zoom_btn)
        
        # Кнопка с информацией о навигации
        self.help_btn = QPushButton("❓ Помощь")
        self.help_btn.clicked.connect(self.show_navigation_help)
        self.help_btn.setToolTip("Показать подсказки по навигации и зуму")
        controls_layout.addWidget(self.help_btn)
        
        controls_layout.addStretch()
        
        # Настройки отображения - убираем галочку сетки
        # self.show_grid_cb = QCheckBox("Сетка")
        # self.show_grid_cb.setChecked(True)
        # self.show_grid_cb.stateChanged.connect(self.refresh_visualization)
        # self.show_grid_cb.setToolTip("Показать/скрыть сетку 100мм для удобства измерений")
        # controls_layout.addWidget(self.show_grid_cb)
        
        self.show_dimensions_cb = QCheckBox("Размеры")
        self.show_dimensions_cb.setChecked(True)
        self.show_dimensions_cb.stateChanged.connect(self.refresh_visualization)
        self.show_dimensions_cb.setToolTip("Показать/скрыть размеры деталей, остатков и отходов")
        controls_layout.addWidget(self.show_dimensions_cb)
        
        self.show_names_cb = QCheckBox("Названия")
        self.show_names_cb.setChecked(True)
        self.show_names_cb.stateChanged.connect(self.refresh_visualization)
        self.show_names_cb.setToolTip("Показать/скрыть названия деталей (удобно при детальном просмотре)")
        controls_layout.addWidget(self.show_names_cb)
        
        layout.addLayout(controls_layout)
        
        # Информационная панель о текущем листе
        self.sheet_info_label = QLabel("Выберите лист для просмотра информации")
        self.sheet_info_label.setStyleSheet("background-color: #3c3c3c; color: #ffffff; padding: 8px; border-radius: 4px; font-size: 11pt;")
        self.sheet_info_label.setWordWrap(True)
        layout.addWidget(self.sheet_info_label)
        
        # Графическая сцена
        self.graphics_scene = QGraphicsScene()
        
        # Используем кастомный вид с поддержкой зума
        self.graphics_view = ZoomableGraphicsView(self.graphics_scene, self)
        self.graphics_view.setRenderHint(QPainter.Antialiasing)
        self.graphics_view.setMinimumHeight(600)
        self.graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.graphics_view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.graphics_view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        
        layout.addWidget(self.graphics_view)
        
        vis_group.setLayout(layout)
        return vis_group
    
    def on_zoom_changed(self, value):
        """Обработка изменения зума - улучшенная версия"""
        scale = value / 100.0
        
        # Сброс трансформации и применение нового масштаба
        self.graphics_view.resetTransform()
        self.graphics_view.scale(scale, scale)
        
        # Обновляем label
        self.zoom_label.setText(f"{value}%")
        
        # Сохраняем текущий масштаб для других операций
        self.current_zoom_level = scale
    
    def wheel_zoom(self, event):
        """Зум колесиком мыши - улучшенная версия с поддержкой Ctrl+колесико для прокрутки"""
        
        # Проверяем, зажата ли клавиша Ctrl для альтернативной прокрутки
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            # При зажатом Ctrl - свободная прокрутка по горизонтали
            delta = event.angleDelta().y()
            current_scroll = self.graphics_view.horizontalScrollBar().value()
            scroll_step = 50  # Шаг прокрутки
            
            if delta > 0:
                new_scroll = current_scroll - scroll_step
            else:
                new_scroll = current_scroll + scroll_step
                
            self.graphics_view.horizontalScrollBar().setValue(new_scroll)
            return
        
        # Обычный зум
        current_scale = self.zoom_slider.value()
        
        # Определяем шаг зума в зависимости от текущего масштаба
        if current_scale < 50:
            zoom_step = 5
        elif current_scale < 200:
            zoom_step = 10
        else:
            zoom_step = 25
        
        # Определяем направление прокрутки
        if event.angleDelta().y() > 0:  # Прокрутка вверх - увеличение
            new_scale = min(500, current_scale + zoom_step)
        else:  # Прокрутка вниз - уменьшение
            new_scale = max(10, current_scale - zoom_step)
        
        # Применяем новый масштаб
        self.zoom_slider.setValue(new_scale)
    
    def reset_zoom(self):
        """Сброс зума для вписывания в окно - улучшенная версия"""
        if hasattr(self, 'current_sheet_rect') and self.current_sheet_rect:
            # Получаем размеры виджета визуализации
            view_rect = self.graphics_view.viewport().rect()
            
            # Размеры листа на сцене
            sheet_rect = self.current_sheet_rect
            sheet_width = sheet_rect.rect().width()
            sheet_height = sheet_rect.rect().height()
            
            # Учитываем отступы для комфортного просмотра
            margin_percent = 0.1  # 10% отступ
            usable_width = view_rect.width() * (1 - 2 * margin_percent)
            usable_height = view_rect.height() * (1 - 2 * margin_percent)
            
            # Вычисляем необходимый масштаб
            if sheet_width > 0 and sheet_height > 0:
                scale_x = usable_width / sheet_width
                scale_y = usable_height / sheet_height
                scale = min(scale_x, scale_y) * 100  # Преобразуем в проценты
                
                # Ограничиваем масштаб
                scale = max(10, min(500, int(scale)))
                
                # Устанавливаем масштаб
                self.zoom_slider.blockSignals(True)
                self.zoom_slider.setValue(scale)
                self.zoom_slider.blockSignals(False)
                
                # Применяем трансформацию
                self.on_zoom_changed(scale)
                
                # Центрируем вид на листе с небольшой задержкой для корректного позиционирования
                def center_view():
                    self.graphics_view.centerOn(sheet_rect.rect().center())
                
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(50, center_view)
            else:
                # Если размеры листа неизвестны, устанавливаем 100%
                self.zoom_slider.setValue(100)

    def draw_grid(self, width, height, scale_factor):
        """Рисование сетки 100мм на листе"""
        grid_step = 100  # размер ячейки сетки в мм
        grid_pen = QPen(QColor(180, 180, 180), 1, Qt.DotLine)
        
        # Вертикальные линии
        x = grid_step
        while x < width:
            self.graphics_scene.addLine(x * scale_factor, 0, x * scale_factor, height * scale_factor, grid_pen)
            x += grid_step
        
        # Горизонтальные линии
        y = grid_step
        while y < height:
            self.graphics_scene.addLine(0, y * scale_factor, width * scale_factor, y * scale_factor, grid_pen)
            y += grid_step

    def show_navigation_help(self):
        """Показ подсказок по навигации и зуму"""
        help_text = """
🔍 НАВИГАЦИЯ И ЗУМ - ПОЛНАЯ СВОБОДА ДВИЖЕНИЯ

📱 ОСНОВНЫЕ СПОСОБЫ НАВИГАЦИИ:
• Перетаскивание мышью - зажмите левую кнопку и тяните для прокрутки
• Полосы прокрутки - используйте горизонтальную и вертикальную полосы прокрутки

🔍 МАСШТАБИРОВАНИЕ:
• Колесико мыши - плавный зум в центре курсора (10%-500%)
• Слайдер масштаба - точное управление масштабом
• Кнопка "Вписать" - автоматически подгоняет лист под размер окна

🎯 ПРОДВИНУТЫЕ ВОЗМОЖНОСТИ:
• Ctrl + колесико мыши - горизонтальная прокрутка
• Средняя кнопка мыши - альтернативное перетаскивание
• Клавиши ← → ↑ ↓ - точная прокрутка (если в фокусе)

🛠️ НАСТРОЙКИ ОТОБРАЖЕНИЯ:
• Сетка - показывает разметку 100мм для удобства измерений
• Размеры - отображает размеры всех элементов
• Названия - показывает названия деталей

💡 СОВЕТЫ:
• При большом зуме используйте перетаскивание для навигации
• Увеличенные границы сцены позволяют свободно прокручивать во все стороны
• Используйте "Вписать" для быстрого обзора всего листа
• При зуме 500% можно рассмотреть мельчайшие детали

🎨 ЦВЕТОВАЯ СХЕМА:
• Синие оттенки - детали для раскроя
• Зеленые области - деловые остатки (можно переиспользовать)
• Красные области - отходы (идут в отходы)
• Серый фон - лист материала

Теперь у вас полная свобода для изучения раскроя! 🚀
"""
        QMessageBox.information(self, "Помощь по навигации", help_text, QMessageBox.Ok)

    def update_remnants_table(self, sheet_layouts):
        """Обновление общей таблицы остатков (для всех листов)"""
        if not hasattr(self, 'remnants_result_table'):
            return
        self.remnants_result_table.setRowCount(0)
        
        # Собираем все полезные остатки со всех листов
        for sheet_idx, layout in enumerate(sheet_layouts):
            for rect in layout.free_rectangles:
                if rect.width > 0 and rect.height > 0:
                    # Проверяем минимальные размеры из параметров оптимизации
                    min_width = self.min_remnant_width.value() if hasattr(self, 'min_remnant_width') else 180
                    min_height = self.min_remnant_height.value() if hasattr(self, 'min_remnant_height') else 100
                    
                    # Используем улучшенную логику: большая сторона >= большего параметра, меньшая >= меньшего
                    element_min_side = min(rect.width, rect.height)
                    element_max_side = max(rect.width, rect.height)
                    param_min = min(min_width, min_height)
                    param_max = max(min_width, min_height)
                    
                    if element_min_side >= param_min and element_max_side >= param_max:
                        row = self.remnants_result_table.rowCount()
                        self.remnants_result_table.insertRow(row)
                        
                        # Артикул материала
                        marking = layout.sheet.material
                        self.remnants_result_table.setItem(row, 0, QTableWidgetItem(marking))
                        
                        # Высота
                        self.remnants_result_table.setItem(row, 1, QTableWidgetItem(f"{rect.height:.0f}"))
                        
                        # Ширина
                        self.remnants_result_table.setItem(row, 2, QTableWidgetItem(f"{rect.width:.0f}"))
                        
                        # Количество (всегда 1)
                        self.remnants_result_table.setItem(row, 3, QTableWidgetItem("1"))

    # ========== МЕТОДЫ ЗАГРУЗКИ ДАННЫХ ==========
    
    def _set_interactive_mode(self, table):
        """Переключение таблицы в интерактивный режим после автоматического определения ширины"""
        try:
            header = table.horizontalHeader()
            # Переключаем все столбцы в интерактивный режим, кроме последнего
            for i in range(table.columnCount() - 1):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            # Последний столбец остается растягивающимся
            if table.columnCount() > 0:
                header.setSectionResizeMode(table.columnCount() - 1, QHeaderView.ResizeMode.Stretch)
        except Exception as e:
            print(f"⚠️ Ошибка настройки интерактивного режима таблицы: {e}")
    
    def _update_table_column_widths(self, table):
        """Обновление ширины столбцов таблицы после заполнения данными"""
        try:
            header = table.horizontalHeader()
            # Временно переключаем в режим подгонки по содержимому
            for i in range(table.columnCount()):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            
            # Обрабатываем события Qt для пересчета размеров
            QApplication.processEvents()
            
            # Через короткий интервал переключаем в интерактивный режим
            QTimer.singleShot(50, lambda: self._set_interactive_mode(table))
        except Exception as e:
            print(f"⚠️ Ошибка обновления ширины столбцов: {e}")
    
    def update_all_table_widths(self):
        """Обновление ширины столбцов во всех таблицах после заполнения данными"""
        table_names = [
            'details_table',
            'remainders_table', 
            'materials_table',
            'remnants_result_table',
            'waste_results_table',
            'current_remnants_table',
            'waste_result_table'
        ]
        
        for table_name in table_names:
            if hasattr(self, table_name):
                table = getattr(self, table_name)
                if table and table.rowCount() > 0:  # Обновляем только заполненные таблицы
                    table.resizeColumnsToContents()
    
    def on_load_data_clicked(self):
        """Обработчик загрузки данных с API"""
        grorderid = self.grorderid_input.text().strip()
        if not grorderid:
            print("❌ Ошибка: Введите номер сменного задания (grorderid)")
            return
        
        try:
            grorderid = int(grorderid)
        except ValueError:
            print("❌ Ошибка: grorderid должен быть числом")
            return
        
        # Блокируем кнопку
        self.load_data_button.setEnabled(False)
        self.load_data_button.setText("Загрузка...")
        
        # Открываем диалог отладки
        self.debug_dialog = DebugDialog(self)
        self.debug_dialog.show()
        
        # Запускаем загрузку в отдельном потоке
        def load_data():
            try:
                self._add_debug_step(f"🔄 Загрузка данных для заказа {grorderid}...")
                
                # Проверка доступности API
                if not check_api_connection():
                    self.error_signal.emit("API недоступен", 
                        "Сервер API недоступен. Проверьте, что сервер запущен на http://localhost:8000", 
                        "warning")
                    return
                
                # Загрузка деталей
                details_data = get_details_raw(grorderid)
                
                # ИСПРАВЛЕНО: Проверяем что API вернул корректные данные
                if details_data is None:
                    details_data = {}
                    
                # API возвращает 'items', а не 'details' - преобразуем для единообразия
                if 'items' in details_data and 'details' not in details_data:
                    details_data['details'] = details_data['items']
                    
                # Проверяем что есть детали для обработки
                details_list = details_data.get('details', [])
                if not details_list:
                    self._add_debug_step("⚠️ Детали не найдены или данные пусты")
                    details_data['details'] = []
                else:
                    self._add_debug_step(f"✅ Загружено {len(details_list)} деталей")
                
                # Получаем уникальные goodsid
                unique_goodsids = set()
                for detail in details_data.get('details', []):
                    goodsid = detail.get('goodsid')
                    if goodsid:
                        unique_goodsids.add(goodsid)
                
                self._add_debug_step(f"🔍 Найдено {len(unique_goodsids)} уникальных материалов")
                
                # Загрузка остатков и материалов
                all_remainders = []
                all_materials = []
                
                for goodsid in unique_goodsids:
                    try:
                        # Загрузка остатков
                        remainders_response = get_warehouse_remainders(goodsid)
                        if remainders_response and 'remainders' in remainders_response:
                            all_remainders.extend(remainders_response['remainders'])
                        
                        # Загрузка материалов
                        materials_response = get_warehouse_main_material(goodsid)
                        if materials_response and 'main_material' in materials_response:
                            all_materials.extend(materials_response['main_material'])
                            
                    except Exception as e:
                        self._add_debug_step(f"⚠️ Ошибка загрузки для goodsid {goodsid}: {e}")
                        continue
                
                self._add_debug_step(f"✅ Загружено {len(all_remainders)} остатков")
                self._add_debug_step(f"✅ Загружено {len(all_materials)} материалов")
                
                # Обновляем данные в UI
                self.data_loaded_signal.emit(details_data, all_remainders, all_materials)
                self._add_debug_step("🎉 Загрузка данных завершена успешно!")
                self.success_signal.emit()
                
            except Exception as e:
                self._add_debug_step(f"❌ Ошибка загрузки: {e}")
                self.error_signal.emit("Ошибка загрузки", str(e), "critical")
            finally:
                self.restore_button_signal.emit()
        
        # Запускаем в потоке
        thread = threading.Thread(target=load_data, daemon=True)
        thread.start()

    # ========== МЕТОДЫ ОПТИМИЗАЦИИ ==========
    
    def on_optimize_clicked(self):
        """Обработчик кнопки оптимизации"""
        if not self.current_details:
            print("⚠️ Нет данных: Сначала загрузите данные для оптимизации")
            return
        
        # Блокируем кнопку
        self.optimize_button.setEnabled(False)
        self.optimize_button.setText("Оптимизация...")
        
        # Показываем диалог прогресса
        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.show()
        
        # Собираем параметры оптимизации
        params = {
            'min_remnant_width': self.min_remnant_width.value(),
            'min_remnant_height': self.min_remnant_height.value(),
            'target_waste_percent': self.target_waste_percent.value(),
            'min_waste_side': self.min_cut_size.value(),
            'use_warehouse_remnants': self.use_remainders.isChecked()
        }
        
        # Запускаем оптимизацию в отдельном потоке
        def run_optimization():
            try:
                def progress_callback(percent):
                    if self.progress_dialog:
                        # ИСПРАВЛЕНО: Используем правильное имя метода 'set_progress'
                        self.progress_dialog.set_progress(percent)
                
                # Запуск оптимизации
                result = optimize(
                    details=self.current_details,
                    materials=self.current_materials,
                    remainders=self.current_remainders,
                    params=params,
                    progress_fn=progress_callback
                )
                
                # ИСПРАВЛЕНО: Обрабатываем результат если есть хотя бы один размещенный лист
                # Частичный успех (когда размещена часть деталей) тоже является результатом!
                if result and (result.success or len(result.layouts) > 0):
                    self.optimization_result = result
                    self.optimization_result_signal.emit(result)
                else:
                    error_msg = "Оптимизация не дала результатов"
                    if result and hasattr(result, 'message'):
                        error_msg = result.message
                    self.optimization_error_signal.emit(error_msg)
                    
            except Exception as e:
                error_msg = f"Ошибка оптимизации: {str(e)}"
                self.optimization_error_signal.emit(error_msg)
            finally:
                self.close_progress_signal.emit()
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=run_optimization, daemon=True)
        thread.start()

    # ========== МЕТОДЫ ВИЗУАЛИЗАЦИИ ==========
    
    def on_sheet_selected(self, index):
        """Обработчик выбора листа"""
        if index >= 0 and self.optimization_result and index < len(self.optimization_result.sheets):
            self.current_sheet_index = index
            self.visualize_sheet(index)
            self.update_navigation_buttons()
    
    def on_prev_sheet(self):
        """Переход к предыдущему листу"""
        if self.current_sheet_index > 0:
            self.sheets_combo.setCurrentIndex(self.current_sheet_index - 1)
    
    def on_next_sheet(self):
        """Переход к следующему листу"""
        if self.optimization_result and self.current_sheet_index < len(self.optimization_result.sheets) - 1:
            self.sheets_combo.setCurrentIndex(self.current_sheet_index + 1)
    
    def update_navigation_buttons(self):
        """Обновление состояния кнопок навигации"""
        if self.optimization_result:
            self.prev_sheet_btn.setEnabled(self.current_sheet_index > 0)
            self.next_sheet_btn.setEnabled(self.current_sheet_index < len(self.optimization_result.sheets) - 1)
        else:
            self.prev_sheet_btn.setEnabled(False)
            self.next_sheet_btn.setEnabled(False)
    
    def refresh_visualization(self):
        """Обновление визуализации"""
        if self.optimization_result and self.current_sheet_index >= 0:
            self.visualize_sheet(self.current_sheet_index)

    def visualize_sheet(self, sheet_index):
        """Визуализация листа"""
        if not self.optimization_result or sheet_index >= len(self.optimization_result.sheets):
            return
        
        from .visualization_widgets import visualize_sheet_layout
        
        sheet_layout = self.optimization_result.sheets[sheet_index]
        
        # Параметры визуализации - убираем проверку сетки, она больше не нужна
        show_grid = False  # Сетка больше не используется
        show_dimensions = self.show_dimensions_cb.isChecked() if hasattr(self, 'show_dimensions_cb') else True
        show_names = self.show_names_cb.isChecked() if hasattr(self, 'show_names_cb') else True
        
        # Визуализация
        sheet_rect = visualize_sheet_layout(
            self.graphics_scene,
            sheet_layout,
            show_grid=show_grid,
            show_dimensions=show_dimensions,
            show_names=show_names
        )
        
        if sheet_rect:
            self.current_sheet_rect = sheet_rect
            # Автоматически подгоняем масштаб при первом показе
            if hasattr(self, '_first_visualization'):
                delattr(self, '_first_visualization')
                QTimer.singleShot(100, self.reset_zoom)
        
        # Обновляем информацию о листе
        info_text = f"Лист #{sheet_index + 1}: {sheet_layout.sheet.material} "
        info_text += f"({sheet_layout.sheet.width:.0f}x{sheet_layout.sheet.height:.0f} мм) | "
        info_text += f"Размещено: {len(sheet_layout.placed_details)} деталей | "
        info_text += f"Эффективность: {sheet_layout.efficiency:.1f}% | "
        info_text += f"Отходы: {sheet_layout.waste_percent:.1f}%"
        
        self.sheet_info_label.setText(info_text)
        
        # ИСПРАВЛЕНО: Теперь обновляем таблицы текущего листа
        self.update_current_sheet_tables(sheet_layout)

    def update_current_sheet_tables(self, sheet_layout):
        """Обновление таблиц остатков и отходов для текущего листа"""
        # Обновляем таблицу деловых остатков текущего листа
        self.update_current_remnants_table(sheet_layout)
        
        # Обновляем таблицу отходов текущего листа
        self.update_waste_table(sheet_layout)

    def update_current_remnants_table(self, sheet_layout):
        """Обновление таблицы деловых остатков для текущего листа"""
        if not hasattr(self, 'current_remnants_table'):
            return
        
        # Временно отключаем сортировку
        sorting_enabled = self.current_remnants_table.isSortingEnabled()
        self.current_remnants_table.setSortingEnabled(False)
        
        # Очищаем таблицу
        self.current_remnants_table.setRowCount(0)
        
        # Добавляем все полезные остатки текущего листа используя параметры оптимизации
        if hasattr(sheet_layout, 'free_rectangles') and sheet_layout.free_rectangles:
            for i, rect in enumerate(sheet_layout.free_rectangles):
                try:
                    # ИСПРАВЛЕНО: Проверяем что rect это объект FreeRectangle с атрибутами
                    if hasattr(rect, 'width') and hasattr(rect, 'height'):
                        if rect.width > 0 and rect.height > 0:
                            # Используем улучшенную логику: большая сторона >= большего параметра, меньшая >= меньшего
                            min_width = self.min_remnant_width.value() if hasattr(self, 'min_remnant_width') else 180
                            min_height = self.min_remnant_height.value() if hasattr(self, 'min_remnant_height') else 100
                            element_min_side = min(rect.width, rect.height)
                            element_max_side = max(rect.width, rect.height)
                            param_min = min(min_width, min_height)
                            param_max = max(min_width, min_height)
                            
                            if element_min_side >= param_min and element_max_side >= param_max:
                                row = self.current_remnants_table.rowCount()
                                self.current_remnants_table.insertRow(row)
                                
                                # Артикул
                                marking = sheet_layout.sheet.material
                                self.current_remnants_table.setItem(row, 0, _create_text_item(marking))
                                
                                # Высота
                                self.current_remnants_table.setItem(row, 1, _create_numeric_item(rect.height))
                                
                                # Ширина  
                                self.current_remnants_table.setItem(row, 2, _create_numeric_item(rect.width))
                                
                                # Количество (всегда 1 для остатков)
                                self.current_remnants_table.setItem(row, 3, _create_numeric_item(1))
                    
                    # ИСПРАВЛЕНО: Обработка случая когда rect это словарь (для совместимости)
                    elif isinstance(rect, dict):
                        if rect.get('width', 0) > 0 and rect.get('height', 0) > 0:
                            # Проверяем минимальные размеры
                            min_width = self.min_remnant_width.value() if hasattr(self, 'min_remnant_width') else 180
                            min_height = self.min_remnant_height.value() if hasattr(self, 'min_remnant_height') else 100
                            element_min_side = min(rect['width'], rect['height'])
                            element_max_side = max(rect['width'], rect['height'])
                            param_min = min(min_width, min_height)
                            param_max = max(min_width, min_height)
                            
                            if element_min_side >= param_min and element_max_side >= param_max:
                                row = self.current_remnants_table.rowCount()
                                self.current_remnants_table.insertRow(row)
                                
                                # Артикул
                                marking = sheet_layout.sheet.material
                                self.current_remnants_table.setItem(row, 0, _create_text_item(marking))
                                
                                # Высота
                                self.current_remnants_table.setItem(row, 1, _create_numeric_item(rect.get('height', 0)))
                                
                                # Ширина  
                                self.current_remnants_table.setItem(row, 2, _create_numeric_item(rect.get('width', 0)))
                                
                                # Количество (всегда 1 для остатков)
                                self.current_remnants_table.setItem(row, 3, _create_numeric_item(1))
                    
                    else:
                        logger.warning(f"Неизвестный формат free_rectangle: {type(rect)}")
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки остатка {i}: {e}")
                    continue
        
        # Восстанавливаем сортировку
        self.current_remnants_table.setSortingEnabled(sorting_enabled)
        
        # Простое обновление размеров столбцов
        self.current_remnants_table.resizeColumnsToContents()

    def update_waste_table(self, sheet_layout):
        """Обновление таблицы отходов для текущего листа"""
        # ИСПРАВЛЕНО: Используем таблицу из вкладки визуализации, а не результатов
        if not hasattr(self, 'waste_result_table'):
            return
        
        # Временно отключаем сортировку
        sorting_enabled = self.waste_result_table.isSortingEnabled()
        self.waste_result_table.setSortingEnabled(False)
        
        # Очищаем таблицу
        self.waste_result_table.setRowCount(0)
        
        # Добавляем все отходные прямоугольники текущего листа
        if hasattr(sheet_layout, 'waste_rectangles') and sheet_layout.waste_rectangles:
            for i, waste_rect in enumerate(sheet_layout.waste_rectangles):
                try:
                    # ИСПРАВЛЕНО: Проверяем что waste_rect это объект FreeRectangle с атрибутами
                    if hasattr(waste_rect, 'width') and hasattr(waste_rect, 'height'):
                        if waste_rect.width > 0 and waste_rect.height > 0:
                            row = self.waste_result_table.rowCount()
                            self.waste_result_table.insertRow(row)
                            
                            # Артикул
                            marking = sheet_layout.sheet.material
                            self.waste_result_table.setItem(row, 0, _create_text_item(marking))
                            
                            # Высота
                            self.waste_result_table.setItem(row, 1, _create_numeric_item(waste_rect.height))
                            
                            # Ширина
                            self.waste_result_table.setItem(row, 2, _create_numeric_item(waste_rect.width))
                            
                            # Количество (всегда 1 для отходов)
                            self.waste_result_table.setItem(row, 3, _create_numeric_item(1))
                    
                    # ИСПРАВЛЕНО: Обработка случая когда waste_rect это словарь (для совместимости)
                    elif isinstance(waste_rect, dict):
                        if waste_rect.get('width', 0) > 0 and waste_rect.get('height', 0) > 0:
                            row = self.waste_result_table.rowCount()
                            self.waste_result_table.insertRow(row)
                            
                            # Артикул
                            marking = sheet_layout.sheet.material
                            self.waste_result_table.setItem(row, 0, _create_text_item(marking))
                            
                            # Высота
                            self.waste_result_table.setItem(row, 1, _create_numeric_item(waste_rect.get('height', 0)))
                            
                            # Ширина
                            self.waste_result_table.setItem(row, 2, _create_numeric_item(waste_rect.get('width', 0)))
                            
                            # Количество (всегда 1 для отходов)
                            self.waste_result_table.setItem(row, 3, _create_numeric_item(1))
                    
                    else:
                        logger.warning(f"Неизвестный формат waste_rect: {type(waste_rect)}")
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки отхода {i}: {e}")
                    continue
        
        # Восстанавливаем сортировку
        self.waste_result_table.setSortingEnabled(sorting_enabled)
        
        # Простое обновление размеров столбцов
        self.waste_result_table.resizeColumnsToContents()

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========
    
    def _add_debug_step(self, message):
        """Добавление шага отладки"""
        print(f"🔧 DEBUG: {message}")
        self.debug_step_signal.emit(message)
    
    def _add_debug_step_safe(self, message):
        """Thread-safe добавление шага отладки"""
        if self.debug_dialog:
            self.debug_dialog.add_step(message)
    
    def _show_error_safe(self, title, message, icon):
        """Thread-safe показ ошибки"""
        print(f"❌ {title}: {message}")
    
    def _show_success_safe(self):
        """Thread-safe показ успеха"""
        if self.debug_dialog:
            # В DebugDialog нет метода success(), просто закрываем диалог
            QTimer.singleShot(2000, self.debug_dialog.close)
    
    def _update_tables_safe(self, details_data, remainders, materials):
        """Thread-safe обновление таблиц"""
        try:
            # Сохраняем grorderid для последующей загрузки в Altawin
            grorderid = self.grorderid_input.text().strip()
            if grorderid.isdigit():
                self.current_grorderid = int(grorderid)
                print(f"💾 Сохранен grorderid для загрузки: {self.current_grorderid}")
            else:
                self.current_grorderid = None
            
            # ИСПРАВЛЕНО: Проверяем что данные не None перед обращением к ним
            if details_data is None:
                details_data = {}
            if remainders is None:
                remainders = []
            if materials is None:
                materials = []
            
            # Сохраняем текущие данные
            self.current_details = details_data.get('details', [])
            self.current_remainders = remainders
            self.current_materials = materials
            
            # Обновляем информацию о задании
            grorder_info = details_data.get('grorder_info', {})
            self.task_name_label.setText(grorder_info.get('gr_name', '<не указано>'))
            
            # Форматируем дату
            groupdate = grorder_info.get('groupdate', '<не указано>')
            if groupdate and groupdate != '<не указано>':
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(str(groupdate))
                    groupdate = date_obj.strftime('%d.%m.%Y')
                except:
                    pass
            self.task_date_label.setText(groupdate)
            
            self.task_orders_label.setText(grorder_info.get('gr_ordernames', '<не указано>'))
            
            # Обновляем таблицы
            self._update_details_table(self.current_details)
            self._update_remainders_table(self.current_remainders)
            self._update_materials_table(self.current_materials)
            
            # Активируем кнопку оптимизации
            self.optimize_button.setEnabled(True)
            
            # Автоматически подгоняем ширину столбцов
            QTimer.singleShot(500, self.update_all_table_widths)
            
        except Exception as e:
            print(f"❌ Ошибка обновления таблиц: {e}")
    
    def _restore_button_safe(self):
        """Thread-safe восстановление кнопки"""
        self.load_data_button.setEnabled(True)
        self.load_data_button.setText("Загрузить данные")
    
    def _update_details_table(self, details):
        """Обновление таблицы деталей"""
        self.details_table.setRowCount(0)
        for detail in details:
            row = self.details_table.rowCount()
            self.details_table.insertRow(row)
            
            self.details_table.setItem(row, 0, _create_text_item(detail.get('oi_name', '')))
            self.details_table.setItem(row, 1, _create_text_item(detail.get('g_marking', '')))
            self.details_table.setItem(row, 2, _create_numeric_item(detail.get('height', 0)))
            self.details_table.setItem(row, 3, _create_numeric_item(detail.get('width', 0)))
            self.details_table.setItem(row, 4, _create_numeric_item(detail.get('total_qty', 0)))
    
    def _update_remainders_table(self, remainders):
        """Обновление таблицы остатков"""
        self.remainders_table.setRowCount(0)
        for remainder in remainders:
            if remainder.get('qty', 0) > 0:  # Показываем только доступные остатки
                row = self.remainders_table.rowCount()
                self.remainders_table.insertRow(row)
                
                self.remainders_table.setItem(row, 0, _create_text_item(remainder.get('g_marking', '')))
                self.remainders_table.setItem(row, 1, _create_numeric_item(remainder.get('height', 0)))
                self.remainders_table.setItem(row, 2, _create_numeric_item(remainder.get('width', 0)))
                self.remainders_table.setItem(row, 3, _create_numeric_item(remainder.get('qty', 0)))
    
    def _update_materials_table(self, materials):
        """Обновление таблицы материалов"""
        self.materials_table.setRowCount(0)
        for material in materials:
            # Проверяем оба поля: res_qty (для API данных) и qty (для отладочных данных)
            res_qty = material.get('res_qty', 0) or material.get('qty', 0)
            if res_qty and res_qty > 0:  # Показываем только доступные материалы
                row = self.materials_table.rowCount()
                self.materials_table.insertRow(row)
                
                self.materials_table.setItem(row, 0, _create_text_item(material.get('g_marking', '')))
                self.materials_table.setItem(row, 1, _create_numeric_item(material.get('height', 0)))
                self.materials_table.setItem(row, 2, _create_numeric_item(material.get('width', 0)))
                self.materials_table.setItem(row, 3, _create_numeric_item(int(res_qty)))
    
    def _handle_optimization_result(self, result):
        """Обработка результата оптимизации"""
        self.optimization_result = result
        
        # Восстанавливаем кнопку
        self.optimize_button.setEnabled(True)
        self.optimize_button.setText("🚀 Запустить оптимизацию")
        
        # Обновляем статистику
        self._update_statistics(result)
        
        # Обновляем визуализацию
        self._update_visualization(result)
        
        # Активируем кнопку загрузки в Altawin если есть grorderid
        if hasattr(self, 'current_grorderid') and self.current_grorderid:
            self.upload_to_altawin_button.setEnabled(True)
            print(f"✅ Кнопка загрузки в Altawin активирована для grorderid={self.current_grorderid}")
        else:
            print(f"⚠️ Кнопка загрузки в Altawin не активирована - отсутствует grorderid")
        
        # Переключаемся на вкладку результатов
        self.tabs.setCurrentIndex(1)
        
        # ИСПРАВЛЕНО: Убираем модальное окно которое блокирует интерфейс
        # Результат и так виден в статистике и таблицах
        print(f"✅ Оптимизация завершена! Размещено: {result.total_placed_details} деталей, "
              f"листов: {result.total_sheets}, эффективность: {result.total_efficiency:.1f}%")
    
    def _handle_optimization_error(self, error_msg):
        """Обработка ошибки оптимизации"""
        # Восстанавливаем кнопку
        self.optimize_button.setEnabled(True)
        self.optimize_button.setText("🚀 Запустить оптимизацию")
        
        # Показываем ошибку в консоли и пользователю
        print(f"❌ Ошибка оптимизации: {error_msg}")
        QMessageBox.critical(self, "Ошибка оптимизации", f"Произошла ошибка во время выполнения оптимизации:\n\n{error_msg}")
    
    def _close_progress_dialog(self):
        """Закрытие диалога прогресса"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
    
    def _update_statistics(self, result):
        """Обновление статистики"""
        # Подсчет использованных материалов и остатков
        materials_used = 0
        remainders_used = 0
        
        for layout in result.sheets:
            if layout.sheet.is_remainder:
                remainders_used += 1
            else:
                materials_used += 1
        
        # ИСПРАВЛЕНО: Подсчет общего количества элементов для распределения
        total_elements_to_place = 0
        placed_elements = result.total_placed_details
        
        # Подсчитываем общее количество элементов из исходных данных
        if hasattr(self, 'current_details') and self.current_details:
            for detail in self.current_details:
                total_qty = detail.get('total_qty', 0)
                if isinstance(total_qty, (int, float)) and total_qty > 0:
                    total_elements_to_place += int(total_qty)
        
        # Обновляем статистику
        self.stats_materials_used.setText(str(materials_used))
        self.stats_remainders_used.setText(str(remainders_used))
        self.stats_total_sheets.setText(str(result.total_sheets))
        self.stats_total_details.setText(str(result.total_placed_details))
        
        # ИСПРАВЛЕНО: Правильное отображение распределенных элементов
        self.stats_distributed_elements.setText(f"{placed_elements}/{total_elements_to_place}")
        
        # Площади
        total_details_area = sum(layout.used_area for layout in result.sheets)
        total_waste_area = sum(layout.waste_area for layout in result.sheets)
        total_remnants_area = sum(r.area for r in result.useful_remnants)
        
        # ИСПРАВЛЕНО: Правильный подсчет количества элементов
        # Подсчитываем количество отходных записей в таблице (сгруппированных)
        waste_grouped = {}
        for layout in result.sheets:
            g_marking = layout.sheet.material
            if hasattr(layout, 'waste_rectangles'):
                for waste_rect in layout.waste_rectangles:
                    if waste_rect.width > 0 and waste_rect.height > 0:
                        key = (g_marking, waste_rect.width, waste_rect.height)
                        if key in waste_grouped:
                            waste_grouped[key] += 1
                        else:
                            waste_grouped[key] = 1
        
        total_waste_count = len(waste_grouped)  # Количество уникальных записей в таблице отходов
        
        # ИСПРАВЛЕНО: Подсчитываем количество записей в таблице деловых остатков (сгруппированных)
        remnants_grouped = {}
        for layout in result.sheets:
            g_marking = layout.sheet.material
            for rect in layout.free_rectangles:
                # Используем ту же логику что и в таблице
                min_width = self.min_remnant_width.value() if hasattr(self, 'min_remnant_width') else 180
                min_height = self.min_remnant_height.value() if hasattr(self, 'min_remnant_height') else 100
                element_min_side = min(rect.width, rect.height)
                element_max_side = max(rect.width, rect.height)
                param_min = min(min_width, min_height)
                param_max = max(min_width, min_height)
                
                if element_min_side >= param_min and element_max_side >= param_max:
                    key = (g_marking, rect.width, rect.height)
                    if key in remnants_grouped:
                        remnants_grouped[key] += 1
                    else:
                        remnants_grouped[key] = 1
        
        total_remnants_count = len(remnants_grouped)  # Количество уникальных записей в таблице
        
        # Вычисляем процент деловых остатков
        total_area = sum(layout.total_area for layout in result.sheets)
        remnants_percent = (total_remnants_area / total_area * 100) if total_area > 0 else 0
        
        # Конвертируем в м²
        self.stats_details_area.setText(f"{total_details_area / 1_000_000:.2f} м²")
        self.stats_waste_area.setText(f"{total_waste_area / 1_000_000:.2f} м²")
        self.stats_waste_count.setText(str(total_waste_count))
        self.stats_waste_percent.setText(f"{result.total_waste_percent:.2f} %")
        self.stats_remnants_area.setText(f"{total_remnants_area / 1_000_000:.2f} м²")
        self.stats_remnants_count.setText(str(total_remnants_count))
        self.stats_remnants_percent.setText(f"{remnants_percent:.2f} %")
        
        # ИСПРАВЛЕНО: Обновляем таблицы результатов с помощью функций из table_widgets
        try:
            # Обновляем таблицу деловых остатков на вкладке "Результаты оптимизации"
            if hasattr(self, 'remnants_result_table'):
                min_width = self.min_remnant_width.value() if hasattr(self, 'min_remnant_width') else 180
                min_height = self.min_remnant_height.value() if hasattr(self, 'min_remnant_height') else 100
                update_remnants_result_table(self.remnants_result_table, result, min_width, min_height)
                
            # Обновляем таблицу отходов на вкладке "Результаты оптимизации"
            if hasattr(self, 'waste_results_table'):
                update_waste_results_table(self.waste_results_table, result)
                
        except Exception as e:
            logger.error(f"Ошибка обновления таблиц результатов: {e}")
            # Fallback: используем старый метод для таблицы остатков
            self.update_remnants_table(result.sheets)
        
        # Обновляем ширину столбцов после заполнения результатами
        QTimer.singleShot(300, lambda: self.update_all_table_widths())
    
    def _update_visualization(self, result):
        """Обновление визуализации"""
        # Очищаем и заполняем выпадающий список листов
        self.sheets_combo.clear()
        for i, layout in enumerate(result.sheets):
            sheet = layout.sheet
            label = f"Лист #{i+1}: {sheet.material} ({sheet.width:.0f}x{sheet.height:.0f})"
            if sheet.is_remainder:
                label += " [Остаток]"
            self.sheets_combo.addItem(label)
        
        # Устанавливаем флаг первой визуализации
        self._first_visualization = True
        
        # Выбираем первый лист
        if result.sheets:
            self.sheets_combo.setCurrentIndex(0)
            self.current_sheet_index = 0
            self.visualize_sheet(0)
            self.update_navigation_buttons()

    # ========== МЕТОДЫ ЗАГРУЗКИ В ALTAWIN ==========
    
    def on_upload_to_altawin(self):
        """Обработчик загрузки данных оптимизации в Altawin"""
        if not self.optimization_result or not self.optimization_result.sheets:
            print("❌ Нет данных оптимизации для загрузки")
            return
        
        if not hasattr(self, 'current_grorderid') or not self.current_grorderid:
            print("❌ Не определен grorderid для загрузки")
            return
        
        # Диалог подтверждения
        reply = QMessageBox.question(
            self, 
            "Подтверждение загрузки", 
            f"Вы точно хотите загрузить данные оптимизации в Altawin?\n\n"
            f"Сменное задание: {self.current_grorderid}\n"
            f"Количество листов: {len(self.optimization_result.sheets)}\n"
            f"Размещено деталей: {self.optimization_result.total_placed_details}\n\n"
            f"⚠️ Внимание: Существующие данные оптимизации для этого задания будут удалены!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._upload_optimization_data_to_altawin()
    
    def _upload_optimization_data_to_altawin(self):
        """Загрузка данных оптимизации в базу данных Altawin"""
        
        # Блокируем кнопку
        self.upload_to_altawin_button.setEnabled(False)
        self.upload_to_altawin_button.setText("📤 Загрузка...")
        
        try:
            print(f"🔄 Начинаем загрузку данных оптимизации в Altawin для grorderid={self.current_grorderid}")
            
            # Импортируем функции для работы с API - исправляем относительный импорт
            import sys
            import os
            
            # Добавляем корневую папку проекта в путь
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)  # client directory
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            try:
                from core.api_client import upload_optimization_data, check_api_connection
            except ImportError:
                # Альтернативный способ импорта
                from client.core.api_client import upload_optimization_data, check_api_connection
            
            # Проверяем доступность API
            if not check_api_connection():
                raise Exception("API сервер недоступен. Проверьте подключение.")
            
            # Подготавливаем данные для загрузки
            optimization_data = self._prepare_optimization_data_for_upload()
            
            print(f"📊 Подготовлено данных: {len(optimization_data)} листов")
            
            # Проверяем все goodsid перед отправкой
            for i, sheet_data in enumerate(optimization_data):
                goodsid = sheet_data.get('goodsid')
                if not goodsid or goodsid == 0:
                    raise Exception(f"Некорректный goodsid={goodsid} для листа #{i+1}. Проверьте данные материалов.")
                print(f"📋 Лист #{i+1}: goodsid={goodsid}, материал={self.optimization_result.sheets[i].sheet.material}")
            
            # Отправляем данные через API
            result = upload_optimization_data(self.current_grorderid, optimization_data)
            
            if result.get('success'):
                print(f"✅ Данные успешно загружены в Altawin!")
                
                # Показываем сообщение об успехе
                QMessageBox.information(
                    self,
                    "Загрузка завершена",
                    f"✅ Данные оптимизации успешно загружены в Altawin!\n\n"
                    f"Сменное задание: {self.current_grorderid}\n"
                    f"Загружено листов: {len(optimization_data)}\n"
                    f"Общая эффективность: {self.optimization_result.total_efficiency:.1f}%"
                )
            else:
                error_msg = result.get('message', 'Неизвестная ошибка')
                raise Exception(f"Ошибка загрузки: {error_msg}")
                
        except Exception as e:
            error_message = f"Ошибка загрузки в Altawin: {str(e)}"
            print(f"❌ {error_message}")
            
            QMessageBox.critical(
                self,
                "Ошибка загрузки",
                f"❌ Не удалось загрузить данные в Altawin:\n\n{error_message}\n\n"
                "Проверьте подключение к серверу API и правильность данных."
            )
        
        finally:
            # Восстанавливаем кнопку
            self.upload_to_altawin_button.setEnabled(True)
            self.upload_to_altawin_button.setText("📤 Загрузить данные оптимизации в Altawin")
    
    def _prepare_optimization_data_for_upload(self):
        """Подготовка данных оптимизации для загрузки в Altawin"""
        optimization_data = []
        
        for sheet_index, sheet_layout in enumerate(self.optimization_result.sheets):
            # Создаем XML данные
            xml_data = self._create_cutting_xml(sheet_layout, sheet_index + 1)
            
            print(f"📄 XML для листа {sheet_index + 1}: {len(xml_data)} символов, кодировка UTF-8")
            
            # Собираем данные о листе
            sheet_data = {
                'num_glass': sheet_index + 1,  # Порядковый номер листа
                'goodsid': self._extract_goodsid_from_sheet(sheet_layout),
                'width': int(sheet_layout.sheet.width),
                'height': int(sheet_layout.sheet.height),
                'trash_area': int(sheet_layout.waste_area),
                'percent_full': round(sheet_layout.efficiency, 6),
                'percent_waste': round(sheet_layout.waste_percent, 6),
                'piece_count': len(sheet_layout.placed_details),
                'sum_area': int(sheet_layout.used_area),
                'qty': 1,  # Количество листов (всегда 1)
                'is_remainder': -1 if sheet_layout.sheet.is_remainder else 0,
                'xml_data': xml_data  # XML данные в правильной кодировке UTF-8
            }
            
            optimization_data.append(sheet_data)
            
        return optimization_data
    
    def _extract_goodsid_from_sheet(self, sheet_layout):
        """Извлекает goodsid из листа оптимизации"""
        # Способ 1: Используем goodsid из атрибутов листа, если есть
        if hasattr(sheet_layout.sheet, 'goodsid') and sheet_layout.sheet.goodsid:
            print(f"🔍 Найден goodsid в атрибутах листа: {sheet_layout.sheet.goodsid}")
            return sheet_layout.sheet.goodsid
        
        # Способ 2: Попытаемся найти goodsid среди размещенных деталей
        if sheet_layout.placed_details:
            for placed_detail in sheet_layout.placed_details:
                if hasattr(placed_detail, 'detail') and hasattr(placed_detail.detail, 'goodsid'):
                    if placed_detail.detail.goodsid:
                        print(f"🔍 Найден goodsid в детали: {placed_detail.detail.goodsid}")
                        return placed_detail.detail.goodsid
        
        # Способ 3: Ищем в загруженных материалах по артикулу (g_marking)
        material_marking = sheet_layout.sheet.material
        print(f"🔍 Ищем goodsid для материала: {material_marking}")
        
        # Ищем среди основных материалов
        if hasattr(self, 'current_materials') and self.current_materials:
            for material in self.current_materials:
                if material.get('g_marking') == material_marking:
                    goodsid = material.get('goodsid')
                    if goodsid:
                        print(f"✅ Найден goodsid в материалах: {goodsid}")
                        return goodsid
        
        # Ищем среди остатков
        if hasattr(self, 'current_remainders') and self.current_remainders:
            for remainder in self.current_remainders:
                if remainder.get('g_marking') == material_marking:
                    goodsid = remainder.get('goodsid')
                    if goodsid:
                        print(f"✅ Найден goodsid в остатках: {goodsid}")
                        return goodsid
        
        # Способ 4: Ищем в исходных деталях
        if hasattr(self, 'current_details') and self.current_details:
            for detail in self.current_details:
                if detail.get('g_marking') == material_marking:
                    goodsid = detail.get('goodsid')
                    if goodsid:
                        print(f"✅ Найден goodsid в деталях: {goodsid}")
                        return goodsid
        
        # Если ничего не найдено - это критическая ошибка
        error_msg = f"❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось найти goodsid для материала '{material_marking}'"
        print(error_msg)
        raise ValueError(error_msg)
    
    def _create_cutting_xml(self, sheet_layout, sheet_num):
        """Создание XML файла раскроя в UTF-8 кодировке"""
        from xml.etree.ElementTree import Element, SubElement, tostring
        from xml.dom import minidom
        
        # Корневой элемент
        cutting = Element("cutting")
        cutting.set("version", "2.1")
        
        # Заголовок
        header = SubElement(cutting, "header")
        
        # Информация о листе
        glass = SubElement(header, "glass")
        glass.set("id", str(self._extract_goodsid_from_sheet(sheet_layout)))
        glass.set("width", str(int(sheet_layout.sheet.width)))
        glass.set("height", str(int(sheet_layout.sheet.height)))
        glass.set("remainder", "1" if sheet_layout.sheet.is_remainder else "0")
        glass.text = sheet_layout.sheet.material + "  "  # Название материала с двойным пробелом
        
        # Параметры
        params = SubElement(glass, "params")
        
        # Минимальные размеры
        min_width = getattr(self, 'min_remnant_width', None)
        min_height = getattr(self, 'min_remnant_height', None)
        
        minwidth = SubElement(params, "minwidth")
        minwidth.text = str(int(min_width.value())) if min_width and hasattr(min_width, 'value') else "180"
        
        minheight = SubElement(params, "minheight")
        minheight.text = str(int(min_height.value())) if min_height and hasattr(min_height, 'value') else "100"
        
        # Границы
        border = SubElement(params, "border")
        border.set("left", "0")
        border.set("right", "0")
        border.set("top", "0")
        border.set("bottom", "0")
        
        # Ширина реза
        cutwidth = SubElement(params, "cutwidth")
        cutwidth.text = "0"
        
        # Секция деталей
        pieces = SubElement(cutting, "pieces")
        pieces.set("count", str(len(sheet_layout.placed_details)))
        
        # Генерируем резы один раз для использования в разных местах
        cuts = self._generate_guillotine_cuts(sheet_layout)
        
        # Пересчитываем реальные размеры кусков на основе геометрии раскроя
        piece_dimensions = self._calculate_actual_piece_dimensions_with_cuts(sheet_layout, cuts)
        
        # Добавляем все размещенные детали
        for i, placed_detail in enumerate(sheet_layout.placed_details):
            piece = SubElement(pieces, "piece")
            piece.set("num", str(i))
            
            # Используем пересчитанные размеры вместо исходных
            actual_width, actual_height = piece_dimensions.get(i, (placed_detail.width, placed_detail.height))
            piece.set("width", str(int(actual_width)))
            piece.set("height", str(int(actual_height)))
            piece.set("direction", "1" if placed_detail.is_rotated else "0")
            
            # Формируем содержимое piece по формату Altawin:
            # Строка 1: Наименование материала (Артикул заполнения)
            # Строка 2: Номер документа заказ стеклопакетов
            # Строка 3: Наименование изделия
            
            # Извлекаем данные из детали
            material_name = sheet_layout.sheet.material
            gp_marking = ""
            orderno = ""
            oi_name = ""
            
            # Артикул заполнения (gp_marking)
            if hasattr(placed_detail.detail, 'gp_marking') and getattr(placed_detail.detail, 'gp_marking'):
                gp_marking = str(getattr(placed_detail.detail, 'gp_marking')).strip()
            
            # Номер документа (orderno)
            if hasattr(placed_detail.detail, 'orderno') and getattr(placed_detail.detail, 'orderno'):
                orderno = str(getattr(placed_detail.detail, 'orderno')).strip()
            
            # Наименование стеклопакета (oi_name)
            if hasattr(placed_detail.detail, 'oi_name') and getattr(placed_detail.detail, 'oi_name'):
                oi_name = str(getattr(placed_detail.detail, 'oi_name')).strip()
            
            # Формируем строки
            if gp_marking:
                line1 = f"{material_name} ({gp_marking})"
            else:
                line1 = material_name
            
            line2 = orderno if orderno else ""
            line3 = oi_name if oi_name else f"Деталь {i+1}"
            
            # Создаем содержимое piece
            piece.text = f"{line1}\n{line2}\n{line3}"
            
            print(f"📄 XML piece {i}: материал+артикул='{line1}', orderno='{line2}', oi_name='{line3}'")
        
        # Карта размещения
        map_elem = SubElement(cutting, "map")
        
        # Добавляем позиции деталей
        for i, placed_detail in enumerate(sheet_layout.placed_details):
            piece_map = SubElement(map_elem, "piece")
            piece_map.set("num", str(i))
            piece_map.set("x", str(int(placed_detail.x)))
            piece_map.set("y", str(int(placed_detail.y)))
            
            # ИСПРАВЛЕНО: Упрощенная логика rotate - всегда вертикальный текст
            # Судя по правильному XML, для стекла всегда используется rotate="0" (вертикальный текст)
            # Это обеспечивает правильное отображение текста в Altawin
            
            rotate_value = "0"  # Всегда вертикальный текст для стекла
            
            piece_map.set("rotate", rotate_value)
            
            print(f"📄 XML piece {i}: размеры {int(placed_detail.width)}x{int(placed_detail.height)}, "
                  f"direction={placed_detail.is_rotated}, rotate={rotate_value} (вертикальный текст)")
        
        # Добавляем резы (используем уже сгенерированные)
        self._add_cuts_to_xml_with_cuts(map_elem, cuts)
        
        # Остатки
        remainders = SubElement(cutting, "remainders")
        
        # Подсчитываем общее количество остатков и отходов
        remnant_count = 0
        
        # Деловые остатки
        for rect in sheet_layout.free_rectangles:
            if rect.width > 0 and rect.height > 0:
                remainder = SubElement(remainders, "remainder")
                remainder.set("x", str(int(rect.x)))
                remainder.set("y", str(int(rect.y)))
                remainder.set("width", str(int(rect.width)))
                remainder.set("height", str(int(rect.height)))
                remainder.set("waste", "0")  # Деловой остаток
                remnant_count += 1
        
        # Отходы
        for rect in sheet_layout.waste_rectangles:
            if rect.width > 0 and rect.height > 0:
                remainder = SubElement(remainders, "remainder")
                remainder.set("x", str(int(rect.x)))
                remainder.set("y", str(int(rect.y)))
                remainder.set("width", str(int(rect.width)))
                remainder.set("height", str(int(rect.height)))
                remainder.set("waste", "1")  # Отход
                remnant_count += 1
        
        remainders.set("count", str(remnant_count))
        
        # Создаем XML в ANSI (Windows-1251)
        print(f"📄 Создаем XML в ANSI кодировке (Windows-1251)")
        
        # Создаем XML с Windows-1251 кодировкой
        rough_string = tostring(cutting, encoding='windows-1251')
        
        # Парсим и форматируем с отступами
        reparsed = minidom.parseString(rough_string)
        
        # Получаем красиво отформатированный XML в Windows-1251
        pretty_xml = reparsed.toprettyxml(indent="  ", encoding='windows-1251').decode('windows-1251')
        
        # Убираем лишние пустые строки
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        
        # Устанавливаем XML декларацию для Windows-1251
        lines[0] = '<?xml version="1.0" encoding="windows-1251" standalone="yes"?>'
        
        # Формируем финальный XML в ANSI
        final_xml_ansi = '\n'.join(lines)
        
        # Исправляем форматирование glass элемента - убираем переносы строк внутри
        import re
        pattern = r'(<glass[^>]*>)\s*\n\s*([^<]+?)\s*(<params>)'
        final_xml_ansi = re.sub(pattern, r'\1\2  \3', final_xml_ansi)
        
        print(f"📄 Создан XML в ANSI: {len(final_xml_ansi)} символов")
        
        # Конвертируем в UTF-8 для отправки
        print(f"📄 Конвертируем из ANSI в UTF-8 для отправки")
        
        try:
            # Кодируем ANSI строку в байты Windows-1251
            ansi_bytes = final_xml_ansi.encode('windows-1251')
            
            # Декодируем байты как UTF-8 (правильная конвертация)
            utf8_xml = ansi_bytes.decode('windows-1251')
            
            # Меняем декларацию кодировки на UTF-8
            utf8_xml = utf8_xml.replace(
                '<?xml version="1.0" encoding="windows-1251" standalone="yes"?>',
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            )
            
            print(f"📄 Конвертирован в UTF-8: {len(utf8_xml)} символов")
            
            return utf8_xml
            
        except Exception as e:
            print(f"❌ Ошибка при конвертации из ANSI в UTF-8: {e}")
            # В случае ошибки возвращаем исходный ANSI XML
            return final_xml_ansi


    def _generate_guillotine_cuts(self, sheet_layout):
        """
        Генерация правильных гильотинных резов без дублирования.
        
        Новый алгоритм:
        1. Собирает все уникальные координаты X и Y
        2. Проверяет каждую потенциальную линию реза
        3. Создает только необходимые резы без дублирования
        4. Обеспечивает согласованность геометрии
        """
        print(f"🔧 Генерация гильотинных резов для листа {sheet_layout.sheet.width}x{sheet_layout.sheet.height}")
        
        # Собираем все прямоугольники (детали, остатки, отходы)
        all_rects = sheet_layout.placed_details + sheet_layout.free_rectangles + sheet_layout.waste_rectangles
        
        if not all_rects:
            print("⚠️ Нет прямоугольников для генерации резов")
            return []

        # Собираем все уникальные координаты
        x_coords = {0, sheet_layout.sheet.width}  # Границы листа
        y_coords = {0, sheet_layout.sheet.height}  # Границы листа

        # Добавляем координаты всех прямоугольников
        for rect in all_rects:
            x_coords.add(rect.x)
            x_coords.add(rect.x + rect.width)
            y_coords.add(rect.y)
            y_coords.add(rect.y + rect.height)

        # Сортируем координаты и убираем дубликаты
        sorted_x = sorted([x for x in x_coords if x is not None])
        sorted_y = sorted([y for y in y_coords if y is not None])

        print(f"🔧 X координаты: {sorted_x}")
        print(f"🔧 Y координаты: {sorted_y}")

        def point_is_inside_rect(px, py, rect):
            """Проверяет, находится ли точка внутри прямоугольника"""
            return (rect.x <= px < rect.x + rect.width and 
                    rect.y <= py < rect.y + rect.height)

        def find_rect_at_point(px, py):
            """Находит прямоугольник, содержащий точку"""
            for i, rect in enumerate(all_rects):
                if point_is_inside_rect(px, py, rect):
                    return i
            return -1  # Пустое место

        cuts = []

        # Проверяем вертикальные резы (внутренние X координаты)
        for x in sorted_x[1:-1]:  # Исключаем границы листа
            # Проверяем каждый сегмент по Y
            segments = []
            for i in range(len(sorted_y) - 1):
                y1, y2 = sorted_y[i], sorted_y[i + 1]
                
                # Проверяем середину сегмента
                mid_y = (y1 + y2) / 2
                
                # Находим прямоугольники слева и справа от линии реза
                left_rect = find_rect_at_point(x - 0.1, mid_y)
                right_rect = find_rect_at_point(x + 0.1, mid_y)
                
                # Если слева и справа разные прямоугольники, нужен рез
                if left_rect != right_rect:
                    segments.append((y1, y2))
            
            # Объединяем соседние сегменты в один длинный рез
            if segments:
                # Сортируем сегменты по Y
                segments.sort()
                
                # Объединяем соседние сегменты
                merged_segments = []
                current_start, current_end = segments[0]
                
                for i in range(1, len(segments)):
                    seg_start, seg_end = segments[i]
                    
                    # Если сегменты соседние, объединяем
                    if abs(current_end - seg_start) < 1e-5:
                        current_end = seg_end
                    else:
                        # Сохраняем текущий сегмент и начинаем новый
                        merged_segments.append((current_start, current_end))
                        current_start, current_end = seg_start, seg_end
                
                # Добавляем последний сегмент
                merged_segments.append((current_start, current_end))
                
                # Создаем резы из объединенных сегментов
                for y1, y2 in merged_segments:
                    cuts.append({
                        "orientation": "vert",
                        "x": x,
                        "y1": y1,
                        "y2": y2
                    })
                    print(f"📏 Вертикальный рез: x={x}, y1={y1}, y2={y2}")

        # Проверяем горизонтальные резы (внутренние Y координаты)
        for y in sorted_y[1:-1]:  # Исключаем границы листа
            # Проверяем каждый сегмент по X
            segments = []
            for i in range(len(sorted_x) - 1):
                x1, x2 = sorted_x[i], sorted_x[i + 1]
                
                # Проверяем середину сегмента
                mid_x = (x1 + x2) / 2
                
                # Находим прямоугольники сверху и снизу от линии реза
                below_rect = find_rect_at_point(mid_x, y - 0.1)
                above_rect = find_rect_at_point(mid_x, y + 0.1)
                
                # Если сверху и снизу разные прямоугольники, нужен рез
                if below_rect != above_rect:
                    segments.append((x1, x2))
            
            # Объединяем соседние сегменты в один длинный рез
            if segments:
                # Сортируем сегменты по X
                segments.sort()
                
                # Объединяем соседние сегменты
                merged_segments = []
                current_start, current_end = segments[0]
                
                for i in range(1, len(segments)):
                    seg_start, seg_end = segments[i]
                    
                    # Если сегменты соседние, объединяем
                    if abs(current_end - seg_start) < 1e-5:
                        current_end = seg_end
                    else:
                        # Сохраняем текущий сегмент и начинаем новый
                        merged_segments.append((current_start, current_end))
                        current_start, current_end = seg_start, seg_end
                
                # Добавляем последний сегмент
                merged_segments.append((current_start, current_end))
                
                # Создаем резы из объединенных сегментов
                for x1, x2 in merged_segments:
                    cuts.append({
                        "orientation": "horiz",
                        "y": y,
                        "x1": x1,
                        "x2": x2
                    })
                    print(f"📏 Горизонтальный рез: y={y}, x1={x1}, x2={x2}")

        print(f"🔧 Создано резов: {len(cuts)}")
        return cuts

    def set_task_id(self, task_id: str):
        """Установить идентификатор сменного задания в поле ввода из внешнего источника"""
        if task_id:
            self.grorderid_input.setText(str(task_id))

    def _calculate_actual_piece_dimensions_with_cuts(self, sheet_layout, cuts):
        """
        Пересчитывает реальные размеры кусков на основе уже сгенерированных резов.
        Возвращает словарь {piece_index: (actual_width, actual_height)}
        """
        print(f"🔧 Пересчет размеров кусков для обеспечения согласованности (оптимизированная версия)")
        
        # Собираем все координаты резов
        x_cuts = {0, sheet_layout.sheet.width}  # Границы листа
        y_cuts = {0, sheet_layout.sheet.height}  # Границы листа
        
        for cut in cuts:
            if cut["orientation"] == "vert":
                x_cuts.add(cut["x"])
            else:  # horiz
                y_cuts.add(cut["y"])
        
        # Сортируем координаты
        sorted_x_cuts = sorted(x_cuts)
        sorted_y_cuts = sorted(y_cuts)
        
        print(f"🔧 X резы: {sorted_x_cuts}")
        print(f"🔧 Y резы: {sorted_y_cuts}")
        
        # Создаем сетку ячеек между резами
        cells = []
        for i in range(len(sorted_x_cuts) - 1):
            for j in range(len(sorted_y_cuts) - 1):
                x1, x2 = sorted_x_cuts[i], sorted_x_cuts[i + 1]
                y1, y2 = sorted_y_cuts[j], sorted_y_cuts[j + 1]
                cells.append({
                    'x': x1,
                    'y': y1,
                    'width': x2 - x1,
                    'height': y2 - y1,
                    'center_x': (x1 + x2) / 2,
                    'center_y': (y1 + y2) / 2
                })
        
        # Сопоставляем куски с ячейками сетки
        piece_dimensions = {}
        
        for piece_idx, placed_detail in enumerate(sheet_layout.placed_details):
            # Находим центр куска
            piece_center_x = placed_detail.x + placed_detail.width / 2
            piece_center_y = placed_detail.y + placed_detail.height / 2
            
            # Ищем ячейку, содержащую центр куска
            for cell in cells:
                if (cell['x'] <= piece_center_x < cell['x'] + cell['width'] and
                    cell['y'] <= piece_center_y < cell['y'] + cell['height']):
                    
                    # Найдена соответствующая ячейка
                    actual_width = cell['width']
                    actual_height = cell['height']
                    
                    piece_dimensions[piece_idx] = (actual_width, actual_height)
                    
                    print(f"🔧 Кусок {piece_idx}: исходный={int(placed_detail.width)}x{int(placed_detail.height)}, "
                          f"реальный={int(actual_width)}x{int(actual_height)}")
                    break
            else:
                # Если не нашли соответствующую ячейку, используем исходные размеры
                piece_dimensions[piece_idx] = (placed_detail.width, placed_detail.height)
                print(f"⚠️ Кусок {piece_idx}: не найдена ячейка, используем исходные размеры")
        
        return piece_dimensions

    def _add_cuts_to_xml_with_cuts(self, map_elem, cuts):
        """Добавление уже сгенерированных резов в XML"""
        from xml.etree.ElementTree import SubElement
        
        print(f"🔧 Добавление {len(cuts)} резов в XML")
        
        # Добавляем резы в порядке, который ожидает Altawin
        for cut_info in cuts:
            cut = SubElement(map_elem, "cut")
            
            if cut_info["orientation"] == "horiz":
                # Для горизонтальных резов: y, x1, x2, orientation (последний)
                cut.set("y", str(int(cut_info["y"])))
                cut.set("x1", str(int(cut_info["x1"])))
                cut.set("x2", str(int(cut_info["x2"])))
                cut.set("orientation", cut_info["orientation"])
            else:  # vert
                # Для вертикальных резов: x, orientation (второй), y1, y2
                cut.set("x", str(int(cut_info["x"])))
                cut.set("orientation", cut_info["orientation"])
                cut.set("y1", str(int(cut_info["y1"])))
                cut.set("y2", str(int(cut_info["y2"])))

    def _calculate_actual_piece_dimensions(self, sheet_layout):
        """
        Пересчитывает реальные размеры кусков на основе геометрии раскроя.
        Возвращает словарь {piece_index: (actual_width, actual_height)}
        """
        print(f"🔧 Пересчет размеров кусков для обеспечения согласованности")
        
        # Генерируем резы для анализа геометрии
        cuts = self._generate_guillotine_cuts(sheet_layout)
        
        # Собираем все координаты резов
        x_cuts = {0, sheet_layout.sheet.width}  # Границы листа
        y_cuts = {0, sheet_layout.sheet.height}  # Границы листа
        
        for cut in cuts:
            if cut["orientation"] == "vert":
                x_cuts.add(cut["x"])
            else:  # horiz
                y_cuts.add(cut["y"])
        
        # Сортируем координаты
        sorted_x_cuts = sorted(x_cuts)
        sorted_y_cuts = sorted(y_cuts)
        
        print(f"🔧 X резы: {sorted_x_cuts}")
        print(f"🔧 Y резы: {sorted_y_cuts}")
        
        # Создаем сетку ячеек между резами
        cells = []
        for i in range(len(sorted_x_cuts) - 1):
            for j in range(len(sorted_y_cuts) - 1):
                x1, x2 = sorted_x_cuts[i], sorted_x_cuts[i + 1]
                y1, y2 = sorted_y_cuts[j], sorted_y_cuts[j + 1]
                cells.append({
                    'x': x1,
                    'y': y1,
                    'width': x2 - x1,
                    'height': y2 - y1,
                    'center_x': (x1 + x2) / 2,
                    'center_y': (y1 + y2) / 2
                })
        
        # Сопоставляем куски с ячейками сетки
        piece_dimensions = {}
        
        for piece_idx, placed_detail in enumerate(sheet_layout.placed_details):
            # Находим центр куска
            piece_center_x = placed_detail.x + placed_detail.width / 2
            piece_center_y = placed_detail.y + placed_detail.height / 2
            
            # Ищем ячейку, содержащую центр куска
            for cell in cells:
                if (cell['x'] <= piece_center_x < cell['x'] + cell['width'] and
                    cell['y'] <= piece_center_y < cell['y'] + cell['height']):
                    
                    # Найдена соответствующая ячейка
                    actual_width = cell['width']
                    actual_height = cell['height']
                    
                    piece_dimensions[piece_idx] = (actual_width, actual_height)
                    
                    print(f"🔧 Кусок {piece_idx}: исходный={int(placed_detail.width)}x{int(placed_detail.height)}, "
                          f"реальный={int(actual_width)}x{int(actual_height)}")
                    break
            else:
                # Если не нашли соответствующую ячейку, используем исходные размеры
                piece_dimensions[piece_idx] = (placed_detail.width, placed_detail.height)
                print(f"⚠️ Кусок {piece_idx}: не найдена ячейка, используем исходные размеры")
        
        return piece_dimensions
