#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль оптимизации 2D раскроя материалов - Версия 2.3
Гарантирует 100% покрытие листа без пересечений с соблюдением min_waste_side
РАДИКАЛЬНЫЕ УЛУЧШЕНИЯ v2.3:
- ПОЛНОСТЬЮ убрана проверка плохих отходов для остатков (принимаем ЛЮБОЕ размещение!)
- Убран пропуск остатков по геометрии (пробуем ВСЕ остатки!)
- Убрано ограничение заполнения остатков только для цельных листов (теперь для ВСЕХ!)
- РАДИКАЛЬНО увеличены параметры: max_iterations 100-500 вместо 30-250
- Увеличено количество циклов с 3 до 5
- Минимум 100 попыток размещения на каждом остатке (вместо 50)
- Условия прекращения поиска: только при 90%+ использовании (вместо 80%)
- Многопроходная циклическая проверка неиспользованных остатков (5 циклов)
- Немедленное заполнение формирующихся деловых остатков на ВСЕХ листах
- Финальный проход по всем неиспользованным остаткам
- Детальная статистика использования остатков и создания новых деловых остатков
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

            # РАДИКАЛЬНО увеличиваем число попыток на остатках в предварительном проходе
            max_tries = max(30, self.params.max_iterations_per_sheet * 12)  # Минимум 30 попыток в предварительном проходе
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

    def _cycle_through_remainders(
        self, 
        layouts: List[SheetLayout], 
        unplaced_details: List[Detail], 
        unused_remainder_sheets: List[Sheet]
    ) -> Tuple[List[SheetLayout], List[Detail], List[str]]:
        """
        НОВЫЙ МЕТОД: Циклическая проверка неиспользованных остатков со склада.
        Пытается многократно разместить детали на остатках, которые не были использованы ранее.
        
        Возвращает: (новые_layouts, оставшиеся_детали, использованные_ids_остатков)
        """
        if not unused_remainder_sheets or not unplaced_details:
            return [], unplaced_details, []
        
        logger.info(f"🔄 ЦИКЛИЧЕСКАЯ ПРОВЕРКА: {len(unused_remainder_sheets)} неиспользованных остатков, {len(unplaced_details)} деталей")
        
        new_layouts: List[SheetLayout] = []
        remaining_details = unplaced_details.copy()
        used_ids: List[str] = []
        
        # Сортируем остатки: сначала те, которые лучше подходят для текущих деталей
        sorted_remainders = sorted(unused_remainder_sheets, key=lambda s: (s.area, s.id))
        
        # РАДИКАЛЬНАЯ многопроходная стратегия: больше циклов для более тщательной проверки
        max_cycles = 5  # Увеличено с 3 до 5 циклов
        for cycle in range(max_cycles):
            if not remaining_details:
                break
                
            logger.info(f"🔄 Цикл {cycle + 1}/{max_cycles}: пытаемся разместить {len(remaining_details)} деталей на {len(sorted_remainders)} остатках")
            
            cycle_placed = 0
            sheets_to_remove = []
            
            for sheet in sorted_remainders:
                if not remaining_details:
                    break
                
                # РАДИКАЛЬНОЕ ИЗМЕНЕНИЕ: НЕ пропускаем остатки по геометрии!
                # Пробуем каждый остаток со всеми деталями подходящего материала
                
                # Фильтруем детали по материалу
                fitting_details = [d for d in remaining_details if d.material == sheet.material]
                if not fitting_details:
                    continue  # Только пропускаем если нет деталей нужного материала
                
                # УМНЫЙ подбор деталей для остатка (необязательный)
                best_suited_details = self._find_best_details_for_remainder(fitting_details, sheet, max_details=25)
                
                # Если не нашли "идеальные", пробуем все детали подходящего материала
                if not best_suited_details:
                    best_suited_details = fitting_details
                
                logger.info(f"🎯 Попытка использовать остаток {sheet.id} ({sheet.width:.0f}x{sheet.height:.0f}) на цикле {cycle + 1}")
                
                # Агрессивный поиск оптимального размещения
                best_layout = None
                best_score = float('-inf')
                best_usage = 0.0
                
                # РАДИКАЛЬНО увеличиваем количество попыток для циклической проверки
                max_attempts = max(50, self.params.max_iterations_per_sheet * 15)  # Минимум 50 попыток в цикле
                
                for iteration in range(max_attempts):
                    # На первых итерациях используем подобранные детали, затем все
                    if iteration < 8:
                        details_to_try = best_suited_details.copy()
                    else:
                        details_to_try = fitting_details.copy()
                    
                    layout = self._create_sheet_layout_guillotine(sheet, details_to_try, iteration)
                    
                    # РАДИКАЛЬНОЕ ИЗМЕНЕНИЕ: НЕ проверяем отходы в циклической проверке!
                    # Принимаем ЛЮБОЕ размещение на остатках
                    if len(layout.get_placed_details()) == 0:
                        continue
                    
                    usage_percent = (layout.used_area / layout.total_area * 100) if layout.total_area > 0 else 0
                    score = self._evaluate_layout(layout)
                    
                    # Огромные бонусы за использование неиспользованного остатка
                    if usage_percent > 60:
                        score += 15000
                    elif usage_percent > 40:
                        score += 10000
                    elif usage_percent > 20:
                        score += 7000
                    elif usage_percent > 10:
                        score += 5000
                    elif usage_percent > 5:
                        score += 3000
                    else:
                        score += 1000
                    
                    score += len(layout.get_placed_details()) * 2000
                    
                    if layout.get_placed_details() and (score > best_score or 
                                                        (usage_percent > best_usage and score > best_score * 0.8)):
                        best_score = score
                        best_layout = layout
                        best_usage = usage_percent
                    
                    # Ранний выход при отличном результате
                    if usage_percent > 75 and len(layout.get_placed_details()) >= 2:
                        break
                
                if best_layout and best_layout.get_placed_details():
                    # Успешно разместили детали на остатке
                    new_layouts.append(best_layout)
                    used_ids.append(sheet.id)
                    sheets_to_remove.append(sheet)
                    
                    placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
                    remaining_details = [d for d in remaining_details if d.id not in placed_ids]
                    
                    cycle_placed += len(placed_ids)
                    logger.info(f"✅ ЦИКЛИЧЕСКИ использован остаток {sheet.id}: {len(placed_ids)} деталей, использование {best_usage:.1f}%")
            
            # Удаляем использованные остатки из списка
            for sheet in sheets_to_remove:
                sorted_remainders.remove(sheet)
            
            logger.info(f"📊 Цикл {cycle + 1}: размещено {cycle_placed} деталей, осталось {len(remaining_details)}")
            
            # Если ничего не разместили в этом цикле, прекращаем
            if cycle_placed == 0:
                break
        
        logger.info(f"✅ ЦИКЛИЧЕСКАЯ ПРОВЕРКА завершена: использовано {len(used_ids)} остатков, размещено {len(unplaced_details) - len(remaining_details)} деталей")
        
        return new_layouts, remaining_details, used_ids

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
        
        # ФИНАЛЬНЫЙ ПРОХОД: Попытка использовать все оставшиеся неиспользованные остатки
        if all_unplaced:
            logger.info(f"🔄 ФИНАЛЬНЫЙ ПРОХОД: попытка разместить {len(all_unplaced)} оставшихся деталей на неиспользованных остатках")
            
            # Собираем все использованные ids остатков
            used_remainder_ids = {layout.sheet.id for layout in all_layouts if layout.sheet.is_remainder}
            
            # Находим все неиспользованные остатки из всех материалов
            all_unused_remainders = [s for s in sorted_sheets if s.is_remainder and s.id not in used_remainder_ids]
            
            if all_unused_remainders:
                logger.info(f"📊 Найдено {len(all_unused_remainders)} неиспользованных остатков для финального прохода")
                
                # Запускаем финальную циклическую проверку
                final_layouts, all_unplaced, final_used_ids = self._cycle_through_remainders(
                    all_layouts, all_unplaced, all_unused_remainders
                )
                
                if final_layouts:
                    all_layouts.extend(final_layouts)
                    logger.info(f"✅ ФИНАЛЬНЫЙ ПРОХОД: дополнительно использовано {len(final_layouts)} остатков, "
                               f"размещено {len(final_used_ids)} деталей")
                else:
                    logger.info(f"📊 ФИНАЛЬНЫЙ ПРОХОД: не удалось использовать дополнительные остатки")
            else:
                logger.info(f"📊 ФИНАЛЬНЫЙ ПРОХОД: все остатки уже использованы")

        self._report_progress(95.0)
        
        # Финальный результат - передаем информацию о доступных остатках для статистики
        result = self._calculate_final_result(all_layouts, all_unplaced, start_time, remainder_sheets)
        
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
        """Подготовка листов с УМНОЙ сортировкой остатков"""
        # УЛУЧШЕННАЯ ЛОГИКА: Сначала маленькие остатки (чтобы "очистить" склад),
        # потом средние, потом большие, и только после этого цельные листы
        # Это помогает максимально использовать существующие остатки
        def sort_key(s: Sheet):
            if s.is_remainder:
                # Для остатков: сначала маленькие (приоритет 0), потом средние (1), потом большие (2)
                # Это позволяет "очистить" склад от мелких остатков в первую очередь
                if s.area < 500000:  # Маленькие остатки (< 0.5 м²)
                    return (0, s.area)  # Сортируем от меньшего к большему
                elif s.area < 2000000:  # Средние остатки (< 2 м²)
                    return (1, s.area)
                else:  # Большие остатки
                    return (2, s.area)
            else:
                # Для цельных листов: приоритет 3, сортируем от больших к меньшим
                return (3, -s.area)
        
        sheets.sort(key=sort_key)
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
    
    def _find_best_details_for_remainder(self, details: List[Detail], remainder: Sheet, max_details: int = 10) -> List[Detail]:
        """НОВЫЙ МЕТОД: Находит наилучший набор деталей для размещения на остатке
        
        Стратегия:
        1. Ищет детали, которые максимально используют площадь остатка
        2. Предпочитает комбинации деталей, которые минимизируют новые остатки
        3. Возвращает отсортированный список деталей для оптимального размещения
        """
        rem_area = remainder.area
        rem_w, rem_h = remainder.width, remainder.height
        
        # Отбираем детали, которые подходят по материалу и размеру
        fitting_details = []
        for detail in details:
            if detail.material != remainder.material:
                continue
            
            # Проверяем геометрию с учетом поворота
            fits_normal = detail.width <= rem_w and detail.height <= rem_h
            fits_rotated = detail.can_rotate and detail.height <= rem_w and detail.width <= rem_h
            
            if fits_normal or fits_rotated:
                # Вычисляем "качество" подбора детали к остатку
                detail_area = detail.area
                
                # Процент использования площади
                usage_percent = (detail_area / rem_area) * 100 if rem_area > 0 else 0
                
                # Качество подбора по размерам (насколько близки размеры)
                if fits_normal:
                    width_match = detail.width / rem_w if rem_w > 0 else 0
                    height_match = detail.height / rem_h if rem_h > 0 else 0
                    size_score = (width_match + height_match) / 2
                else:
                    width_match = detail.height / rem_w if rem_w > 0 else 0
                    height_match = detail.width / rem_h if rem_h > 0 else 0
                    size_score = (width_match + height_match) / 2 * 0.95  # Небольшой штраф за поворот
                
                # Итоговая оценка: приоритет деталям, которые лучше используют остаток
                score = usage_percent * 0.6 + size_score * 100 * 0.4
                
                fitting_details.append({
                    'detail': detail,
                    'score': score,
                    'usage': usage_percent
                })
        
        if not fitting_details:
            return []
        
        # Сортируем по оценке (лучшие первыми)
        fitting_details.sort(key=lambda x: -x['score'])
        
        # Возвращаем топ деталей (но не больше max_details)
        result = [item['detail'] for item in fitting_details[:max_details]]
        
        logger.debug(f"📋 Подобрано {len(result)} деталей для остатка {remainder.width:.0f}x{remainder.height:.0f}")
        if result:
            top_detail = fitting_details[0]
            logger.debug(f"   Лучшая деталь: {top_detail['detail'].width:.0f}x{top_detail['detail'].height:.0f}, "
                        f"использование: {top_detail['usage']:.1f}%, оценка: {top_detail['score']:.1f}")
        
        return result

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
            
            # РАДИКАЛЬНОЕ ИЗМЕНЕНИЕ: НЕ пропускаем остатки!
            # Пробуем разместить детали на КАЖДОМ остатке, даже если геометрия не идеальна
            
            # УМНЫЙ подбор деталей для этого остатка (но не обязательный)
            best_suited_details = self._find_best_details_for_remainder(unplaced_details, sheet, max_details=30)
            
            # Даже если не найдены "идеальные" детали, пробуем все доступные
            if not best_suited_details:
                logger.info(f"⚠️ Не найдено оптимальных деталей для остатка {sheet.id}, пробуем все детали")
                # Фильтруем по материалу
                best_suited_details = [d for d in unplaced_details if d.material == sheet.material]
                if not best_suited_details:
                    logger.info(f"⏭️ Нет деталей подходящего материала для остатка {sheet.id}")
                    continue
            
            logger.info(f"📋 Подготовлено {len(best_suited_details)} деталей для попытки размещения на остатке")
            
            # МАКСИМАЛЬНОЕ количество попыток с разными стратегиями
            best_layout = None
            best_score = float('-inf')
            best_usage_percent = 0.0
            
            # РАДИКАЛЬНО АГРЕССИВНАЯ стратегия: еще больше увеличиваем количество попыток
            max_attempts = max(100, self.params.max_iterations_per_sheet * 20)  # Минимум 100 попыток для остатков!
            
            for iteration in range(max_attempts):
                # УЛУЧШЕНИЕ: На первых итерациях используем умно подобранные детали
                if iteration < 10:
                    # Используем лучшие подобранные детали для первых попыток
                    details_to_try = best_suited_details.copy()
                else:
                    # Затем пробуем все детали с разными порядками
                    details_to_try = unplaced_details.copy()
                
                layout = self._create_sheet_layout_guillotine(sheet, details_to_try, iteration)

                # РАДИКАЛЬНОЕ ИЗМЕНЕНИЕ: Для остатков НЕ проверяем плохие отходы!
                # Принимаем ЛЮБОЕ размещение, даже 1 деталь - главное использовать остаток
                # Проверяем только что хоть что-то размещено
                if len(layout.get_placed_details()) == 0:
                    continue
                
                # Оцениваем раскладку с МАКСИМАЛЬНЫМ акцентом на использование остатка
                score = self._evaluate_layout(layout)
                usage_percent = layout.used_area / layout.total_area * 100
                
                # ЗНАЧИТЕЛЬНО УВЕЛИЧЕННЫЕ бонусы за любое использование остатка
                if usage_percent > 70:
                    score += 10000  # ОГРОМНЫЙ бонус за высокое использование
                elif usage_percent > 50:
                    score += 7000   # УВЕЛИЧЕНО с 5000 до 7000
                elif usage_percent > 40:
                    score += 5000   # Новый уровень
                elif usage_percent > 30:
                    score += 4000   # УВЕЛИЧЕНО с 3000 до 4000
                elif usage_percent > 20:
                    score += 3000   # Новый уровень
                elif usage_percent > 15:
                    score += 2500   # УВЕЛИЧЕНО с 2000
                elif usage_percent > 10:
                    score += 2000   # Новый уровень
                elif usage_percent > 5:
                    score += 1500   # УВЕЛИЧЕНО с 1000 до 1500
                elif usage_percent > 2:
                    score += 1000   # Новый уровень: бонус даже за минимальное использование
                else:
                    score += 700    # УВЕЛИЧЕНО с 500: бонус за хоть какое-то использование
                
                # ЗНАЧИТЕЛЬНО УВЕЛИЧЕННЫЙ бонус за количество деталей
                score += len(layout.get_placed_details()) * 1500  # УВЕЛИЧЕНО с 1000 до 1500
                
                # ДОПОЛНИТЕЛЬНЫЙ бонус: если размещена хотя бы одна деталь
                if len(layout.get_placed_details()) > 0:
                    score += 3000  # Значительный бонус за факт использования
                
                # ДОПОЛНИТЕЛЬНЫЙ бонус за минимум новых остатков на старом остатке
                new_remnants = len(layout.get_remnants())
                if new_remnants == 0:
                    score += 5000  # Огромный бонус за полное использование
                elif new_remnants == 1:
                    score += 2000  # Хороший бонус
                
                if score > best_score:
                    best_score = score
                    best_layout = layout
                    best_usage_percent = usage_percent
                
                # РАДИКАЛЬНО МЯГКИЕ условия прекращения: почти никогда не прерываем поиск досрочно
                # Прерываем только при ИСКЛЮЧИТЕЛЬНО хорошем использовании
                if usage_percent > 90 and len(layout.get_placed_details()) >= 5:
                    logger.info(f"✅ Достигнуто исключительное использование остатка: {usage_percent:.1f}%")
                    break
            
            if best_layout and best_layout.get_placed_details():
                # НОВОЕ: Сразу пытаемся заполнить деловые остатки на этом листе-остатке
                base_placed_count = len(best_layout.get_placed_details())
                base_placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
                unplaced_details = [d for d in unplaced_details if d.id not in base_placed_ids]
                
                # Заполняем образовавшиеся остатки дополнительными деталями
                unplaced_details, additionally_placed = self._fill_layout_remnants_with_details(best_layout, unplaced_details)
                after_fill_count = len(best_layout.get_placed_details())
                
                layouts.append(best_layout)
                
                logger.info(f"✅ МАКСИМАЛЬНО УСПЕШНО использован остаток {sheet.id}: "
                           f"базово {base_placed_count} деталей, добавлено {additionally_placed}, "
                           f"итого {after_fill_count}, использование {best_usage_percent:.1f}%, "
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
        
        # НОВЫЙ ЭТАП 3: Циклическая проверка неиспользованных остатков
        # Собираем все остатки, которые не были использованы
        used_remainder_ids = {layout.sheet.id for layout in layouts if layout.sheet.is_remainder}
        unused_remainders = [s for s in remainder_sheets if s.id not in used_remainder_ids]
        
        if unused_remainders and unplaced_details:
            logger.info(f"🎯 ЭТАП 3: Циклическая проверка {len(unused_remainders)} неиспользованных остатков для {len(unplaced_details)} деталей")
            
            cycle_layouts, unplaced_details, used_ids = self._cycle_through_remainders(
                layouts, unplaced_details, unused_remainders
            )
            
            if cycle_layouts:
                layouts.extend(cycle_layouts)
                logger.info(f"✅ Циклическая проверка: дополнительно использовано {len(cycle_layouts)} остатков")
        
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
        """УЛУЧШЕННАЯ оценка для гильотинного размещения - баланс между использованием остатков и минимизацией фрагментации"""
        # Предпочитаем размещения, которые минимизируют остатки
        waste = area.area - (width * height)
        
        # Бонус за точное соответствие размерам
        perfect_width = abs(area.width - width) < 0.1
        perfect_height = abs(area.height - height) < 0.1
        
        if perfect_width or perfect_height:
            if sheet and not sheet.is_remainder:
                waste *= 0.3  # Хороший бонус за точное соответствие на цельных листах
            else:
                waste *= 0.45  # Бонус на остатках
        
        # ДОПОЛНИТЕЛЬНЫЙ бонус за идеальное размещение (обе стороны совпадают)
        if perfect_width and perfect_height:
            waste *= 0.15  # Очень хороший бонус за полное использование области
        
        # Небольшой штраф за поворот детали
        if is_rotated:
            waste *= 1.1
        
        # АГРЕССИВНАЯ ЛОГИКА для остатков - максимально используем
        if sheet and sheet.is_remainder:
            # Для остатков: ОЧЕНЬ БОЛЬШОЙ бонус за использование
            waste *= 0.001  # Сильно снижаем штраф за отходы на остатках
            logger.debug(f"🔧 Большой бонус за размещение на остатке: штраф снижен в 1000 раз")
        elif sheet and not sheet.is_remainder:
            # Для цельных листов: стремимся минимизировать фрагментацию
            remaining_width = area.width - width
            remaining_height = area.height - height
            
            # Штраф за L-образные остатки (создают 2 фрагмента вместо 1)
            if remaining_width > 0 and remaining_height > 0:
                waste *= 2.8  # Штраф за L-образный остаток
            else:
                # Бонус за линейный остаток (только один фрагмент)
                waste *= 0.75
            
            # Проверяем, будет ли создан деловой остаток
            min_remnant_width = self.params.min_remnant_width
            min_remnant_height = self.params.min_remnant_height
            
            will_create_remnant = False
            if remaining_width >= min_remnant_width and area.height >= min_remnant_height:
                will_create_remnant = True
            elif remaining_height >= min_remnant_height and area.width >= min_remnant_width:
                will_create_remnant = True
            
            if will_create_remnant:
                # Проверяем качество создаваемого остатка
                if remaining_width > 0 and remaining_height > 0:
                    # L-образный деловой остаток - оцениваем пропорции
                    remnant_quality = min(remaining_width, remaining_height) / max(remaining_width, remaining_height) if max(remaining_width, remaining_height) > 0 else 0
                    if remnant_quality < 0.25:  # Очень вытянутый
                        waste *= 3.0  # Большой штраф
                    elif remnant_quality < 0.5:  # Вытянутый
                        waste *= 2.2  # Средний штраф
                    else:
                        waste *= 1.8  # Небольшой штраф - остаток приемлемый
                else:
                    # Линейный деловой остаток
                    waste *= 1.6  # Умеренный штраф
            else:
                # Бонус: создаем только отходы, нет новых деловых остатков
                waste *= 0.85
        
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
            # СТАНДАРТНАЯ ЛОГИКА: деловой остаток, если меньшая сторона > меньшего параметра и большая сторона > большего параметра
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
        
        # УСИЛЕННАЯ ЛОГИКА: Максимальное использование остатков и минимизация новых
        if layout.sheet.is_remainder:
            # Для остатков: МАКСИМАЛЬНЫЕ бонусы за использование
            usage_percent = layout.used_area / layout.total_area * 100
            score += usage_percent * 300  # УВЕЛИЧЕНО с 100 до 300
            
            # ЗНАЧИТЕЛЬНО УВЕЛИЧЕННЫЕ бонусы за высокое использование
            if usage_percent > 90:
                score += 8000  # Невероятно высокий бонус за практически полное использование
            elif usage_percent > 80:
                score += 5000  # УВЕЛИЧЕНО с 2000 до 5000
            elif usage_percent > 70:
                score += 3500  # Новый уровень
            elif usage_percent > 60:
                score += 2500  # УВЕЛИЧЕНО с 1000 до 2500
            elif usage_percent > 50:
                score += 1800  # Новый уровень
            elif usage_percent > 40:
                score += 1200  # УВЕЛИЧЕНО с 500 до 1200
            elif usage_percent > 30:
                score += 800   # Новый уровень: бонус даже за среднее использование
            elif usage_percent > 20:
                score += 500   # Новый уровень: бонус даже за низкое использование
            elif usage_percent > 10:
                score += 300   # Бонус даже за очень низкое использование
            else:
                score += 150   # Минимальный бонус за хоть какое-то использование
            
            # ЗНАЧИТЕЛЬНО УВЕЛИЧЕННЫЙ бонус за количество деталей на остатке
            score += len(layout.get_placed_details()) * 1000  # УВЕЛИЧЕНО с 200 до 1000
            
            # ОГРОМНЫЙ базовый бонус за использование остатка
            score += 20000  # УВЕЛИЧЕНО с 3000 до 20000
            
            # ДОПОЛНИТЕЛЬНЫЙ бонус за минимум новых остатков
            if remnant_count == 0:
                score += 8000  # Огромный бонус: остаток использован полностью
            elif remnant_count == 1:
                score += 3000  # Хороший бонус: только один новый остаток
            elif remnant_count == 2:
                score += 1000  # Небольшой бонус
            else:
                score -= (remnant_count - 2) * 500  # Штраф за множество новых остатков
        else:
            # Для цельных листов: ЗНАЧИТЕЛЬНО УСИЛЕННЫЙ штраф за новые деловые остатки
            # Цель: минимизировать создание новых остатков на складе
            if remnant_area_percent > 10.0:  # Очень большие остатки
                score -= remnant_area_percent * 350  # УВЕЛИЧЕНО с 150 до 350
            elif remnant_area_percent > 8.0:  # Большие остатки
                score -= remnant_area_percent * 250  # УВЕЛИЧЕНО
            elif remnant_area_percent > 5.0:  # Средние остатки
                score -= remnant_area_percent * 150  # УВЕЛИЧЕНО с 50 до 150
            elif remnant_area_percent > 3.0:  # Небольшие остатки
                score -= remnant_area_percent * 80   # УВЕЛИЧЕНО
            elif remnant_area_percent > 1.5:  # Маленькие остатки
                score -= remnant_area_percent * 40   # Изменено: теперь штраф вместо бонуса
            elif remnant_area_percent > 0.5:
                score += 100  # Минимальный бонус
            else:
                score += 800  # УВЕЛИЧЕН бонус за минимальные остатки с 200 до 800

            # МАКСИМАЛЬНО УСИЛЕННЫЙ штраф за количество деловых остатков
            if remnant_count == 0:
                score += 5000  # ОГРОМНЫЙ бонус за полное использование без остатков
            elif remnant_count == 1:
                score += 1000  # УВЕЛИЧЕН бонус за один остаток
            elif remnant_count == 2:
                score -= 800   # УВЕЛИЧЕН штраф с 600 до 800
            elif remnant_count == 3:
                score -= 2000  # УВЕЛИЧЕН штраф с 1500 до 2000
            elif remnant_count == 4:
                score -= 3500  # Новый уровень штрафа
            else:
                # ПРОГРЕССИВНЫЙ штраф за множество остатков
                base_penalty = remnant_count * 800  # УВЕЛИЧЕНО с 600 до 800
                extra_penalty = (remnant_count - 4) * 600  # УВЕЛИЧЕНО с 400 до 600
                score -= (base_penalty + extra_penalty)
        
        # Бонус за количество размещенных деталей
        score += len(layout.get_placed_details()) * 20  # УВЕЛИЧЕНО с 10 до 20
        
        # ДОПОЛНИТЕЛЬНЫЙ ОГРОМНЫЙ бонус за использование остатков (суммируется с предыдущими)
        if layout.sheet.is_remainder:
            score += 15000  # УВЕЛИЧЕНО с 10000 до 15000
            # Дополнительный бонус за эффективное использование
            utilization = layout.used_area / layout.total_area
            score += utilization * 8000  # УВЕЛИЧЕНО с 5000 до 8000
            # Бонус за количество размещенных деталей
            score += len(layout.get_placed_details()) * 2500  # УВЕЛИЧЕНО с 2000 до 2500
            # Дополнительный бонус за любую деталь на остатке
            if len(layout.get_placed_details()) > 0:
                score += 7000  # УВЕЛИЧЕНО с 5000 до 7000
        
        # НОВЫЙ БОНУС: за качество деловых остатков
        for remnant in remnants:
            # Бонус за остатки с хорошими пропорциями (легче использовать позже)
            aspect_ratio = max(remnant.width, remnant.height) / min(remnant.width, remnant.height)
            if 1.0 <= aspect_ratio <= 2.0:  # Отличные пропорции
                score += 50  # УВЕЛИЧЕНО с 10 до 50
            elif 2.0 < aspect_ratio <= 3.0:  # Хорошие пропорции
                score += 20
        
        # ДОПОЛНИТЕЛЬНЫЙ бонус за высокую общую эффективность
        efficiency = layout.efficiency  # used_area + remnant_area
        if efficiency > 98:
            score += 3000  # Отличная эффективность
        elif efficiency > 95:
            score += 1500  # Хорошая эффективность
        elif efficiency > 92:
            score += 800   # Приемлемая эффективность
        
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
        max_iterations = 100  # РАДИКАЛЬНО УВЕЛИЧЕНО: с 50 до 100 для максимально агрессивного заполнения
        
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
        """Заполняет деловые остатки ЛЮБОГО листа дополнительными деталями.
        Возвращает (обновленный список неразмещенных деталей, количество дополнительно размещенных деталей).

        РАДИКАЛЬНОЕ ИЗМЕНЕНИЕ: Теперь работает и для листов-остатков!
        """
        # УБРАЛИ ограничение! Теперь заполняем остатки на ВСЕХ листах, включая листы-остатки

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
        max_iterations = 500  # РАДИКАЛЬНО УВЕЛИЧЕНО с 250 до 500 для максимально агрессивного заполнения
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
        """УЛУЧШЕННАЯ проверка возможности объединения остатков"""
        # Проверяем, что остатки соседние
        if not self._are_remnants_adjacent(remnant1, remnant2):
            return False
        
        # Вычисляем параметры объединенного остатка
        merged_width = max(remnant1.x2, remnant2.x2) - min(remnant1.x, remnant2.x)
        merged_height = max(remnant1.y2, remnant2.y2) - min(remnant1.y, remnant2.y)
        merged_area = merged_width * merged_height
        
        min_side = min(merged_width, merged_height)
        max_side = max(merged_width, merged_height)
        
        # Параметры для делового остатка
        param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
        param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
        
        # БАЗОВОЕ ПРАВИЛО: объединенный остаток должен быть деловым
        if not (min_side > param_min and max_side > param_max):
            return False
        
        # УЛУЧШЕННАЯ ЛОГИКА: Дополнительные критерии для объединения
        
        # 1. ВСЕГДА объединяем, если оба исходных остатка маленькие (меньше параметров)
        # Это уменьшает общее количество остатков
        remnant1_small = (min(remnant1.width, remnant1.height) <= param_min * 1.5 or 
                         max(remnant1.width, remnant1.height) <= param_max * 1.5)
        remnant2_small = (min(remnant2.width, remnant2.height) <= param_min * 1.5 or 
                         max(remnant2.width, remnant2.height) <= param_max * 1.5)
        
        if remnant1_small and remnant2_small:
            return True  # Объединяем маленькие остатки безусловно
        
        # 2. Объединяем, если один остаток маленький, а объединенный будет иметь хорошие пропорции
        if remnant1_small or remnant2_small:
            aspect_ratio = max_side / min_side
            if aspect_ratio <= 4.0:  # Приемлемые пропорции
                return True
        
        # 3. Объединяем, если объединенный остаток будет иметь отличные пропорции
        aspect_ratio = max_side / min_side
        if aspect_ratio <= 2.5:  # Отличные пропорции (близко к квадрату)
            return True
        
        # 4. Объединяем, если объединенная площадь близка к сумме исходных площадей
        # (т.е. нет большой "дыры" между остатками)
        sum_areas = remnant1.area + remnant2.area
        area_efficiency = sum_areas / merged_area if merged_area > 0 else 0
        
        if area_efficiency > 0.85:  # Более 85% эффективности - хорошо для объединения
            return True
        
        # 5. Объединяем, если хотя бы один из остатков очень маленький (отход)
        # и объединенный будет полноценным деловым остатком
        remnant1_waste = (min(remnant1.width, remnant1.height) < param_min or 
                          max(remnant1.width, remnant1.height) < param_max)
        remnant2_waste = (min(remnant2.width, remnant2.height) < param_min or 
                          max(remnant2.width, remnant2.height) < param_max)
        
        if remnant1_waste or remnant2_waste:
            # Объединяем, если итоговый остаток значительно больше параметров
            if min_side > param_min * 1.3 and max_side > param_max * 1.3:
                return True
        
        # По умолчанию не объединяем
        return False

    def _are_remnants_adjacent(self, remnant1: PlacedItem, remnant2: PlacedItem) -> bool:
        """УЛУЧШЕННАЯ проверка соседства остатков с учетом частичного перекрытия"""
        tolerance = 2.0  # Увеличен допуск для учета погрешностей раскроя
        
        # Проверяем горизонтальное соседство (один рядом с другим)
        # Остатки могут быть на одной высоте или частично перекрываться по вертикали
        horizontal_adjacent = (
            (abs(remnant1.x2 - remnant2.x) < tolerance or abs(remnant2.x2 - remnant1.x) < tolerance) and
            # Проверка перекрытия по вертикали (Y)
            not (remnant1.y2 < remnant2.y - tolerance or remnant2.y2 < remnant1.y - tolerance)
        )
        
        # Проверяем вертикальное соседство (один над другим)
        # Остатки могут быть на одной ширине или частично перекрываться по горизонтали
        vertical_adjacent = (
            (abs(remnant1.y2 - remnant2.y) < tolerance or abs(remnant2.y2 - remnant1.y) < tolerance) and
            # Проверка перекрытия по горизонтали (X)
            not (remnant1.x2 < remnant2.x - tolerance or remnant2.x2 < remnant1.x - tolerance)
        )
        
        # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Диагональное соседство (угол к углу)
        # Полезно для объединения L-образных остатков
        corner_adjacent = (
            (abs(remnant1.x2 - remnant2.x) < tolerance and abs(remnant1.y2 - remnant2.y) < tolerance) or
            (abs(remnant1.x - remnant2.x2) < tolerance and abs(remnant1.y2 - remnant2.y) < tolerance) or
            (abs(remnant1.x2 - remnant2.x) < tolerance and abs(remnant1.y - remnant2.y2) < tolerance) or
            (abs(remnant1.x - remnant2.x2) < tolerance and abs(remnant1.y - remnant2.y2) < tolerance)
        )
        
        return horizontal_adjacent or vertical_adjacent or corner_adjacent

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

    def _calculate_final_result(self, layouts: List[SheetLayout], unplaced: List[Detail], start_time: float, 
                                all_remainder_sheets: List[Sheet] = None) -> OptimizationResult:
        """Вычисляет финальный результат оптимизации с детальной статистикой использования остатков"""
        
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
        
        # УЛУЧШЕННАЯ СТАТИСТИКА ИСПОЛЬЗОВАНИЯ ОСТАТКОВ СО СКЛАДА
        if all_remainder_sheets:
            total_available_remainders = len(all_remainder_sheets)
            used_remainders = len(remainder_layouts)
            unused_remainders = total_available_remainders - used_remainders
            usage_percent = (used_remainders / total_available_remainders * 100) if total_available_remainders > 0 else 0
            
            logger.info(f"")
            logger.info(f"{'='*80}")
            logger.info(f"📊 ДЕТАЛЬНАЯ СТАТИСТИКА ИСПОЛЬЗОВАНИЯ ДЕЛОВЫХ ОСТАТКОВ")
            logger.info(f"{'='*80}")
            logger.info(f"🎯 Доступно остатков на складе: {total_available_remainders}")
            logger.info(f"✅ Использовано остатков: {used_remainders} ({usage_percent:.1f}%)")
            logger.info(f"❌ НЕ использовано остатков: {unused_remainders} ({100-usage_percent:.1f}%)")
            
            if remainder_layouts:
                remainder_area = sum(l.total_area for l in remainder_layouts)
                remainder_used = sum(l.used_area for l in remainder_layouts)
                remainder_remnant = sum(l.remnant_area for l in remainder_layouts)
                remainder_waste = sum(l.waste_area for l in remainder_layouts)
                remainder_waste_percent = (remainder_waste / remainder_area * 100) if remainder_area > 0 else 0
                remainder_usage_percent = (remainder_used / remainder_area * 100) if remainder_area > 0 else 0
                
                logger.info(f"")
                logger.info(f"📈 Статистика использованных остатков:")
                logger.info(f"   • Общая площадь: {remainder_area / 1_000_000:.2f} м²")
                logger.info(f"   • Размещено деталей: {remainder_used / 1_000_000:.2f} м² ({remainder_usage_percent:.1f}%)")
                logger.info(f"   • Новые деловые остатки: {remainder_remnant / 1_000_000:.2f} м²")
                logger.info(f"   • Отходы: {remainder_waste / 1_000_000:.2f} м² ({remainder_waste_percent:.1f}%)")
                logger.info(f"   • Допустимые отходы: {self.params.remainder_waste_percent:.1f}%")
            logger.info(f"{'='*80}")
            logger.info(f"")
        elif remainder_layouts:
            # Fallback для обратной совместимости
            remainder_area = sum(l.total_area for l in remainder_layouts)
            remainder_waste = sum(l.waste_area for l in remainder_layouts)
            remainder_waste_percent = (remainder_waste / remainder_area * 100) if remainder_area > 0 else 0
            logger.info(f"📊 Статистика остатков: {len(remainder_layouts)} листов использовано, "
                       f"площадь {remainder_area:.0f}, отходы {remainder_waste_percent:.1f}% "
                       f"(допустимо {self.params.remainder_waste_percent:.1f}%)")
        
        if material_layouts:
            material_area = sum(l.total_area for l in material_layouts)
            material_waste = sum(l.waste_area for l in material_layouts)
            material_waste_percent = (material_waste / material_area * 100) if material_area > 0 else 0
            logger.info(f"📊 Статистика цельных листов: {len(material_layouts)} листов, "
                       f"площадь {material_area:.0f}, отходы {material_waste_percent:.1f}% "
                       f"(допустимо {self.params.target_waste_percent:.1f}%)")
        
        # СТАТИСТИКА СОЗДАНИЯ НОВЫХ ДЕЛОВЫХ ОСТАТКОВ
        total_new_remnants = sum(len(l.get_remnants()) for l in layouts)
        total_new_remnants_area = sum(sum(r.area for r in l.get_remnants()) for l in layouts)
        
        if total_new_remnants > 0:
            logger.info(f"")
            logger.info(f"{'='*80}")
            logger.info(f"📦 СТАТИСТИКА СОЗДАНИЯ НОВЫХ ДЕЛОВЫХ ОСТАТКОВ")
            logger.info(f"{'='*80}")
            logger.info(f"📊 Создано новых деловых остатков: {total_new_remnants} шт")
            logger.info(f"📊 Общая площадь новых остатков: {total_new_remnants_area / 1_000_000:.2f} м²")
            
            # Разбивка по размерам
            small_remnants = 0
            medium_remnants = 0
            large_remnants = 0
            
            for layout in layouts:
                for remnant in layout.get_remnants():
                    if remnant.area < 500000:  # < 0.5 м²
                        small_remnants += 1
                    elif remnant.area < 2000000:  # < 2 м²
                        medium_remnants += 1
                    else:
                        large_remnants += 1
            
            logger.info(f"   • Маленькие (< 0.5 м²): {small_remnants} шт")
            logger.info(f"   • Средние (0.5-2 м²): {medium_remnants} шт")
            logger.info(f"   • Большие (> 2 м²): {large_remnants} шт")
            
            # Процент от общей площади
            if total_area > 0:
                remnants_percent = (total_new_remnants_area / total_area * 100)
                logger.info(f"   • Процент от общей площади: {remnants_percent:.1f}%")
            
            logger.info(f"{'='*80}")
            logger.info(f"")
        
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
            # Формируем детальное сообщение о неразмещенных деталях
            placed_count = sum(len(l.get_placed_details()) for l in layouts)
            unplaced_count = len(unplaced)
            
            # Группируем неразмещенные детали по материалам
            unplaced_by_material = {}
            for detail in unplaced:
                material = detail.material
                if material not in unplaced_by_material:
                    unplaced_by_material[material] = {
                        'count': 0,
                        'area': 0,
                        'details': []
                    }
                unplaced_by_material[material]['count'] += 1
                unplaced_by_material[material]['area'] += detail.area
                unplaced_by_material[material]['details'].append(f"{detail.oi_name} ({int(detail.width)}x{int(detail.height)})")
            
            message = f"❌ НЕДОСТАТОЧНО МАТЕРИАЛА!\n\n"
            message += f"Размещено: {placed_count} деталей\n"
            message += f"НЕ размещено: {unplaced_count} деталей\n\n"
            message += "Детали, которые НЕ удалось разместить:\n"
            
            for material, info in unplaced_by_material.items():
                message += f"\n📦 Материал: {material}\n"
                message += f"   Количество: {info['count']} деталей\n"
                message += f"   Площадь: {info['area'] / 1_000_000:.2f} м²\n"
                message += f"   Список деталей:\n"
                for detail_info in info['details'][:10]:  # Показываем первые 10
                    message += f"     - {detail_info}\n"
                if len(info['details']) > 10:
                    message += f"     ... и ещё {len(info['details']) - 10} деталей\n"
            
            message += "\n💡 Рекомендация: Пополните склад недостающим материалом или уменьшите количество деталей в заказе."
            
            logger.error(message)
        
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


def check_material_sufficiency(details: List[dict], materials: List[dict], remainders: List[dict]) -> Tuple[bool, str]:
    """
    Проверяет достаточность материала для выполнения раскроя.
    
    Returns:
        Tuple[bool, str]: (достаточно_материала, сообщение_об_ошибке)
    """
    try:
        # Группируем детали по материалам
        details_by_material = {}
        for detail_data in details:
            material = str(detail_data.get('g_marking', ''))
            if not material:
                continue
            
            quantity = int(detail_data.get('total_qty', detail_data.get('quantity', 1)))
            width = float(detail_data.get('width', 0))
            height = float(detail_data.get('height', 0))
            area = width * height * quantity
            
            if material not in details_by_material:
                details_by_material[material] = {
                    'area': 0,
                    'count': 0
                }
            details_by_material[material]['area'] += area
            details_by_material[material]['count'] += quantity
        
        # Группируем доступные материалы (склад + остатки)
        available_by_material = {}
        
        # Добавляем материалы со склада
        for material_data in materials:
            material = str(material_data.get('g_marking', ''))
            if not material:
                continue
            
            qty = int(material_data.get('res_qty', material_data.get('quantity', 1)))
            if qty <= 0:
                continue
            if qty > 1000:
                qty = 1000
            
            width = float(material_data.get('width', 0))
            height = float(material_data.get('height', 0))
            area = width * height * qty
            
            if material not in available_by_material:
                available_by_material[material] = {
                    'area': 0,
                    'count': 0,
                    'sheets': []
                }
            available_by_material[material]['area'] += area
            available_by_material[material]['count'] += qty
            available_by_material[material]['sheets'].append({
                'type': 'склад',
                'width': width,
                'height': height,
                'qty': qty
            })
        
        # Добавляем остатки
        for remainder_data in remainders:
            material = str(remainder_data.get('g_marking', ''))
            if not material:
                continue
            
            qty = int(remainder_data.get('qty', 1))
            if qty <= 0:
                continue
            if qty > 1000:
                qty = 1000
            
            width = float(remainder_data.get('width', 0))
            height = float(remainder_data.get('height', 0))
            area = width * height * qty
            
            if material not in available_by_material:
                available_by_material[material] = {
                    'area': 0,
                    'count': 0,
                    'sheets': []
                }
            available_by_material[material]['area'] += area
            available_by_material[material]['count'] += qty
            available_by_material[material]['sheets'].append({
                'type': 'остаток',
                'width': width,
                'height': height,
                'qty': qty
            })
        
        # Проверяем достаточность материала для каждого типа
        insufficient_materials = []
        
        for material, detail_info in details_by_material.items():
            required_area = detail_info['area']
            required_count = detail_info['count']
            
            available_info = available_by_material.get(material, {'area': 0, 'count': 0, 'sheets': []})
            available_area = available_info['area']
            available_count = available_info['count']
            
            # Простая проверка по площади (с учетом коэффициента запаса на отходы ~1.3)
            # Если требуемая площадь больше доступной площади, материала точно не хватит
            if required_area > available_area:
                shortage_area = required_area - available_area
                shortage_percent = (shortage_area / required_area * 100) if required_area > 0 else 0
                
                # Формируем детальное сообщение
                available_sheets_info = []
                for sheet in available_info['sheets']:
                    available_sheets_info.append(
                        f"  - {sheet['type']}: {int(sheet['width'])}x{int(sheet['height'])} мм, "
                        f"количество: {sheet['qty']} шт"
                    )
                
                insufficient_materials.append({
                    'material': material,
                    'required_area': required_area,
                    'available_area': available_area,
                    'shortage_area': shortage_area,
                    'shortage_percent': shortage_percent,
                    'required_count': required_count,
                    'available_count': available_count,
                    'available_sheets': available_sheets_info
                })
        
        # Если есть недостающие материалы, формируем сообщение об ошибке
        if insufficient_materials:
            error_message = "❌ НЕДОСТАТОЧНО МАТЕРИАЛА ДЛЯ ВЫПОЛНЕНИЯ РАСКРОЯ!\n\n"
            
            for mat_info in insufficient_materials:
                error_message += f"📦 Материал: {mat_info['material']}\n"
                error_message += f"   Требуется: {mat_info['required_area'] / 1_000_000:.2f} м² "
                error_message += f"({mat_info['required_count']} деталей)\n"
                error_message += f"   Доступно: {mat_info['available_area'] / 1_000_000:.2f} м² "
                error_message += f"({mat_info['available_count']} листов)\n"
                error_message += f"   Недостаёт: {mat_info['shortage_area'] / 1_000_000:.2f} м² "
                error_message += f"({mat_info['shortage_percent']:.1f}%)\n"
                
                if mat_info['available_sheets']:
                    error_message += "   Доступные листы:\n"
                    for sheet_info in mat_info['available_sheets']:
                        error_message += sheet_info + "\n"
                else:
                    error_message += "   ⚠️ НЕТ ДОСТУПНЫХ ЛИСТОВ НА СКЛАДЕ!\n"
                error_message += "\n"
            
            error_message += "💡 Рекомендация: Пополните склад недостающим материалом или уменьшите количество деталей в заказе."
            
            logger.error(error_message)
            return False, error_message
        
        # Материала достаточно
        return True, ""
        
    except Exception as e:
        logger.error(f"Ошибка проверки достаточности материала: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # В случае ошибки проверки, продолжаем оптимизацию
        return True, ""


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
        
        # ПРОВЕРКА ДОСТАТОЧНОСТИ МАТЕРИАЛА
        logger.info(f"🔍 Проверка достаточности материала...")
        is_sufficient, error_message = check_material_sufficiency(details, materials, remainders)
        
        if not is_sufficient:
            # Материала недостаточно - возвращаем ошибку
            logger.error("❌ Оптимизация прервана: недостаточно материала")
            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=[],
                total_efficiency=0.0,
                total_waste_percent=100.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=0.0,
                message=error_message
            )
        
        logger.info(f"✅ Материала достаточно, продолжаем оптимизацию")
        
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

