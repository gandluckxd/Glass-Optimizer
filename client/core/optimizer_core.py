#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль оптимизации 2D раскроя материалов - Версия 2.0
Гарантирует 100% покрытие листа без пересечений с соблюдением min_waste_side
"""

import time
import copy
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Set
from enum import Enum
import random

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
    priority: int = 0
    oi_name: str = ""
    goodsid: Optional[int] = None  # Добавлено поле goodsid
    
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
    goodsid: Optional[int] = None  # Добавлено поле goodsid
    
    def __post_init__(self):
        self.area = self.width * self.height

@dataclass
class PlacedItem:
    """Размещенный элемент (деталь или остаток/отход)"""
    x: float
    y: float
    width: float
    height: float
    item_type: str  # "detail", "remnant", "waste"
    detail: Optional[Detail] = None
    is_rotated: bool = False
    
    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height

@dataclass
class Rectangle:
    """Прямоугольная область"""
    x: float
    y: float
    width: float
    height: float
    
    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height
        
    def intersects(self, other: 'Rectangle') -> bool:
        """Проверяет пересечение с другим прямоугольником"""
        return not (self.x2 <= other.x or other.x2 <= self.x or 
                   self.y2 <= other.y or other.y2 <= self.y)
                   
    def contains(self, other: 'Rectangle') -> bool:
        """Проверяет, содержит ли данный прямоугольник другой"""
        return (self.x <= other.x and self.y <= other.y and
                other.x2 <= self.x2 and other.y2 <= self.y2)

@dataclass
class SheetLayout:
    """Раскладка на одном листе с ПОЛНЫМ покрытием"""
    sheet: Sheet
    placed_items: List[PlacedItem] = field(default_factory=list)
    
    def get_placed_details(self) -> List[PlacedItem]:
        """Возвращает только размещенные детали"""
        return [item for item in self.placed_items if item.item_type == "detail"]
    
    def get_remnants(self) -> List[PlacedItem]:
        """Возвращает деловые остатки"""
        return [item for item in self.placed_items if item.item_type == "remnant"]
    
    def get_waste(self) -> List[PlacedItem]:
        """Возвращает отходы"""
        return [item for item in self.placed_items if item.item_type == "waste"]
    
    @property
    def placed_details(self):
        """Для совместимости со старым кодом"""
        return [PlacedDetail(
            detail=item.detail,
            x=item.x,
            y=item.y,
            width=item.width,
            height=item.height,
            is_rotated=item.is_rotated,
            sheet_id=self.sheet.id
        ) for item in self.get_placed_details()]
    
    @property
    def free_rectangles(self):
        """Для совместимости со старым кодом"""
        return [FreeRectangle(r.x, r.y, r.width, r.height) for r in self.get_remnants()]
    
    @property
    def waste_rectangles(self):
        """Для совместимости со старым кодом"""
        return [FreeRectangle(r.x, r.y, r.width, r.height) for r in self.get_waste()]
    
    @property
    def total_area(self):
        return self.sheet.area
    
    @property
    def used_area(self):
        return sum(item.area for item in self.get_placed_details())
    
    @property
    def remnant_area(self):
        return sum(item.area for item in self.get_remnants())
    
    @property
    def waste_area(self):
        return sum(item.area for item in self.get_waste())
    
    @property
    def efficiency(self):
        effective_used = self.used_area + self.remnant_area
        return (effective_used / self.total_area * 100) if self.total_area > 0 else 0
    
    @property
    def waste_percent(self):
        return (self.waste_area / self.total_area * 100) if self.total_area > 0 else 0
    
    def get_coverage_percent(self) -> float:
        """Возвращает процент покрытия листа"""
        total_covered = sum(item.area for item in self.placed_items)
        return (total_covered / self.total_area * 100) if self.total_area > 0 else 0
    
    def has_bad_waste(self, min_waste_side: float) -> bool:
        """Проверяет, есть ли отходы с стороной меньше min_waste_side"""
        for waste in self.get_waste():
            if min(waste.width, waste.height) < min_waste_side:
                return True
        return False

# Старые классы для совместимости
@dataclass
class PlacedDetail:
    detail: Detail
    x: float
    y: float
    width: float
    height: float
    is_rotated: bool = False
    sheet_id: str = ""
    
    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height

@dataclass
class FreeRectangle:
    x: float
    y: float
    width: float
    height: float
    
    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height

@dataclass
class OptimizationParams:
    """Параметры оптимизации"""
    min_remnant_width: float = 100.0
    min_remnant_height: float = 100.0
    target_waste_percent: float = 5.0
    remainder_waste_percent: float = 20.0  # ДОБАВЛЕНО: Процент отходов для деловых остатков
    min_waste_side: float = 10.0
    use_warehouse_remnants: bool = True
    rotation_mode: RotationMode = RotationMode.ALLOW_90
    force_adjacent_placement: bool = True
    max_waste_rectangles: int = 10
    cutting_width: float = 3.0
    max_iterations_per_sheet: int = 5  # Максимум попыток пересборки листа

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
        self.sheets = self.layouts  # Для совместимости

class GuillotineOptimizer:
    """
    Оптимизатор с алгоритмом гильотинного раскроя
    Гарантирует 100% покрытие листа без пересечений
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
        
        logger.info(f"🚀 Начинаем оптимизацию v2.0: {len(details)} деталей, {len(sheets)} листов")
        
        # Подсчитываем остатки
        remainder_sheets = [s for s in sheets if s.is_remainder]
        material_sheets = [s for s in sheets if not s.is_remainder]
        logger.info(f"📊 Доступно остатков: {len(remainder_sheets)}, цельных листов: {len(material_sheets)}")
        
        # Подготовка данных
        expanded_details = self._prepare_details(details)
        sorted_sheets = self._prepare_sheets(sheets)
        
        self._report_progress(10.0)
        
        # Группировка по материалам
        material_groups = self._group_details_by_material(expanded_details)
        
        self._report_progress(20.0)
        
        # Оптимизация для каждого материала
        all_layouts = []
        all_unplaced = []
        progress_step = 70.0 / len(material_groups)
        current_progress = 20.0
        
        for material, material_details in material_groups.items():
            logger.info(f"📦 Оптимизируем материал {material}: {len(material_details)} деталей")
            
            material_sheets = [s for s in sorted_sheets if s.material == material]
            layouts, unplaced = self._optimize_material(material_details, material_sheets)
            
            all_layouts.extend(layouts)
            all_unplaced.extend(unplaced)
            
            current_progress += progress_step
            self._report_progress(current_progress)
        
        self._report_progress(95.0)
        
        # Финальный результат
        result = self._calculate_final_result(all_layouts, all_unplaced, start_time)
        
        self._report_progress(100.0)
        
        logger.info(f"✅ Оптимизация завершена за {result.optimization_time:.2f}с")
        logger.info(f"📊 Результат: {result.message}")
        
        return result

    def _prepare_details(self, details: List[Detail]) -> List[Detail]:
        """Подготовка деталей"""
        expanded = []
        
        for detail in details:
            for i in range(detail.quantity):
                detail_copy = copy.deepcopy(detail)
                detail_copy.id = f"{detail.id}_{i+1}"
                detail_copy.quantity = 1
                expanded.append(detail_copy)
        
        # Сортировка: сначала большие детали
        expanded.sort(key=lambda d: (-d.area, -d.priority, d.id))
        
        return expanded

    def _prepare_sheets(self, sheets: List[Sheet]) -> List[Sheet]:
        """Подготовка листов"""
        # Остатки используем первыми
        sheets.sort(key=lambda s: (not s.is_remainder, -s.area))
        return sheets

    def _group_details_by_material(self, details: List[Detail]) -> Dict[str, List[Detail]]:
        """Группировка деталей по материалам"""
        groups = {}
        for detail in details:
            if detail.material not in groups:
                groups[detail.material] = []
            groups[detail.material].append(detail)
        return groups

    def _can_fit_on_remainder(self, details: List[Detail], remainder: Sheet) -> bool:
        """Проверяет, можно ли разместить хотя бы одну деталь на остатке"""
        # Проверяем, поместится ли хотя бы самая большая деталь
        largest_detail = max(details, key=lambda d: d.area)
        # Используем параметр remainder_waste_percent из GUI
        allowed_usage_percent = 100.0 - self.params.remainder_waste_percent
        return largest_detail.area <= remainder.area * (allowed_usage_percent / 100.0)

    def _optimize_material(self, details: List[Detail], sheets: List[Sheet]) -> Tuple[List[SheetLayout], List[Detail]]:
        """Оптимизация размещения деталей одного материала с АВТОМАТИЧЕСКИМ приоритетом остатков"""
        layouts = []
        unplaced_details = details.copy()
        
        # НОВАЯ ЛОГИКА: Автоматический приоритет остатков
        remainder_sheets = [s for s in sheets if s.is_remainder]
        material_sheets = [s for s in sheets if not s.is_remainder]
        
        logger.info(f"🔄 Оптимизация материала: {len(unplaced_details)} деталей, "
                   f"{len(remainder_sheets)} остатков, {len(material_sheets)} цельных листов")
        
        # ПЕРВЫЙ ЭТАП: Агрессивное использование остатков
        logger.info(f"🎯 ЭТАП 1: Агрессивное использование {len(remainder_sheets)} остатков")
        
        # Сортируем остатки по эффективности использования (от меньших к большим)
        sorted_remainders = sorted(remainder_sheets, key=lambda sheet: (
            sheet.area,  # Сначала маленькие остатки
            sheet.id     # Для стабильности
        ))
        
        for sheet in sorted_remainders:
            if not unplaced_details:
                break
            
            logger.info(f"🎯 Пытаемся использовать остаток {sheet.id} ({sheet.width}x{sheet.height})")
            
            # Множественные попытки с разными стратегиями
            best_layout = None
            best_score = float('-inf')
            best_usage_percent = 0.0
            
            for iteration in range(self.params.max_iterations_per_sheet * 2):  # Увеличиваем попытки для остатков
                layout = self._create_sheet_layout_guillotine(sheet, unplaced_details.copy(), iteration)
                
                # Проверяем покрытие
                coverage = layout.get_coverage_percent()
                if coverage < 99.9:
                    continue
                
                # Проверяем наличие плохих отходов
                if layout.has_bad_waste(self.params.min_waste_side):
                    continue
                
                # Оцениваем раскладку с акцентом на использование остатка
                score = self._evaluate_layout(layout)
                usage_percent = layout.used_area / layout.total_area * 100
                
                # Дополнительный бонус за высокое использование остатка
                if usage_percent > 70:
                    score += 1000  # Огромный бонус за эффективное использование
                elif usage_percent > 50:
                    score += 500   # Большой бонус
                elif usage_percent > 30:
                    score += 200   # Средний бонус
                
                if score > best_score:
                    best_score = score
                    best_layout = layout
                    best_usage_percent = usage_percent
                
                # Если достигли отличного использования, прекращаем
                if usage_percent > 80:
                    logger.info(f"✅ Достигнуто отличное использование остатка: {usage_percent:.1f}%")
                    break
            
            if best_layout and best_layout.get_placed_details():
                layouts.append(best_layout)
                # Удаляем размещенные детали
                placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
                unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                
                logger.info(f"✅ УСПЕШНО использован остаток {sheet.id}: "
                           f"{len(best_layout.get_placed_details())} деталей, "
                           f"использование {best_usage_percent:.1f}%, "
                           f"отходы {best_layout.waste_percent:.1f}%")
        
        # ВТОРОЙ ЭТАП: Обработка цельных листов с минимизацией остатков
        logger.info(f"🎯 ЭТАП 2: Обработка {len(material_sheets)} цельных листов с минимизацией остатков")
        
        # Сортируем цельные листы по размеру (от больших к малым)
        sorted_material_sheets = sorted(material_sheets, key=lambda sheet: (
            -sheet.area,  # Сначала большие листы
            sheet.id      # Для стабильности
        ))
        
        for sheet in sorted_material_sheets:
            if not unplaced_details:
                break
            
            logger.info(f"🎯 Обрабатываем цельный лист {sheet.id} ({sheet.width}x{sheet.height})")
            
            best_layout = None
            best_score = float('-inf')
            
            for iteration in range(self.params.max_iterations_per_sheet):
                layout = self._create_sheet_layout_guillotine(sheet, unplaced_details.copy(), iteration)
                
                # Проверяем покрытие
                coverage = layout.get_coverage_percent()
                if coverage < 99.9:
                    continue
                
                # Проверяем наличие плохих отходов
                if layout.has_bad_waste(self.params.min_waste_side):
                    continue
                
                # Оцениваем раскладку с акцентом на минимизацию остатков
                score = self._evaluate_layout(layout)
                
                # Дополнительный штраф за создание деловых остатков на цельных листах
                remnant_area_percent = layout.remnant_area / layout.total_area * 100
                if remnant_area_percent > 3.0:  # Если создается больше 3% деловых остатков
                    score -= remnant_area_percent * 50  # Сильный штраф
                
                if score > best_score:
                    best_score = score
                    best_layout = layout
                
                # Если нашли раскладку с минимальными остатками, прекращаем
                if remnant_area_percent < 2.0:
                    logger.info(f"✅ Найдена раскладка с минимальными остатками: {remnant_area_percent:.1f}%")
                    break
            
            if best_layout and best_layout.get_placed_details():
                layouts.append(best_layout)
                # Удаляем размещенные детали
                placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
                unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                
                remnant_area_percent = best_layout.remnant_area / best_layout.total_area * 100
                logger.info(f"📋 Цельный лист {sheet.id}: размещено {len(best_layout.get_placed_details())} деталей, "
                           f"деловых остатков {remnant_area_percent:.1f}%, "
                           f"отходы {best_layout.waste_percent:.1f}%")
        
        return layouts, unplaced_details

    def _create_sheet_layout_guillotine(self, sheet: Sheet, details: List[Detail], iteration: int) -> SheetLayout:
        """Создание раскладки методом гильотинного раскроя с ГАРАНТИЕЙ 100% покрытия"""
        layout = SheetLayout(sheet=sheet)
        
        # Начинаем с полного листа как свободной области
        free_areas = [Rectangle(0, 0, sheet.width, sheet.height)]
        
        # Варьируем порядок деталей в зависимости от итерации
        if iteration > 0:
            # Случайная перестановка для разнообразия
            random.seed(42 + iteration)  # Фиксированный seed для воспроизводимости
            details = details.copy()
            random.shuffle(details)
        
        placed_detail_ids = set()
        
        # Размещаем детали
        while details and free_areas:
            best_placement = None
            best_score = float('inf')
            best_area_idx = -1
            
            for area_idx, area in enumerate(free_areas):
                for detail in details:
                    if detail.id in placed_detail_ids:
                        continue
                    
                    # Пробуем без поворота и с поворотом
                    orientations = [(detail.width, detail.height, False)]
                    if self.params.rotation_mode != RotationMode.NONE and detail.can_rotate:
                        orientations.append((detail.height, detail.width, True))
                    
                    for width, height, is_rotated in orientations:
                        if area.width >= width and area.height >= height:
                            # Проверяем, что разрез создаст допустимые остатки
                            if self._is_valid_guillotine_cut(area, width, height):
                                score = self._calculate_guillotine_score(area, width, height, is_rotated, sheet)
                                if score < best_score:
                                    best_score = score
                                    best_placement = (detail, width, height, is_rotated, area)
                                    best_area_idx = area_idx
            
            if not best_placement:
                break
            
            # Размещаем деталь
            detail, width, height, is_rotated, area = best_placement
            
            placed_item = PlacedItem(
                x=area.x,
                y=area.y,
                width=width,
                height=height,
                item_type="detail",
                detail=detail,
                is_rotated=is_rotated
            )
            layout.placed_items.append(placed_item)
            placed_detail_ids.add(detail.id)
            details.remove(detail)
            
            # Делаем гильотинный разрез и получаем новые области
            new_areas = self._guillotine_cut(area, width, height)
            
            # Заменяем использованную область новыми
            free_areas[best_area_idx:best_area_idx+1] = new_areas
        
        # КРИТИЧЕСКИ ВАЖНО: заполняем ВСЕ оставшиеся области
        self._fill_remaining_areas(layout, free_areas)
        
        # Проверка покрытия
        coverage = layout.get_coverage_percent()
        if coverage < 99.9:
            logger.error(f"❌ ОШИБКА: Покрытие листа только {coverage:.1f}%!")
        
        return layout

    def _is_valid_guillotine_cut(self, area: Rectangle, detail_width: float, detail_height: float) -> bool:
        """Проверяет, создаст ли гильотинный разрез допустимые остатки"""
        # Остатки после горизонтального разреза
        remainder_right = area.width - detail_width
        remainder_top = area.height - detail_height
        
        # Если остаток слишком мал, но не нулевой - это недопустимо
        if 0 < remainder_right < self.params.min_waste_side:
            return False
        if 0 < remainder_top < self.params.min_waste_side:
            return False
        
        # Проверяем подобласти, которые будут созданы
        if remainder_right > 0 and remainder_top > 0:
            # Будет создана L-образная область, проверяем обе части
            if detail_height < self.params.min_waste_side:
                return False
            if remainder_top < self.params.min_waste_side:
                return False
        
        return True

    def _calculate_guillotine_score(self, area: Rectangle, width: float, height: float, is_rotated: bool = False, sheet: Sheet = None) -> float:
        """Вычисляет оценку для гильотинного размещения"""
        # Предпочитаем размещения, которые минимизируют остатки
        waste = area.area - (width * height)
        
        # Бонус за точное соответствие размерам
        if abs(area.width - width) < 0.1 or abs(area.height - height) < 0.1:
            waste *= 0.5
        
        # Штраф за поворот детали (предпочитаем исходную ориентацию)
        if is_rotated:
            waste *= 1.2
        
        # НОВАЯ ЛОГИКА: Автоматическая оптимизация использования остатков
        if sheet and sheet.is_remainder:
            # Для остатков: ОГРОМНЫЙ бонус за использование
            waste *= 0.01  # Значительно снижаем штраф за отходы на остатках
            logger.debug(f"🔧 ОГРОМНЫЙ бонус за размещение на остатке: штраф снижен с {waste/0.01:.1f} до {waste:.1f}")
        elif sheet and not sheet.is_remainder:
            # Для цельных листов: штраф за создание деловых остатков
            remaining_width = area.width - width
            remaining_height = area.height - height
            
            # Если создаются деловые остатки, добавляем сильный штраф
            if (remaining_width >= self.params.min_remnant_width and remaining_width > 0) or \
               (remaining_height >= self.params.min_remnant_height and remaining_height > 0):
                waste *= 5.0  # Сильный штраф за создание деловых остатков
                logger.debug(f"🔧 Сильный штраф за создание деловых остатков: {remaining_width:.0f}x{remaining_height:.0f}")
        
        return waste

    def _guillotine_cut(self, area: Rectangle, used_width: float, used_height: float) -> List[Rectangle]:
        """Выполняет гильотинный разрез области"""
        new_areas = []
        
        # Правая часть (если есть)
        if area.width > used_width:
            right_area = Rectangle(
                area.x + used_width,
                area.y,
                area.width - used_width,
                used_height
            )
            if right_area.width >= self.params.min_waste_side and right_area.height >= self.params.min_waste_side:
                new_areas.append(right_area)
        
        # Верхняя часть (на всю ширину)
        if area.height > used_height:
            top_area = Rectangle(
                area.x,
                area.y + used_height,
                area.width,
                area.height - used_height
            )
            if top_area.width >= self.params.min_waste_side and top_area.height >= self.params.min_waste_side:
                new_areas.append(top_area)
        
        return new_areas

    def _fill_remaining_areas(self, layout: SheetLayout, free_areas: List[Rectangle]):
        """Заполняет все оставшиеся области как остатки или отходы"""
        print(f"🔧 OPTIMIZER: Заполнение оставшихся областей. Количество областей: {len(free_areas)}")
        
        for i, area in enumerate(free_areas):
            # НОВАЯ ЛОГИКА: Автоматическая классификация с учетом типа листа
            min_side = min(area.width, area.height)
            max_side = max(area.width, area.height)
            param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
            param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
            
            # Базовые критерии для деловых остатков
            min_area = self.params.min_remnant_width * self.params.min_remnant_height
            area_size = area.width * area.height
            
            # Для остатков: более мягкие критерии (хотим использовать остатки)
            if layout.sheet.is_remainder:
                if (min_side >= param_min and max_side >= param_max and 
                    area_size >= min_area * 1.2):  # Мягче для остатков
                    item_type = "remnant"
                    print(f"🔧 OPTIMIZER (ОСТАТОК): Область {i+1}: {area.width:.0f}x{area.height:.0f} - ДЕЛОВОЙ ОСТАТОК")
                else:
                    item_type = "waste"
                    print(f"🔧 OPTIMIZER (ОСТАТОК): Область {i+1}: {area.width:.0f}x{area.height:.0f} - ОТХОД")
            else:
                # Для цельных листов: очень строгие критерии (не хотим создавать остатки)
                if (min_side >= param_min * 1.5 and max_side >= param_max * 1.5 and 
                    area_size >= min_area * 3.0):  # Очень строго для цельных листов
                    item_type = "remnant"
                    print(f"🔧 OPTIMIZER (ЦЕЛЬНЫЙ): Область {i+1}: {area.width:.0f}x{area.height:.0f} - ДЕЛОВОЙ ОСТАТОК")
                else:
                    item_type = "waste"
                    print(f"🔧 OPTIMIZER (ЦЕЛЬНЫЙ): Область {i+1}: {area.width:.0f}x{area.height:.0f} - ОТХОД")
            
            placed_item = PlacedItem(
                x=area.x,
                y=area.y,
                width=area.width,
                height=area.height,
                item_type=item_type,
                detail=None,
                is_rotated=False
            )
            layout.placed_items.append(placed_item)
        
        # Подсчитываем итоги
        remnants_count = len([item for item in layout.placed_items if item.item_type == "remnant"])
        waste_count = len([item for item in layout.placed_items if item.item_type == "waste"])
        print(f"🔧 OPTIMIZER: Итоги заполнения - Деловых остатков: {remnants_count}, Отходов: {waste_count}")
        
        # Дополнительная проверка на 100% покрытие
        total_area_covered = sum(item.area for item in layout.placed_items)
        sheet_area = layout.sheet.area
        
        if abs(total_area_covered - sheet_area) > 0.1:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Покрыто {total_area_covered:.1f} из {sheet_area:.1f} мм²")
            
            # Аварийное заполнение пропущенных областей
            self._emergency_fill_gaps(layout)

    def _emergency_fill_gaps(self, layout: SheetLayout):
        """Аварийное заполнение пропущенных областей"""
        # Создаем карту занятых областей
        sheet_width = layout.sheet.width
        sheet_height = layout.sheet.height
        
        # Находим все непокрытые области методом сканирования
        gaps = []
        
        # Простой метод: проверяем сетку точек
        step = self.params.min_waste_side
        for x in range(0, int(sheet_width), int(step)):
            for y in range(0, int(sheet_height), int(step)):
                # Проверяем, покрыта ли эта точка
                covered = False
                for item in layout.placed_items:
                    if item.x <= x < item.x2 and item.y <= y < item.y2:
                        covered = True
                        break
                
                if not covered:
                    # Находим размер непокрытой области
                    max_width = sheet_width - x
                    max_height = sheet_height - y
                    
                    # Ограничиваем существующими элементами
                    for item in layout.placed_items:
                        if item.x > x and item.y <= y < item.y2:
                            max_width = min(max_width, item.x - x)
                        if item.y > y and item.x <= x < item.x2:
                            max_height = min(max_height, item.y - y)
                    
                    if max_width > 0 and max_height > 0:
                        gap = Rectangle(x, y, max_width, max_height)
                        
                        # Проверяем, не добавили ли мы уже эту область
                        is_duplicate = False
                        for existing_gap in gaps:
                            if existing_gap.contains(gap):
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            gaps.append(gap)
                            
                            # Добавляем как отход
                            placed_item = PlacedItem(
                                x=gap.x,
                                y=gap.y,
                                width=gap.width,
                                height=gap.height,
                                item_type="waste",
                                detail=None,
                                is_rotated=False
                            )
                            layout.placed_items.append(placed_item)
                            
                            logger.warning(f"⚠️ Заполнен пропущенный участок: {gap.x:.0f},{gap.y:.0f} {gap.width:.0f}x{gap.height:.0f}")

    def _get_allowed_waste_percent(self, sheet: Sheet) -> float:
        """Возвращает допустимый процент отходов в зависимости от типа листа"""
        if sheet.is_remainder:
            return self.params.remainder_waste_percent
        else:
            return self.params.target_waste_percent

    def _evaluate_layout(self, layout: SheetLayout) -> float:
        """Оценивает качество раскладки"""
        # Основные критерии:
        # 1. Минимум отходов (главный критерий)
        # 2. Оптимальное количество деловых остатков (не слишком много, не слишком мало)
        # 3. Компактность размещения
        
        score = 0.0
        
        # Получаем допустимый процент отходов для данного листа
        allowed_waste_percent = self._get_allowed_waste_percent(layout.sheet)
        
        # Штраф за отходы (учитываем допустимый процент для данного типа листа)
        waste_penalty = max(0, layout.waste_percent - allowed_waste_percent) * 100
        score -= waste_penalty
        
        # НОВАЯ ЛОГИКА: Оптимальное количество деловых остатков
        remnants = layout.get_remnants()
        remnant_count = len(remnants)
        remnant_area_percent = layout.remnant_area / layout.total_area * 100
        
        # НОВАЯ ЛОГИКА: Автоматическая оптимизация использования остатков
        if layout.sheet.is_remainder:
            # Для остатков: ОГРОМНЫЙ бонус за использование
            usage_percent = layout.used_area / layout.total_area * 100
            score += usage_percent * 100  # Бонус пропорциональный использованию
            
            # Дополнительный бонус за высокое использование
            if usage_percent > 80:
                score += 2000  # Огромный бонус
            elif usage_percent > 60:
                score += 1000  # Большой бонус
            elif usage_percent > 40:
                score += 500   # Средний бонус
            
            # Бонус за количество размещенных деталей на остатке
            score += len(layout.get_placed_details()) * 200
        else:
            # Для цельных листов: штраф за создание деловых остатков
            if remnant_area_percent > 3.0:
                score -= remnant_area_percent * 100  # Сильный штраф за избыточные остатки
            elif remnant_area_percent > 1.0:
                score -= remnant_area_percent * 50   # Средний штраф
            else:
                score += 100  # Бонус за минимальные остатки
        
        # Бонус за количество размещенных деталей
        score += len(layout.get_placed_details()) * 10
        
        # ОГРОМНЫЙ бонус за использование деловых остатков (если это остаток)
        if layout.sheet.is_remainder:
            score += 5000  # Очень большой бонус за использование остатков
            # Дополнительный бонус за эффективное использование остатка
            utilization = layout.used_area / layout.total_area
            score += utilization * 2000  # Бонус за процент использования остатка
            # Бонус за количество размещенных деталей на остатке
            score += len(layout.get_placed_details()) * 100
        
        # НОВЫЙ БОНУС: за качество деловых остатков
        for remnant in remnants:
            # Бонус за остатки с хорошими пропорциями
            aspect_ratio = max(remnant.width, remnant.height) / min(remnant.width, remnant.height)
            if 1.0 <= aspect_ratio <= 3.0:  # Хорошие пропорции
                score += 10
        
        return score

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
        
        # Сортируем листы: сначала деловые остатки, потом полноразмерные материалы
        # Внутри каждой группы сортируем по артикулу и размеру (от меньшего к большему)
        layouts.sort(key=lambda layout: (
            not layout.sheet.is_remainder,  # Остатки первыми (False < True)
            layout.sheet.material,          # По артикулу материала
            layout.sheet.area,              # По площади (от меньшей к большей)
            min(layout.sheet.width, layout.sheet.height),  # По минимальной стороне
            layout.sheet.id                 # По ID для стабильности
        ))
        # Подробное логирование сортировки
        remainder_count = len([l for l in layouts if l.sheet.is_remainder])
        material_count = len([l for l in layouts if not l.sheet.is_remainder])
        
        logger.info(f"📊 Отсортированы листы: {remainder_count} из остатков, {material_count} из полноразмерных материалов")
        
        # Группируем по материалам для логирования
        from collections import defaultdict
        material_groups = defaultdict(list)
        for layout in layouts:
            key = f"{'Остаток' if layout.sheet.is_remainder else 'Материал'} {layout.sheet.material}"
            material_groups[key].append(layout)
        
        for material_key, group_layouts in material_groups.items():
            sizes = [f"{int(l.sheet.width)}x{int(l.sheet.height)}" for l in group_layouts]
            logger.info(f"  📋 {material_key}: {len(group_layouts)} листов, размеры: {', '.join(sizes)}")
        
        # Общая статистика
        total_area = sum(layout.total_area for layout in layouts)
        total_used = sum(layout.used_area for layout in layouts)
        total_remnant_area = sum(layout.remnant_area for layout in layouts)
        total_waste_area = sum(layout.waste_area for layout in layouts)
        
        # Статистика по типам листов
        remainder_layouts = [l for l in layouts if l.sheet.is_remainder]
        material_layouts = [l for l in layouts if not l.sheet.is_remainder]
        
        if remainder_layouts:
            remainder_area = sum(l.total_area for l in remainder_layouts)
            remainder_waste = sum(l.waste_area for l in remainder_layouts)
            remainder_waste_percent = (remainder_waste / remainder_area * 100) if remainder_area > 0 else 0
            logger.info(f"📊 Статистика остатков: {len(remainder_layouts)} листов, "
                       f"площадь {remainder_area:.0f}, отходы {remainder_waste_percent:.1f}% "
                       f"(допустимо {self.params.remainder_waste_percent:.1f}%)")
            
            # Дополнительная статистика по использованию остатков
            # Подсчитываем общее количество остатков из всех листов
            total_remainder_sheets = len([l for l in layouts if l.sheet.is_remainder])
            used_remainders = len(remainder_layouts)
            if total_remainder_sheets > 0:
                usage_percent = used_remainders / total_remainder_sheets * 100
                logger.info(f"🎯 Использование остатков: {used_remainders}/{total_remainder_sheets} остатков использовано "
                           f"({usage_percent:.1f}% эффективность использования)")
            else:
                logger.info(f"🎯 Остатки: нет доступных остатков для использования")
        
        if material_layouts:
            material_area = sum(l.total_area for l in material_layouts)
            material_waste = sum(l.waste_area for l in material_layouts)
            material_waste_percent = (material_waste / material_area * 100) if material_area > 0 else 0
            logger.info(f"📊 Статистика цельных листов: {len(material_layouts)} листов, "
                       f"площадь {material_area:.0f}, отходы {material_waste_percent:.1f}% "
                       f"(допустимо {self.params.target_waste_percent:.1f}%)")
        
        # Собираем полезные остатки
        useful_remnants = []
        for layout in layouts:
            for remnant in layout.get_remnants():
                useful_remnants.append(FreeRectangle(
                    remnant.x, remnant.y, 
                    remnant.width, remnant.height
                ))
        
        total_efficiency = ((total_used + total_remnant_area) / total_area * 100) if total_area > 0 else 0
        total_waste_percent = (total_waste_area / total_area * 100) if total_area > 0 else 0
        
        # Общая стоимость
        total_cost = sum(layout.sheet.cost_per_unit * layout.sheet.area for layout in layouts)
        
        # Проверка покрытия
        for i, layout in enumerate(layouts):
            coverage = layout.get_coverage_percent()
            if coverage < 99.9:
                logger.error(f"❌ Лист {i+1}: покрытие только {coverage:.1f}%!")
        
        # Сообщение о результате
        success = len(unplaced) == 0
        if success:
            message = f"Все детали успешно размещены на {len(layouts)} листах"
        else:
            message = f"Размещено {sum(len(l.get_placed_details()) for l in layouts)} деталей, не размещено: {len(unplaced)}"
        
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

