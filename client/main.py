#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Точка входа в приложение оптимизации 2D раскроя
Минимальная реализация - только запуск приложения
"""

import sys
import os

# Добавляем папку проекта в путь для корректного импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Главная функция - точка входа в приложение"""
    try:
        from PyQt5.QtWidgets import QApplication
        from gui.main_window import OptimizerWindow
        
        app = QApplication(sys.argv)
        window = OptimizerWindow()
        # Если передан аргумент командной строки — идентификатор сменного задания,
        # автоматически подставляем его в соответствующее поле интерфейса
        if len(sys.argv) > 1:
            window.set_task_id(sys.argv[1])
        
        # Запуск в максимизированном окне
        window.showMaximized()
        
        sys.exit(app.exec_())
        
    except ImportError as e:
        print(f"Import Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"Critical Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 