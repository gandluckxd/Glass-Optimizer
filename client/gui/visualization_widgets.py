"""
Виджеты визуализации для приложения оптимизации 2D раскроя
"""

from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox, QPushButton, QGraphicsTextItem
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QPen, QColor, QPainter, QFont
from .config import VISUALIZATION_DEFAULTS, COLORS


class ZoomableGraphicsView(QGraphicsView):
    """Виджет графической области с возможностью масштабирования"""
    
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
    
    def wheelEvent(self, event):
        """Обработка колеса мыши для масштабирования"""
        # Получаем угол поворота колеса
        angle = event.angleDelta().y()
        
        # Вычисляем фактор масштабирования
        factor = 1.2 if angle > 0 else 1 / 1.2
        
        # Применяем масштабирование
        self.scale(factor, factor)
        
        # Передаем событие дальше
        event.accept()


class VisualizationManager:
    """Менеджер визуализации"""
    
    def __init__(self):
        self.current_zoom_level = VISUALIZATION_DEFAULTS['zoom_default']
        self.graphics_scene = None
        self.graphics_view = None
        self.sheets_combo = None
        self.current_sheet_index = 0
        self.optimization_result = None
        
        # Кэш для отрисовки
        self.cached_drawings = {}
    
    def setup_graphics_view(self, graphics_view, graphics_scene):
        """Настройка графического представления"""
        self.graphics_view = graphics_view
        self.graphics_scene = graphics_scene
        
        # Настройка сцены
        self.graphics_scene.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        
        # Настройка вида
        self.graphics_view.setRenderHint(QPainter.Antialiasing)
        self.graphics_view.setDragMode(QGraphicsView.ScrollHandDrag)
    
    def setup_navigation(self, sheets_combo, prev_btn, next_btn):
        """Настройка навигации по листам"""
        self.sheets_combo = sheets_combo
        self.prev_sheet_btn = prev_btn
        self.next_sheet_btn = next_btn
        
        # Подключение сигналов
        self.sheets_combo.currentIndexChanged.connect(self.on_sheet_selected)
        self.prev_sheet_btn.clicked.connect(self.on_prev_sheet)
        self.next_sheet_btn.clicked.connect(self.on_next_sheet)
    
    def set_sheet_changed_callback(self, callback):
        """Установка callback для изменения листа"""
        self.sheet_changed_callback = callback
    
    def setup_zoom_controls(self, zoom_slider, zoom_label, reset_btn):
        """Настройка элементов управления масштабом"""
        self.zoom_slider = zoom_slider
        self.zoom_label = zoom_label
        self.reset_zoom_btn = reset_btn
        
        # Настройка слайдера масштаба
        self.zoom_slider.setRange(
            VISUALIZATION_DEFAULTS['zoom_min'], 
            VISUALIZATION_DEFAULTS['zoom_max']
        )
        self.zoom_slider.setValue(VISUALIZATION_DEFAULTS['zoom_default'])
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        
        # Кнопка сброса масштаба
        self.reset_zoom_btn.clicked.connect(self.reset_zoom)
        
        # Обновляем label
        self.update_zoom_label()
    
    def on_zoom_changed(self, value):
        """Обработка изменения масштаба"""
        if not self.graphics_view:
            return
            
        # Сохраняем центр вида
        center = self.graphics_view.mapToScene(self.graphics_view.viewport().rect().center())
        
        # Сбрасываем трансформацию и применяем новый масштаб
        self.graphics_view.resetTransform()
        scale_factor = value / 100.0
        self.graphics_view.scale(scale_factor, scale_factor)
        
        # Восстанавливаем центр вида
        self.graphics_view.centerOn(center)
        
        # Обновляем значение масштаба
        self.current_zoom_level = value
        self.update_zoom_label()
    
    def wheel_zoom(self, event):
        """Масштабирование колесом мыши"""
        if not self.graphics_view:
            return
            
        # Получаем угол поворота колеса
        angle = event.angleDelta().y()
        
        # Вычисляем новое значение масштаба
        if angle > 0:
            new_zoom = min(self.current_zoom_level * 1.2, VISUALIZATION_DEFAULTS['zoom_max'])
        else:
            new_zoom = max(self.current_zoom_level / 1.2, VISUALIZATION_DEFAULTS['zoom_min'])
        
        # Применяем новый масштаб
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.setValue(int(new_zoom))
        
        event.accept()
    
    def reset_zoom(self):
        """Сброс масштаба к значению по умолчанию"""
        if hasattr(self, 'zoom_slider'):
            self.zoom_slider.setValue(VISUALIZATION_DEFAULTS['zoom_default'])
        
        # Центрируем вид с задержкой для корректного применения масштаба
        if self.graphics_view and self.graphics_scene:
            QTimer.singleShot(100, self.center_view)
    
    def center_view(self):
        """Центрирование вида на содержимом сцены"""
        if self.graphics_view and self.graphics_scene:
            self.graphics_view.fitInView(
                self.graphics_scene.itemsBoundingRect(), 
                Qt.KeepAspectRatio
            )
    
    def update_zoom_label(self):
        """Обновление метки масштаба"""
        if hasattr(self, 'zoom_label'):
            self.zoom_label.setText(f"{self.current_zoom_level}%")
    
    def update_visualization(self, result):
        """Обновление визуализации с результатами оптимизации"""
        if not self.sheets_combo or not result:
            return
            
        self.optimization_result = result
        self.sheets_combo.clear()
        
        if not result.sheets:
            if self.graphics_scene:
                self.graphics_scene.clear()
            return
        
        # Заполнение комбобокса листов
        for i, sheet_data in enumerate(result.sheets):
            width = sheet_data['width']
            height = sheet_data['height']
            self.sheets_combo.addItem(f"Лист {i+1} ({width}×{height} мм)")
        
        # Показ первого листа
        if result.sheets:
            self.sheets_combo.setCurrentIndex(0)
            self.show_sheet(0)
        
        # Активация кнопок навигации
        self.update_navigation_buttons()
    
    def show_sheet(self, index):
        """Отображение конкретного листа"""
        if not self.optimization_result or not self.graphics_scene:
            return
            
        if index < 0 or index >= len(self.optimization_result.sheets):
            return
            
        self.current_sheet_index = index
        sheet_data = self.optimization_result.sheets[index]
        
        # Очищаем сцену
        self.graphics_scene.clear()
        
        # Получаем размеры листа
        sheet_width = sheet_data['width']
        sheet_height = sheet_data['height']
        
        # Масштабирование для отображения (1 мм = 1 пиксель)
        scale_factor = 1.0
        
        # УЛУЧШЕНИЕ 1: Добавляем отступы для свободной прокрутки
        padding = max(sheet_width, sheet_height) * 0.3  # 30% от максимальной стороны листа
        
        # Рисуем контур листа с четкими границами
        sheet_pen = QPen(QColor(COLORS['sheet_border']), 3)  # Увеличена толщина
        self.graphics_scene.addRect(
            0, 0, sheet_width * scale_factor, sheet_height * scale_factor, 
            sheet_pen
        )
        
        # Рисуем размещенные детали
        placements = sheet_data.get('placements', [])
        for placement in placements:
            x = placement['x'] * scale_factor
            y = placement['y'] * scale_factor
            width = placement['width'] * scale_factor
            height = placement['height'] * scale_factor
            
            # УЛУЧШЕНИЕ 3: Четкие границы деталей
            detail_pen = QPen(QColor(COLORS['detail_border']), 2)  # Увеличена толщина
            detail_brush = QBrush(QColor(COLORS['detail_fill']))
            detail_rect = self.graphics_scene.addRect(x, y, width, height, detail_pen, detail_brush)
            
            # УЛУЧШЕНИЕ 2: Добавляем текст с названием и размерами
            if 'oi_name' in placement or 'name' in placement:
                # Получаем название детали
                detail_name = placement.get('oi_name', placement.get('name', ''))
                
                # Размеры в оригинальных единицах (мм)
                orig_width = placement['width']
                orig_height = placement['height']
                
                # Формируем текст
                detail_text_parts = []
                if detail_name:
                    detail_text_parts.append(detail_name)
                if orig_width and orig_height:
                    detail_text_parts.append(f"{orig_width:.0f}×{orig_height:.0f} мм")
                
                if detail_text_parts:
                    detail_text = "\n".join(detail_text_parts)
                    
                    # УЛУЧШЕННАЯ АДАПТИВНАЯ ЛОГИКА ШРИФТА - увеличено в 2 раза + умная адаптация
                    font_size = _calculate_adaptive_font_size(detail_text, width, height)
                    
                    if font_size > 0:  # Только если нашли подходящий размер
                        # Создаем текстовый элемент
                        text_item = QGraphicsTextItem(detail_text)
                        text_item.setDefaultTextColor(QColor(COLORS['text']))
                        text_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                        
                        # Позиционируем текст в центре детали
                        text_rect = text_item.boundingRect()
                        text_x = x + (width - text_rect.width()) / 2
                        text_y = y + (height - text_rect.height()) / 2
                        text_item.setPos(text_x, text_y)
                        
                        self.graphics_scene.addItem(text_item)
        
        # Рисуем полезные остатки с четкими границами и размерами
        useful_remnants = sheet_data.get('useful_remnants', [])
        for remnant in useful_remnants:
            if hasattr(remnant, 'x') and hasattr(remnant, 'y'):
                x = remnant.x * scale_factor
                y = remnant.y * scale_factor
                width = remnant.width * scale_factor
                height = remnant.height * scale_factor
                
                # УЛУЧШЕНИЕ 3: Четкие границы остатков
                remnant_pen = QPen(QColor(COLORS['remainder_border']), 2)  # Увеличена толщина
                remnant_brush = QBrush(QColor(COLORS['remainder_fill']))
                self.graphics_scene.addRect(x, y, width, height, remnant_pen, remnant_brush)
                
                # Добавляем размеры остатка если он достаточно большой
                if width > 80 and height > 40:
                    remnant_text = f"{remnant.width:.0f}×{remnant.height:.0f}"
                    font_size = _calculate_adaptive_font_size(remnant_text, width, height)
                    
                    if font_size > 0:
                        text_item = QGraphicsTextItem(remnant_text)
                        text_item.setDefaultTextColor(QColor('#000000'))  # Черный текст на оранжевом фоне
                        text_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                        
                        text_rect = text_item.boundingRect()
                        text_x = x + (width - text_rect.width()) / 2
                        text_y = y + (height - text_rect.height()) / 2
                        text_item.setPos(text_x, text_y)
                        
                        self.graphics_scene.addItem(text_item)
        
        # Рисуем отходы с четкими границами и размерами
        waste_rectangles = sheet_data.get('waste_rectangles', [])
        for waste in waste_rectangles:
            x = waste['x'] * scale_factor
            y = waste['y'] * scale_factor
            width = waste['width'] * scale_factor
            height = waste['height'] * scale_factor
            
            # УЛУЧШЕНИЕ 3: Четкие границы отходов
            waste_pen = QPen(QColor(COLORS['waste_border']), 2)  # Увеличена толщина
            waste_brush = QBrush(QColor(COLORS['waste_fill']))
            self.graphics_scene.addRect(x, y, width, height, waste_pen, waste_brush)
            
            # Добавляем размеры отхода если он достаточно большой
            if width > 60 and height > 30:
                waste_text = f"{waste['width']:.0f}×{waste['height']:.0f}"
                font_size = _calculate_adaptive_font_size(waste_text, width, height)
                
                if font_size > 0:
                    text_item = QGraphicsTextItem(waste_text)
                    text_item.setDefaultTextColor(QColor('#FFFFFF'))  # Белый текст на красном фоне
                    text_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                    
                    text_rect = text_item.boundingRect()
                    text_x = x + (width - text_rect.width()) / 2
                    text_y = y + (height - text_rect.height()) / 2
                    text_item.setPos(text_x, text_y)
                    
                    self.graphics_scene.addItem(text_item)
        
        # УЛУЧШЕНИЕ 1: Устанавливаем размер сцены с отступами для свободной прокрутки
        self.graphics_scene.setSceneRect(
            -padding, -padding, 
            (sheet_width * scale_factor) + (padding * 2), 
            (sheet_height * scale_factor) + (padding * 2)
        )
        
        # Применяем текущий масштаб
        if hasattr(self, 'zoom_slider'):
            self.on_zoom_changed(self.zoom_slider.value())
    
    def on_sheet_selected(self, index):
        """Обработка выбора листа из комбобокса"""
        if index >= 0:
            self.show_sheet(index)
            # Обновляем таблицу отходов для текущего листа, если есть callback
            if hasattr(self, 'sheet_changed_callback') and self.sheet_changed_callback:
                self.sheet_changed_callback(index)
    
    def on_prev_sheet(self):
        """Переход к предыдущему листу"""
        if self.sheets_combo:
            current = self.sheets_combo.currentIndex()
            if current > 0:
                self.sheets_combo.setCurrentIndex(current - 1)
    
    def on_next_sheet(self):
        """Переход к следующему листу"""
        if self.sheets_combo:
            current = self.sheets_combo.currentIndex()
            if current < self.sheets_combo.count() - 1:
                self.sheets_combo.setCurrentIndex(current + 1)
    
    def update_navigation_buttons(self):
        """Обновление состояния кнопок навигации"""
        if not self.sheets_combo:
            return
            
        has_sheets = self.sheets_combo.count() > 0
        current_index = self.sheets_combo.currentIndex()
        max_index = self.sheets_combo.count() - 1
        
        if hasattr(self, 'prev_sheet_btn'):
            self.prev_sheet_btn.setEnabled(has_sheets and current_index > 0)
        if hasattr(self, 'next_sheet_btn'):
            self.next_sheet_btn.setEnabled(has_sheets and current_index < max_index)
    
    def draw_grid(self, width, height, scale_factor):
        """Отрисовка сетки на листе"""
        if not self.graphics_scene:
            return
            
        grid_size = VISUALIZATION_DEFAULTS['grid_size'] * scale_factor
        grid_pen = QPen(QColor(COLORS['grid']), 1)
        grid_pen.setStyle(Qt.DotLine)
        
        # Вертикальные линии
        x = grid_size
        while x < width * scale_factor:
            self.graphics_scene.addLine(x, 0, x, height * scale_factor, grid_pen)
            x += grid_size
        
        # Горизонтальные линии
        y = grid_size
        while y < height * scale_factor:
            self.graphics_scene.addLine(0, y, width * scale_factor, y, grid_pen)
            y += grid_size
    
    def refresh_visualization(self):
        """Обновление текущего отображения"""
        if self.optimization_result and self.current_sheet_index >= 0:
            self.show_sheet(self.current_sheet_index) 


