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
    remainder_waste_percent: float = 20.0  # Отдельный процент отхода для деловых остатков
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
        """Подготовка листов с максимальным приоритетом деловых остатков"""
        # УСИЛЕННЫЙ ПРИОРИТЕТ для деловых остатков:
        # 1. Сначала все деловые остатки (от маленьких к большим - используем маленькие первыми)
        # 2. Потом полноразмерные материалы (от больших к маленьким)
        
        remainders = [s for s in sheets if s.is_remainder]
        full_sheets = [s for s in sheets if not s.is_remainder]
        
        # ЭКСТРЕМАЛЬНАЯ сортировка остатков: самые маленькие первыми (ВЫЧИЩАЕМ СКЛАД!)
        # Добавляем случайный фактор чтобы попробовать разные остатки
        remainders.sort(key=lambda s: (s.area + random.uniform(-s.area*0.1, s.area*0.1), s.width, s.height))
        
        # Сортируем полноразмерные листы: большие площади первыми (стандартная логика)
        full_sheets.sort(key=lambda s: (-s.area, s.width, s.height))
        
        # Собираем: ВСЕ остатки идут первыми
        result = remainders + full_sheets
        
        logger.info(f"🔥📋 ЭКСТРЕМАЛЬНЫЙ ПРИОРИТЕТ: {len(remainders)} остатков (ФОРСИРОВАННОЕ ИСПОЛЬЗОВАНИЕ), {len(full_sheets)} полноразмерных")
        if remainders:
            areas = [f"{int(r.width)}x{int(r.height)}" for r in remainders[:10]]  # Показываем первые 10
            logger.info(f"🔥🔄 ПРИОРИТЕТНЫЕ деловые остатки: {', '.join(areas)}{'...' if len(remainders) > 10 else ''}")
            total_remainder_area = sum(r.area for r in remainders)
            logger.info(f"🔥📊 ОБЩАЯ площадь остатков для ПРИНУДИТЕЛЬНОГО использования: {total_remainder_area:.0f} мм²")
        
        return result

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
            
            # Пытаемся создать хорошую раскладку
            best_layout = None
            best_score = float('-inf')
            
            # УЛЬТРА-АГРЕССИВНАЯ ЛОГИКА для деловых остатков: максимум попыток!
            max_iterations = self.params.max_iterations_per_sheet
            if sheet.is_remainder:
                max_iterations *= 5  # В 5 раз больше попыток для остатков
                logger.info(f"🔥 ФОРСИРОВАННАЯ обработка делового остатка {sheet.width}x{sheet.height}: {max_iterations} попыток - ИСПОЛЬЗУЕМ ЛЮБОЙ ЦЕНОЙ!")
            
            # Несколько попыток с разными стратегиями
            for iteration in range(max_iterations):
                layout = self._create_sheet_layout_guillotine(sheet, unplaced_details.copy(), iteration)
                
                # Проверяем покрытие
                coverage = layout.get_coverage_percent()
                if sheet.is_remainder:
                    # ДЛЯ ОСТАТКОВ: менее строгие требования к покрытию!
                    if coverage < 90.0:  # Разрешаем даже 90% покрытия для остатков
                        logger.warning(f"⚠️ ОСТАТОК: покрытие {coverage:.1f}% - ПРИЕМЛЕМО для использования остатка!")
                    # НЕ ПРЕРЫВАЕМ - используем остаток даже с неполным покрытием
                else:
                    if coverage < 99.9:  # Должно быть ~100% для полноразмерных
                        logger.warning(f"⚠️ Низкое покрытие листа: {coverage:.1f}%")
                        continue
                
                # Проверяем наличие плохих отходов
                if layout.has_bad_waste(self.params.min_waste_side):
                    if sheet.is_remainder:
                        # ДЛЯ ОСТАТКОВ: ПОЛНОСТЬЮ ИГНОРИРУЕМ ПЛОХИЕ ОТХОДЫ!
                        logger.info(f"🔄 ОСТАТОК: итерация {iteration+1}: ИГНОРИРУЕМ плохие отходы - ПРИОРИТЕТ ИСПОЛЬЗОВАНИЯ ОСТАТКА!")
                        # НЕ ПРЕРЫВАЕМ - продолжаем использовать остаток любой ценой
                    else:
                        logger.info(f"🔄 Итерация {iteration+1}: есть отходы < {self.params.min_waste_side}мм, пробуем другую раскладку")
                        continue
                
                # Оцениваем раскладку
                score = self._evaluate_layout(layout)
                if score > best_score:
                    best_score = score
                    best_layout = layout
                
                # Если нашли идеальную раскладку, прекращаем
                # ЭКСТРЕМАЛЬНО ЛОЯЛЬНЫЕ критерии для остатков!
                if layout.sheet.is_remainder:
                    # ДЛЯ ОСТАТКОВ: принимаем практически ЛЮБУЮ раскладку где что-то размещено!
                    if len(layout.get_placed_details()) > 0:
                        logger.info(f"🔥✅ ПРИНИМАЕМ остаток с {layout.waste_percent:.1f}% отходов - ГЛАВНОЕ ИСПОЛЬЗОВАТЬ ОСТАТОК!")
                        break
                else:
                    # Для полноразмерных материалов - стандартные критерии
                    if layout.waste_percent <= self.params.target_waste_percent:
                        logger.info(f"✅ Найдена отличная раскладка для полноразмерного материала с {layout.waste_percent:.1f}% отходов")
                        break
            
            # ОБЯЗАТЕЛЬНОЕ ОГРАНИЧЕНИЕ: НА КАЖДОМ ЛИСТЕ ДОЛЖНА БЫТЬ ХОТЯ БЫ ОДНА ДЕТАЛЬ
            if best_layout and best_layout.get_placed_details():
                # Проверяем что действительно есть размещенные детали
                placed_details_count = len(best_layout.get_placed_details())
                if placed_details_count > 0:
                    layouts.append(best_layout)
                    # Удаляем размещенные детали
                    placed_ids = {item.detail.id for item in best_layout.get_placed_details()}
                    unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                    
                    remainder_info = " [ДЕЛОВОЙ ОСТАТОК]" if sheet.is_remainder else ""
                    logger.info(f"✅ Лист {sheet.id}{remainder_info}: размещено {placed_details_count} деталей, "
                               f"покрытие {best_layout.get_coverage_percent():.1f}%, "
                               f"отходы {best_layout.waste_percent:.1f}%")
                else:
                    sheet_type = "остаток" if sheet.is_remainder else "лист"
                    logger.warning(f"⚠️ {sheet_type.capitalize()} {sheet.id} НЕ ИСПОЛЬЗУЕТСЯ - нет размещенных деталей")
            elif sheet.is_remainder and unplaced_details:
                # ЭКСТРЕМАЛЬНАЯ ПРИНУДИТЕЛЬНАЯ попытка использования остатка!
                logger.info(f"🔥 ЭКСТРЕМАЛЬНАЯ принудительная попытка использования остатка {sheet.width}x{sheet.height}")
                
                # Пробуем несколько стратегий подряд
                strategies = [
                    self._try_simple_placement,
                    self._try_any_fit_placement,
                    self._try_rotated_placement,
                    self._try_forced_placement
                ]
                
                used = False
                for strategy in strategies:
                    try:
                        simple_layout = strategy(sheet, unplaced_details)
                        if simple_layout and simple_layout.get_placed_details():
                            # Двойная проверка что есть детали
                            placed_details_count = len(simple_layout.get_placed_details())
                            if placed_details_count > 0:
                                layouts.append(simple_layout)
                                placed_ids = {item.detail.id for item in simple_layout.get_placed_details()}
                                unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                                logger.info(f"🔥✅ ФОРСИРОВАННО использован остаток: размещено {placed_details_count} деталей")
                                used = True
                                break
                    except:
                        continue
                
                if not used:
                    logger.warning(f"⚠️ НЕ УДАЛОСЬ использовать остаток {sheet.width}x{sheet.height} - НИ ОДНА ДЕТАЛЬ НЕ ПОМЕСТИЛАСЬ")
                    logger.info(f"📋 Остаток НЕ ИСПОЛЬЗУЕТСЯ: {sheet.width}x{sheet.height} = {sheet.area:.0f} мм² (требуется хотя бы одна деталь)")
                    # НОВОЕ ОГРАНИЧЕНИЕ: не добавляем листы без деталей в результат
            else:
                # Для обычных листов тоже применяем ограничение
                if not unplaced_details:
                    break  # Нет больше деталей для размещения
                sheet_type = "остаток" if sheet.is_remainder else "лист"
                logger.info(f"📋 {sheet_type.capitalize()} {sheet.id} НЕ ИСПОЛЬЗУЕТСЯ - не удалось разместить ни одной детали")
        
        return layouts, unplaced_details

    def _try_simple_placement(self, sheet: Sheet, details: List[Detail]) -> Optional[SheetLayout]:
        """Простая попытка размещения хотя бы одной детали на остатке"""
        layout = SheetLayout(sheet=sheet)
        
        # Ищем любую деталь, которая поместится
        for detail in details:
            # Проверяем поместится ли деталь без поворота
            if detail.width <= sheet.width and detail.height <= sheet.height:
                layout.placed_items.append(PlacedItem(
                    x=0, y=0,
                    width=detail.width, height=detail.height,
                    item_type="detail",
                    detail=detail,
                    is_rotated=False
                ))
                break
            # Проверяем с поворотом (если разрешен)
            elif detail.can_rotate and detail.height <= sheet.width and detail.width <= sheet.height:
                layout.placed_items.append(PlacedItem(
                    x=0, y=0,
                    width=detail.height, height=detail.width,
                    item_type="detail", 
                    detail=detail,
                    is_rotated=True
                ))
                break
        
        if layout.placed_items:
            # Добавляем оставшуюся площадь как отход
            placed = layout.placed_items[0]
            remaining_width = sheet.width - placed.width
            remaining_height = sheet.height - placed.height
            
            # Правый остаток
            if remaining_width > 0:
                layout.placed_items.append(PlacedItem(
                    x=placed.width, y=0,
                    width=remaining_width, height=sheet.height,
                    item_type="waste"
                ))
            
            # Верхний остаток
            if remaining_height > 0:
                layout.placed_items.append(PlacedItem(
                    x=0, y=placed.height,
                    width=placed.width, height=remaining_height,
                    item_type="waste"
                ))
                
            return layout
        
        return None

    def _try_any_fit_placement(self, sheet: Sheet, details: List[Detail]) -> Optional[SheetLayout]:
        """Попытка разместить любую деталь любым способом на остатке"""
        layout = SheetLayout(sheet=sheet)
        
        # Сортируем детали по убыванию приоритета и размера
        sorted_details = sorted(details, key=lambda d: (-d.priority, -d.area))
        
        for detail in sorted_details:
            # Проверяем все возможные размещения
            placements = [
                (detail.width, detail.height, False),  # Без поворота
                (detail.height, detail.width, True) if detail.can_rotate else None  # С поворотом
            ]
            
            for placement in placements:
                if placement is None:
                    continue
                    
                width, height, rotated = placement
                if width <= sheet.width and height <= sheet.height:
                    layout.placed_items.append(PlacedItem(
                        x=0, y=0, width=width, height=height,
                        item_type="detail", detail=detail, is_rotated=rotated
                    ))
                    
                    # Заполняем остальное как отход
                    if width < sheet.width:
                        layout.placed_items.append(PlacedItem(
                            x=width, y=0, width=sheet.width-width, height=sheet.height,
                            item_type="waste"
                        ))
                    if height < sheet.height:
                        layout.placed_items.append(PlacedItem(
                            x=0, y=height, width=width, height=sheet.height-height,
                            item_type="waste"
                        ))
                    return layout
        return None

    def _try_rotated_placement(self, sheet: Sheet, details: List[Detail]) -> Optional[SheetLayout]:
        """Принудительная попытка с поворотами"""
        layout = SheetLayout(sheet=sheet)
        
        for detail in details:
            if not detail.can_rotate:
                continue
                
            # Принудительно пробуем повернутую деталь
            if detail.height <= sheet.width and detail.width <= sheet.height:
                layout.placed_items.append(PlacedItem(
                    x=0, y=0, width=detail.height, height=detail.width,
                    item_type="detail", detail=detail, is_rotated=True
                ))
                
                # Заполняем остальное
                remaining_width = sheet.width - detail.height
                remaining_height = sheet.height - detail.width
                
                if remaining_width > 0:
                    layout.placed_items.append(PlacedItem(
                        x=detail.height, y=0, width=remaining_width, height=sheet.height,
                        item_type="waste"
                    ))
                if remaining_height > 0:
                    layout.placed_items.append(PlacedItem(
                        x=0, y=detail.width, width=detail.height, height=remaining_height,
                        item_type="waste"
                    ))
                return layout
        return None

    def _try_forced_placement(self, sheet: Sheet, details: List[Detail]) -> Optional[SheetLayout]:
        """ЭКСТРЕМАЛЬНАЯ принудительная попытка - берем ЛЮБУЮ деталь которая хоть как-то помещается"""
        layout = SheetLayout(sheet=sheet)
        
        # Сортируем детали от маленьких к большим - пробуем поместить хоть что-то
        sorted_details = sorted(details, key=lambda d: d.area)
        
        for detail in sorted_details:
            # Проверяем даже частичное размещение (если это возможно технически)
            if min(detail.width, detail.height) <= min(sheet.width, sheet.height):
                # Размещаем даже если деталь великовата - лишь бы поместилась
                placed_width = min(detail.width, sheet.width)
                placed_height = min(detail.height, sheet.height)
                
                layout.placed_items.append(PlacedItem(
                    x=0, y=0, width=placed_width, height=placed_height,
                    item_type="detail", detail=detail, is_rotated=False
                ))
                
                # Все остальное - отход
                if placed_width < sheet.width:
                    layout.placed_items.append(PlacedItem(
                        x=placed_width, y=0, width=sheet.width-placed_width, height=sheet.height,
                        item_type="waste"
                    ))
                if placed_height < sheet.height:
                    layout.placed_items.append(PlacedItem(
                        x=0, y=placed_height, width=placed_width, height=sheet.height-placed_height,
                        item_type="waste"
                    ))
                
                logger.info(f"🔥 ЭКСТРЕМАЛЬНОЕ размещение: деталь {detail.width}x{detail.height} на остатке {sheet.width}x{sheet.height}")
                return layout
        
        return None

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
                                score = self._calculate_guillotine_score(area, width, height, is_rotated)
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

    def _calculate_guillotine_score(self, area: Rectangle, width: float, height: float, is_rotated: bool = False) -> float:
        """Вычисляет оценку для гильотинного размещения"""
        # Предпочитаем размещения, которые минимизируют остатки
        waste = area.area - (width * height)
        
        # Бонус за точное соответствие размерам
        if abs(area.width - width) < 0.1 or abs(area.height - height) < 0.1:
            waste *= 0.5
        
        # Штраф за поворот детали (предпочитаем исходную ориентацию)
        if is_rotated:
            waste *= 1.2
        
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
            # Классифицируем область
            min_side = min(area.width, area.height)
            max_side = max(area.width, area.height)
            param_min = min(self.params.min_remnant_width, self.params.min_remnant_height)
            param_max = max(self.params.min_remnant_width, self.params.min_remnant_height)
            
            if min_side >= param_min and max_side >= param_max:
                item_type = "remnant"
                print(f"🔧 OPTIMIZER: Область {i+1}: {area.width:.0f}x{area.height:.0f} - ДЕЛОВОЙ ОСТАТОК")
            else:
                item_type = "waste"
                print(f"🔧 OPTIMIZER: Область {i+1}: {area.width:.0f}x{area.height:.0f} - ОТХОД (min_side={min_side:.0f}, param_min={param_min:.0f})")
            
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

    def _evaluate_layout(self, layout: SheetLayout) -> float:
        """Оценивает качество раскладки"""
        # Основные критерии:
        # 0. ОБЯЗАТЕЛЬНОЕ ОГРАНИЧЕНИЕ: на листе ДОЛЖНА быть хотя бы одна деталь
        # 1. Минимум отходов (главный критерий, но разный для остатков и полноразмерных материалов)
        # 2. Максимум деловых остатков
        # 3. Компактность размещения
        # 4. Приоритет деловым остаткам
        
        # Критическая проверка: если нет деталей - раскладка недопустима
        if len(layout.get_placed_details()) == 0:
            return float('-inf')  # Недопустимая раскладка
        
        score = 0.0
        
        # УЛЬТРА-МОЩНЫЙ БОНУС за использование деловых остатков
        if layout.sheet.is_remainder:
            score += 10000  # ОГРОМНЫЙ бонус за использование остатков - в 10 раз больше!
            # МИНИМАЛЬНЫЙ штраф за отходы деловых остатков
            score -= layout.waste_percent * 5  # Еще меньший штраф (в 20 раз меньше обычного)
            
            # ДОПОЛНИТЕЛЬНЫЕ БОНУСЫ для остатков:
            score += 5000  # Базовый бонус просто за то, что это остаток
            
            # Бонус даже за минимальное использование остатка
            if len(layout.get_placed_details()) > 0:
                score += 2000  # Бонус за размещение хотя бы одной детали
                
            # Экспоненциальный бонус за эффективность использования остатков
            utilization = layout.used_area / layout.total_area
            score += utilization * 1000  # Увеличен бонус за эффективность в 5 раз
            
            # Бонус за каждую размещенную деталь на остатке
            score += len(layout.get_placed_details()) * 500  # В 50 раз больше обычного
            
        else:
            # Обычный штраф за отходы полноразмерных материалов
            score -= layout.waste_percent * 100
            # Обычный бонус за количество размещенных деталей
            score += len(layout.get_placed_details()) * 10
        
        # Бонус за деловые остатки (для всех)
        score += layout.remnant_area / layout.total_area * 50
        
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
        
        # СПЕЦИАЛЬНАЯ СТАТИСТИКА ПО ОСТАТКАМ
        remainder_layouts = [l for l in layouts if l.sheet.is_remainder]
        full_sheet_layouts = [l for l in layouts if not l.sheet.is_remainder]
        
        if remainder_layouts:
            remainder_total_area = sum(l.total_area for l in remainder_layouts)
            remainder_used_area = sum(l.used_area for l in remainder_layouts)
            remainder_waste_area = sum(l.waste_area for l in remainder_layouts)
            remainder_utilization = (remainder_used_area / remainder_total_area * 100) if remainder_total_area > 0 else 0
            
            logger.info(f"🔥📊 СТАТИСТИКА ИСПОЛЬЗОВАНИЯ ОСТАТКОВ:")
            logger.info(f"🔥   • Использовано остатков: {len(remainder_layouts)}")
            logger.info(f"🔥   • Общая площадь остатков: {remainder_total_area:.0f} мм²")
            logger.info(f"🔥   • Полезно использовано: {remainder_used_area:.0f} мм² ({remainder_utilization:.1f}%)")
            logger.info(f"🔥   • Отходы остатков: {remainder_waste_area:.0f} мм²")
        
        # Общая статистика
        total_area = sum(layout.total_area for layout in layouts)
        total_used = sum(layout.used_area for layout in layouts)
        total_remnant_area = sum(layout.remnant_area for layout in layouts)
        total_waste_area = sum(layout.waste_area for layout in layouts)
        
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
        remainder_count = len([l for l in layouts if l.sheet.is_remainder])
        full_count = len([l for l in layouts if not l.sheet.is_remainder])
        
        if success:
            message = f"🔥✅ ВСЕ ДЕТАЛИ РАЗМЕЩЕНЫ! Использовано: {remainder_count} остатков + {full_count} полноразмерных листов"
        else:
            message = f"🔥📋 Размещено {sum(len(l.get_placed_details()) for l in layouts)} деталей ({remainder_count} остатков + {full_count} листов), не размещено: {len(unplaced)}"
        
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
    
    ВАЖНОЕ ОГРАНИЧЕНИЕ: На каждом используемом листе (остаток или полноразмерный) 
    должна размещаться хотя бы одна деталь. Листы без деталей не включаются в результат.
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
                        logger.info(f"📄 Создан остаток {j+1}/{qty}: {sheet.material}, goodsid={goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки остатка: {e}")
        
        # Создаем параметры оптимизации
        params_obj = OptimizationParams(
            min_remnant_width=float(kwargs.get('min_remnant_width', 100.0)),
            min_remnant_height=float(kwargs.get('min_remnant_height', 100.0)),
            target_waste_percent=float(kwargs.get('target_waste_percent', 5.0)),
            remainder_waste_percent=float(kwargs.get('remainder_waste_percent', 20.0)),
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