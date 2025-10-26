"""
Менеджер данных для приложения оптимизации 2D раскроя
"""

import threading
import json
import os
from PyQt5.QtCore import QObject, pyqtSignal
from core.api_client import get_details_raw, get_warehouse_main_material, get_warehouse_remainders, check_api_connection
from core.optimizer_core import optimize




class DataManager(QObject):
    """Менеджер для работы с данными"""
    
    # Сигналы для thread-safe коммуникации
    debug_step_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str, str, str)  # title, message, icon
    success_signal = pyqtSignal()
    data_loaded_signal = pyqtSignal(dict, list, list)  # details_data, remainders, materials
    restore_button_signal = pyqtSignal()
    
    # Сигналы для оптимизации
    optimization_result_signal = pyqtSignal(object)  # OptimizationResult
    optimization_error_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_details = []
        self.current_materials = []
        self.current_remainders = []
        self.optimization_result = None
    
    def load_data_async(self, grorderid):
        """Асинхронная загрузка данных с API"""
        if not check_api_connection():
            self.error_signal.emit("API недоступен", "API сервер недоступен", "warning")
            return
        
        def load_data():
            try:
                self.debug_step_signal.emit(f"🔄 Загрузка данных для заказа {grorderid}...")
                
                # Загрузка деталей
                details_data = get_details_raw(grorderid)
                self.debug_step_signal.emit(f"✅ Загружено {len(details_data.get('details', []))} деталей")
                
                # Получаем уникальные goodsid из деталей для загрузки остатков и материалов
                unique_goodsids = set()
                for detail in details_data.get('details', []):
                    goodsid = detail.get('goodsid')
                    if goodsid:
                        unique_goodsids.add(goodsid)
                
                self.debug_step_signal.emit(f"🔍 Найдено {len(unique_goodsids)} уникальных материалов")
                
                # Загрузка остатков и материалов для каждого goodsid
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
                        self.debug_step_signal.emit(f"⚠️ Ошибка загрузки для goodsid {goodsid}: {e}")
                        continue
                
                self.debug_step_signal.emit(f"✅ Загружено {len(all_remainders)} остатков")
                self.debug_step_signal.emit(f"✅ Загружено {len(all_materials)} материалов")
                
                # Передаем данные в UI
                self.data_loaded_signal.emit(details_data, all_remainders, all_materials)
                self.success_signal.emit()
                
            except Exception as e:
                self.debug_step_signal.emit(f"❌ Ошибка загрузки: {e}")
                self.error_signal.emit("Ошибка загрузки", str(e), "critical")
            finally:
                self.restore_button_signal.emit()
        
        # Запускаем в потоке
        thread = threading.Thread(target=load_data, daemon=True)
        thread.start()
    
    def update_data(self, details_data, remainders, materials):
        """Обновление текущих данных"""
        self.current_details = details_data.get('details', [])
        self.current_materials = materials
        self.current_remainders = remainders
    
    def run_optimization_async(self, progress_callback=None):
        """Асинхронная оптимизация"""
        def run_optimization():
            try:
                if progress_callback:
                    def progress_wrapper(percent):
                        # Thread-safe обновление прогресса через сигнал
                        progress_callback(percent)
                else:
                    progress_wrapper = None
                
                # Запуск оптимизации
                # Пробрасываем параметры оптимизации из core.config (с маппингом ключей)
                try:
                    from core.config import DEFAULT_OPTIMIZATION_PARAMS as DEFAULTS
                except Exception:
                    DEFAULTS = {}

                params = {}
                if DEFAULTS:
                    # Маппинг имён параметров GUI/CORE -> optimize()
                    if 'target_waste_percent' in DEFAULTS:
                        params['target_waste_percent'] = DEFAULTS['target_waste_percent']
                    if 'remainder_waste_percent' in DEFAULTS:
                        params['remainder_waste_percent'] = DEFAULTS['remainder_waste_percent']
                    if 'allow_rotation' in DEFAULTS:
                        params['allow_rotation'] = DEFAULTS['allow_rotation']
                    # GUI: min_cut_size -> optimize: min_waste_side
                    if 'min_cut_size' in DEFAULTS:
                        params['min_waste_side'] = DEFAULTS['min_cut_size']
                    # GUI: blade_width -> optimize: cutting_width
                    if 'blade_width' in DEFAULTS:
                        params['cutting_width'] = DEFAULTS['blade_width']
                    # GUI: use_remainders -> optimize: use_warehouse_remnants
                    if 'use_remainders' in DEFAULTS:
                        params['use_warehouse_remnants'] = DEFAULTS['use_remainders']
                    # Если заданы размеры деловых остатков
                    if 'min_remnant_width' in DEFAULTS:
                        params['min_remnant_width'] = DEFAULTS['min_remnant_width']
                    if 'min_remnant_height' in DEFAULTS:
                        params['min_remnant_height'] = DEFAULTS['min_remnant_height']

                result = optimize(
                    details=self.current_details,
                    materials=self.current_materials,
                    remainders=self.current_remainders,
                    params=params if params else None,
                    progress_fn=progress_wrapper
                )
                
                if result and result.success:
                    self.optimization_result = result
                    self.optimization_result_signal.emit(result)
                else:
                    # Используем детальное сообщение из результата оптимизации
                    error_msg = result.message if result else "Оптимизация не дала результатов"
                    self.optimization_error_signal.emit(error_msg)
                    
            except Exception as e:
                error_msg = f"Ошибка оптимизации: {str(e)}"
                self.optimization_error_signal.emit(error_msg)
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=run_optimization, daemon=True)
        thread.start()
    
    def get_optimization_params(self):
        """Получение параметров оптимизации"""
        from gui.config import OPTIMIZATION_DEFAULTS
        return OPTIMIZATION_DEFAULTS.copy()
    
    def has_data(self):
        """Проверка наличия загруженных данных"""
        return bool(self.current_details and self.current_materials and self.current_remainders)
    
    def has_optimization_result(self):
        """Проверка наличия результата оптимизации"""
        return self.optimization_result is not None
    
    def clear_data(self):
        """Очистка всех данных"""
        self.current_details = []
        self.current_materials = []
        self.current_remainders = []
        self.optimization_result = None 