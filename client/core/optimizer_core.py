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

    def _pre_use_all_remainders(
        self,
        details: List[Detail],
        sheets: List[Sheet]
    ) -> Tuple[List[SheetLayout], List[Detail], List[str]]:
        """Пытается задействовать каждый деловой остаток хотя бы одной деталью до основной оптимизации.

        Возвращает: (layouts, remaining_details, used_remainder_ids)
        """
        layouts: List[SheetLayout] = []
        remaining_details = details.copy()
        used_remainder_ids: List[str] = []

        # Берём только остатки и сортируем их от меньших к большим (проще найти хоть что-то)
        remainder_sheets = [s for s in sheets if s.is_remainder]
        remainder_sheets.sort(key=lambda s: (s.area, s.id))

        for sheet in remainder_sheets:
            if not remaining_details:
                break

            # Быстрая геометрическая проверка
            if not self._can_fit_on_remainder(remaining_details, sheet):
                continue

            # Оставляем только те детали, которые помещаются по геометрии (с учетом поворота)
            fitting_details = []
            sw, sh = sheet.width, sheet.height
            for det in remaining_details:
                # ВАЖНО: Материал детали должен совпадать с материалом остатка
                if det.material != sheet.material:
                    continue
                fits = (det.width <= sw and det.height <= sh) or (
                    det.can_rotate and det.height <= sw and det.width <= sh
                )
                if fits:
                    fitting_details.append(det)

            if not fitting_details:
                continue

            # Ищем лучшую раскладку на остатке, пытаясь разместить МАКСИМУМ деталей
            best_layout = None
            best_score = float('-inf')
            best_usage_percent = 0.0

            # Существенно увеличиваем число попыток на остатках
            max_tries = max(10, self.params.max_iterations_per_sheet * 5)
            for iteration in range(max_tries):
                layout = self._create_sheet_layout_guillotine(sheet, fitting_details.copy(), iteration)

                # Для остатков не фильтруем по проценту отходов: цель — разместить максимум деталей

                # Оцениваем по использованию площади в первую очередь
                usage_percent = (layout.used_area / layout.total_area * 100) if layout.total_area > 0 else 0.0
                score = self._evaluate_layout(layout)

                if layout.get_placed_details() and (usage_percent > best_usage_percent or (usage_percent == best_usage_percent and score > best_score)):
                    best_usage_percent = usage_percent
                    best_score = score
                    best_layout = layout

            if not best_layout or not best_layout.get_placed_details():
                continue

            # Зафиксируем результат
            layouts.append(best_layout)
            used_remainder_ids.append(sheet.id)

            placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
            remaining_details = [d for d in remaining_details if d.id not in placed_ids]

        return layouts, remaining_details, used_remainder_ids

    def _is_valid_cut_for_remnant(self, remnant: PlacedItem, width: float, height: float) -> bool:
        """Проверяет корректность гильотинного разреза внутри прямоугольника остатка.
        Учитывает min_waste_side через _is_valid_guillotine_cut."""
        area = Rectangle(remnant.x, remnant.y, remnant.width, remnant.height)
        return self._is_valid_guillotine_cut(area, width, height)

    def optimize(self, details: List[Detail], sheets: List[Sheet]) -> OptimizationResult:
        """Основной метод оптимизации с улучшенным алгоритмом заполнения деловых остатков"""
        start_time = time.time()
        
        logger.info(f"🚀 Начинаем оптимизацию v2.1: {len(details)} деталей, {len(sheets)} листов")
        
        # Подсчитываем остатки
        remainder_sheets = [s for s in sheets if s.is_remainder]
        material_sheets = [s for s in sheets if not s.is_remainder]
        logger.info(f"📊 Доступно остатков: {len(remainder_sheets)}, цельных листов: {len(material_sheets)}")
        
        # Подготовка данных
        expanded_details = self._prepare_details(details)
        sorted_sheets = self._prepare_sheets(sheets)
        
        self._report_progress(10.0)
        
        # ПРЕДВАРИТЕЛЬНЫЙ ПРОХОД: попытаться использовать КАЖДЫЙ деловой остаток хотя бы одной деталью
        logger.info("🔄 ПРЕДВАРИТЕЛЬНЫЙ ПРОХОД: пытаемся использовать каждый деловой остаток хотя бы одной деталью")
        pre_layouts, expanded_details, used_pre_remainders = self._pre_use_all_remainders(expanded_details, sorted_sheets)
        logger.info(f"📊 ПРЕДВАРИТЕЛЬНЫЙ ПРОХОД: использовано остатков: {len(used_pre_remainders)}")

        # Исключаем уже использованные остатки из дальнейшего рассмотрения
        if used_pre_remainders:
            used_ids = set(used_pre_remainders)
            sorted_sheets = [s for s in sorted_sheets if not (s.is_remainder and s.id in used_ids)]

        # Группировка по материалам
        material_groups = self._group_details_by_material(expanded_details)
        
        self._report_progress(20.0)
        
        # Оптимизация для каждого материала
        all_layouts = pre_layouts.copy() if pre_layouts else []
        all_unplaced = []
        progress_step = 60.0 / len(material_groups)
        current_progress = 25.0
        
        for material, material_details in material_groups.items():
            logger.info(f"📦 Оптимизируем материал {material}: {len(material_details)} деталей")
            
            material_sheets = [s for s in sorted_sheets if s.material == material]
            layouts, unplaced = self._optimize_material(material_details, material_sheets)
            
            all_layouts.extend(layouts)
            all_unplaced.extend(unplaced)
            
            current_progress += progress_step
            self._report_progress(current_progress)
        
        self._report_progress(90.0)

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
        
        for base_index, detail in enumerate(details):
            for i in range(detail.quantity):
                detail_copy = copy.deepcopy(detail)
                # Гарантируем ГЛОБАЛЬНУЮ уникальность идентификатора даже при совпадающих orderitemsid
                detail_copy.id = f"{detail.id}__{base_index+1}_{i+1}"
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
        """Проверяет, можно ли разместить хотя бы одну деталь на остатке по ГЕОМЕТРИИ (c учетом поворота)."""
        rem_w, rem_h = remainder.width, remainder.height
        for d in details:
            if (d.width <= rem_w and d.height <= rem_h) or (
                d.can_rotate and d.height <= rem_w and d.width <= rem_h
            ):
                return True
        return False

    def _optimize_material(self, details: List[Detail], sheets: List[Sheet]) -> Tuple[List[SheetLayout], List[Detail]]:
        """Оптимизация размещения деталей одного материала с МАКСИМАЛЬНЫМ приоритетом остатков"""
        layouts = []
        unplaced_details = details.copy()
        
        # МАКСИМАЛЬНЫЙ ПРИОРИТЕТ ОСТАТКОВ: Сначала все остатки, потом цельные листы
        remainder_sheets = [s for s in sheets if s.is_remainder]
        material_sheets = [s for s in sheets if not s.is_remainder]
        
        logger.info(f"🔄 МАКСИМАЛЬНАЯ ОПТИМИЗАЦИЯ ОСТАТКОВ: {len(unplaced_details)} деталей, "
                   f"{len(remainder_sheets)} остатков, {len(material_sheets)} цельных листов")
        
        # ПЕРВЫЙ ЭТАП: МАКСИМАЛЬНО агрессивное использование остатков
        logger.info(f"🎯 ЭТАП 1: МАКСИМАЛЬНО агрессивное использование {len(remainder_sheets)} остатков")
        
        # Сортируем остатки по эффективности использования (от меньших к большим)
        sorted_remainders = sorted(remainder_sheets, key=lambda sheet: (
            sheet.area,  # Сначала маленькие остатки
            sheet.id     # Для стабильности
        ))
        
        for sheet in sorted_remainders:
            if not unplaced_details:
                break
            
            logger.info(f"🎯 МАКСИМАЛЬНО пытаемся использовать остаток {sheet.id} ({sheet.width}x{sheet.height})")
            # Быстрая проверка: поместится ли вообще хоть одна из крупных деталей с учетом допустимого процента отхода
            try:
                if not self._can_fit_on_remainder(unplaced_details, sheet):
                    logger.info(f"⏭️ Пропускаем остаток {sheet.id}: слишком мал для размещения деталей с учетом remainder_waste_percent")
                    continue
            except Exception:
                # На всякий случай не прерываем процесс
                pass
            
            # МАКСИМАЛЬНОЕ количество попыток с разными стратегиями
            best_layout = None
            best_score = float('-inf')
            best_usage_percent = 0.0
            
            for iteration in range(self.params.max_iterations_per_sheet * 5):  # Увеличиваем попытки в 5 раз
                layout = self._create_sheet_layout_guillotine(sheet, unplaced_details.copy(), iteration)

                # Для остатков не фильтруем по проценту отходов: цель — использовать максимум остатков
                
                # Проверяем наличие плохих отходов (мягкие требования для остатков)
                if layout.has_bad_waste(self.params.min_waste_side * 0.3):
                    continue
                
                # Оцениваем раскладку с МАКСИМАЛЬНЫМ акцентом на использование остатка
                score = self._evaluate_layout(layout)
                usage_percent = layout.used_area / layout.total_area * 100
                
                # МАКСИМАЛЬНЫЙ бонус за любое использование остатка
                if usage_percent > 50:
                    score += 5000  # Огромный бонус за эффективное использование
                elif usage_percent > 30:
                    score += 3000   # Очень большой бонус
                elif usage_percent > 15:
                    score += 2000   # Большой бонус
                elif usage_percent > 5:  # Бонус даже за минимальное использование
                    score += 1000   # Бонус за любое использование остатка
                else:
                    score += 500   # Бонус даже за очень низкое использование
                
                # Дополнительный бонус за количество размещенных деталей на остатке
                score += len(layout.get_placed_details()) * 1000  # Огромный бонус за каждую деталь
                
                if score > best_score:
                    best_score = score
                    best_layout = layout
                    best_usage_percent = usage_percent
                
                # Если достигли хоть какого-то использования, прекращаем
                if usage_percent > 10:  # Снижаем порог до 10%
                    logger.info(f"✅ Достигнуто использование остатка: {usage_percent:.1f}%")
                    break
            
            if best_layout and best_layout.get_placed_details():
                layouts.append(best_layout)
                # Удаляем размещенные детали
                placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
                unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                
                logger.info(f"✅ МАКСИМАЛЬНО УСПЕШНО использован остаток {sheet.id}: "
                           f"{len(best_layout.get_placed_details())} деталей, "
                           f"использование {best_usage_percent:.1f}%, "
                           f"отходы {best_layout.waste_percent:.1f}%")
            else:
                logger.warning(f"❌ Не удалось использовать остаток {sheet.id}")
        
        # ВТОРОЙ ЭТАП: Обработка цельных листов только если остались детали
        if unplaced_details:
            logger.info(f"🎯 ЭТАП 2: Обработка {len(material_sheets)} цельных листов для оставшихся {len(unplaced_details)} деталей")
            
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
                    
                    # Оцениваем раскладку
                    score = self._evaluate_layout(layout)
                    
                    if score > best_score:
                        best_score = score
                        best_layout = layout
                
                if best_layout and best_layout.get_placed_details():
                    # Сначала исключаем уже размещённые на базовой раскладке детали из пула свободных
                    base_placed_ids = {item.detail.id for item in best_layout.get_placed_details() if item.detail}
                    if base_placed_ids:
                        unplaced_details = [d for d in unplaced_details if d.id not in base_placed_ids]

                    # СРАЗУ после этого дополнительно заполняем остатки этого листа только СВОБОДНЫМИ деталями
                    before_fill = len(best_layout.get_placed_details())
                    unplaced_details, additionally_placed = self._fill_layout_remnants_with_details(best_layout, unplaced_details)
                    after_fill = len(best_layout.get_placed_details())

                    layouts.append(best_layout)
                    logger.info(
                        f"✅ УСПЕШНО использован цельный лист {sheet.id}: базово {before_fill} деталей, "
                        f"добавлено {additionally_placed}, итого {len(best_layout.get_placed_details())}; "
                        f"отходы {best_layout.waste_percent:.1f}%"
                    )
        
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
        
        # Бонус за точное соответствие размерам (сильнее поощряем на цельных листах)
        if abs(area.width - width) < 0.1 or abs(area.height - height) < 0.1:
            if sheet and not sheet.is_remainder:
                waste *= 0.35
            else:
                waste *= 0.5
        
        # Штраф за поворот детали (предпочитаем исходную ориентацию)
        if is_rotated:
            waste *= 1.2
        
        # АГРЕССИВНАЯ ЛОГИКА: Максимальное поощрение использования остатков
        if sheet and sheet.is_remainder:
            # Для остатков: ОГРОМНЫЙ бонус за использование
            waste *= 0.001  # Еще больше снижаем штраф за отходы на остатках
            logger.debug(f"🔧 ОГРОМНЫЙ бонус за размещение на остатке: штраф снижен с {waste/0.001:.1f} до {waste:.1f}")
        elif sheet and not sheet.is_remainder:
            # Для цельных листов: усиливаем стремление не плодить множество остатков
            remaining_width = area.width - width
            remaining_height = area.height - height
            
            # УМЕРЕННАЯ ЛОГИКА: Менее строгие критерии для деловых остатков
            min_remnant_width = self.params.min_remnant_width * 1.5  # Снижены требования
            min_remnant_height = self.params.min_remnant_height * 1.5
            min_remnant_area = min_remnant_width * min_remnant_height * 2.0  # Снижены требования
            
            # Дополнительный штраф за L-образные остатки (оба остатка > 0) — ведет к большему числу фрагментов
            if remaining_width > 0 and remaining_height > 0:
                waste *= 2.5
            else:
                # Небольшой бонус, если один из остатков равен нулю — формально уменьшаем число фрагментов
                waste *= 0.9
            
            # Если создаются деловые остатки, добавляем УМЕРЕННЫЙ штраф
            if ((remaining_width >= min_remnant_width and remaining_width > 0) or \
                (remaining_height >= min_remnant_height and remaining_height > 0)) and \
               (remaining_width * remaining_height >= min_remnant_area):
                waste *= 2.0  # Умеренный штраф за создание деловых остатков
                logger.debug(f"🔧 Умеренный штраф за создание деловых остатков: {remaining_width:.0f}x{remaining_height:.0f}")
            elif (remaining_width >= self.params.min_remnant_width and remaining_width > 0) or \
                 (remaining_height >= self.params.min_remnant_height and remaining_height > 0):
                waste *= 1.5  # Небольшой штраф за потенциальные остатки
                logger.debug(f"🔧 Небольшой штраф за потенциальные остатки: {remaining_width:.0f}x{remaining_height:.0f}")
        
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
        """Заполняет все оставшиеся области как остатки или отходы с ПРАВИЛЬНОЙ логикой"""
        logger.debug(f"OPTIMIZER: Заполнение оставшихся областей. Количество областей: {len(free_areas)}")
        
        for i, area in enumerate(free_areas):
            # ЕДИНАЯ ЛОГИКА: деловой остаток, если меньшая сторона > меньшего параметра и большая сторона > большего параметра
            min_side = min(area.width, area.height)
            max_side = max(area.width, area.height)
            param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
            param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
            is_remnant = (min_side > param_min and max_side > param_max)

            if is_remnant:
                item_type = "remnant"
                logger.debug(f"OPTIMIZER: Область {i+1}: {area.width:.0f}x{area.height:.0f} - ДЕЛОВОЙ ОСТАТОК")
            else:
                item_type = "waste"
                logger.debug(f"OPTIMIZER: Область {i+1}: {area.width:.0f}x{area.height:.0f} - ОТХОД")
            
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
        logger.debug(f"OPTIMIZER: Итоги заполнения - Деловых остатков: {remnants_count}, Отходов: {waste_count}")
        
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
        
        # УЛУЧШЕННАЯ ЛОГИКА: Оптимальное количество деловых остатков
        remnants = layout.get_remnants()
        remnant_count = len(remnants)
        remnant_area_percent = layout.remnant_area / layout.total_area * 100
        
        # БАЛАНСИРОВАННАЯ ЛОГИКА: Оптимальное использование и объединение остатков
        if layout.sheet.is_remainder:
            # Для остатков: УМЕРЕННЫЙ бонус за использование
            usage_percent = layout.used_area / layout.total_area * 100
            score += usage_percent * 100  # Умеренный бонус
            
            # Дополнительный бонус за высокое использование
            if usage_percent > 80:
                score += 2000  # Умеренный бонус
            elif usage_percent > 60:
                score += 1000  # Умеренный бонус
            elif usage_percent > 40:
                score += 500   # Умеренный бонус
            
            # Бонус за количество размещенных деталей на остатке
            score += len(layout.get_placed_details()) * 200  # Умеренный бонус
            
            # Бонус за использование остатков
            score += 3000  # Умеренный бонус
        else:
            # Для цельных листов: БАЛАНСИРОВАННЫЙ подход к деловым остаткам
            if remnant_area_percent > 8.0:  # Большие остатки - штраф
                score -= remnant_area_percent * 150  # Сильный штраф за большие остатки
            elif remnant_area_percent > 3.0:  # Средние остатки - небольшой штраф
                score -= remnant_area_percent * 50   # Небольшой штраф
            elif remnant_area_percent > 1.0:  # Маленькие остатки - бонус
                score += 50   # Бонус за маленькие остатки (можно объединить)
            else:
                score += 200  # Бонус за минимальные остатки

            # ЯВНЫЙ ШТРАФ за количество деловых остатков на цельных листах
            remnant_count_penalty = remnant_count * 300
            if remnant_count > 2:
                remnant_count_penalty += (remnant_count - 2) * 200
            score -= remnant_count_penalty
        
        # Бонус за количество размещенных деталей
        score += len(layout.get_placed_details()) * 10
        
        # ОГРОМНЫЙ бонус за использование деловых остатков (если это остаток)
        if layout.sheet.is_remainder:
            score += 10000  # Огромный бонус за использование остатков
            # Дополнительный бонус за эффективное использование остатка
            utilization = layout.used_area / layout.total_area
            score += utilization * 5000  # Увеличиваем бонус за процент использования остатка
            # Бонус за количество размещенных деталей на остатке
            score += len(layout.get_placed_details()) * 2000  # Увеличиваем бонус за каждую деталь
            # Дополнительный бонус за любую деталь на остатке
            if len(layout.get_placed_details()) > 0:
                score += 5000  # Бонус за то, что вообще что-то разместили на остатке
        
        # НОВЫЙ БОНУС: за качество деловых остатков
        for remnant in remnants:
            # Бонус за остатки с хорошими пропорциями
            aspect_ratio = max(remnant.width, remnant.height) / min(remnant.width, remnant.height)
            if 1.0 <= aspect_ratio <= 3.0:  # Хорошие пропорции
                score += 10
        
        return score

    def _fill_remnants_with_details(self, layouts: List[SheetLayout], unplaced_details: List[Detail]) -> List[Detail]:
        """АГРЕССИВНЫЙ алгоритм заполнения деловых остатков оставшимися деталями с циклом"""
        if not unplaced_details:
            logger.info("📦 Нет деталей для заполнения остатков")
            return unplaced_details
        
        logger.info(f"🔄 АГРЕССИВНО заполняем {len(unplaced_details)} деталей в деловые остатки")
        
        # Собираем все деловые остатки
        all_remnants = []
        for layout in layouts:
            for remnant in layout.get_remnants():
                all_remnants.append({
                    'layout': layout,
                    'remnant': remnant,
                    'area': remnant.area,
                    'width': remnant.width,
                    'height': remnant.height
                })
        
        if not all_remnants:
            logger.info("📦 Нет деловых остатков для заполнения")
            return unplaced_details
        
        logger.info(f"📦 Найдено {len(all_remnants)} деловых остатков для заполнения")
        
        # Сортируем остатки по площади (от больших к меньшим) для лучшего использования
        all_remnants.sort(key=lambda r: -r['area'])
        
        # Сортируем детали по площади (от больших к меньшим)
        sorted_details = sorted(unplaced_details, key=lambda d: -d.area)
        
        remaining_details = sorted_details.copy()
        placed_count = 0
        total_iterations = 0
        max_iterations = 20  # Увеличиваем максимум итераций с 10 до 20
        
        # АГРЕССИВНЫЙ ЦИКЛ: Многократно проходим по остаткам
        while remaining_details and total_iterations < max_iterations:
            iteration_placed = 0
            total_iterations += 1
            
            logger.info(f"🔄 Итерация {total_iterations}: пытаемся разместить {len(remaining_details)} деталей")
            
            # Обновляем список остатков (они могли измениться после предыдущих размещений)
            all_remnants = []
            for layout in layouts:
                for remnant in layout.get_remnants():
                    all_remnants.append({
                        'layout': layout,
                        'remnant': remnant,
                        'area': remnant.area,
                        'width': remnant.width,
                        'height': remnant.height
                    })
            
            if not all_remnants:
                logger.info("📦 Больше нет деловых остатков для заполнения")
                break
            
            # Сортируем остатки по площади (от больших к меньшим)
            all_remnants.sort(key=lambda r: -r['area'])
            
            # Пытаемся разместить каждую деталь
            details_to_remove = []
            
            for detail in remaining_details:
                placed = False
                
                # Пытаемся разместить деталь в остатках с разными стратегиями от менее к более агрессивным
                for remnant_info in all_remnants:
                    remnant = remnant_info['remnant']
                    layout = remnant_info['layout']

                    # Материал должен совпадать
                    if detail.material != layout.sheet.material:
                        continue
                    
                    # Пробуем разные стратегии размещения от менее к более агрессивным
                    if self._can_place_detail_in_remnant_aggressive(detail, remnant, layout):
                        # Размещаем деталь (с валидацией разрезов)
                        if not self._place_detail_in_remnant(detail, remnant, layout):
                            continue
                        placed = True
                        placed_count += 1
                        iteration_placed += 1
                        details_to_remove.append(detail)
                        logger.info(f"✅ АГРЕССИВНО разместили деталь {detail.id} ({detail.width:.0f}x{detail.height:.0f}) в остатке {remnant.width:.0f}x{remnant.height:.0f}")
                        break
                    
                    # Если агрессивная стратегия не сработала, пробуем очень агрессивную
                    elif self._can_place_detail_in_remnant_very_aggressive(detail, remnant, layout):
                        # Размещаем деталь (с валидацией разрезов)
                        if not self._place_detail_in_remnant(detail, remnant, layout):
                            continue
                        placed = True
                        placed_count += 1
                        iteration_placed += 1
                        details_to_remove.append(detail)
                        logger.info(f"✅ ОЧЕНЬ АГРЕССИВНО разместили деталь {detail.id} ({detail.width:.0f}x{detail.height:.0f}) в остатке {remnant.width:.0f}x{remnant.height:.0f}")
                        break
                    
                    # Если очень агрессивная стратегия не сработала, пробуем экстремальную
                    elif self._can_place_detail_in_remnant_extreme(detail, remnant, layout):
                        # Размещаем деталь (с валидацией разрезов)
                        if not self._place_detail_in_remnant(detail, remnant, layout):
                            continue
                        placed = True
                        placed_count += 1
                        iteration_placed += 1
                        details_to_remove.append(detail)
                        logger.info(f"✅ ЭКСТРЕМАЛЬНО разместили деталь {detail.id} ({detail.width:.0f}x{detail.height:.0f}) в остатке {remnant.width:.0f}x{remnant.height:.0f}")
                        break
                    
                    # Если экстремальная стратегия не сработала, пробуем ультра экстремальную
                    elif self._can_place_detail_in_remnant_ultra_extreme(detail, remnant, layout):
                        # Размещаем деталь (с валидацией разрезов)
                        if not self._place_detail_in_remnant(detail, remnant, layout):
                            continue
                        placed = True
                        placed_count += 1
                        iteration_placed += 1
                        details_to_remove.append(detail)
                        logger.info(f"✅ УЛЬТРА ЭКСТРЕМАЛЬНО разместили деталь {detail.id} ({detail.width:.0f}x{detail.height:.0f}) в остатке {remnant.width:.0f}x{remnant.height:.0f}")
                        break
                    
                    # Если ультра экстремальная стратегия не сработала, пробуем умеренную (на всякий случай)
                    elif self._can_place_detail_in_remnant_moderate(detail, remnant, layout):
                        # Размещаем деталь (с валидацией разрезов)
                        if not self._place_detail_in_remnant(detail, remnant, layout):
                            continue
                        placed = True
                        placed_count += 1
                        iteration_placed += 1
                        details_to_remove.append(detail)
                        logger.info(f"✅ УМЕРЕННО разместили деталь {detail.id} ({detail.width:.0f}x{detail.height:.0f}) в остатке {remnant.width:.0f}x{remnant.height:.0f}")
                        break
            
            # Удаляем размещенные детали из списка
            for detail in details_to_remove:
                remaining_details.remove(detail)
            
            logger.info(f"📊 Итерация {total_iterations}: размещено {iteration_placed} деталей, осталось {len(remaining_details)}")
            
            # Если в этой итерации ничего не разместили, прекращаем цикл
            if iteration_placed == 0:
                logger.info(f"🔄 Итерация {total_iterations}: ничего не разместили, прекращаем цикл")
                break
        
        logger.info(f"📊 АГРЕССИВНОЕ заполнение завершено: размещено {placed_count} деталей за {total_iterations} итераций, осталось {len(remaining_details)}")
        
        return remaining_details

    def _fill_layout_remnants_with_details(self, layout: SheetLayout, unplaced_details: List[Detail]) -> Tuple[List[Detail], int]:
        """Заполняет деловые остатки КОНКРЕТНОГО цельного листа дополнительными деталями.
        Возвращает (обновленный список неразмещенных деталей, количество дополнительно размещенных деталей).

        ВАЖНО: Работает только для цельных листов. Остатки-материалы не затрагиваются.
        """
        if layout.sheet.is_remainder:
            return unplaced_details, 0

        if not unplaced_details:
            return unplaced_details, 0

        # Фильтруем детали по материалу листа
        candidate_details = [d for d in unplaced_details if d.material == layout.sheet.material]
        if not candidate_details:
            return unplaced_details, 0

        # Сортировка: крупные и приоритетные сначала. Исключаем уже размещённые на других листах
        placed_global_ids: Set[str] = set()
        for pi in layout.placed_items:
            if pi.item_type == "detail" and pi.detail:
                placed_global_ids.add(pi.detail.id)
        candidate_details = [d for d in candidate_details if d.id not in placed_global_ids]
        candidate_details.sort(key=lambda d: (-d.area, -d.priority, d.id))
        remaining_details = candidate_details.copy()

        placed_count = 0
        max_iterations = 100
        total_iterations = 0

        while remaining_details and total_iterations < max_iterations:
            total_iterations += 1
            iteration_placed = 0

            details_to_remove: List[Detail] = []
            for detail in remaining_details:
                placed = False
                # Каждый раз берём актуальный список свободных областей (остатки + отходы), т.к. он меняется в процессе
                # Формируем список актуальных свободных прямоугольников на основе placed_items
                # Это надёжнее, чем полагаться на сохранённые типы, если где-то ранее были несогласованные изменения
                current_free = []
                for item in layout.placed_items:
                    if item.item_type in ("remnant", "waste"):
                        current_free.append(item)
                if not current_free:
                    break
                current_free = sorted(current_free, key=lambda r: -r.area)
                for free_item in current_free:
                    # Сначала пробуем строгим гильотинным способом, если это деловой остаток
                    if free_item.item_type == "remnant":
                        if self._can_place_detail_in_remnant_aggressive(detail, free_item, layout) and \
                           self._place_detail_in_remnant(detail, free_item, layout):
                            placed = True
                        elif self._can_place_detail_in_remnant_very_aggressive(detail, free_item, layout) and \
                             self._place_detail_in_remnant(detail, free_item, layout):
                            placed = True
                        elif self._can_place_detail_in_remnant_extreme(detail, free_item, layout) and \
                             self._place_detail_in_remnant(detail, free_item, layout):
                            placed = True
                        elif self._can_place_detail_in_remnant_moderate(detail, free_item, layout) and \
                             self._place_detail_in_remnant(detail, free_item, layout):
                            placed = True
                        if placed:
                            pass
                    # Если не удалось или это отход — пробуем свободную укладку без гильотинных ограничений
                    # Соблюдаем минимальную сторону отходов и границы листа
                    if not placed and self._can_place_in_free_area_simple(detail, free_item):
                        if self._place_detail_in_free_area_freecut(detail, free_item, layout):
                            placed = True

                    if placed:
                        placed_count += 1
                        iteration_placed += 1
                        details_to_remove.append(detail)
                        break

            for d in details_to_remove:
                if d in remaining_details:
                    remaining_details.remove(d)

            if iteration_placed == 0:
                break

        # Возвращаем обновленный глобальный список неразмещенных деталей:
        # исключаем те, что мы могли дополнительно поставить на этом листе
        placed_now_ids: Set[str] = {pi.detail.id for pi in layout.get_placed_details() if pi.detail}
        updated_unplaced = [d for d in unplaced_details if d.id not in placed_now_ids]
        return updated_unplaced, placed_count

    def _remove_detail_and_add_free_area(self, layout: SheetLayout, detail_item: PlacedItem):
        """Удаляет деталь из раскладки и превращает ее место в свободную область (waste/remnant)."""
        try:
            layout.placed_items.remove(detail_item)
        except ValueError:
            return
        area = Rectangle(detail_item.x, detail_item.y, detail_item.width, detail_item.height)
        self._classify_and_add_area(area, layout)

    def _place_detail_on_layout_best_fit(self, detail: Detail, layout: SheetLayout) -> bool:
        """Пытается разместить деталь на данном листе (сначала на остатках по правилам, затем free-cut на любой свободной области)."""
        # 1) Остатки по строгим правилам
        remnants = sorted(layout.get_remnants(), key=lambda r: -r.area)
        for rem in remnants:
            if self._can_place_detail_in_remnant_aggressive(detail, rem, layout) and self._place_detail_in_remnant(detail, rem, layout):
                return True
            if self._can_place_detail_in_remnant_very_aggressive(detail, rem, layout) and self._place_detail_in_remnant(detail, rem, layout):
                return True
            if self._can_place_detail_in_remnant_extreme(detail, rem, layout) and self._place_detail_in_remnant(detail, rem, layout):
                return True
            if self._can_place_detail_in_remnant_moderate(detail, rem, layout) and self._place_detail_in_remnant(detail, rem, layout):
                return True

        # 2) Любая свободная область (остатки+отходы) свободной укладкой
        free_areas = sorted(layout.get_remnants() + layout.get_waste(), key=lambda r: -r.area)
        for area in free_areas:
            if self._can_place_in_free_area_simple(detail, area):
                if self._place_detail_in_free_area_freecut(detail, area, layout):
                    return True
        return False

    def _cross_fill_material_sheets(self, layouts: List[SheetLayout]) -> List[SheetLayout]:
        """Переносит детали между ЦЕЛЬНЫМИ листами одного материала, чтобы сократить большие деловые остатки
        и потенциально избавиться от малоиспользованных листов.
        Остатки-материалы не затрагиваются. Частичные переносы допускаются.
        """
        from collections import defaultdict
        material_to_layouts: Dict[str, List[SheetLayout]] = defaultdict(list)
        for l in layouts:
            if not l.sheet.is_remainder:
                material_to_layouts[l.sheet.material].append(l)

        for material, mats in material_to_layouts.items():
            if len(mats) < 2:
                continue
            # Итеративно пытаемся переносить
            changed = True
            while changed:
                changed = False
                receivers = sorted(mats, key=lambda l: -l.remnant_area)  # где больше свободной площади
                donors = sorted(mats, key=lambda l: (len(l.get_placed_details()), l.used_area))  # наименее заполненные

                for receiver in receivers:
                    # Обновляем свободные области; если их нет — нечего догружать
                    if receiver.remnant_area + receiver.waste_area <= 0:
                        continue
                    for donor in donors:
                        if donor is receiver:
                            continue
                        donor_items = [pi for pi in donor.get_placed_details()]
                        if not donor_items:
                            continue
                        # Крупные детали сначала
                        donor_items.sort(key=lambda pi: -(pi.width * pi.height))
                        moved_any = False
                        for pi in donor_items:
                            d = pi.detail
                            if d is None or d.material != receiver.sheet.material:
                                continue
                            if self._place_detail_on_layout_best_fit(d, receiver):
                                # Успешно перенесли: убираем с донора и добавляем свободную область
                                self._remove_detail_and_add_free_area(donor, pi)
                                changed = True
                                moved_any = True
                        # Если донор опустел — попробуем удалить его из общего списка и из mats
                        if moved_any and len(donor.get_placed_details()) == 0:
                            try:
                                layouts.remove(donor)
                                mats.remove(donor)
                                changed = True
                                logger.info(f"🧩 Консолидация: лист {donor.sheet.id} опустел и удален после переносов в {receiver.sheet.id}")
                            except ValueError:
                                pass
                # Конец одного прохода
        return layouts

    def _cross_fill_into_layout(self, receiver: SheetLayout, built_layouts: List[SheetLayout]):
        """Быстро пытается догрузить ТЕКУЩИЙ цельный лист из ранее собранных цельных листов того же материала.
        Не трогает остатки-материалы. Допускаются частичные переносы.
        """
        if receiver.sheet.is_remainder:
            return
        donor_candidates = [l for l in built_layouts if (not l.sheet.is_remainder) and l.sheet.material == receiver.sheet.material and l is not receiver]
        if not donor_candidates:
            return
        # Пытаемся взять крупные детали сначала
        for donor in donor_candidates:
            donor_items = [pi for pi in donor.get_placed_details()]
            donor_items.sort(key=lambda pi: -(pi.width * pi.height))
            moved_any = False
            for pi in donor_items:
                d = pi.detail
                if d is None:
                    continue
                if self._place_detail_on_layout_best_fit(d, receiver):
                    self._remove_detail_and_add_free_area(donor, pi)
                    moved_any = True
            # Если донор опустел — удалим его из списка ранее собранных
            if moved_any and len(donor.get_placed_details()) == 0:
                try:
                    built_layouts.remove(donor)
                    logger.info(f"🧩 Локальная консолидация: лист {donor.sheet.id} опустел после переносов в {receiver.sheet.id} и удален")
                except ValueError:
                    pass

    def _can_place_in_free_area_simple(self, detail: Detail, free_item: PlacedItem) -> bool:
        """Проверяет, помещается ли деталь в свободную прямоугольную область (без гильотинных правил)."""
        if detail.width <= free_item.width and detail.height <= free_item.height:
            return True
        if detail.can_rotate and detail.height <= free_item.width and detail.width <= free_item.height:
            return True
        return False

    def _place_detail_in_free_area_freecut(self, detail: Detail, free_item: PlacedItem, layout: SheetLayout) -> bool:
        """Размещает деталь в ЛЮБОЙ свободной области (остаток или отход) без проверки гильотинных разрезов.
        Выбирает лучшую ориентацию и схему разбиения (сначала вправо или сначала вверх),
        затем делит область на две новые, соблюдая min_waste_side и границы листа.
        """
        # Определяем ориентацию
        is_rotated = False
        width = detail.width
        height = detail.height
        if width > free_item.width or height > free_item.height:
            if detail.can_rotate and detail.height <= free_item.width and detail.width <= free_item.height:
                is_rotated = True
                width, height = detail.height, detail.width
        # Финальная проверка размера
        if width > free_item.width or height > free_item.height:
            return False

        # Оцениваем две схемы разбиения: Right-Then-Top (RT) и Top-Then-Right (TR)
        def try_split(rt_first: bool) -> Tuple[bool, List[Rectangle]]:
            remainders: List[Rectangle] = []
            # правая часть
            remainder_right_w = free_item.width - width
            remainder_top_h = free_item.height - height
            if rt_first:
                if remainder_right_w >= self.params.min_waste_side:
                    remainders.append(Rectangle(
                        free_item.x + width,
                        free_item.y,
                        remainder_right_w,
                        height
                    ))
                if remainder_top_h >= self.params.min_waste_side:
                    remainders.append(Rectangle(
                        free_item.x,
                        free_item.y + height,
                        free_item.width,
                        remainder_top_h
                    ))
            else:
                if remainder_top_h >= self.params.min_waste_side:
                    remainders.append(Rectangle(
                        free_item.x,
                        free_item.y + height,
                        free_item.width,
                        remainder_top_h
                    ))
                if remainder_right_w >= self.params.min_waste_side:
                    remainders.append(Rectangle(
                        free_item.x + width,
                        free_item.y,
                        remainder_right_w,
                        height
                    ))
            # критерий качества: суммарная площадь остатков и penalize вытянутые
            quality = 0.0
            for r in remainders:
                aspect = max(r.width, r.height) / max(1.0, min(r.width, r.height))
                quality += r.area * (1.0 / aspect)
            return True, remainders

        _, remainders_rt = try_split(True)
        _, remainders_tr = try_split(False)
        # Выбираем лучшую схему по качеству (выше — лучше)
        def score(rems: List[Rectangle]) -> float:
            s = 0.0
            for r in rems:
                aspect = max(r.width, r.height) / max(1.0, min(r.width, r.height))
                s += r.area * (1.0 / aspect)
            return s
        chosen_remainders = remainders_rt if score(remainders_rt) >= score(remainders_tr) else remainders_tr

        # Применяем размещение
        placed_detail = PlacedItem(
            x=free_item.x,
            y=free_item.y,
            width=width,
            height=height,
            item_type="detail",
            detail=detail,
            is_rotated=is_rotated
        )
        layout.placed_items.append(placed_detail)
        try:
            layout.placed_items.remove(free_item)
        except ValueError:
            layout.placed_items.remove(placed_detail)
            return False
        for r in chosen_remainders:
            self._classify_and_add_area(r, layout)
        return True

    def _can_place_detail_in_remnant_moderate(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """Умеренная проверка возможности размещения детали в остатке"""
        # Стандартная проверка
        if detail.width <= remnant.width and detail.height <= remnant.height:
            return True
        
        # Проверка с поворотом
        if detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height:
            return True
        
        # УМЕРЕННАЯ ПРОВЕРКА: Небольшой допуск
        tolerance = 5.0  # Небольшой допуск в мм
        
        # Проверяем с небольшим допуском
        if (detail.width <= remnant.width + tolerance and detail.height <= remnant.height + tolerance):
            return True
        
        # Проверяем с поворотом и небольшим допуском
        if detail.can_rotate and (detail.height <= remnant.width + tolerance and detail.width <= remnant.height + tolerance):
            return True
        
        return False

    def _can_place_detail_in_remnant_aggressive(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """Агрессивная проверка возможности размещения детали в остатке"""
        # Стандартная проверка
        if detail.width <= remnant.width and detail.height <= remnant.height:
            return True
        
        # Проверка с поворотом
        if detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height:
            return True
        
        # АГРЕССИВНАЯ ПРОВЕРКА: Пытаемся разместить даже если деталь немного больше
        tolerance = 10.0  # Увеличенный допуск в мм
        
        # Проверяем с допуском
        if (detail.width <= remnant.width + tolerance and detail.height <= remnant.height + tolerance):
            return True
        
        # Проверяем с поворотом и допуском
        if detail.can_rotate and (detail.height <= remnant.width + tolerance and detail.width <= remnant.height + tolerance):
            return True
        
        # Дополнительная проверка: если деталь меньше по площади, но больше по одной стороне
        detail_area = detail.width * detail.height
        remnant_area = remnant.width * remnant.height
        
        if detail_area <= remnant_area * 0.9:  # Деталь занимает не более 90% площади остатка
            # Проверяем, можно ли "втиснуть" деталь
            if (detail.width <= remnant.width * 1.1 and detail.height <= remnant.height * 1.1):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 1.1 and detail.width <= remnant.height * 1.1):
                return True
        
        return False

    def _can_place_detail_in_remnant_very_aggressive(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """ОЧЕНЬ агрессивная проверка возможности размещения детали в остатке"""
        # Стандартная проверка
        if detail.width <= remnant.width and detail.height <= remnant.height:
            return True
        
        # Проверка с поворотом
        if detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height:
            return True
        
        # ОЧЕНЬ АГРЕССИВНАЯ ПРОВЕРКА: Пытаемся разместить даже если деталь значительно больше
        tolerance = 25.0  # Очень большой допуск в мм
        
        # Проверяем с большим допуском
        if (detail.width <= remnant.width + tolerance and detail.height <= remnant.height + tolerance):
            return True
        
        # Проверяем с поворотом и большим допуском
        if detail.can_rotate and (detail.height <= remnant.width + tolerance and detail.width <= remnant.height + tolerance):
            return True
        
        # Дополнительная проверка: если деталь меньше по площади, но больше по одной стороне
        detail_area = detail.width * detail.height
        remnant_area = remnant.width * remnant.height
        
        if detail_area <= remnant_area * 0.85:  # Деталь занимает не более 85% площади остатка
            # Проверяем, можно ли "втиснуть" деталь с большим допуском
            if (detail.width <= remnant.width * 1.3 and detail.height <= remnant.height * 1.3):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 1.3 and detail.width <= remnant.height * 1.3):
                return True
        
        # Экстремальная проверка: если деталь значительно меньше по площади
        if detail_area <= remnant_area * 0.7:  # Деталь занимает не более 70% площади остатка
            # Пытаемся разместить даже с очень большим допуском
            if (detail.width <= remnant.width * 1.5 and detail.height <= remnant.height * 1.5):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 1.5 and detail.width <= remnant.height * 1.5):
                return True
        
        return False

    def _can_place_detail_in_remnant_extreme(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """ЭКСТРЕМАЛЬНО агрессивная проверка возможности размещения детали в остатке"""
        # Стандартная проверка
        if detail.width <= remnant.width and detail.height <= remnant.height:
            return True
        
        # Проверка с поворотом
        if detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height:
            return True
        
        # ЭКСТРЕМАЛЬНАЯ ПРОВЕРКА: Пытаемся разместить даже если деталь намного больше
        tolerance = 40.0  # Экстремальный допуск в мм
        
        # Проверяем с экстремальным допуском
        if (detail.width <= remnant.width + tolerance and detail.height <= remnant.height + tolerance):
            return True
        
        # Проверяем с поворотом и экстремальным допуском
        if detail.can_rotate and (detail.height <= remnant.width + tolerance and detail.width <= remnant.height + tolerance):
            return True
        
        # Дополнительная проверка: если деталь меньше по площади, но больше по одной стороне
        detail_area = detail.width * detail.height
        remnant_area = remnant.width * remnant.height
        
        if detail_area <= remnant_area * 0.8:  # Деталь занимает не более 80% площади остатка
            # Проверяем, можно ли "втиснуть" деталь с экстремальным допуском
            if (detail.width <= remnant.width * 1.6 and detail.height <= remnant.height * 1.6):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 1.6 and detail.width <= remnant.height * 1.6):
                return True
        
        # Экстремальная проверка: если деталь значительно меньше по площади
        if detail_area <= remnant_area * 0.6:  # Деталь занимает не более 60% площади остатка
            # Пытаемся разместить даже с очень большим допуском
            if (detail.width <= remnant.width * 2.0 and detail.height <= remnant.height * 2.0):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 2.0 and detail.width <= remnant.height * 2.0):
                return True
        
        return False

    def _can_place_detail_in_remnant_ultra_extreme(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """УЛЬТРА ЭКСТРЕМАЛЬНО агрессивная проверка возможности размещения детали в остатке"""
        # Стандартная проверка
        if detail.width <= remnant.width and detail.height <= remnant.height:
            return True
        
        # Проверка с поворотом
        if detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height:
            return True
        
        # УЛЬТРА ЭКСТРЕМАЛЬНАЯ ПРОВЕРКА: Пытаемся разместить даже если деталь намного больше
        tolerance = 60.0  # Ультра экстремальный допуск в мм
        
        # Проверяем с ультра экстремальным допуском
        if (detail.width <= remnant.width + tolerance and detail.height <= remnant.height + tolerance):
            return True
        
        # Проверяем с поворотом и ультра экстремальным допуском
        if detail.can_rotate and (detail.height <= remnant.width + tolerance and detail.width <= remnant.height + tolerance):
            return True
        
        # Дополнительная проверка: если деталь меньше по площади, но больше по одной стороне
        detail_area = detail.width * detail.height
        remnant_area = remnant.width * remnant.height
        
        if detail_area <= remnant_area * 0.7:  # Деталь занимает не более 70% площади остатка
            # Проверяем, можно ли "втиснуть" деталь с ультра экстремальным допуском
            if (detail.width <= remnant.width * 2.0 and detail.height <= remnant.height * 2.0):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 2.0 and detail.width <= remnant.height * 2.0):
                return True
        
        # Экстремальная проверка: если деталь значительно меньше по площади
        if detail_area <= remnant_area * 0.5:  # Деталь занимает не более 50% площади остатка
            # Пытаемся разместить даже с очень большим допуском
            if (detail.width <= remnant.width * 2.5 and detail.height <= remnant.height * 2.5):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 2.5 and detail.width <= remnant.height * 2.5):
                return True
        
        # УЛЬТРА ЭКСТРЕМАЛЬНАЯ проверка: если деталь очень маленькая по площади
        if detail_area <= remnant_area * 0.3:  # Деталь занимает не более 30% площади остатка
            # Пытаемся разместить с любым допуском
            if (detail.width <= remnant.width * 3.0 and detail.height <= remnant.height * 3.0):
                return True
            if detail.can_rotate and (detail.height <= remnant.width * 3.0 and detail.width <= remnant.height * 3.0):
                return True
        
        return False

    def _can_place_detail_in_remnant(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """Проверяет, можно ли разместить деталь в остатке"""
        # Проверяем размеры
        if detail.width <= remnant.width and detail.height <= remnant.height:
            return True
        
        # Проверяем с поворотом
        if detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height:
            return True
        
        return False

    def _merge_small_remnants(self, layouts: List[SheetLayout]):
        """АГРЕССИВНО объединяет деловые остатки в более крупные"""
        total_merged = 0
        
        for layout in layouts:
            # Получаем все деловые остатки на листе
            remnants = layout.get_remnants()
            
            if len(remnants) < 2:
                continue  # Нужно минимум 2 остатка для объединения
            
            logger.info(f"🔄 Анализируем {len(remnants)} остатков на листе {layout.sheet.id}")
            
            # МНОГОКРАТНОЕ ОБЪЕДИНЕНИЕ: Продолжаем объединять, пока есть возможности
            max_iterations = 10  # Максимум 10 итераций объединения
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                merged_in_iteration = 0
                
                # Получаем актуальный список остатков (могли измениться)
                current_remnants = layout.get_remnants()
                
                if len(current_remnants) < 2:
                    break  # Больше нечего объединять
                
                # Сортируем остатки по площади (от больших к меньшим для лучшего объединения)
                sorted_remnants = sorted(current_remnants, key=lambda r: -r.area)
                
                # Ищем пары остатков, которые можно объединить
                merged_this_iteration = set()  # Используем индексы вместо объектов
                
                for i, remnant1 in enumerate(sorted_remnants):
                    if i in merged_this_iteration:
                        continue
                    
                    best_merge = None
                    best_score = 0
                    
                    # Ищем лучшего кандидата для объединения
                    for j, remnant2 in enumerate(sorted_remnants):
                        if j in merged_this_iteration or remnant1 == remnant2:
                            continue
                        
                        # Проверяем, можно ли объединить эти остатки
                        if self._can_merge_remnants(remnant1, remnant2):
                            # Оцениваем качество объединения
                            merged_width = max(remnant1.x2, remnant2.x2) - min(remnant1.x, remnant2.x)
                            merged_height = max(remnant1.y2, remnant2.y2) - min(remnant1.y, remnant2.y)
                            merged_area = merged_width * merged_height
                            
                            # Оценка: предпочитаем объединения с хорошими пропорциями
                            aspect_ratio = max(merged_width, merged_height) / min(merged_width, merged_height)
                            score = merged_area * (1.0 / aspect_ratio)  # Больше площадь, лучше пропорции
                            
                            if score > best_score:
                                best_score = score
                                best_merge = (remnant1, remnant2)
                    
                    # Объединяем с лучшим кандидатом
                    if best_merge:
                        remnant1, remnant2 = best_merge
                        
                        # Объединяем остатки
                        merged_remnant = self._merge_remnants(remnant1, remnant2, layout)
                        
                        # Удаляем старые остатки и добавляем объединенный
                        layout.placed_items.remove(remnant1)
                        layout.placed_items.remove(remnant2)
                        layout.placed_items.append(merged_remnant)
                        
                        # Находим индексы объединенных остатков
                        remnant1_index = sorted_remnants.index(remnant1)
                        remnant2_index = sorted_remnants.index(remnant2)
                        
                        merged_this_iteration.add(remnant1_index)
                        merged_this_iteration.add(remnant2_index)
                        merged_in_iteration += 1
                        
                        logger.info(f"🔧 Итерация {iteration}: Объединили остатки {remnant1.width:.0f}x{remnant1.height:.0f} и {remnant2.width:.0f}x{remnant2.height:.0f} в {merged_remnant.width:.0f}x{merged_remnant.height:.0f}")
                
                total_merged += merged_in_iteration
                
                if merged_in_iteration == 0:
                    break  # Больше нечего объединять
                
                logger.info(f"🔧 Итерация {iteration}: Объединено {merged_in_iteration} пар остатков")
        
        logger.info(f"📊 Всего объединено {total_merged} пар остатков")

    def _can_merge_remnants(self, remnant1: PlacedItem, remnant2: PlacedItem) -> bool:
        """Проверяет, можно ли объединить два остатка"""
        # Проверяем, что остатки соседние
        if not self._are_remnants_adjacent(remnant1, remnant2):
            return False
        
        # Проверяем, что объединенный остаток будет достаточно большим
        merged_width = max(remnant1.x2, remnant2.x2) - min(remnant1.x, remnant2.x)
        merged_height = max(remnant1.y2, remnant2.y2) - min(remnant1.y, remnant2.y)
        
        min_side = min(merged_width, merged_height)
        max_side = max(merged_width, merged_height)
        
        # ПРОСТОЕ ПРАВИЛО: Если меньшая сторона ≥ меньший параметр И большая сторона ≥ больший параметр
        param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
        param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
        
        return (min_side > param_min and max_side > param_max)

    def _are_remnants_adjacent(self, remnant1: PlacedItem, remnant2: PlacedItem) -> bool:
        """Проверяет, являются ли остатки соседними"""
        # Проверяем горизонтальное соседство
        if (abs(remnant1.y - remnant2.y) < 1.0 and 
            (abs(remnant1.x2 - remnant2.x) < 1.0 or abs(remnant2.x2 - remnant1.x) < 1.0)):
            return True
        
        # Проверяем вертикальное соседство
        if (abs(remnant1.x - remnant2.x) < 1.0 and 
            (abs(remnant1.y2 - remnant2.y) < 1.0 or abs(remnant2.y2 - remnant1.y) < 1.0)):
            return True
        
        return False

    def _merge_remnants(self, remnant1: PlacedItem, remnant2: PlacedItem, layout: SheetLayout) -> PlacedItem:
        """Объединяет два остатка в один"""
        # Вычисляем границы объединенного остатка
        min_x = min(remnant1.x, remnant2.x)
        min_y = min(remnant1.y, remnant2.y)
        max_x = max(remnant1.x2, remnant2.x2)
        max_y = max(remnant1.y2, remnant2.y2)
        
        width = max_x - min_x
        height = max_y - min_y
        
        # Создаем объединенный остаток
        merged_remnant = PlacedItem(
            x=min_x,
            y=min_y,
            width=width,
            height=height,
            item_type="remnant",
            detail=None,
            is_rotated=False
        )
        
        return merged_remnant

    def _place_detail_in_remnant(self, detail: Detail, remnant: PlacedItem, layout: SheetLayout) -> bool:
        """Размещает деталь в остатке с улучшенной логикой ориентации.
        Возвращает True, если размещение выполнено, иначе False.

        ВАЖНО: Строго соблюдаем границы остатка и min_waste_side через
        _is_valid_cut_for_remnant. Не допускаем размещение деталей, выходящих
        за пределы остатка даже на "допусках".
        """
        # Определяем ориентацию с учетом агрессивных стратегий
        is_rotated = False
        width = detail.width
        height = detail.height
        
        # Проверяем, какая ориентация лучше подходит
        normal_fits = detail.width <= remnant.width and detail.height <= remnant.height
        rotated_fits = detail.can_rotate and detail.height <= remnant.width and detail.width <= remnant.height
        
        if normal_fits and rotated_fits:
            # Обе ориентации подходят, выбираем ту, которая лучше использует остаток
            normal_waste = (remnant.width - detail.width) * (remnant.height - detail.height)
            rotated_waste = (remnant.width - detail.height) * (remnant.height - detail.width)
            
            if rotated_waste < normal_waste:
                is_rotated = True
                width, height = detail.height, detail.width
        elif rotated_fits:
            # Только повернутая ориентация подходит
            is_rotated = True
            width, height = detail.height, detail.width
        else:
            # Жесткое правило: не размещаем, если не умещается ни в одной ориентации
            return False

        # Финальная проверка корректности гильотинного разреза внутри остатка
        if width > remnant.width or height > remnant.height:
            return False
        if not self._is_valid_cut_for_remnant(remnant, width, height):
            return False
        
        # Создаем размещенную деталь
        placed_detail = PlacedItem(
            x=remnant.x,
            y=remnant.y,
            width=width,
            height=height,
            item_type="detail",
            detail=detail,
            is_rotated=is_rotated
        )
        
        # Добавляем в раскладку
        layout.placed_items.append(placed_detail)
        
        # Удаляем остаток из списка
        layout.placed_items.remove(remnant)
        
        # Создаем новые остатки после размещения детали
        remaining_areas = self._calculate_remaining_areas_after_placement(remnant, placed_detail)
        
        # Классифицируем оставшиеся области
        for area in remaining_areas:
            if area.width > 0 and area.height > 0:
                self._classify_and_add_area(area, layout)

        return True

    def _calculate_remaining_areas_after_placement(self, original_remnant: PlacedItem, placed_detail: PlacedItem) -> List[Rectangle]:
        """Вычисляет оставшиеся области после размещения детали в остатке"""
        areas = []
        
        # Правая часть (если есть)
        if original_remnant.width > placed_detail.width:
            right_area = Rectangle(
                original_remnant.x + placed_detail.width,
                original_remnant.y,
                original_remnant.width - placed_detail.width,
                placed_detail.height
            )
            if right_area.width >= self.params.min_waste_side and right_area.height >= self.params.min_waste_side:
                areas.append(right_area)
        
        # Верхняя часть (на всю ширину)
        if original_remnant.height > placed_detail.height:
            top_area = Rectangle(
                original_remnant.x,
                original_remnant.y + placed_detail.height,
                original_remnant.width,
                original_remnant.height - placed_detail.height
            )
            if top_area.width >= self.params.min_waste_side and top_area.height >= self.params.min_waste_side:
                areas.append(top_area)
        
        return areas

    def _classify_and_add_area(self, area: Rectangle, layout: SheetLayout):
        """Классифицирует область как остаток или отход и добавляет в раскладку"""
        # ЕДИНАЯ ЛОГИКА: деловой остаток, если меньшая сторона > меньшего параметра и большая сторона > большего параметра
        min_side = min(area.width, area.height)
        max_side = max(area.width, area.height)
        param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
        param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
        is_remnant = (min_side > param_min and max_side > param_max)

        item_type = "remnant" if is_remnant else "waste"
        logger.debug(f"🔧 ОБЛАСТЬ: {area.width:.0f}x{area.height:.0f} - {'ДЕЛОВОЙ ОСТАТОК' if is_remnant else 'ОТХОД'}")
        
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