# Функция для совместимости с существующим интерфейсом
def optimize(details: List[dict], materials: List[dict], remainders: List[dict], 
            params: dict = None, progress_fn: Optional[Callable[[float], None]] = None, **kwargs) -> OptimizationResult:
    """
    Главная функция оптимизации для совместимости с существующим GUI
    """
    
    try:
        logger.info(f"🚀 Запуск алгоритма v2.0 с гарантией 100% покрытия")
        
        # Объединяем параметры
        if params:
            kwargs.update(params)
        
        # Преобразуем входные данные
        detail_objects = []
        for detail_data in details:
            try:
                # Извлекаем goodsid
                goodsid = detail_data.get('goodsid')
                if goodsid:
                    goodsid = int(goodsid)
                
                detail = Detail(
                    id=str(detail_data.get('orderitemsid', detail_data.get('id', f'detail_{len(detail_objects)}'))),
                    width=float(detail_data.get('width', 0)),
                    height=float(detail_data.get('height', 0)),
                    material=str(detail_data.get('g_marking', '')),
                    quantity=int(detail_data.get('total_qty', detail_data.get('quantity', 1))),
                    can_rotate=True,
                    priority=int(detail_data.get('priority', 0)),
                    oi_name=str(detail_data.get('oi_name', '')),
                    goodsid=goodsid  # Передаем goodsid в деталь
                )
                
                # ДОБАВЛЕНО: Передаем новые поля для XML генерации
                detail.gp_marking = str(detail_data.get('gp_marking', ''))
                detail.orderno = str(detail_data.get('orderno', ''))
                detail.orderitemsid = detail_data.get('orderitemsid', '')
                if detail.width > 0 and detail.height > 0 and detail.material:
                    detail_objects.append(detail)
                    logger.info(f"🔧 Создана деталь: {detail.oi_name}, материал={detail.material}, goodsid={goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки детали: {e}")
        
        # Создаем листы
        sheets = []
        for material_data in materials:
            try:
                qty = int(material_data.get('res_qty', material_data.get('quantity', 1)))
                if qty <= 0:
                    logger.warning(f"⚠️ Пропускаем материал с некорректным количеством: qty={qty}")
                    continue
                if qty > 1000:
                    qty = 1000
                
                # Извлекаем goodsid
                goodsid = material_data.get('goodsid')
                if goodsid:
                    goodsid = int(goodsid)
                
                for j in range(qty):
                    sheet = Sheet(
                        id=f"sheet_{material_data.get('g_marking', 'unknown')}_{j+1}",
                        width=float(material_data.get('width', 0)),
                        height=float(material_data.get('height', 0)),
                        material=str(material_data.get('g_marking', '')),
                        cost_per_unit=float(material_data.get('cost', 0)),
                        is_remainder=False,
                        goodsid=goodsid  # Передаем goodsid в лист
                    )
                    if sheet.width > 0 and sheet.height > 0 and sheet.material:
                        sheets.append(sheet)
                        logger.info(f"📄 Создан лист материала: {sheet.material}, goodsid={goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки материала: {e}")
        
        # Остатки
        for remainder_data in remainders:
            try:
                # Извлекаем goodsid
                goodsid = remainder_data.get('goodsid')
                if goodsid:
                    goodsid = int(goodsid)
                
                # Получаем количество штук остатка
                qty = int(remainder_data.get('qty', 1))
                if qty <= 0:
                    logger.warning(f"⚠️ Пропускаем остаток с некорректным количеством: qty={qty}")
                    continue
                if qty > 1000:  # Защита от слишком больших значений
                    logger.warning(f"⚠️ Ограничение количества остатков с {qty} до 1000")
                    qty = 1000
                
                logger.info(f"📄 Обработка остатка: материал={remainder_data.get('g_marking', '')}, "
                           f"размер={remainder_data.get('width', 0)}x{remainder_data.get('height', 0)}, "
                           f"количество={qty}")
                
                # Создаем листы по количеству остатков
                for j in range(qty):
                    sheet = Sheet(
                        id=f"remainder_{remainder_data.get('id', len(sheets))}_{j+1}",
                        width=float(remainder_data.get('width', 0)),
                        height=float(remainder_data.get('height', 0)),
                        material=str(remainder_data.get('g_marking', '')),
                        cost_per_unit=float(remainder_data.get('cost', 0)),
                        is_remainder=True,
                        remainder_id=str(remainder_data.get('id', '')),
                        goodsid=goodsid  # Передаем goodsid в остаток
                    )
                    if sheet.width > 0 and sheet.height > 0 and sheet.material:
                        sheets.append(sheet)
                        logger.info(f"�� Создан остаток {j+1}/{qty}: {sheet.material}, goodsid={goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки остатка: {e}")
        
        # Создаем параметры оптимизации
        params_obj = OptimizationParams(
            min_remnant_width=float(kwargs.get('min_remnant_width', 100.0)),
            min_remnant_height=float(kwargs.get('min_remnant_height', 100.0)),
            target_waste_percent=float(kwargs.get('target_waste_percent', 5.0)),
            remainder_waste_percent=float(kwargs.get('remainder_waste_percent', 20.0)), # Добавляем новый параметр
            min_waste_side=float(kwargs.get('min_waste_side', 10.0)),
            use_warehouse_remnants=bool(kwargs.get('use_warehouse_remnants', True)),
            rotation_mode=RotationMode.ALLOW_90 if kwargs.get('allow_rotation', True) else RotationMode.NONE,
            cutting_width=float(kwargs.get('cutting_width', 3.0)),
            max_iterations_per_sheet=int(kwargs.get('max_iterations_per_sheet', 5))
        )
        
        # Создаем оптимизатор и запускаем
        optimizer = GuillotineOptimizer(params_obj)
        if progress_fn:
            optimizer.set_progress_callback(progress_fn)
        
        return optimizer.optimize(detail_objects, sheets)
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
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

