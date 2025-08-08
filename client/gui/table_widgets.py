"""
Виджеты и функции для работы с таблицами в приложении оптимизации
"""

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


def _create_numeric_item(value, default=0):
    """Создание элемента таблицы для числовых значений с правильной сортировкой"""
    try:
        # УЛУЧШЕННАЯ ОБРАБОТКА: проверяем различные типы данных
        if value is None:
            numeric_value = default
        elif isinstance(value, (int, float)):
            numeric_value = int(value) if isinstance(value, int) else float(value)
        elif isinstance(value, str):
            # Удаляем пробелы и проверяем на пустоту
            cleaned_value = str(value).strip()
            if cleaned_value == '' or cleaned_value.lower() in ['none', 'null', 'nan']:
                numeric_value = default
            else:
                # Пытаемся преобразовать в число
                try:
                    numeric_value = int(float(cleaned_value))
                except (ValueError, TypeError):
                    numeric_value = default
        else:
            numeric_value = default
        
        # ОБЯЗАТЕЛЬНО создаем элемент с данными
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, numeric_value)
        
        # ДОПОЛНИТЕЛЬНАЯ ЗАЩИТА: устанавливаем текст для отображения
        item.setText(str(numeric_value))
        
        # КРИТИЧНО: Устанавливаем выравнивание по правому краю для чисел
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        return item
        
    except Exception as e:
        # FALLBACK: в случае любой ошибки создаем элемент со значением по умолчанию
        logger.warning(f"Error creating numeric item for value '{value}': {e}")
        item = QTableWidgetItem()
        item.setData(Qt.DisplayRole, default)
        item.setText(str(default))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item


def _create_text_item(value):
    """Создание элемента таблицы для текстовых значений"""
    try:
        # УЛУЧШЕННАЯ ОБРАБОТКА: проверяем различные типы данных
        if value is None:
            text_value = ''
        elif isinstance(value, str):
            text_value = value.strip()
        elif isinstance(value, (int, float)):
            text_value = str(value)
        else:
            text_value = str(value) if value is not None else ''
        
        # ДОПОЛНИТЕЛЬНАЯ ОЧИСТКА: убираем спецсимволы которые могут вызвать проблемы
        if text_value.lower() in ['none', 'null', 'nan']:
            text_value = ''
        
        # ОБЯЗАТЕЛЬНО создаем элемент
        item = QTableWidgetItem(text_value)
        
        # ДОПОЛНИТЕЛЬНАЯ ЗАЩИТА: устанавливаем текст явно
        item.setText(text_value)
        
        # Устанавливаем выравнивание по левому краю для текста
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        return item
        
    except Exception as e:
        # FALLBACK: в случае любой ошибки создаем пустой элемент
        logger.warning(f"Error creating text item for value '{value}': {e}")
        item = QTableWidgetItem('')
        item.setText('')
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return item


def _ensure_table_update(table: QTableWidget):
    """Гарантирует обновление отображения таблицы"""
    try:
        # Принудительное обновление размеров столбцов
        table.resizeColumnsToContents()
        
        # Немного расширяем столбцы для лучшего вида
        for col in range(table.columnCount()):
            current_width = table.columnWidth(col)
            table.setColumnWidth(col, current_width + 20)
        
        # Обновление размеров строк
        table.resizeRowsToContents()
        
        # Принудительная перерисовка
        table.viewport().update()
        table.update()
        
        # Убеждаемся что заголовки видны
        if table.horizontalHeader():
            table.horizontalHeader().setVisible(True)
            
    except Exception as e:
        logger.error(f"Error updating table display: {e}")


