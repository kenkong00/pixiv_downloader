# Pixiv Downloader - 主程序入口
"""
Pixiv 图片批量下载器 GUI 应用
支持多任务并发下载、实时进度显示、断点续传等功能
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.main_window import MainWindow


def main():
    # 启用高 DPI 支持
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    # 创建应用实例
    app = QApplication(sys.argv)
    app.setApplicationName("Pixiv Downloader")
    app.setApplicationDisplayName("Pixiv 图片批量下载器")

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 运行事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