def visualize_sheet_layout(graphics_scene, sheet_layout, show_grid=True, show_dimensions=True, show_names=True):
    """
    Функция для отрисовки макета листа на графической сцене
    
    Args:
        graphics_scene: QGraphicsScene для отрисовки
        sheet_layout: объект с данными о макете листа
        show_grid: показывать ли сетку
        show_dimensions: показывать ли размеры
        show_names: показывать ли названия деталей
    
    Returns:
        QGraphicsRectItem: прямоугольник листа
    """
    if not graphics_scene or not sheet_layout:
        return None
    
    # Очищаем сцену
    graphics_scene.clear()
    
    # Получаем размеры листа
    sheet = sheet_layout.sheet
    sheet_width = sheet.width
    sheet_height = sheet.height
    
    # Масштабирование для отображения (1 мм = 1 пиксель по умолчанию)
    scale_factor = 1.0
    
    # УЛУЧШЕНИЕ 1: Добавляем отступы для свободной прокрутки
    padding = max(sheet_width, sheet_height) * 0.3  # 30% от максимальной стороны листа
    
    # УЛУЧШЕНИЕ 3: Рисуем контур листа с четкими границами
    sheet_pen = QPen(QColor(COLORS.get('sheet_border', '#FFFFFF')), 3)  # Увеличена толщина
    sheet_brush = QBrush(QColor(COLORS.get('sheet_fill', '#2A2A2A')))
    sheet_rect = graphics_scene.addRect(
        0, 0, sheet_width * scale_factor, sheet_height * scale_factor, 
        sheet_pen, sheet_brush
    )
    
    # Рисуем сетку если включена
    if show_grid:
        _draw_grid_on_scene(graphics_scene, sheet_width, sheet_height, scale_factor)
    
    # Рисуем размещенные детали
    if hasattr(sheet_layout, 'placed_details'):
        for placed_detail in sheet_layout.placed_details:
            x = placed_detail.x * scale_factor
            y = placed_detail.y * scale_factor
            width = placed_detail.width * scale_factor
            height = placed_detail.height * scale_factor
            
            # УЛУЧШЕНИЕ 3: Четкие границы деталей
            detail_pen = QPen(QColor(COLORS.get('detail_border', '#2E7D32')), 2)  # Увеличена толщина
            detail_brush = QBrush(QColor(COLORS.get('detail_fill', '#4CAF50')))
            detail_rect = graphics_scene.addRect(x, y, width, height, detail_pen, detail_brush)
            
            # УЛУЧШЕНИЕ 2: Добавляем название детали и размеры
            if show_names or show_dimensions:
                detail_name = ""
                if show_names and hasattr(placed_detail.detail, 'oi_name') and placed_detail.detail.oi_name:
                    detail_name = placed_detail.detail.oi_name
                elif show_names and hasattr(placed_detail.detail, 'id'):
                    detail_name = placed_detail.detail.id
                
                detail_dimensions = ""
                if show_dimensions:
                    # Используем оригинальные размеры детали
                    orig_width = placed_detail.detail.width
                    orig_height = placed_detail.detail.height
                    detail_dimensions = f"{orig_width:.0f}×{orig_height:.0f} мм"
                
                # Формируем текст
                detail_text_parts = []
                if detail_name:
                    detail_text_parts.append(detail_name)
                if detail_dimensions:
                    detail_text_parts.append(detail_dimensions)
                
                if detail_text_parts:
                    detail_text = "\n".join(detail_text_parts)
                    
                    # УЛУЧШЕННАЯ АДАПТИВНАЯ ЛОГИКА ШРИФТА - увеличено в 2 раза + умная адаптация
                    font_size = _calculate_adaptive_font_size(detail_text, width, height)
                    
                    if font_size > 0:  # Только если нашли подходящий размер
                        # Создаем текстовый элемент
                        text_item = QGraphicsTextItem(detail_text)
                        text_item.setDefaultTextColor(QColor(COLORS.get('text', '#FFFFFF')))
                        text_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                        
                        # Позиционируем текст в центре детали
                        text_rect = text_item.boundingRect()
                        text_x = x + (width - text_rect.width()) / 2
                        text_y = y + (height - text_rect.height()) / 2
                        text_item.setPos(text_x, text_y)
                        
                        graphics_scene.addItem(text_item)
    
    # Рисуем полезные остатки с четкими границами и размерами
    if hasattr(sheet_layout, 'free_rectangles'):
        for remnant in sheet_layout.free_rectangles:
            if remnant.width > 50 and remnant.height > 50:  # Показываем только крупные остатки
                x = remnant.x * scale_factor
                y = remnant.y * scale_factor
                width = remnant.width * scale_factor
                height = remnant.height * scale_factor
                
                # УЛУЧШЕНИЕ 3: Четкие границы остатков
                remnant_pen = QPen(QColor(COLORS.get('remainder_border', '#F57C00')), 2)  # Увеличена толщина
                remnant_brush = QBrush(QColor(COLORS.get('remainder_fill', '#FF9800')))
                remnant_rect = graphics_scene.addRect(x, y, width, height, remnant_pen, remnant_brush)
                
                # Добавляем размеры остатка если он достаточно большой
                if show_dimensions and width > 80 and height > 40:
                    remnant_text = f"{remnant.width:.0f}×{remnant.height:.0f}"
                    font_size = _calculate_adaptive_font_size(remnant_text, width, height)
                    
                    if font_size > 0:
                        text_item = QGraphicsTextItem(remnant_text)
                        text_item.setDefaultTextColor(QColor('#000000'))  # Черный текст на оранжевом фоне
                        text_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                        
                        text_rect = text_item.boundingRect()
                        text_x = x + (width - text_rect.width()) / 2
                        text_y = y + (height - text_rect.height()) / 2
                        text_item.setPos(text_x, text_y)
                        
                        graphics_scene.addItem(text_item)
    
    # Рисуем отходы с четкими границами и размерами
    if hasattr(sheet_layout, 'waste_rectangles'):
        for waste in sheet_layout.waste_rectangles:
            x = waste.x * scale_factor
            y = waste.y * scale_factor
            width = waste.width * scale_factor
            height = waste.height * scale_factor
            
            # УЛУЧШЕНИЕ 3: Четкие границы отходов
            waste_pen = QPen(QColor(COLORS.get('waste_border', '#d32f2f')), 2)  # Увеличена толщина
            waste_brush = QBrush(QColor(COLORS.get('waste_fill', '#f44336')))
            waste_rect = graphics_scene.addRect(x, y, width, height, waste_pen, waste_brush)
            
            # Добавляем размеры отхода если он достаточно большой
            if show_dimensions and width > 60 and height > 30:
                waste_text = f"{waste.width:.0f}×{waste.height:.0f}"
                font_size = _calculate_adaptive_font_size(waste_text, width, height)
                
                if font_size > 0:
                    text_item = QGraphicsTextItem(waste_text)
                    text_item.setDefaultTextColor(QColor('#FFFFFF'))  # Белый текст на красном фоне
                    text_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                    
                    text_rect = text_item.boundingRect()
                    text_x = x + (width - text_rect.width()) / 2
                    text_y = y + (height - text_rect.height()) / 2
                    text_item.setPos(text_x, text_y)
                    
                    graphics_scene.addItem(text_item)
    
    # УЛУЧШЕНИЕ 1: Устанавливаем размер сцены с отступами для свободной прокрутки
    graphics_scene.setSceneRect(
        -padding, -padding, 
        (sheet_width * scale_factor) + (padding * 2), 
        (sheet_height * scale_factor) + (padding * 2)
    )
    
    return sheet_rect