def fill_details_table(table: QTableWidget, details):
    """Заполнение таблицы деталей"""
    if not details:
        table.setRowCount(0)
        return
    
    # Настройка таблицы
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(['Материал', 'Наименование', 'Высота', 'Ширина', 'Количество'])
    table.setRowCount(len(details))
    
    # Заполнение строк
    for row, detail in enumerate(details):
        table.setItem(row, 0, _create_text_item(detail.get('g_marking', '')))
        table.setItem(row, 1, _create_text_item(detail.get('oi_name', '')))
        table.setItem(row, 2, _create_numeric_item(detail.get('height', '')))
        table.setItem(row, 3, _create_numeric_item(detail.get('width', '')))
        table.setItem(row, 4, _create_numeric_item(detail.get('total_qty', '')))
    
    # Гарантированное обновление
    _ensure_table_update(table)


def fill_materials_table(table: QTableWidget, materials):
    """Заполнение таблицы материалов"""
    if not materials:
        table.setRowCount(0)
        return
    
    # Настройка таблицы
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(['Материал', 'Высота', 'Ширина', 'Количество'])
    table.setRowCount(len(materials))
    
    # Заполнение строк
    for row, material in enumerate(materials):
        table.setItem(row, 0, _create_text_item(material.get('g_marking', '')))
        table.setItem(row, 1, _create_numeric_item(material.get('height', '')))
        table.setItem(row, 2, _create_numeric_item(material.get('width', '')))
        table.setItem(row, 3, _create_numeric_item(material.get('qty', '')))
    
    # Гарантированное обновление
    _ensure_table_update(table)


def fill_remainders_table(table: QTableWidget, remainders):
    """Заполнение таблицы остатков"""
    if not remainders:
        table.setRowCount(0)
        return
    
    # Настройка таблицы
    table.setColumnCount(4)
    table.setHorizontalHeaderLabels(['Материал', 'Высота', 'Ширина', 'Количество'])
    table.setRowCount(len(remainders))
    
    # Заполнение строк
    for row, remainder in enumerate(remainders):
        table.setItem(row, 0, _create_text_item(remainder.get('g_marking', '')))
        table.setItem(row, 1, _create_numeric_item(remainder.get('height', '')))
        table.setItem(row, 2, _create_numeric_item(remainder.get('width', '')))
        table.setItem(row, 3, _create_numeric_item(remainder.get('qty', '')))
    
    # Гарантированное обновление
    _ensure_table_update(table)


def update_remnants_result_table(table: QTableWidget, result, min_remnant_width=100, min_remnant_height=100):
    """Обновление таблицы деловых остатков результатов"""
    # Временно отключаем сортировку для корректной загрузки данных
    table.setSortingEnabled(False)
    
    # Собираем полезные остатки из всех листов с правильными атрибутами
    remnants_grouped = {}
    
    for sheet_layout in result.sheets:
        g_marking = sheet_layout.sheet.material
        
        for rect in sheet_layout.free_rectangles:
            try:
                # Используем улучшенную логику: большая сторона >= большего параметра, меньшая >= меньшего
                element_min_side = min(rect.width, rect.height)
                element_max_side = max(rect.width, rect.height)
                param_min = min(min_remnant_width, min_remnant_height)
                param_max = max(min_remnant_width, min_remnant_height)
                
                if element_min_side > param_min and element_max_side > param_max:
                    # Используем материал листа как g_marking
                    key = (g_marking, rect.width, rect.height)
                    if key in remnants_grouped:
                        remnants_grouped[key] += 1
                    else:
                        remnants_grouped[key] = 1
                        
            except AttributeError as e:
                logger.warning(f"Free rectangle missing required attributes: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing free rectangle: {e}")
    
    # Заполнение таблицы
    table.setRowCount(len(remnants_grouped))
    
    for row, ((g_marking, width, height), count) in enumerate(remnants_grouped.items()):
        try:
            table.setItem(row, 0, _create_text_item(g_marking))
            table.setItem(row, 1, _create_numeric_item(height))
            table.setItem(row, 2, _create_numeric_item(width))
            table.setItem(row, 3, _create_numeric_item(count))
            
        except ValueError as e:
            logger.warning(f"Invalid value in remnants table row {row}: {e}")
        except Exception as e:
            logger.error(f"Error setting remnants table item in row {row}: {e}")
    
    # Включаем сортировку обратно
    table.setSortingEnabled(True)
    # Гарантированное обновление
    _ensure_table_update(table)


