"""
Диалог для управления паролями приложения
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QPushButton, QLabel, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt
from .password_manager import PasswordManager

class PasswordManagementDialog(QDialog):
    """Диалог для управления паролями"""
    
    def __init__(self, password_manager: PasswordManager, parent=None):
        super().__init__(parent)
        self.password_manager = password_manager
        self.setWindowTitle("Управление паролями")
        self.setModal(True)
        self.setFixedSize(800, 600)
        self.init_ui()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)
        
        # Заголовок
        title_label = QLabel("Управление паролями для критических параметров")
        title_label.setStyleSheet("font-weight: bold; font-size: 14pt; color: #ffffff;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Группа для пароля "% отхода для деловых остатков"
        remainder_group = QGroupBox("🔒 Пароль для '% отхода для деловых остатков'")
        remainder_layout = QFormLayout(remainder_group)
        
        remainder_info = QLabel("Защищает изменение критического параметра оптимизации")
        remainder_info.setStyleSheet("color: #cccccc; font-size: 10pt;")
        remainder_layout.addRow(remainder_info)
        
        remainder_buttons = QHBoxLayout()
        
        change_remainder_btn = QPushButton("Изменить пароль")
        change_remainder_btn.clicked.connect(lambda: self.change_password('remainder_waste_percent'))
        remainder_buttons.addWidget(change_remainder_btn)
        
        reset_remainder_btn = QPushButton("Сбросить к дефолту")
        reset_remainder_btn.clicked.connect(lambda: self.reset_password('remainder_waste_percent'))
        remainder_buttons.addWidget(reset_remainder_btn)
        
        remainder_layout.addRow(remainder_buttons)
        layout.addWidget(remainder_group)
        
        # Группа для пароля "Сохранить параметры по умолчанию"
        save_group = QGroupBox("🔒 Пароль для 'Сохранить параметры по умолчанию'")
        save_layout = QFormLayout(save_group)
        
        save_info = QLabel("Защищает сохранение настроек по умолчанию")
        save_info.setStyleSheet("color: #cccccc; font-size: 10pt;")
        save_layout.addRow(save_info)
        
        save_buttons = QHBoxLayout()
        
        change_save_btn = QPushButton("Изменить пароль")
        change_save_btn.clicked.connect(lambda: self.change_password('save_default_settings'))
        save_buttons.addWidget(change_save_btn)
        
        reset_save_btn = QPushButton("Сбросить к дефолту")
        reset_save_btn.clicked.connect(lambda: self.reset_password('save_default_settings'))
        save_buttons.addWidget(reset_save_btn)
        
        save_layout.addRow(save_buttons)
        layout.addWidget(save_group)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        buttons_layout.addWidget(close_btn)
        
        layout.addLayout(buttons_layout)
    
    def change_password(self, action: str):
        """Изменение пароля"""
        if self.password_manager.change_password(action, self):
            display_name = self.password_manager.get_display_name(action)
            QMessageBox.information(
                self,
                "Успех",
                f"Пароль для '{display_name}' успешно изменен!",
                QMessageBox.Ok
            )
    
    def reset_password(self, action: str):
        """Сброс пароля к дефолтному значению"""
        display_name = self.password_manager.get_display_name(action)
        reply = QMessageBox.question(
            self,
            "Подтверждение сброса",
            f"Вы уверены, что хотите сбросить пароль для '{display_name}' к дефолтному значению?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.password_manager.reset_to_default(action):
                QMessageBox.information(
                    self,
                    "Пароль сброшен",
                    f"Пароль для '{display_name}' сброшен к дефолтному значению.",
                    QMessageBox.Ok
                )
            else:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Не удалось сбросить пароль.",
                    QMessageBox.Ok
                ) 