def _draw_grid_on_scene(graphics_scene, width, height, scale_factor):
    """Отрисовка сетки на сцене"""
    grid_size = VISUALIZATION_DEFAULTS.get('grid_size', 100) * scale_factor
    grid_pen = QPen(QColor(COLORS.get('grid', '#555555')), 1)
    grid_pen.setStyle(Qt.DotLine)
    
    # Вертикальные линии
    x = grid_size
    while x < width * scale_factor:
        graphics_scene.addLine(x, 0, x, height * scale_factor, grid_pen)
        x += grid_size
    
    # Горизонтальные линии
    y = grid_size
    while y < height * scale_factor:
        graphics_scene.addLine(0, y, width * scale_factor, y, grid_pen)
        y += grid_size


def _calculate_adaptive_font_size(text, rect_width, rect_height):
    """
    Вычисляет оптимальный размер шрифта для текста в прямоугольнике
    
    Args:
        text: текст для отображения
        rect_width: ширина прямоугольника
        rect_height: высота прямоугольника
    
    Returns:
        int: размер шрифта (0 если текст не помещается)
    """
    # УВЕЛИЧЕННЫЕ БАЗОВЫЕ РАЗМЕРЫ (в 2 раза больше чем раньше)
    min_dimension = min(rect_width, rect_height)
    
    # Стартовые размеры увеличены в 2 раза
    if min_dimension > 400:
        base_font_size = 28  # было 14
    elif min_dimension > 200:
        base_font_size = 24  # было 12  
    elif min_dimension > 100:
        base_font_size = 20  # было 10
    elif min_dimension > 50:
        base_font_size = 16  # было 8
    else:
        base_font_size = 12  # было 6
    
    # Пробуем размеры от базового до минимального
    for font_size in range(base_font_size, 7, -1):  # Минимум 8pt
        # Создаем временный элемент для измерения
        temp_item = QGraphicsTextItem(text)
        temp_item.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
        text_rect = temp_item.boundingRect()
        
        # Более строгие требования для маленьких элементов
        if min_dimension < 100:
            margin = 0.75  # 75% заполнения для маленьких элементов
        else:
            margin = 0.85  # 85% заполнения для больших элементов
        
        # Проверяем, помещается ли текст с отступами
        if (text_rect.width() <= rect_width * margin and 
            text_rect.height() <= rect_height * margin):
            return font_size
    
    # Если даже минимальный размер не помещается, возвращаем 0
    return 0