def update_waste_results_table(table: QTableWidget, result):
    """Обновление таблицы отходов результатов"""
    # Временно отключаем сортировку для корректной загрузки данных
    table.setSortingEnabled(False)
    
    # Собираем все отходы со всех листов
    waste_grouped = {}
    
    for sheet_layout in result.sheets:
        g_marking = sheet_layout.sheet.material
        
        # Обрабатываем waste_rectangles если они есть
        if hasattr(sheet_layout, 'waste_rectangles'):
            for waste_rect in sheet_layout.waste_rectangles:
                try:
                    if waste_rect.width > 0 and waste_rect.height > 0:
                        key = (g_marking, waste_rect.width, waste_rect.height)
                        if key in waste_grouped:
                            waste_grouped[key] += 1
                        else:
                            waste_grouped[key] = 1
                            
                except AttributeError as e:
                    logger.error(f"Waste rectangle missing required attributes: {e}")
                except Exception as e:
                    logger.error(f"Error processing waste rectangle: {e}")
    
    # Заполнение таблицы отходов
    table.setRowCount(len(waste_grouped))
    
    for row, ((g_marking, width, height), count) in enumerate(waste_grouped.items()):
        try:
            table.setItem(row, 0, _create_text_item(g_marking))
            table.setItem(row, 1, _create_numeric_item(height))
            table.setItem(row, 2, _create_numeric_item(width))
            table.setItem(row, 3, _create_numeric_item(count))
            
        except ValueError as e:
            logger.warning(f"Invalid value in waste table row {row}: {e}")
        except Exception as e:
            logger.error(f"Error setting waste table item in row {row}: {e}")
    
    # Включаем сортировку обратно
    table.setSortingEnabled(True)
    # Гарантированное обновление
    _ensure_table_update(table)


def update_current_sheet_waste_table(table: QTableWidget, sheet_data):
    """Обновление таблицы отходов для текущего листа"""
    # Временно отключаем сортировку
    sorting_enabled = table.isSortingEnabled()
    table.setSortingEnabled(False)
    
    # Собираем отходы для текущего листа
    waste_rectangles = sheet_data.get('waste_rectangles', [])
    g_marking = sheet_data.get('g_marking', '')
    
    # Очищаем текущую таблицу отходов
    table.setRowCount(0)
    
    # ИСПРАВЛЕНО: Правильное заполнение таблицы отходов
    if waste_rectangles:
        table.setRowCount(len(waste_rectangles))
        
        for row, waste_rect in enumerate(waste_rectangles):
            try:
                # Проверяем наличие необходимых ключей
                if all(key in waste_rect for key in ['width', 'height']):
                    table.setItem(row, 0, _create_text_item(g_marking))
                    table.setItem(row, 1, _create_numeric_item(waste_rect['height']))
                    table.setItem(row, 2, _create_numeric_item(waste_rect['width']))
                    table.setItem(row, 3, _create_numeric_item(1))  # Количество отходов
                    
            except TypeError as e:
                logger.error(f"Invalid waste rectangle format in row {row}: {e}")
            except Exception as e:
                logger.error(f"Error processing waste rectangle in row {row}: {e}")
    
    # Восстанавливаем сортировку
    table.setSortingEnabled(sorting_enabled)
    
    # Гарантированное обновление
    _ensure_table_update(table)


class TableManager:
    """Менеджер для управления таблицами"""
    
    def __init__(self):
        self.tables = {}
    
    def register_table(self, name, table):
        """Регистрация таблицы"""
        self.tables[name] = table
    
    def get_table(self, name):
        """Получение таблицы по имени"""
        return self.tables.get(name)
    
    def clear_all(self):
        """Очистка всех таблиц"""
        for table in self.tables.values():
            table.setRowCount(0) 