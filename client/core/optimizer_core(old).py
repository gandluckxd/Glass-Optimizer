#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль оптимизации 2D раскроя материалов
Использует алгоритм Best-Fit с Bottom-Left-Fill для максимальной эффективности
"""

import time
import copy
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Callable
from enum import Enum

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RotationMode(Enum):
    """Режимы поворота деталей"""
    NONE = "none"           # Без поворота
    ALLOW_90 = "allow_90"   # Разрешить поворот на 90°
    OPTIMAL = "optimal"     # Автоматический выбор наилучшего поворота

@dataclass
class Detail:
    """Деталь для размещения"""
    id: str
    width: float
    height: float
    material: str
    quantity: int = 1
    can_rotate: bool = True
    priority: int = 0  # Приоритет размещения (больше = важнее)
    oi_name: str = ""  # Название изделия
    
    def __post_init__(self):
        self.area = self.width * self.height
        
    def get_rotated(self) -> 'Detail':
        """Возвращает повернутую на 90° копию детали"""
        rotated = copy.copy(self)
        rotated.width, rotated.height = self.height, self.width
        return rotated

@dataclass 
class Sheet:
    """Лист материала"""
    id: str
    width: float
    height: float
    material: str
    cost_per_unit: float = 0.0
    is_remainder: bool = False
    remainder_id: Optional[str] = None
    
    def __post_init__(self):
        self.area = self.width * self.height

@dataclass
class PlacedDetail:
    """Размещенная деталь с координатами"""
    detail: Detail
    x: float
    y: float
    width: float  # Фактическая ширина после возможного поворота
    height: float # Фактическая высота после возможного поворота
    is_rotated: bool = False
    sheet_id: str = ""
    
    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height

@dataclass
class FreeRectangle:
    """Свободный прямоугольник на листе"""
    x: float
    y: float
    width: float
    height: float
    
    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height
        
    def intersects(self, other: 'FreeRectangle') -> bool:
        """Проверяет пересечение с другим прямоугольником"""
        return not (self.x2 <= other.x or other.x2 <= self.x or 
                   self.y2 <= other.y or other.y2 <= self.y)
                   
    def contains_point(self, x: float, y: float) -> bool:
        """Проверяет, содержит ли прямоугольник точку"""
        return self.x <= x <= self.x2 and self.y <= y <= self.y2
        
    def can_fit(self, width: float, height: float) -> bool:
        """Проверяет, поместится ли прямоугольник заданного размера"""
        return self.width >= width and self.height >= height

@dataclass
class SheetLayout:
    """Раскладка на одном листе"""
    sheet: Sheet
    placed_details: List[PlacedDetail]
    free_rectangles: List[FreeRectangle]
    waste_rectangles: List[FreeRectangle]
    
    def __post_init__(self):
        self.used_area = sum(pd.width * pd.height for pd in self.placed_details)
        self.total_area = self.sheet.area
        self.waste_area = self.total_area - self.used_area
        self.efficiency = (self.used_area / self.total_area) * 100 if self.total_area > 0 else 0
        self.waste_percent = (self.waste_area / self.total_area) * 100 if self.total_area > 0 else 0

@dataclass
class OptimizationParams:
    """Параметры оптимизации"""
    min_remnant_width: float = 100.0
    min_remnant_height: float = 100.0
    target_waste_percent: float = 5.0
    min_waste_side: float = 10.0
    use_warehouse_remnants: bool = True
    rotation_mode: RotationMode = RotationMode.ALLOW_90
    force_adjacent_placement: bool = True  # Принудительное размещение деталей впритык
    max_waste_rectangles: int = 10  # Максимальное количество отходных прямоугольников
    cutting_width: float = 3.0  # Ширина реза

@dataclass
class OptimizationResult:
    """Результат оптимизации"""
    success: bool
    layouts: List[SheetLayout]
    unplaced_details: List[Detail]
    total_efficiency: float
    total_waste_percent: float
    total_cost: float
    useful_remnants: List[FreeRectangle]
    optimization_time: float
    message: str = ""
    
    def __post_init__(self):
        self.total_sheets = len(self.layouts)
        self.total_placed_details = sum(len(layout.placed_details) for layout in self.layouts)
        # Для совместимости с GUI добавляем атрибут sheets
        self.sheets = self.layouts

class BestFitOptimizer:
    """
    Оптимизатор использующий алгоритм Best-Fit с Bottom-Left-Fill
    Обеспечивает высокую эффективность размещения с минимальными отходами
    """
    
    def __init__(self, params: OptimizationParams):
        self.params = params
        self.progress_callback: Optional[Callable[[float], None]] = None

    def set_progress_callback(self, callback: Callable[[float], None]):
        """Установка callback для отслеживания прогресса"""
        self.progress_callback = callback

    def _report_progress(self, progress: float):
        """Отправка прогресса"""
        if self.progress_callback:
            self.progress_callback(progress)

    def optimize(self, details: List[Detail], sheets: List[Sheet]) -> OptimizationResult:
        """Основной метод оптимизации"""
        start_time = time.time()
        
        logger.info(f"Начинаем оптимизацию: {len(details)} деталей, {len(sheets)} листов")
        
        # Подготовка данных
        expanded_details = self._prepare_details(details)
        sorted_sheets = self._prepare_sheets(sheets)
        
        logger.info(f"Подготовлено {len(expanded_details)} деталей для размещения")
        logger.info(f"Подготовлено {len(sorted_sheets)} листов")
        
        self._report_progress(10.0)
        
        # Группировка деталей по материалам
        material_groups = self._group_details_by_material(expanded_details)
        logger.info(f"Детали сгруппированы по {len(material_groups)} материалам")
        
        self._report_progress(20.0)
        
        # Оптимизация для каждого материала
        all_layouts = []
        all_unplaced = []
        progress_step = 70.0 / len(material_groups)
        current_progress = 20.0
        
        for material, material_details in material_groups.items():
            logger.info(f"Оптимизируем материал {material}: {len(material_details)} деталей")
            
            # Фильтруем листы для данного материала
            material_sheets = [s for s in sorted_sheets if s.material == material]
            logger.info(f"Оптимизируем {len(material_details)} деталей на {len(material_sheets)} листах")
            
            # Оптимизация для материала
            layouts, unplaced = self._optimize_material(material_details, material_sheets)
            
            all_layouts.extend(layouts)
            all_unplaced.extend(unplaced)
            
            current_progress += progress_step
            self._report_progress(current_progress)
        
        self._report_progress(95.0)
        
        # Финальный анализ результатов
        result = self._calculate_final_result(all_layouts, all_unplaced, start_time)
        
        self._report_progress(100.0)
        
        logger.info(f"Оптимизация завершена за {result.optimization_time:.2f}с")
        logger.info(f"Размещено: {result.total_placed_details}/{len(details)} деталей")
        logger.info(f"Эффективность: {result.total_efficiency:.1f}%")
        logger.info(result.message)
        
        return result

    def _prepare_details(self, details: List[Detail]) -> List[Detail]:
        """Подготовка деталей: разворачивание по количеству и УМНАЯ сортировка"""
        expanded = []
        
        for detail in details:
            for i in range(detail.quantity):
                detail_copy = copy.deepcopy(detail)
                detail_copy.id = f"{detail.id}_{i+1}"
                detail_copy.quantity = 1
                expanded.append(detail_copy)
        
        # СУПЕР-УМНАЯ сортировка для минимизации отходов:
        # 1. Большие детали первыми (занимают больше места)
        # 2. Детали с неудобным соотношением сторон (сложнее разместить)
        # 3. Квадратные детали в конце (легче помещаются в остатки)
        def sort_key(d):
            aspect_ratio = max(d.width, d.height) / min(d.width, d.height)
            # Приоритет: большая площадь + неудобное соотношение сторон
            difficulty_score = d.area * aspect_ratio
            return (-difficulty_score, -d.priority, d.id)
        
        expanded.sort(key=sort_key)
        
        return expanded

    def _prepare_sheets(self, sheets: List[Sheet]) -> List[Sheet]:
        """СУПЕР-УМНАЯ подготовка листов для максимальной эффективности"""
        expanded = []
        
        for sheet in sheets:
            if sheet.is_remainder:
                expanded.append(sheet)
            else:
                expanded.append(sheet)
        
        # СУПЕР-УМНАЯ сортировка для минимизации отходов:
        def sort_key(s):
            if s.is_remainder:
                # Остатки: сначала большие, потом средние, потом маленькие
                # Это позволяет эффективно использовать весь склад остатков
                return (0, -s.area, s.id)  # Высший приоритет
            else:
                # Основные листы: оптимальная очередность по площади
                return (1, -s.area, s.id)  # Второй приоритет
        
        expanded.sort(key=sort_key)
        
        logger.info(f"🎯 Приоритет использования: {len([s for s in expanded if s.is_remainder])} остатков, затем {len([s for s in expanded if not s.is_remainder])} основных листов")
        
        return expanded

    def _group_details_by_material(self, details: List[Detail]) -> Dict[str, List[Detail]]:
        """Группировка деталей по материалам"""
        groups = {}
        for detail in details:
            if detail.material not in groups:
                groups[detail.material] = []
            groups[detail.material].append(detail)
        return groups

    def _optimize_material(self, details: List[Detail], sheets: List[Sheet]) -> Tuple[List[SheetLayout], List[Detail]]:
        """Оптимизация размещения деталей одного материала"""
        layouts = []
        unplaced_details = details.copy()
        
        for sheet in sheets:
            if not unplaced_details:
                break
            
            layout = self._create_sheet_layout(sheet, unplaced_details.copy())
            
            if layout.placed_details:
                layouts.append(layout)
                # Удаляем размещенные детали
                placed_ids = {pd.detail.id for pd in layout.placed_details}
                unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                
                logger.info(f"На листе {sheet.id} размещено {len(layout.placed_details)} деталей")
            else:
                logger.warning(f"На листе {sheet.id} ничего не удалось разместить")
        
        return layouts, unplaced_details

    def _create_sheet_layout(self, sheet: Sheet, details: List[Detail]) -> SheetLayout:
        """Создание раскладки на одном листе"""
        layout = SheetLayout(
            sheet=sheet,
            placed_details=[],
            free_rectangles=[FreeRectangle(0, 0, sheet.width, sheet.height)],
            waste_rectangles=[]
        )
        
        logger.debug(f"Начинаем размещение на листе {sheet.id} ({sheet.width}x{sheet.height})")
        
        # Размещаем детали по алгоритму Best-Fit
        remaining_details = details.copy()
        
        while remaining_details and layout.free_rectangles:
            best_placement = self._find_best_placement(layout, remaining_details)
            
            if not best_placement:
                break
            
            detail, free_rect, position, is_rotated = best_placement
            x, y = position
            
            # Размещаем деталь
            placed_detail = PlacedDetail(
                detail=detail,
                x=x,
                y=y,
                width=detail.height if is_rotated else detail.width,
                height=detail.width if is_rotated else detail.height,
                is_rotated=is_rotated,
                sheet_id=sheet.id
            )
            
            layout.placed_details.append(placed_detail)
            remaining_details.remove(detail)
            
            logger.debug(f"Размещена деталь {detail.id} в позиции ({x}, {y})")
            
            # Обновляем свободные прямоугольники
            self._update_free_rectangles(layout, placed_detail)
        
        # Анализируем отходы и остатки
        self._analyze_waste_and_remnants(layout)
        
        logger.debug(f"Размещение завершено: {len(layout.placed_details)} деталей на листе {sheet.id}")
        
        return layout

    def _find_best_placement(self, layout: SheetLayout, details: List[Detail]) -> Optional[Tuple[Detail, FreeRectangle, Tuple[float, float], bool]]:
        """Поиск лучшего размещения детали с ЖЁСТКОЙ проверкой min_waste_side"""
        best_placement = None
        best_score = float('inf')
        
        for detail in details:
            for free_rect in layout.free_rectangles:
                # Проверяем размещение без поворота
                placements = [(detail.width, detail.height, False)]
                
                # Проверяем размещение с поворотом, если разрешено
                if (self.params.rotation_mode != RotationMode.NONE and 
                    detail.can_rotate and 
                    detail.width != detail.height):
                    placements.append((detail.height, detail.width, True))
                
                for width, height, is_rotated in placements:
                    if free_rect.can_fit(width, height):
                        # Bottom-Left позиция
                        x, y = free_rect.x, free_rect.y
                        
                        # КРИТИЧЕСКАЯ ПРОВЕРКА: все остатки должны соблюдать min_waste_side
                        if not self._check_waste_side_compliance(free_rect, width, height):
                            continue  # Пропускаем это размещение, если создаются недопустимые остатки
                        
                        # Вычисляем score для данного размещения
                        score = self._calculate_placement_score(layout, free_rect, width, height, x, y)
                        
                        if score < best_score:
                            best_score = score
                            best_placement = (detail, free_rect, (x, y), is_rotated)
        
        return best_placement
    
    def _check_waste_side_compliance(self, free_rect: FreeRectangle, detail_width: float, detail_height: float) -> bool:
        """КРИТИЧЕСКАЯ ПРОВЕРКА: все создаваемые остатки должны соблюдать min_waste_side ИЛИ быть нулевыми"""
        
        # Вычисляем все возможные остатки
        leftover_width = free_rect.width - detail_width
        leftover_height = free_rect.height - detail_height
        
        # Проверяем ширину остатка справа
        if leftover_width > 0.01:  # Если есть остаток по ширине
            if leftover_width < self.params.min_waste_side:
                return False  # Остаток слишком узкий - ЗАПРЕЩЕНО!
        
        # Проверяем высоту остатка сверху
        if leftover_height > 0.01:  # Если есть остаток по высоте
            if leftover_height < self.params.min_waste_side:
                return False  # Остаток слишком низкий - ЗАПРЕЩЕНО!
        
        # Если размещение создает L-образную область, проверяем все её части
        if leftover_width > 0.01 and leftover_height > 0.01:
            # L-образная область создаёт 2 прямоугольника:
            # 1. Правый: (detail_width, 0) -> (free_rect.width, detail_height)
            # 2. Верхний: (0, detail_height) -> (free_rect.width, free_rect.height)
            
            # Правый прямоугольник
            right_rect_width = leftover_width
            right_rect_height = detail_height
            
            # Верхний прямоугольник  
            top_rect_width = free_rect.width
            top_rect_height = leftover_height
            
            # Проверяем, что оба прямоугольника соблюдают min_waste_side
            if (right_rect_width < self.params.min_waste_side or 
                right_rect_height < self.params.min_waste_side or
                top_rect_width < self.params.min_waste_side or 
                top_rect_height < self.params.min_waste_side):
                return False  # Один из остатков слишком мал - ЗАПРЕЩЕНО!
        
        return True  # Все остатки соблюдают ограничения

    def _calculate_placement_score(self, layout: SheetLayout, free_rect: FreeRectangle, 
                                 width: float, height: float, x: float, y: float) -> float:
        """УПРОЩЁННОЕ вычисление оценки размещения (штрафы за маленькие остатки убраны)"""
        
        # 1. Площадь оставшегося места (основной критерий)
        remaining_area = (free_rect.width - width) * (free_rect.height - height)
        score = remaining_area * 10
        
        # 2. Bottom-Left приоритет (плотная упаковка)
        score += (x + y) * 0.1
        
        # 3. МЕГА-БОНУС за соседство (создание блоков)
        adjacency_bonus = self._calculate_adjacency_bonus(layout, (x, y), width, height)
        score -= adjacency_bonus * 5000  # Очень важно!
        
        # 4. БОНУС за полное заполнение прямоугольника
        if remaining_area < 10:  # Почти полностью заполнили
            score -= 3000  # Большой бонус
        
        # 5. Best-Area-Fit: предпочитаем прямоугольники, близкие по размеру к детали
        area_efficiency = (width * height) / (free_rect.width * free_rect.height)
        if area_efficiency > 0.8:  # Эффективное использование площади
            score -= 1000 * area_efficiency
        
        return score

    def _calculate_adjacency_bonus(self, layout: SheetLayout, pos: Tuple[float, float], 
                                 width: float, height: float) -> float:
        """Вычисляет бонус за соседство с размещенными деталями"""
        x, y = pos
        bonus = 0.0
        
        for placed in layout.placed_details:
            # Проверяем соседство по стороне (общая граница)
            if (abs(placed.x2 - x) < 0.01 and  # Левая граница новой детали касается правой границы размещенной
                not (y + height <= placed.y or placed.y2 <= y)):  # И есть пересечение по Y
                bonus += min(height, placed.height)  # Длина общей границы
                
            elif (abs(placed.x - (x + width)) < 0.01 and  # Правая граница новой детали касается левой границы размещенной
                  not (y + height <= placed.y or placed.y2 <= y)):
                bonus += min(height, placed.height)
                
            elif (abs(placed.y2 - y) < 0.01 and  # Нижняя граница новой детали касается верхней границы размещенной
                  not (x + width <= placed.x or placed.x2 <= x)):
                bonus += min(width, placed.width)
                
            elif (abs(placed.y - (y + height)) < 0.01 and  # Верхняя граница новой детали касается нижней границы размещенной
                  not (x + width <= placed.x or placed.x2 <= x)):
                bonus += min(width, placed.width)
        
        return bonus

    def _update_free_rectangles(self, layout: SheetLayout, placed_detail: PlacedDetail):
        """Обновляет список свободных прямоугольников после размещения детали"""
        new_rectangles = []
        
        for rect in layout.free_rectangles:
            # Проверяем пересечение размещенной детали со свободным прямоугольником
            if not (placed_detail.x2 <= rect.x or placed_detail.x >= rect.x2 or
                   placed_detail.y2 <= rect.y or placed_detail.y >= rect.y2):
                
                # Есть пересечение - разделяем прямоугольник
                split_rects = self._split_rectangle(rect, placed_detail)
                new_rectangles.extend(split_rects)
            else:
                # Нет пересечения - оставляем прямоугольник как есть
                new_rectangles.append(rect)
        
        # Удаляем дублирующиеся и вложенные прямоугольники
        layout.free_rectangles = self._remove_redundant_rectangles(new_rectangles)

    def _split_rectangle(self, rect: FreeRectangle, placed: PlacedDetail) -> List[FreeRectangle]:
        """КЛАССИЧЕСКИЙ MaxRects: Разделяет свободный прямоугольник создавая максимальные прямоугольники"""
        result = []
        
        # Создаем максимальные прямоугольники по алгоритму MaxRects
        # Это создаст пересекающиеся прямоугольники, что нормально
        
        # Левая часть (если есть)
        if placed.x > rect.x:
            left_width = placed.x - rect.x
            if left_width >= self.params.min_waste_side:
                result.append(FreeRectangle(
                    rect.x, rect.y,
                    left_width, rect.height  # На всю высоту исходного прямоугольника
                ))
        
        # Правая часть (если есть) 
        if placed.x2 < rect.x2:
            right_width = rect.x2 - placed.x2
            if right_width >= self.params.min_waste_side:
                result.append(FreeRectangle(
                    placed.x2, rect.y,
                    right_width, rect.height  # На всю высоту исходного прямоугольника
                ))
        
        # Нижняя часть (если есть)
        if placed.y > rect.y:
            bottom_height = placed.y - rect.y
            if bottom_height >= self.params.min_waste_side:
                result.append(FreeRectangle(
                    rect.x, rect.y,
                    rect.width, bottom_height  # На всю ширину исходного прямоугольника
                ))
        
        # Верхняя часть (если есть)
        if placed.y2 < rect.y2:
            top_height = rect.y2 - placed.y2  
            if top_height >= self.params.min_waste_side:
                result.append(FreeRectangle(
                    rect.x, placed.y2,
                    rect.width, top_height  # На всю ширину исходного прямоугольника
                ))
        
        # Фильтруем результаты: оставляем только валидные прямоугольники
        valid_rectangles = []
        for r in result:
            if (r.width > 0.01 and r.height > 0.01 and 
                r.width >= self.params.min_waste_side and 
                r.height >= self.params.min_waste_side):
                valid_rectangles.append(r)
        
        logger.debug(f"🔪 Разрез: создано {len(valid_rectangles)} прямоугольников (возможны пересечения - это нормально)")
        return valid_rectangles

    def _remove_redundant_rectangles(self, rectangles: List[FreeRectangle]) -> List[FreeRectangle]:
        """КЛАССИЧЕСКИЙ MaxRects: Удаляет только вложенные и дублирующиеся прямоугольники"""
        if not rectangles:
            return []
        
        # Фильтруем по min_waste_side: оставляем только достаточно большие прямоугольники
        valid_rects = []
        for rect in rectangles:
            if (rect.width >= self.params.min_waste_side and 
                rect.height >= self.params.min_waste_side):
                valid_rects.append(rect)
        
        # Удаляем дубликаты
        unique_rects = []
        for rect in valid_rects:
            is_duplicate = False
            for existing in unique_rects:
                if (abs(rect.x - existing.x) < 0.01 and abs(rect.y - existing.y) < 0.01 and
                    abs(rect.width - existing.width) < 0.01 and abs(rect.height - existing.height) < 0.01):
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_rects.append(rect)
        
        # Удаляем только ВЛОЖЕННЫЕ прямоугольники (пересекающиеся оставляем!)
        filtered = []
        for i, rect in enumerate(unique_rects):
            is_contained = False
            for j, other in enumerate(unique_rects):
                if i != j and self._is_contained(rect, other):
                    logger.debug(f"📦 Удаляем вложенный прямоугольник: {rect.x:.0f},{rect.y:.0f} {rect.width:.0f}x{rect.height:.0f}")
                    is_contained = True
                    break
            if not is_contained:
                filtered.append(rect)
        
        logger.debug(f"🧹 Фильтрация: {len(rectangles)} -> {len(filtered)} прямоугольников (удалены только вложенные и дубликаты)")
        return filtered

    def _is_contained(self, rect1: FreeRectangle, rect2: FreeRectangle) -> bool:
        """Проверяет, содержится ли rect1 внутри rect2"""
        return (rect2.x <= rect1.x and rect2.y <= rect1.y and
                rect1.x2 <= rect2.x2 and rect1.y2 <= rect2.y2)

    def _analyze_waste_and_remnants(self, layout: SheetLayout):
        """ИСПРАВЛЕНО: Анализ остатков с правильной обработкой пересечений"""
        
        # Очищаем списки
        layout.waste_rectangles.clear()
        
        logger.debug(f"🔍 Анализируем {len(layout.free_rectangles)} свободных прямоугольников...")
        
        # Сначала разделяем прямоугольники на категории
        useful_remnants = []
        potential_waste = []
        
        for rect in layout.free_rectangles:
            # Используем улучшенную логику: большая сторона >= большего параметра, меньшая >= меньшего
            element_min_side = min(rect.width, rect.height)
            element_max_side = max(rect.width, rect.height)
            param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
            param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
            
            if element_min_side >= param_min and element_max_side >= param_max:
                useful_remnants.append(rect)
                logger.debug(f"✅ Деловой остаток: {rect.x:.0f},{rect.y:.0f} {rect.width:.0f}x{rect.height:.0f}")
            else:
                potential_waste.append(rect)
                logger.debug(f"🗑️ Потенциальный отход: {rect.x:.0f},{rect.y:.0f} {rect.width:.0f}x{rect.height:.0f}")
        
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Решаем конфликты пересечений
        # Приоритет у деловых остатков! Если отход пересекается с деловым остатком, отход удаляется
        final_waste = []
        for waste_rect in potential_waste:
            intersects_with_remnant = False
            
            for remnant_rect in useful_remnants:
                if waste_rect.intersects(remnant_rect):
                    logger.debug(f"🔄 Конфликт: отход {waste_rect.x:.0f},{waste_rect.y:.0f} {waste_rect.width:.0f}x{waste_rect.height:.0f} пересекается с остатком {remnant_rect.x:.0f},{remnant_rect.y:.0f} {remnant_rect.width:.0f}x{remnant_rect.height:.0f}")
                    logger.debug(f"📋 Приоритет деловому остатку - отход исключается")
                    intersects_with_remnant = True
                    break
            
            if not intersects_with_remnant:
                final_waste.append(waste_rect)
                layout.waste_rectangles.append(waste_rect)
        
        logger.debug(f"📊 Итого: {len(useful_remnants)} деловых остатков, {len(final_waste)} отходов")
        
        # Подсчет площадей
        total_remnant_area = sum(r.area for r in useful_remnants)
        total_waste_area = sum(r.area for r in final_waste)
        
        # Обновляем статистику листа
        layout.remnant_area = total_remnant_area
        layout.waste_area = total_waste_area
        
        # Пересчитываем статистику
        layout.used_area = sum(pd.width * pd.height for pd in layout.placed_details)
        effective_used_area = layout.used_area + total_remnant_area
        layout.efficiency = (effective_used_area / layout.total_area) * 100 if layout.total_area > 0 else 0
        layout.waste_percent = (total_waste_area / layout.total_area) * 100 if layout.total_area > 0 else 0
        
        # Обновляем список свободных прямоугольников (только деловые остатки)
        layout.free_rectangles = useful_remnants
        
        # Логирование с учётом ограничений min_waste_side
        total_covered_area = layout.used_area + total_remnant_area + total_waste_area
        logger.debug(f"📊 Покрытие листа: использовано={layout.used_area:.0f}мм², остатки={total_remnant_area:.0f}мм², отходы={total_waste_area:.0f}мм²")
        logger.debug(f"📊 Общая покрытая площадь: {total_covered_area:.0f}мм² из {layout.total_area:.0f}мм² ({total_covered_area/layout.total_area*100:.1f}%)")
        
        # Вычисляем площадь, которая могла быть исключена из-за ограничений min_waste_side
        uncovered_area = layout.total_area - total_covered_area
        if uncovered_area > 1.0:  # Если есть значительная непокрытая площадь
            logger.info(f"ℹ️ Непокрытая площадь: {uncovered_area:.0f}мм² (исключена из-за ограничения min_waste_side={self.params.min_waste_side}мм)")
        
        if useful_remnants:
            logger.debug(f"✅ Найдено {len(useful_remnants)} полезных остатков (площадь {total_remnant_area:.0f}мм²)")
        if final_waste:
            logger.debug(f"🗑️ В отходы: {len(final_waste)} кусков (площадь {total_waste_area:.0f}мм²)")
        
        # Логируем соблюдение ограничений
        logger.debug(f"✅ Все остатки соблюдают ограничение min_waste_side={self.params.min_waste_side}мм")
        logger.debug(f"✅ Конфликты пересечений решены в пользу деловых остатков")

    def _calculate_final_result(self, layouts: List[SheetLayout], unplaced: List[Detail], start_time: float) -> OptimizationResult:
        """Вычисляет финальный результат оптимизации"""
        
        if not layouts and unplaced:
            return OptimizationResult(
                success=False,
                layouts=layouts,
                unplaced_details=unplaced,
                total_efficiency=0.0,
                total_waste_percent=100.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=time.time() - start_time,
                message="Не удалось разместить ни одной детали"
            )
        
        # ТОЧНАЯ общая статистика с учётом полезных остатков
        total_area = sum(layout.total_area for layout in layouts)
        total_used = sum(layout.used_area for layout in layouts)
        
        # Полезные остатки собираем из всех листов с простым условием пользователя
        useful_remnants = []
        for layout in layouts:
            for rect in layout.free_rectangles:
                # Используем улучшенную логику: большая сторона >= большего параметра, меньшая >= меньшего
                element_min_side = min(rect.width, rect.height)
                element_max_side = max(rect.width, rect.height)
                param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
                param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
                
                if element_min_side >= param_min and element_max_side >= param_max:
                    useful_remnants.append(rect)
        
        # Площадь полезных остатков НЕ считается отходами!
        total_useful_remnants_area = sum(r.area for r in useful_remnants)
        total_effective_used = total_used + total_useful_remnants_area
        
        # Только реальные отходы
        total_real_waste = sum(layout.waste_area for layout in layouts)
        
        total_efficiency = (total_effective_used / total_area * 100) if total_area > 0 else 0
        total_waste_percent = (total_real_waste / total_area * 100) if total_area > 0 else 0
        
        # Общая стоимость
        total_cost = sum(layout.sheet.cost_per_unit * layout.sheet.area for layout in layouts)
        
        # Сообщение о результате
        success = len(unplaced) == 0
        if success:
            message = f"Все детали успешно размещены на {len(layouts)} листах"
        else:
            message = f"Размещено {sum(len(l.placed_details) for l in layouts)} деталей, не размещено: {len(unplaced)}"
        
        return OptimizationResult(
            success=success,
            layouts=layouts,
            unplaced_details=unplaced,
            total_efficiency=total_efficiency,
            total_waste_percent=total_waste_percent,
            total_cost=total_cost,
            useful_remnants=useful_remnants,
            optimization_time=time.time() - start_time,
            message=message
        )

# Главная функция для совместимости с существующим интерфейсом
def optimize(details: List[dict], materials: List[dict], remainders: List[dict], 
            params: dict = None, progress_fn: Optional[Callable[[float], None]] = None, **kwargs) -> OptimizationResult:
    """
    Главная функция оптимизации для совместимости с существующим GUI
    """
    
    try:
        logger.info(f"🚀 Начинаем функцию optimize")
        logger.info(f"📋 Получено деталей: {len(details)}")
        logger.info(f"📦 Получено материалов: {len(materials)}")
        logger.info(f"♻️ Получено остатков: {len(remainders)}")
        logger.info(f"⚙️ Параметры: {params}")
        logger.info(f"🔧 Kwargs: {kwargs}")
        
        # Объединяем параметры из params и kwargs
        if params:
            kwargs.update(params)
            
        # Преобразуем входные данные в наш формат
        detail_objects = []
        logger.info(f"🔄 Начинаем обработку деталей...")
        
        for i, detail_data in enumerate(details):
            logger.debug(f"Обрабатываем деталь {i+1}/{len(details)}: {detail_data}")
            try:
                # Получаем ID из различных возможных полей
                detail_id = str(detail_data.get('orderitemsid', detail_data.get('id', detail_data.get('oi_name', f'detail_{len(detail_objects)}'))))
                
                # ЗАЩИТА: Проверяем и преобразуем числовые значения
                try:
                    width = float(detail_data.get('width', 0))
                    if width <= 0:
                        logger.warning(f"Пропускаем деталь {detail_id}: некорректная ширина {width}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Пропускаем деталь {detail_id}: не удается преобразовать ширину")
                    continue
                
                try:
                    height = float(detail_data.get('height', 0))
                    if height <= 0:
                        logger.warning(f"Пропускаем деталь {detail_id}: некорректная высота {height}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Пропускаем деталь {detail_id}: не удается преобразовать высоту")
                    continue
                
                try:
                    quantity = int(detail_data.get('total_qty', detail_data.get('quantity', 1)))
                    if quantity <= 0:
                        logger.warning(f"Пропускаем деталь {detail_id}: некорректное количество {quantity}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Пропускаем деталь {detail_id}: не удается преобразовать количество")
                    continue
                
                # ЗАЩИТА: Проверяем строковые значения
                material = detail_data.get('g_marking', '')
                if material is None:
                    material = ''
                material = str(material).strip()
                if not material:
                    logger.warning(f"Пропускаем деталь {detail_id}: отсутствует материал")
                    continue
                
                # ЗАЩИТА: Проверяем oi_name
                oi_name = detail_data.get('oi_name', '')
                if oi_name is None:
                    oi_name = ''
                oi_name = str(oi_name).strip()
                
                detail = Detail(
                    id=detail_id,
                    width=width,
                    height=height,
                    material=material,
                    quantity=quantity,
                    can_rotate=True,  # По умолчанию разрешаем поворот
                    priority=int(detail_data.get('priority', 0)),
                    oi_name=oi_name
                )
                detail_objects.append(detail)
                
            except Exception as e:
                logger.error(f"Ошибка обработки детали {detail_data}: {e}")
                continue
        
        if not detail_objects:
            logger.warning("⚠️ Нет корректных деталей для оптимизации")
            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=[],
                total_efficiency=0.0,
                total_waste_percent=0.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=0.0,
                message="Нет корректных деталей для оптимизации"
            )
        
        logger.info(f"✅ Успешно обработано {len(detail_objects)} деталей")
        
        # Создаем листы из материалов и остатков
        sheets = []
        logger.info(f"🔄 Начинаем обработку материалов...")
        
        # Основные листы из материалов  
        for i, material_data in enumerate(materials):
            logger.info(f"🔍 Обрабатываем материал {i+1}/{len(materials)}: {material_data}")
            try:
                # ЗАЩИТА: Проверяем и преобразуем количество листов
                logger.debug(f"Проверяем количество листов...")
                try:
                    # ИСПРАВЛЕНО: Для материалов используем res_qty, а не qty
                    # qty может содержать общий объем, а res_qty - количество листов
                    qty = int(material_data.get('res_qty', material_data.get('quantity', 1)))
                    
                    # ЗАЩИТА: Разумное ограничение количества листов
                    if qty > 1000:  # Максимум 1000 листов одного материала
                        logger.warning(f"Слишком большое количество листов ({qty}), ограничиваем до 1000")
                        qty = 1000
                    
                    logger.debug(f"Количество листов: {qty}")
                    if qty <= 0:
                        logger.warning(f"Пропускаем материал: некорректное количество {qty}")
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(f"Пропускаем материал: не удается преобразовать количество: {e}")
                    continue
                
                # ЗАЩИТА: Проверяем размеры
                logger.debug(f"Проверяем ширину...")
                try:
                    width = float(material_data.get('width', 0))
                    logger.debug(f"Ширина: {width}")
                    if width <= 0:
                        logger.warning(f"Пропускаем материал: некорректная ширина {width}")
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(f"Пропускаем материал: не удается преобразовать ширину: {e}")
                    continue
                
                logger.debug(f"Проверяем высоту...")
                try:
                    height = float(material_data.get('height', 0))
                    logger.debug(f"Высота: {height}")
                    if height <= 0:
                        logger.warning(f"Пропускаем материал: некорректная высота {height}")
                        continue
                except (ValueError, TypeError) as e:
                    logger.warning(f"Пропускаем материал: не удается преобразовать высоту: {e}")
                    continue
                
                # ЗАЩИТА: Проверяем материал
                logger.debug(f"Проверяем маркировку материала...")
                material = material_data.get('g_marking', '')
                if material is None:
                    material = ''
                material = str(material).strip()
                logger.debug(f"Материал: '{material}'")
                if not material:
                    logger.warning(f"Пропускаем материал: отсутствует маркировка")
                    continue
                
                # ЗАЩИТА: Проверяем стоимость
                logger.debug(f"Проверяем стоимость...")
                try:
                    cost = float(material_data.get('cost', 0))
                    logger.debug(f"Стоимость: {cost}")
                except (ValueError, TypeError) as e:
                    logger.debug(f"Не удается преобразовать стоимость, используем 0.0: {e}")
                    cost = 0.0
                
                # Создаем нужное количество листов
                logger.debug(f"Создаем {qty} листов материала '{material}'...")
                for j in range(qty):
                    logger.debug(f"Создаем лист {j+1}/{qty}...")
                    sheet = Sheet(
                        id=f"sheet_{material}_{j+1}" if qty > 1 else f"sheet_{material}",
                        width=width,
                        height=height,
                        material=material,
                        cost_per_unit=cost,
                        is_remainder=False
                    )
                    sheets.append(sheet)
                    logger.debug(f"Лист создан: {sheet.id}")
                    
                logger.info(f"✅ Материал {i+1} обработан успешно, создано {qty} листов")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки материала {i+1}: {material_data}")
                logger.error(f"❌ Детали ошибки: {e}")
                logger.error(f"❌ Тип ошибки: {type(e)}")
                import traceback
                logger.error(f"❌ Трассировка: {traceback.format_exc()}")
                continue
        
        # Остатки склада
        logger.info(f"🔄 Начинаем обработку остатков...")
        for i, remainder_data in enumerate(remainders):
            logger.debug(f"Обрабатываем остаток {i+1}/{len(remainders)}: {remainder_data}")
            try:
                # ЗАЩИТА: Проверяем размеры остатков
                try:
                    width = float(remainder_data.get('width', 0))
                    if width <= 0:
                        logger.warning(f"Пропускаем остаток: некорректная ширина {width}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Пропускаем остаток: не удается преобразовать ширину")
                    continue
                
                try:
                    height = float(remainder_data.get('height', 0))
                    if height <= 0:
                        logger.warning(f"Пропускаем остаток: некорректная высота {height}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Пропускаем остаток: не удается преобразовать высоту")
                    continue
                
                # ЗАЩИТА: Проверяем материал остатка
                material = remainder_data.get('g_marking', '')
                if material is None:
                    material = ''
                material = str(material).strip()
                if not material:
                    logger.warning(f"Пропускаем остаток: отсутствует маркировка")
                    continue
                
                # ЗАЩИТА: Проверяем стоимость
                try:
                    cost = float(remainder_data.get('cost', 0))
                except (ValueError, TypeError):
                    cost = 0.0
                
                # ЗАЩИТА: Проверяем ID остатка
                remainder_id = remainder_data.get('id', '')
                if remainder_id is None:
                    remainder_id = ''
                remainder_id = str(remainder_id).strip()
                
                sheet = Sheet(
                    id=f"remainder_{remainder_id}" if remainder_id else f"remainder_{len(sheets)}",
                    width=width,
                    height=height,
                    material=material,
                    cost_per_unit=cost,
                    is_remainder=True,
                    remainder_id=remainder_id
                )
                sheets.append(sheet)
                
            except Exception as e:
                logger.error(f"Ошибка обработки остатка {remainder_data}: {e}")
                continue
        
        if not sheets:
            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=[],
                total_efficiency=0.0,
                total_waste_percent=0.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=0.0,
                message="Нет корректных листов для оптимизации"
            )
        
        # Создаем параметры оптимизации из kwargs
        try:
            params_obj = OptimizationParams(
                min_remnant_width=float(kwargs.get('min_remnant_width', 100.0)),
                min_remnant_height=float(kwargs.get('min_remnant_height', 100.0)),
                target_waste_percent=float(kwargs.get('target_waste_percent', 5.0)),
                min_waste_side=float(kwargs.get('min_waste_side', 10.0)),
                use_warehouse_remnants=bool(kwargs.get('use_warehouse_remnants', True)),
                rotation_mode=RotationMode.ALLOW_90 if kwargs.get('allow_rotation', True) else RotationMode.NONE,
                force_adjacent_placement=bool(kwargs.get('force_adjacent_placement', True)),
                cutting_width=float(kwargs.get('cutting_width', 3.0))
            )
        except Exception as e:
            logger.error(f"Ошибка создания параметров оптимизации: {e}")
            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=[],
                total_efficiency=0.0,
                total_waste_percent=0.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=0.0,
                message=f"Ошибка создания параметров: {str(e)}"
            )
        
        logger.info(f"Начинаем оптимизацию: {len(detail_objects)} деталей, {len(sheets)} листов")
        
        # Создаем оптимизатор
        try:
            optimizer = BestFitOptimizer(params_obj)
            if progress_fn:
                optimizer.set_progress_callback(progress_fn)
        except Exception as e:
            logger.error(f"Ошибка создания оптимизатора: {e}")
            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=[],
                total_efficiency=0.0,
                total_waste_percent=0.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=0.0,
                message=f"Ошибка создания оптимизатора: {str(e)}"
            )
        
        # Запускаем оптимизацию
        try:
            result = optimizer.optimize(detail_objects, sheets)
            logger.info(f"Оптимизация завершена: {result.message}")
            return result
        except Exception as e:
            logger.error(f"Ошибка во время оптимизации: {e}")
            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=detail_objects,
                total_efficiency=0.0,
                total_waste_percent=100.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=0.0,
                message=f"Ошибка во время оптимизации: {str(e)}"
            )
        
    except Exception as e:
        logger.error(f"Ошибка в функции optimize: {e}")
        return OptimizationResult(
            success=False,
            layouts=[],
            unplaced_details=[],
            total_efficiency=0.0,
            total_waste_percent=100.0,
            total_cost=0.0,
            useful_remnants=[],
            optimization_time=0.0,
            message=f"Критическая ошибка: {str(e)}"
        )

if __name__ == "__main__":
    # Простой тест
    print("Тестирование оптимизатора BestFit...")
    
    # Тестовые данные
    test_details = [
        {"id": "1", "width": 200, "height": 300, "g_marking": "ДСП", "quantity": 2},
        {"id": "2", "width": 150, "height": 400, "g_marking": "ДСП", "quantity": 1},
        {"id": "3", "width": 100, "height": 200, "g_marking": "ДСП", "quantity": 3}
    ]
    
    test_materials = [
        {"g_marking": "ДСП", "width": 1000, "height": 2000, "cost": 100}
    ]
    
    test_remainders = [
        {"id": "r1", "width": 500, "height": 600, "g_marking": "ДСП", "cost": 50}
    ]
    
    def test_progress(percent):
        print(f"Прогресс: {percent:.1f}%")
    
    result = optimize(test_details, test_materials, test_remainders, progress_fn=test_progress)
    
    print(f"Результат: {result.success}")
    print(f"Сообщение: {result.message}")
    print(f"Листов использовано: {result.total_sheets}")
    print(f"Эффективность: {result.total_efficiency:.1f}%") 