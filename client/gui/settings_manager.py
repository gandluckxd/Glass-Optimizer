"""
Менеджер настроек для приложения оптимизации 2D раскроя
Позволяет сохранять и загружать пользовательские настройки по умолчанию
"""

import json
import os
from typing import Dict, Any, Optional

class SettingsManager:
    """Класс для управления настройками пользователя"""
    
    def __init__(self, settings_file: str = "user_settings.json"):
        """
        Инициализация менеджера настроек
        
        Args:
            settings_file: Путь к файлу настроек
        """
        self.settings_file = settings_file
        self.default_settings = {
            'min_remnant_width': 180,
            'min_remnant_height': 100,
            'target_waste_percent': 5,
            'min_cut_size': 10,
            'use_remainders': True,
            'allow_rotation': True
        }
    
    def load_settings(self) -> Dict[str, Any]:
        """
        Загрузка настроек из файла
        
        Returns:
            Словарь с настройками или значения по умолчанию
        """
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # Объединяем с дефолтными настройками на случай, если в файле нет всех параметров
                    merged_settings = self.default_settings.copy()
                    merged_settings.update(settings)
                    return merged_settings
            else:
                return self.default_settings.copy()
        except Exception as e:
            print(f"Ошибка при загрузке настроек: {e}")
            return self.default_settings.copy()
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Сохранение настроек в файл
        
        Args:
            settings: Словарь с настройками для сохранения
            
        Returns:
            True если сохранение прошло успешно, False в противном случае
        """
        try:
            # Создаем директорию если её нет
            os.makedirs(os.path.dirname(self.settings_file) if os.path.dirname(self.settings_file) else '.', exist_ok=True)
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении настроек: {e}")
            return False
    
    def get_default_settings(self) -> Dict[str, Any]:
        """
        Получение настроек по умолчанию
        
        Returns:
            Словарь с настройками по умолчанию
        """
        return self.default_settings.copy()
    
 