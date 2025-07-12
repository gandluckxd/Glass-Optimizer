"""
Диалоги для приложения оптимизации 2D раскроя
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QProgressBar, QApplication, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from datetime import datetime
from .config import DIALOG_STYLE


class DebugDialog(QDialog):
    """Диалог отладки загрузки данных"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отладка загрузки данных")
        self.setModal(False)  # Не модальный, чтобы можно было видеть консоль
        self.setMinimumSize(600, 500)
        
        # Центрирование относительно родительского окна
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 600) // 2
            y = parent_geo.y() + (parent_geo.height() - 500) // 2
            self.setGeometry(x, y, 600, 500)
        
        # Применение темной темы
        self.setStyleSheet(DIALOG_STYLE)
        
        self.init_ui()
        
        # Начальное сообщение
        self.add_step("🚀 Инициализация загрузки данных...")
        
        print("🔧 DEBUG: Диалог отладки инициализирован")

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        title_label = QLabel("Отладка загрузки данных API")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Область текста
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 9))
        layout.addWidget(self.text_area)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def add_step(self, message):
        """Добавление шага в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        self.text_area.append(formatted_message)
        self.text_area.verticalScrollBar().setValue(
            self.text_area.verticalScrollBar().maximum()
        )
        
        # Принудительная обработка событий для обновления интерфейса
        QApplication.processEvents()
        
        print(f"🔧 DEBUG: {formatted_message}")

    def add_success(self, message):
        """Добавление сообщения об успехе"""
        self.add_step(f"✅ {message}")

    def add_error(self, message):
        """Добавление сообщения об ошибке"""
        self.add_step(f"❌ {message}")

    def add_warning(self, message):
        """Добавление предупреждения"""
        self.add_step(f"⚠️ {message}")

    def add_info(self, message):
        """Добавление информационного сообщения"""
        self.add_step(f"ℹ️ {message}")

    def add_data(self, title, data):
        """Добавление данных с заголовком"""
        self.add_step(f"📊 {title}:")
        if isinstance(data, dict):
            for key, value in data.items():
                self.add_step(f"    {key}: {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data[:10]):  # Показываем только первые 10 элементов
                self.add_step(f"    [{i}]: {item}")
            if len(data) > 10:
                self.add_step(f"    ... и еще {len(data) - 10} элементов")
        else:
            self.add_step(f"    {data}")

    def clear_log(self):
        """Очистка лога"""
        self.text_area.clear()
        self.add_step("🧹 Лог очищен")


class ProgressDialog(QDialog):
    """Диалог прогресса для длительных операций"""
    
    # Сигнал для отмены операции
    cancelled = pyqtSignal()
    
    def __init__(self, parent=None, title="Обработка...", message="Выполняется операция..."):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(400, 150)
        
        # Центрирование относительно родительского окна
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - 400) // 2
            y = parent_geo.y() + (parent_geo.height() - 150) // 2
            self.setGeometry(x, y, 400, 150)
        
        # Применение темной темы
        self.setStyleSheet(DIALOG_STYLE)
        
        self.init_ui(message)
        
        # Флаг отмены
        self.is_cancelled = False
    
    def init_ui(self, message):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        
        # Сообщение
        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)
        
        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Кнопка отмены
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.cancel_operation)
        layout.addWidget(self.cancel_btn)
        
        self.setLayout(layout)
    
    def set_message(self, message):
        """Изменение сообщения"""
        self.message_label.setText(message)
        QApplication.processEvents()
    
    def set_progress(self, value, maximum=100):
        """Установка прогресса"""
        # Убираем лишнюю установку range, он теперь в init_ui
        self.progress_bar.setValue(int(value))
        QApplication.processEvents()
    
    def cancel_operation(self):
        """Отмена операции"""
        self.is_cancelled = True
        self.cancelled.emit()
        self.close()


def show_centered_message(parent, title, message, icon_type="information"):
    """Показ центрированного сообщения"""
    
    # Создаем сообщение
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    
    # Устанавливаем иконку
    if icon_type == "information":
        msg_box.setIcon(QMessageBox.Information)
    elif icon_type == "warning":
        msg_box.setIcon(QMessageBox.Warning)
    elif icon_type == "critical":
        msg_box.setIcon(QMessageBox.Critical)
    
    # Применяем стиль
    msg_box.setStyleSheet(DIALOG_STYLE)
    
    # Центрируем относительно родительского окна
    if parent:
        parent_geo = parent.geometry()
        msg_box.move(
            parent_geo.x() + (parent_geo.width() - msg_box.width()) // 2,
            parent_geo.y() + (parent_geo.height() - msg_box.height()) // 2
        )
    
    return msg_box.exec_() 