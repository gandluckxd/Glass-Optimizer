"""
Менеджер паролей для защиты критических параметров приложения
"""

import hashlib
import json
import os
from typing import Optional, Dict, Any, Set
from PyQt5.QtWidgets import QInputDialog, QMessageBox, QWidget, QLineEdit
from PyQt5.QtCore import Qt

class PasswordManager:
    """Класс для управления паролями и их проверки"""
    
    def __init__(self, password_file: str = "passwords.json"):
        """
        Инициализация менеджера паролей
        
        Args:
            password_file: Путь к файлу с хешами паролей
        """
        self.password_file = password_file
        self.default_passwords = {
            'remainder_waste_percent': 'admin123',
            'save_default_settings': 'admin456'
        }
        # Кэш успешных проверок пароля в рамках сессии
        self._verified_actions: Set[str] = set()
        self._load_passwords()
    
    def _load_passwords(self):
        """Загрузка паролей из файла или создание дефолтных"""
        try:
            if os.path.exists(self.password_file):
                with open(self.password_file, 'r', encoding='utf-8') as f:
                    self.passwords = json.load(f)
            else:
                # Создаем дефолтные пароли
                self.passwords = {}
                for key, password in self.default_passwords.items():
                    self.passwords[key] = self._hash_password(password)
                self._save_passwords()
        except Exception as e:
            print(f"Ошибка при загрузке паролей: {e}")
            # Создаем дефолтные пароли в случае ошибки
            self.passwords = {}
            for key, password in self.default_passwords.items():
                self.passwords[key] = self._hash_password(password)
    
    def _save_passwords(self):
        """Сохранение паролей в файл"""
        try:
            os.makedirs(os.path.dirname(self.password_file) if os.path.dirname(self.password_file) else '.', exist_ok=True)
            with open(self.password_file, 'w', encoding='utf-8') as f:
                json.dump(self.passwords, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка при сохранении паролей: {e}")
    
    def _hash_password(self, password: str) -> str:
        """Хеширование пароля"""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Проверка пароля"""
        return self._hash_password(password) == stored_hash
    
    def check_password(self, action: str, parent_widget: Optional[QWidget] = None) -> bool:
        """
        Проверка пароля для конкретного действия
        
        Args:
            action: Действие для которого проверяется пароль
            parent_widget: Родительский виджет для диалога
            
        Returns:
            True если пароль введен правильно, False в противном случае
        """
        if action not in self.passwords:
            print(f"Неизвестное действие: {action}")
            return False
        
        # Проверяем, была ли уже успешная проверка пароля для этого действия в рамках сессии
        if action in self._verified_actions:
            return True
        
        # Запрашиваем пароль у пользователя
        password, ok = QInputDialog.getText(
            parent_widget,
            "Введите пароль",
            f"Для изменения параметра '{action}' требуется пароль:",
            QLineEdit.Password,
            ""
        )
        
        if not ok:
            return False
        
        # Проверяем пароль
        if self._verify_password(password, self.passwords[action]):
            # Добавляем действие в кэш успешных проверок
            self._verified_actions.add(action)
            return True
        else:
            QMessageBox.warning(
                parent_widget,
                "Неверный пароль",
                "Введен неверный пароль. Доступ запрещен.",
                QMessageBox.Ok
            )
            return False
    
    def clear_session_cache(self):
        """Очистка кэша успешных проверок пароля (для новой сессии)"""
        self._verified_actions.clear()
    
    def remove_from_cache(self, action: str):
        """Удаление конкретного действия из кэша (для принудительной повторной проверки)"""
        self._verified_actions.discard(action)
    
    def change_password(self, action: str, parent_widget: Optional[QWidget] = None) -> bool:
        """
        Изменение пароля для конкретного действия
        
        Args:
            action: Действие для которого изменяется пароль
            parent_widget: Родительский виджет для диалога
            
        Returns:
            True если пароль изменен успешно, False в противном случае
        """
        if action not in self.passwords:
            print(f"Неизвестное действие: {action}")
            return False
        
        # Запрашиваем текущий пароль
        current_password, ok = QInputDialog.getText(
            parent_widget,
            "Текущий пароль",
            f"Введите текущий пароль для '{action}':",
            QLineEdit.Password,
            ""
        )
        
        if not ok:
            return False
        
        # Проверяем текущий пароль
        if not self._verify_password(current_password, self.passwords[action]):
            QMessageBox.warning(
                parent_widget,
                "Неверный пароль",
                "Введен неверный текущий пароль.",
                QMessageBox.Ok
            )
            return False
        
        # Запрашиваем новый пароль
        new_password, ok = QInputDialog.getText(
            parent_widget,
            "Новый пароль",
            f"Введите новый пароль для '{action}':",
            QLineEdit.Password,
            ""
        )
        
        if not ok or not new_password:
            return False
        
        # Подтверждаем новый пароль
        confirm_password, ok = QInputDialog.getText(
            parent_widget,
            "Подтверждение пароля",
            f"Повторите новый пароль для '{action}':",
            QLineEdit.Password,
            ""
        )
        
        if not ok or new_password != confirm_password:
            QMessageBox.warning(
                parent_widget,
                "Ошибка",
                "Пароли не совпадают.",
                QMessageBox.Ok
            )
            return False
        
        # Сохраняем новый пароль
        self.passwords[action] = self._hash_password(new_password)
        self._save_passwords()
        
        # Удаляем действие из кэша, так как пароль изменился
        self._verified_actions.discard(action)
        
        QMessageBox.information(
            parent_widget,
            "Пароль изменен",
            f"Пароль для '{action}' успешно изменен.",
            QMessageBox.Ok
        )
        
        return True
    
    def get_default_password(self, action: str) -> Optional[str]:
        """Получение дефолтного пароля для действия"""
        return self.default_passwords.get(action)
    
    def reset_to_default(self, action: str) -> bool:
        """Сброс пароля к дефолтному значению"""
        if action in self.default_passwords:
            self.passwords[action] = self._hash_password(self.default_passwords[action])
            self._save_passwords()
            # Удаляем действие из кэша, так как пароль изменился
            self._verified_actions.discard(action)
            return True
        return False 