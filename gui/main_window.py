"""
Pixiv 图片批量下载器 - 主窗口
"""

import os
import sys
import uuid
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QMenuBar, QMenu, QToolBar, QStatusBar,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QProgressBar, QGroupBox, QTextEdit, QSplitter,
    QMessageBox, QFileDialog, QHeaderView, QApplication, QCheckBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont, QAction, QContextMenuEvent

# 导入项目模块
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.task_model import DownloadTask, TaskStatus
from models.config import Config
from core.auth import PixivAuth
from core.civitai_auth import CivitaiAuth
from core.downloader import DownloadEngine
from core.url_parser import URLParser
from core.task_history import TaskHistory
from core.civitai_downloader import CivitaiDownloadWorker
from gui.login_dialog import LoginDialog
from gui.task_dialog import TaskDialog
from gui.civitai_task_dialog import CivitaiTaskDialog


class MainWindow(QMainWindow):
    """主窗口类"""

    def __init__(self):
        super().__init__()

        # 初始化组件
        self.config = Config()
        self.auth = PixivAuth()
        self.civitai_auth = CivitaiAuth()
        self.engine = DownloadEngine(
            max_concurrent=self.config.get('download', 'max_concurrent_tasks', 3),
            session=self.auth.get_session()
        )
        
        # 初始化历史记录
        self.history = TaskHistory()

        # Civitai 任务追踪
        self._civitai_tasks: Dict[str, dict] = {}  # task_id -> {worker, output_dir, ...}
        self._civitai_row_map: Dict[str, int] = {}  # task_id -> table row

        # 剪贴板监控相关
        self._clipboard_last_text = ""  # 上次检测到的剪贴板内容
        self._clipboard_timer = QTimer()  # 定时器，用于周期性检查剪贴板
        self._clipboard_timer.setInterval(500)  # 每 500ms 检查一次
        self._clipboard_timer.timeout.connect(self._check_clipboard)
        self._current_task_dialog = None  # 当前打开的任务对话框（用于更新而非新建）
        self._current_civitai_dialog = None  # 当前打开的 Civitai 任务对话框

        # 设置窗口属性
        self.setWindowTitle("Pixiv 图片批量下载器")
        self.setMinimumSize(1000, 700)

        # 恢复窗口位置和大小
        self._restore_window_geometry()

        # 初始化 UI
        self._init_ui()
        self._connect_signals()
        self._update_status_bar()

    def _restore_window_geometry(self):
        """恢复窗口位置和大小"""
        x = self.config.get('window', 'x', 100)
        y = self.config.get('window', 'y', 100)
        w = self.config.get('window', 'width', 1200)
        h = self.config.get('window', 'height', 800)
        self.setGeometry(x, y, w, h)

        if self.config.get('window', 'maximized', False):
            self.showMaximized()

    def _save_window_geometry(self):
        """保存窗口位置和大小"""
        if not self.isMaximized():
            geo = self.geometry()
            self.config.set('window', 'x', geo.x())
            self.config.set('window', 'y', geo.y())
            self.config.set('window', 'width', geo.width())
            self.config.set('window', 'height', geo.height())
        self.config.set('window', 'maximized', self.isMaximized())

    def _init_ui(self):
        """初始化用户界面"""

        # 中央部件 - 使用分割器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ===== 工具栏区域（使用 GroupBox 包裹）=====
        toolbar_group = QGroupBox("操作")
        toolbar_layout = QHBoxLayout(toolbar_group)

        # 新建 Pixiv 任务按钮
        self.btn_new_task = QPushButton("+ Pixiv任务")
        self.btn_new_task.setMinimumHeight(35)
        self.btn_new_task.setStyleSheet("font-weight: bold; font-size: 13px;")
        toolbar_layout.addWidget(self.btn_new_task)

        # 新建 Civitai 任务按钮
        self.btn_civitai_task = QPushButton("+ Civitai任务")
        self.btn_civitai_task.setMinimumHeight(35)
        self.btn_civitai_task.setStyleSheet("font-weight: bold; font-size: 13px;")
        toolbar_layout.addWidget(self.btn_civitai_task)

        # 开始按钮
        self.btn_start_all = QPushButton("▶ 全部开始")
        self.btn_start_all.setMinimumHeight(35)
        toolbar_layout.addWidget(self.btn_start_all)

        # 暂停按钮
        self.btn_pause = QPushButton("⏸ 暂停选中")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setMinimumHeight(35)
        toolbar_layout.addWidget(self.btn_pause)

        # 停止按钮
        self.btn_stop = QPushButton("⏹ 停止选中")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setMinimumHeight(35)
        toolbar_layout.addWidget(self.btn_stop)

        # 删除按钮组 + 剪贴板监控
        btn_delete_layout = QHBoxLayout()
        self.btn_delete_completed = QPushButton("🗑 删除已完成")
        self.btn_delete_completed.setMinimumHeight(35)
        btn_delete_layout.addWidget(self.btn_delete_completed)

        self.btn_delete_all = QPushButton("🗑 删除全部")
        self.btn_delete_all.setMinimumHeight(35)
        btn_delete_layout.addWidget(self.btn_delete_all)

        # 剪贴板监控勾选框
        self.chk_clipboard_monitor = QCheckBox("剪贴板监控")
        self.chk_clipboard_monitor.setToolTip("开启后，复制 Pixiv 作品链接会自动新建任务")
        btn_delete_layout.addWidget(self.chk_clipboard_monitor)

        toolbar_layout.addLayout(btn_delete_layout)

        toolbar_layout.addStretch()

        # 登录状态标签
        self.lbl_login_status = QLabel("● 未登录")
        self.lbl_login_status.setStyleSheet("color: red; font-weight: bold;")
        toolbar_layout.addWidget(self.lbl_login_status)

        main_layout.addWidget(toolbar_group)

        # ===== 任务列表表格 =====
        table_group = QGroupBox("任务列表")
        table_layout = QVBoxLayout(table_group)

        self.table_tasks = QTableWidget()
        self.table_tasks.setColumnCount(6)
        self.table_tasks.setHorizontalHeaderLabels([
            "", "状态", "目录名称", "进度", "速度", "操作"
        ])

        # 设置列宽
        header = self.table_tasks.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)   # 选择框
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)   # 状态
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # 名称
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)   # 进度
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)   # 速度
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)   # 操作

        self.table_tasks.setColumnWidth(0, 30)
        self.table_tasks.setColumnWidth(1, 80)
        self.table_tasks.setColumnWidth(3, 150)
        self.table_tasks.setColumnWidth(4, 90)
        self.table_tasks.setColumnWidth(5, 100)

        self.table_tasks.setAlternatingRowColors(True)
        self.table_tasks.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_tasks.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        # 启用右键菜单
        self.table_tasks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_tasks.customContextMenuRequested.connect(self._on_table_context_menu)

        # 连接选择变化信号
        self.table_tasks.itemSelectionChanged.connect(self._on_selection_changed)

        table_layout.addWidget(self.table_tasks)
        main_layout.addWidget(table_group, stretch=1)

        # ===== 详细信息面板 =====
        details_group = QGroupBox("详细信息")
        details_layout = QVBoxLayout(details_group)

        # 进度条 - 任务完成进度
        progress_row = QHBoxLayout()
        progress_row.addWidget(QLabel("任务进度:"))
        self.progress_total = QProgressBar()
        self.progress_total.setMinimumHeight(25)
        self.progress_total.setTextVisible(True)
        self.progress_total.setFormat("%v/%m (%p%)")
        progress_row.addWidget(self.progress_total)
        details_layout.addLayout(progress_row)

        # 信息行1：当前下载状态 + 统计
        info_row1 = QHBoxLayout()
        self.lbl_current = QLabel("当前任务: -")
        info_row1.addWidget(self.lbl_current)
        info_row1.addStretch()
        self.lbl_stats = QLabel("已完成: 0 个任务 | 0 张图片")
        info_row1.addWidget(self.lbl_stats)
        details_layout.addLayout(info_row1)

        # 信息行2：下载速度 + 平均速度
        info_row2 = QHBoxLayout()
        self.lbl_speed = QLabel("当前速度: -")
        info_row2.addWidget(self.lbl_speed)
        info_row2.addStretch()
        self.lbl_avg_speed = QLabel("平均速度: -")
        info_row2.addWidget(self.lbl_avg_speed)
        details_layout.addLayout(info_row2)

        # 日志显示
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(120)
        self.txt_log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        details_layout.addWidget(self.txt_log)

        main_layout.addWidget(details_group)

        # ===== 菜单栏 =====
        self._create_menu_bar()

        # ===== 状态栏 =====
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        action_new_task = QAction("新建任务(&N)", self)
        action_new_task.setShortcut("Ctrl+N")
        action_new_task.triggered.connect(self.on_new_task)
        file_menu.addAction(action_new_task)

        file_menu.addSeparator()

        action_import = QAction("导入任务列表(&I)...", self)
        action_import.triggered.connect(self.on_import_tasks)
        file_menu.addAction(action_import)

        action_export = QAction("导出任务列表(&E)...", self)
        action_export.triggered.connect(self.on_export_tasks)
        file_menu.addAction(action_export)

        file_menu.addSeparator()

        action_exit = QAction("退出(&X)", self)
        action_exit.setShortcut("Alt+F4")
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")

        action_select_all = QAction("全选(&A)", self)
        action_select_all.setShortcut("Ctrl+A")
        action_select_all.triggered.connect(self.table_tasks.selectAll)
        edit_menu.addAction(action_select_all)

        edit_menu.addSeparator()

        action_delete_selected = QAction("删除选中(&D)", self)
        action_delete_selected.setShortcut("Delete")
        action_delete_selected.triggered.connect(self.on_delete_selected)
        edit_menu.addAction(action_delete_selected)

        action_clear_completed = QAction("清除已完成(&C)", self)
        action_clear_completed.triggered.connect(self.on_clear_completed)
        edit_menu.addAction(action_clear_completed)

        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")

        action_login = QAction("登录/设置 Cookie(&L)", self)
        action_login.setShortcut("Ctrl+L")
        action_login.triggered.connect(self.on_login)
        tools_menu.addAction(action_login)

        action_settings = QAction("设置(&S)", self)
        action_settings.setShortcut("Ctrl+,")
        action_settings.triggered.connect(self.on_settings)
        tools_menu.addAction(action_settings)

        tools_menu.addSeparator()

        action_history = QAction("下载历史(&H)...", self)
        action_history.triggered.connect(self.on_show_history)
        tools_menu.addAction(action_history)

        action_retry_failed = QAction("重试失败图片(&R)", self)
        action_retry_failed.setShortcut("Ctrl+R")
        action_retry_failed.triggered.connect(self.on_retry_failed)
        tools_menu.addAction(action_retry_failed)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        action_about = QAction("关于(&A)", self)
        action_about.triggered.connect(self.on_about)
        help_menu.addAction(action_about)

        action_usage = QAction("使用说明(&U)", self)
        action_usage.triggered.connect(self.on_show_usage)
        help_menu.addAction(action_usage)

    def _connect_signals(self):
        """连接信号槽"""
        # 按钮信号
        self.btn_new_task.clicked.connect(self.on_new_task)
        self.btn_civitai_task.clicked.connect(self.on_civitai_task)
        self.btn_start_all.clicked.connect(self.on_start_all)
        self.btn_pause.clicked.connect(self.on_pause_selected)
        self.btn_stop.clicked.connect(self.on_stop_selected)
        self.btn_delete_completed.clicked.connect(self.on_clear_completed)
        self.btn_delete_all.clicked.connect(self.on_delete_all)

        # 剪贴板监控勾选框信号
        self.chk_clipboard_monitor.stateChanged.connect(self._on_clipboard_monitor_toggled)

        # 引擎信号 - 基础
        self.engine.task_added.connect(self._on_task_added)
        self.engine.task_removed.connect(self._on_task_removed)
        self.engine.all_completed.connect(self._on_all_completed)
        self.engine.stats_updated.connect(self._on_stats_updated)

        # 引擎信号 - 实时任务状态更新（关键！）
        self.engine.task_progress_updated.connect(self._on_engine_progress_updated)
        self.engine.task_speed_updated.connect(self._on_engine_speed_updated)
        self.engine.task_status_changed.connect(self._on_engine_status_changed)
        self.engine.task_image_downloaded.connect(self._on_engine_image_downloaded)
        self.engine.task_error.connect(self._on_engine_error)
        self.engine.task_finished.connect(self._on_engine_task_finished)
        self.engine.task_log.connect(self._on_engine_log)

    def _on_selection_changed(self):
        """处理表格选择变化"""
        has_selection = len(self.table_tasks.selectedItems()) > 0
        self.btn_pause.setEnabled(has_selection)
        self.btn_stop.setEnabled(has_selection)

    def _on_table_context_menu(self, pos):
        """任务列表右键菜单"""
        item = self.table_tasks.itemAt(pos)
        if not item:
            return
        row = item.row()
        task_id_item = self.table_tasks.item(row, 0)
        if not task_id_item:
            return
        task_id = task_id_item.data(Qt.ItemDataRole.UserRole)
        
        # 先查 Pixiv 任务
        task = self.engine._find_task(task_id)
        output_dir = None
        if task and task.output_dir:
            output_dir = task.output_dir
        else:
            # 查 Civitai 任务
            civitai_info = self._civitai_tasks.get(task_id)
            if civitai_info:
                output_dir = civitai_info['output_dir']
        
        if not output_dir:
            return

        menu = QMenu(self)
        # 打开目录
        action_open_dir = QAction("打开目录", self)
        action_open_dir.triggered.connect(lambda: self._open_task_directory(output_dir))
        menu.addAction(action_open_dir)
        menu.exec(self.table_tasks.viewport().mapToGlobal(pos))

    def _open_task_directory(self, directory: str):
        """在文件资源管理器中打开指定目录"""
        if os.path.isdir(directory):
            os.startfile(directory)
        else:
            QMessageBox.warning(self, "提示", f"目录不存在：\n{directory}")

    def _on_task_added(self, task: DownloadTask):
        """处理任务添加事件 - 新任务插入到顶部"""
        # 插入到第0行（顶部），新任务在上方
        self.table_tasks.insertRow(0)

        # 填充行数据
        self._update_table_row(0, task)

        # 自动选中新添加的行（顶部）
        self.table_tasks.selectRow(0)

        # 更新日志
        self._log(f"✅ 任务已添加: {task.artwork_name}")

    def _on_task_removed(self, task_id: str):
        """处理任务移除事件"""
        for row in range(self.table_tasks.rowCount()):
            item = self.table_tasks.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                self.table_tasks.removeRow(row)
                break

    def _update_table_row(self, row: int, task: DownloadTask):
        """更新表格中的指定行"""
        # 第0列：复选框（用空白占位）
        checkbox_item = QTableWidgetItem("")
        checkbox_item.setData(Qt.ItemDataRole.UserRole, task.id)
        checkbox_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_tasks.setItem(row, 0, checkbox_item)

        # 第1列：状态
        status_item = QTableWidgetItem(f"{task.status.icon} {task.status.display_name}")
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_tasks.setItem(row, 1, status_item)

        # 第2列：目录名称（鼠标悬停显示完整路径）
        name_item = QTableWidgetItem(task.artwork_name)
        name_item.setToolTip(f"完整路径: {task.output_dir}")
        self.table_tasks.setItem(row, 2, name_item)

        # 第3列：进度（带进度条）
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(5, 2, 5, 2)

        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(task.progress.total_images if task.progress.total_images > 0 else 100)
        progress_bar.setValue(task.progress.current_image)
        progress_bar.setTextVisible(True)
        progress_bar.setFormat(f"{task.progress.current_image}/{task.progress.total_images or '?'}")

        if task.progress.total_images > 0:
            percent = int((task.progress.current_image / task.progress.total_images) * 100)
            progress_bar.setValue(percent)

        progress_layout.addWidget(progress_bar)
        self.table_tasks.setCellWidget(row, 3, progress_widget)

        # 第4列：速度
        speed_item = QTableWidgetItem(task.progress.speed_display)
        speed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_tasks.setItem(row, 4, speed_item)

        # 第5列：操作按钮
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(5, 2, 5, 2)

        if task.status == TaskStatus.DOWNLOADING:
            btn_pause = QPushButton("⏸")
            btn_pause.setToolTip("暂停")
            btn_pause.clicked.connect(lambda _, tid=task.id: self.on_pause_task(tid))
            btn_layout.addWidget(btn_pause)
        elif task.status in [TaskStatus.PAUSED, TaskStatus.STOPPED]:
            btn_resume = QPushButton("▶")
            btn_resume.setToolTip("继续")
            btn_resume.clicked.connect(lambda _, tid=task.id: self.on_resume_task(tid))
            btn_layout.addWidget(btn_resume)

        btn_stop = QPushButton("✕")
        btn_stop.setToolTip("停止并删除")
        btn_stop.clicked.connect(lambda _, tid=task.id: self.on_remove_task(tid))
        btn_layout.addWidget(btn_stop)

        self.table_tasks.setCellWidget(row, 5, btn_widget)

    def _refresh_table_from_engine(self):
        """从引擎刷新整个表格"""
        self.table_tasks.setRowCount(0)

        for task in self.engine.tasks:
            row = self.table_tasks.rowCount()
            self.table_tasks.insertRow(row)
            self._update_table_row(row, task)

    def _on_stats_updated(self, total: int, downloading: int, completed: int):
        """处理统计更新 - 更新总进度条为任务完成进度"""
        if total > 0:
            self.progress_total.setMaximum(total)
            self.progress_total.setValue(completed)  # 只显示已完成数
            self.progress_total.setFormat(f"{completed}/{total} 任务完成 (%p%)")

        # 更新统计标签
        total_images = sum(t.progress.success_count for t in self.engine.tasks)
        self.lbl_stats.setText(f"已完成: {completed} 个任务 | {total_images} 张图片")

        self._update_status_bar()

    def _on_all_completed(self):
        """所有任务完成 - 只记录日志，不弹窗"""
        # 统计所有任务
        total_tasks = len(self.engine.tasks)
        completed_tasks = sum(1 for t in self.engine.tasks if t.status == TaskStatus.COMPLETED)
        total_images = sum(t.progress.success_count for t in self.engine.tasks)
        total_failed = sum(t.progress.fail_count for t in self.engine.tasks)

        # 只在状态栏和日志显示，不弹窗
        self._log(f"🎉 全部完成！共 {completed_tasks}/{total_tasks} 个任务，{total_images} 张图片 (失败: {total_failed})")
        
        # 更新状态栏
        self.status_bar.showMessage(
            f"✅ 全部完成 | {completed_tasks}/{total_tasks} 任务 | {total_images} 张图片"
        )

    def _log(self, message: str):
        """添加日志消息"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{timestamp}] {message}")

        # 自动滚动到底部
        scrollbar = self.txt_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_status_bar(self):
        """更新状态栏"""
        total = len(self.engine.tasks)
        completed = sum(1 for t in self.engine.tasks if t.status == TaskStatus.COMPLETED)
        downloading = sum(1 for t in self.engine.tasks if t.status == TaskStatus.DOWNLOADING)

        total_images = sum(t.progress.success_count for t in self.engine.tasks)

        pixiv_status = "已登录" if self.auth.is_logged_in else "未登录"
        civitai_status = "已登录" if self.civitai_auth.is_logged_in else "未登录"

        self.status_bar.showMessage(
            f"就绪 | Pixiv: {pixiv_status} | Civitai: {civitai_status} | 任务: {total} 个 | 已完成: {completed} 个 | "
            f"正在下载: {downloading} 个 | 共下载: {total_images} 张图片"
        )

        # 更新登录状态标签
        if self.auth.is_logged_in:
            self.lbl_login_status.setText("● Pixiv已登录")
            self.lbl_login_status.setStyleSheet("color: green; font-weight: bold;")
        elif self.civitai_auth.is_logged_in:
            self.lbl_login_status.setText("● Civitai已登录")
            self.lbl_login_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_login_status.setText("● 未登录")
            self.lbl_login_status.setStyleSheet("color: red; font-weight: bold;")

    # ===== 引擎信号处理方法（实时更新 UI）=====

    def _find_row_by_task_id(self, task_id: str) -> int:
        """根据 task_id 查找表格行号"""
        for row in range(self.table_tasks.rowCount()):
            item = self.table_tasks.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                return row
        return -1

    def _on_engine_progress_updated(self, task_id: str, current: int, total: int):
        """处理进度更新 - 更新表格中的进度条"""
        row = self._find_row_by_task_id(task_id)
        if row >= 0:
            task = self.engine._find_task(task_id)
            if task:
                # 重新渲染该行的进度条
                self._update_table_row(row, task)

        # 更新详细信息面板 - 统计所有正在下载的任务
        self._update_current_status()

    def _update_current_status(self):
        """更新"当前任务"状态信息"""
        # 统计各状态任务
        downloading_tasks = [t for t in self.engine.tasks if t.status == TaskStatus.DOWNLOADING]
        completed_tasks = [t for t in self.engine.tasks if t.status == TaskStatus.COMPLETED]

        if downloading_tasks:
            # 有正在下载的任务，统计总下载数
            total_current = sum(t.progress.current_image for t in downloading_tasks)
            total_success = sum(t.progress.success_count for t in completed_tasks)

            # 显示当前下载信息（多任务时汇总）
            if len(downloading_tasks) == 1:
                task = downloading_tasks[0]
                self.lbl_current.setText(
                    f"当前: 正在下载「{task.artwork_name}」第 {task.progress.current_image} 张"
                )
            else:
                self.lbl_current.setText(
                    f"当前: {len(downloading_tasks)} 个任务正在下载，共已下载 {total_current} 张"
                )

        elif completed_tasks:
            # 没有正在下载的任务，但有已完成的
            total_success = sum(t.progress.success_count for t in completed_tasks)
            total_failed = sum(t.progress.fail_count for t in self.engine.tasks)
            self.lbl_current.setText(
                f"已完成: {len(completed_tasks)} 个任务 | 共 {total_success} 张图片 (失败: {total_failed})"
            )
        else:
            # 无任何任务或都在等待中
            pending_count = sum(1 for t in self.engine.tasks if t.status == TaskStatus.PENDING)
            if pending_count > 0:
                self.lbl_current.setText(f"等待中: {pending_count} 个任务")
            else:
                self.lbl_current.setText("当前: -")

    def _on_engine_speed_updated(self, task_id: str, speed: float):
        """处理速度更新 - 更新表格中的速度显示"""
        row = self._find_row_by_task_id(task_id)
        if row >= 0:
            task = self.engine._find_task(task_id)
            if task:
                # 更新速度列
                speed_item = QTableWidgetItem(task.progress.speed_display)
                speed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_tasks.setItem(row, 4, speed_item)

        # 更新详细信息面板
        self.lbl_speed.setText(f"当前速度: {task.progress.speed_display if task else '-'}")

    def _on_engine_status_changed(self, task_id: str, status: str):
        """处理状态变化 - 更新表格中的状态显示"""
        row = self._find_row_by_task_id(task_id)
        if row >= 0:
            task = self.engine._find_task(task_id)
            if task:
                # 完整更新该行（状态、操作按钮等都会变化）
                self._update_table_row(row, task)

        # 更新当前状态信息
        self._update_current_status()
        self._update_status_bar()

    def _on_engine_image_downloaded(self, task_id: str, filename: str, success: bool):
        """处理单张图片下载完成"""
        if success:
            self._log(f"[{task_id[:8]}] ✅ {filename}")
        else:
            self._log(f"[{task_id[:8]}] ❌ {filename}")

    def _on_engine_error(self, task_id: str, error: str):
        """处理错误"""
        self._log(f"[{task_id[:8]}] ⚠️ {error}")

    def _on_engine_task_finished(self, task_id: str):
        """处理单个任务完成 - 保存历史记录"""
        task = self.engine._find_task(task_id)
        if task:
            if task.status == TaskStatus.COMPLETED:
                # 保存到历史记录
                self.history.add_task(task)
                
                # 只记录日志，不弹窗
                self._log(f"✅ 任务完成: {task.artwork_name} (成功: {task.progress.success_count} 张)")
            elif task.status == TaskStatus.STOPPED:
                # 停止的任务也保存（包含失败图片信息）
                if task.progress.fail_count > 0 or len(task.failed_images) > 0:
                    self.history.add_task(task)
                    self._log(f"⏹ 任务已停止: {task.artwork_name} (失败 {len(task.failed_images)} 张待重试)")
                else:
                    self._log(f"⏹ 任务已停止: {task.artwork_name}")
            elif task.status == TaskStatus.FAILED:
                # 失败的任务也保存
                self.history.add_task(task)
                self._log(f"❌ 任务失败: {task.artwork_name} - {task.error_message}")

            # 更新表格显示
            row = self._find_row_by_task_id(task_id)
            if row >= 0:
                self._update_table_row(row, task)

    def _on_engine_log(self, task_id: str, message: str):
        """处理日志消息"""
        self._log(message)

    # ===== 公共方法（供外部调用）=====

    def on_new_task(self):
        """新建 Pixiv 任务"""
        dialog = TaskDialog(self.config, self, auth=self.auth)
        self._current_task_dialog = dialog  # 记录当前对话框，供剪贴板监控更新用
        result = dialog.exec()
        self._current_task_dialog = None  # 对话框关闭后清除引用

        if result == dialog.DialogCode.Accepted:
            task = dialog.get_task()

            # 检查是否已下载过（历史记录）
            if self.history.is_downloaded(task.artwork_id):
                history_record = self.history.get_task_history(task.artwork_id)
                reply = QMessageBox.question(
                    self,
                    "重复检测",
                    f"该作品「{task.artwork_name}」已经下载过！\n\n"
                    f"上次下载时间: {history_record.get('completed_at', '未知')[:19]}\n"
                    f"上次成功: {history_record.get('success_count', 0)} 张图片\n\n"
                    f"是否仍然添加新任务？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No  # 默认选择"否"
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # 添加到引擎
            if self.engine.add_task(task):
                self._log(f"✅ 新建任务: {task.artwork_name} ({task.artwork_id})")

                # 直接开始下载，不弹窗询问
                self.on_start_all()
            else:
                QMessageBox.warning(self, "警告", "该作品的任务可能已在当前列表中！")

    def on_civitai_task(self):
        """新建 Civitai 任务"""
        dialog = CivitaiTaskDialog(self.config, self, auth=self.civitai_auth)
        self._current_civitai_dialog = dialog
        result = dialog.exec()
        self._current_civitai_dialog = None

        if result == dialog.DialogCode.Accepted:
            task_data = dialog.get_task_data()
            if task_data:
                self._start_civitai_task(task_data)

    def _start_civitai_task(self, task_data: dict):
        """启动 Civitai 下载任务"""
        if task_data.get('is_single_image'):
            self._start_civitai_single_image(task_data)
            return

        task_id = str(uuid.uuid4())
        version_id = task_data['version_id']
        output_dir = task_data['output_dir']
        max_pages = task_data['max_pages']
        interval = task_data['interval']

        # 创建下载工作线程
        session = self.civitai_auth.get_session() if self.civitai_auth.is_logged_in else None
        worker = CivitaiDownloadWorker(
            task_id=task_id,
            version_id=version_id,
            output_dir=output_dir,
            max_pages=max_pages,
            interval=interval,
            session=session
        )

        # 记录任务
        dir_name = os.path.basename(output_dir)
        self._civitai_tasks[task_id] = {
            'worker': worker,
            'output_dir': output_dir,
            'version_id': version_id,
            'name': dir_name,
            'total': 0,
            'current': 0,
            'status': 'downloading',
        }

        # 添加到表格
        self._add_civitai_table_row(task_id, dir_name)

        # 连接信号
        worker.progress_updated.connect(self._on_civitai_progress)
        worker.image_downloaded.connect(self._on_civitai_image)
        worker.status_changed.connect(self._on_civitai_status)
        worker.log_message.connect(self._on_civitai_log)
        worker.finished.connect(self._on_civitai_finished)
        worker.error.connect(self._on_civitai_error)

        # 启动
        worker.start()
        self._log(f"✅ 新建 Civitai 任务: {dir_name} (版本: {version_id})")

    def _start_civitai_single_image(self, task_data: dict):
        """启动单张图片下载任务"""
        from core.civitai_downloader import CivitaiSingleImageWorker

        image_id = task_data['image_id']
        image_url = task_data['image_url']
        output_dir = task_data['output_dir']

        task_id = str(uuid.uuid4())
        session = self.civitai_auth.get_session() if self.civitai_auth.is_logged_in else None

        worker = CivitaiSingleImageWorker(
            task_id=task_id,
            image_id=image_id,
            image_url=image_url,
            output_dir=output_dir,
            session=session
        )

        dir_name = os.path.basename(output_dir)
        self._civitai_tasks[task_id] = {
            'worker': worker,
            'output_dir': output_dir,
            'version_id': '',
            'name': f"[单图] {dir_name}",
            'total': 1,
            'current': 0,
            'status': 'downloading',
        }

        # 添加到表格
        self._add_civitai_table_row(task_id, f"[单图] {dir_name}")

        # 连接信号
        worker.progress_updated.connect(self._on_civitai_progress)
        worker.image_downloaded.connect(self._on_civitai_image)
        worker.status_changed.connect(self._on_civitai_status)
        worker.log_message.connect(self._on_civitai_log)
        worker.finished.connect(self._on_civitai_finished)
        worker.error.connect(self._on_civitai_error)

        worker.start()
        self._log(f"✅ 新建 Civitai 单图任务: {dir_name}")

    def _add_civitai_table_row(self, task_id: str, name: str):
        """添加 Civitai 任务行到表格"""
        row = self.table_tasks.rowCount()
        self.table_tasks.insertRow(row)
        self._civitai_row_map[task_id] = row

        # 第0列：ID 标记
        id_item = QTableWidgetItem("")
        id_item.setData(Qt.ItemDataRole.UserRole, task_id)
        id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_tasks.setItem(row, 0, id_item)

        # 第1列：状态
        status_item = QTableWidgetItem("⬇ 下载中")
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_tasks.setItem(row, 1, status_item)

        # 第2列：名称
        name_item = QTableWidgetItem(f"[Civitai] {name}")
        name_item.setToolTip(f"完整路径: {self._civitai_tasks[task_id]['output_dir']}")
        self.table_tasks.setItem(row, 2, name_item)

        # 第3列：进度
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setContentsMargins(5, 2, 5, 2)
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(0)  # 未知总数
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        progress_bar.setFormat("0/?")
        progress_layout.addWidget(progress_bar)
        self.table_tasks.setCellWidget(row, 3, progress_widget)

        # 第4列：速度
        speed_item = QTableWidgetItem("-")
        speed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_tasks.setItem(row, 4, speed_item)

        # 第5列：操作按钮
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(5, 2, 5, 2)
        btn_stop = QPushButton("✕")
        btn_stop.setToolTip("停止并删除")
        btn_stop.clicked.connect(lambda: self._stop_civitai_task(task_id))
        btn_layout.addWidget(btn_stop)
        self.table_tasks.setCellWidget(row, 5, btn_widget)

    def _stop_civitai_task(self, task_id: str):
        """停止 Civitai 任务"""
        task_info = self._civitai_tasks.get(task_id)
        if task_info:
            task_info['worker'].stop()
            self._log(f"⏹ 已停止 Civitai 任务: {task_info['name']}")

    # ===== Civitai 信号处理 =====

    def _on_civitai_progress(self, task_id: str, current: int, total: int):
        task_info = self._civitai_tasks.get(task_id)
        if not task_info:
            return
        task_info['current'] = current
        task_info['total'] = total

        row = self._civitai_row_map.get(task_id)
        if row is not None and row < self.table_tasks.rowCount():
            progress_widget = self.table_tasks.cellWidget(row, 3)
            if progress_widget:
                progress_bar = progress_widget.findChild(QProgressBar)
                if progress_bar:
                    if total > 0:
                        progress_bar.setMaximum(total)
                    progress_bar.setValue(current)
                    progress_bar.setFormat(f"{current}/{total or '?'}")

    def _on_civitai_image(self, task_id: str, filename: str, success: bool):
        if success:
            self._log(f"[Civitai {task_id[:8]}] ✅ {filename}")
        else:
            self._log(f"[Civitai {task_id[:8]}] ❌ {filename}")

    def _on_civitai_status(self, task_id: str, status: str):
        task_info = self._civitai_tasks.get(task_id)
        if not task_info:
            return
        task_info['status'] = status

        row = self._civitai_row_map.get(task_id)
        if row is not None and row < self.table_tasks.rowCount():
            status_item = self.table_tasks.item(row, 1)
            if status_item:
                if status == 'completed':
                    status_item.setText("✓ 已完成")
                elif status == 'downloading':
                    status_item.setText("⬇ 下载中")
                else:
                    status_item.setText(status)

    def _on_civitai_log(self, task_id: str, message: str):
        self._log(f"[Civitai {task_id[:8]}] {message}")

    def _on_civitai_error(self, task_id: str, error: str):
        self._log(f"[Civitai {task_id[:8]}] ⚠️ 错误: {error}")

    def _on_civitai_finished(self, task_id: str):
        self._log(f"[Civitai {task_id[:8]}] ✅ 任务完成")

    # ===== 剪贴板监控相关方法 =====

    def _on_clipboard_monitor_toggled(self, state):
        """剪贴板监控勾选框状态变化"""
        if state == Qt.CheckState.Checked.value:
            # 开启监控
            self._clipboard_last_text = ""
            self._clipboard_timer.start()
            self._log("📋 剪贴板监控已开启")
        else:
            # 关闭监控
            self._clipboard_timer.stop()
            self._log("📋 剪贴板监控已关闭")

    def _check_clipboard(self):
        """定时检查剪贴板内容"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        # 内容没变化则跳过
        if not text or text == self._clipboard_last_text:
            return

        # 检测是否是 Pixiv 作品链接
        result = URLParser.parse_artwork_url(text)
        if result:
            self._clipboard_last_text = text
            artwork_id = result['artwork_id']
            self._log(f"📋 检测到 Pixiv 作品链接: {artwork_id}")

            # 将窗口置前，方便用户操作
            self.raise_()
            self.activateWindow()

            # 如果已有打开的任务对话框，更新它
            if self._current_task_dialog and self._current_task_dialog.isVisible():
                self._update_dialog_with_url(text)
            else:
                # 否则新建任务对话框
                self._auto_create_task(text)
            return

        # 检测是否是 Civitai 链接
        if self._is_civitai_url(text):
            self._clipboard_last_text = text
            self._log(f"📋 检测到 Civitai 链接: {text[:80]}...")

            # 将窗口置前，方便用户操作
            self.raise_()
            self.activateWindow()

            # 如果已有打开的 Civitai 对话框，更新它
            if self._current_civitai_dialog and self._current_civitai_dialog.isVisible():
                self._current_civitai_dialog.txt_model_url.setText(text)
            else:
                self._auto_create_civitai_task(text)
            return

    def _is_civitai_url(self, text: str) -> bool:
        """判断是否是 Civitai 链接"""
        import re
        return bool(re.search(r'civitai\.(com|red|green)/(models|images)/\d+', text, re.IGNORECASE))

    def _auto_create_civitai_task(self, url: str):
        """自动创建 Civitai 任务（通过剪贴板检测到链接时调用）"""
        dialog = CivitaiTaskDialog(self.config, self, auth=self.civitai_auth, prefilled_url=url)
        self._current_civitai_dialog = dialog

        result = dialog.exec()
        self._current_civitai_dialog = None

        if result == dialog.DialogCode.Accepted:
            task_data = dialog.get_task_data()
            if task_data:
                self._start_civitai_task(task_data)

    def _update_dialog_with_url(self, artwork_url: str):
        """更新已打开的任务对话框中的 URL"""
        if not self._current_task_dialog:
            return

        # 更新作品链接输入框
        self._current_task_dialog.txt_artwork_url.setText(artwork_url)
        self._log(f"📋 已更新任务对话框的作品链接 → {artwork_url}")

    def _auto_create_task(self, artwork_url: str):
        """自动创建新任务（通过剪贴板检测到链接时调用）"""
        dialog = TaskDialog(self.config, self, auth=self.auth)
        self._current_task_dialog = dialog

        # 预填充作品链接
        dialog.txt_artwork_url.setText(artwork_url)

        # 模态对话框，等待用户操作
        result = dialog.exec()
        self._current_task_dialog = None

        if result == dialog.DialogCode.Accepted:
            task = dialog.get_task()

            # 检查是否已下载过（历史记录）
            if self.history.is_downloaded(task.artwork_id):
                history_record = self.history.get_task_history(task.artwork_id)
                reply = QMessageBox.question(
                    self,
                    "重复检测",
                    f"该作品「{task.artwork_name}」已经下载过！\n\n"
                    f"上次下载时间: {history_record.get('completed_at', '未知')[:19]}\n"
                    f"上次成功: {history_record.get('success_count', 0)} 张图片\n\n"
                    f"是否仍然添加新任务？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )

                if reply != QMessageBox.StandardButton.Yes:
                    return

            # 添加到引擎并直接开始下载
            if self.engine.add_task(task):
                self._log(f"✅ 新建任务(剪贴板): {task.artwork_name} ({task.artwork_id})")
                self.on_start_all()
            else:
                QMessageBox.warning(self, "警告", "该作品的任务可能已在当前列表中！")

    def on_start_all(self):
        """开始所有任务"""
        if not self.auth.is_logged_in:
            reply = QMessageBox.question(
                self, "未登录",
                "您尚未登录 Pixiv，部分图片可能无法下载。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        pending_count = sum(1 for t in self.engine.tasks if t.status == TaskStatus.PENDING)
        if pending_count == 0:
            QMessageBox.information(self, "提示", "没有等待中的任务")
            return

        self.engine.start_all()
        self._log(f"▶ 开始下载 {pending_count} 个任务...")

    def on_pause_selected(self):
        """暂停选中的任务"""
        selected_rows = set(item.row() for item in self.table_tasks.selectedItems())
        for row in selected_rows:
            item = self.table_tasks.item(row, 0)
            if item:
                task_id = item.data(Qt.ItemDataRole.UserRole)
                self.engine.pause_task(task_id)
                self._log(f"⏸ 暂停任务: {task_id[:8]}...")

    def on_stop_selected(self):
        """停止选中的任务"""
        selected_rows = set(item.row() for item in self.table_tasks.selectedItems())
        for row in selected_rows:
            item = self.table_tasks.item(row, 0)
            if item:
                task_id = item.data(Qt.ItemDataRole.UserRole)
                reply = QMessageBox.question(
                    self, "确认停止",
                    f"确定要停止并删除这个任务吗？\n\n已下载的图片将保留在磁盘上。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.engine.stop_task(task_id)
                    self.engine.remove_task(task_id)
                    self._log(f"⏹ 已删除任务: {task_id[:8]}...")

    def on_delete_selected(self):
        """删除选中的任务"""
        self.on_stop_selected()

    def on_clear_completed(self):
        """清除已完成的任务"""
        completed_ids = [t.id for t in self.engine.tasks if t.status == TaskStatus.COMPLETED]

        if not completed_ids:
            QMessageBox.information(self, "提示", "没有已完成的任务")
            return

        reply = QMessageBox.question(
            self, "确认清除",
            f"确定要删除 {len(completed_ids)} 个已完成的任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            for task_id in completed_ids:
                self.engine.remove_task(task_id)
            self._log(f"🗑 清除了 {len(completed_ids)} 个已完成任务")

    def on_pause_task(self, task_id: str):
        """暂停指定任务"""
        self.engine.pause_task(task_id)
        self._refresh_table_from_engine()

    def on_resume_task(self, task_id: str):
        """恢复指定任务"""
        self.engine.resume_task(task_id)
        self._refresh_table_from_engine()

    def on_remove_task(self, task_id: str):
        """移除指定任务 - 带确认提示"""
        task = self.engine._find_task(task_id)
        if not task:
            return

        # 构建任务信息
        task_info = task.artwork_name
        status_text = f"（{task.status.display_name}）"

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除任务「{task_info}」{status_text}吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No  # 默认焦点在"否"
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.engine.stop_task(task_id)
            self.engine.remove_task(task_id)
            self._refresh_table_from_engine()
            self._log(f"🗑 已删除任务: {task_info}")

    def on_delete_all(self):
        """删除全部任务 - 带确认提示"""
        total = len(self.engine.tasks)

        if total == 0:
            QMessageBox.information(self, "提示", "当前没有任务")
            return

        # 统计各状态数量
        downloading = sum(1 for t in self.engine.tasks if t.status == TaskStatus.DOWNLOADING)
        pending = sum(1 for t in self.engine.tasks if t.status == TaskStatus.PENDING)

        warning_msg = f"确定要删除全部 {total} 个任务吗？"
        if downloading > 0 or pending > 0:
            details = []
            if downloading > 0:
                details.append(f"{downloading} 个正在下载")
            if pending > 0:
                details.append(f"{pending} 个等待中")
            warning_msg += f"\n\n⚠️ 其中包含：{'、'.join(details)}"

        reply = QMessageBox.warning(
            self, "确认删除全部",
            warning_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No  # 默认焦点在"否"
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 先停止所有正在下载的任务
            for task in self.engine.tasks:
                if task.status in [TaskStatus.DOWNLOADING, TaskStatus.PAUSED]:
                    self.engine.stop_task(task.id)

            # 收集所有 ID 后再删除（避免迭代时修改列表）
            all_ids = [t.id for t in self.engine.tasks]
            for task_id in all_ids:
                self.engine.remove_task(task_id)

            self._refresh_table_from_engine()
            self._log(f"🗑 已删除全部 {total} 个任务")

    def on_login(self):
        """打开登录对话框"""
        dialog = LoginDialog(self.auth, self.civitai_auth, self)
        dialog.exec()

        # 更新引擎的 Session
        self.engine.set_session(self.auth.get_session())

        # 更新 UI
        self._update_status_bar()

    def on_show_history(self):
        """显示下载历史"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QLabel
        
        history_list = self.history.get_all_history()
        stats = self.history.get_statistics()
        
        # 创建历史记录对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"下载历史 (共 {stats['total_tasks']} 条)")
        dialog.setMinimumSize(800, 500)
        
        layout = QVBoxLayout(dialog)
        
        # 统计信息
        stats_label = QLabel(
            f"总任务: {stats['total_tasks']} | "
            f"已完成: {stats['completed_tasks']} | "
            f"失败: {stats['failed_tasks']} | "
            f"总图片: {stats['total_images']} 张"
        )
        layout.addWidget(stats_label)
        
        # 历史表格
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(['作品ID', '标题', '状态', '成功/失败', '完成时间', '操作'])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        table.setRowCount(len(history_list))
        
        for row, record in enumerate(history_list):
            # 作品 ID
            table.setItem(row, 0, QTableWidgetItem(record.get('artwork_id', '')))
            
            # 标题
            table.setItem(row, 1, QTableWidgetItem(record.get('title', '')))
            
            # 状态
            status = record.get('status', '')
            status_text = {'completed': '✓ 已完成', 'failed': '✕ 失败', 'stopped': '■ 已停止'}.get(status, status)
            table.setItem(row, 2, QTableWidgetItem(status_text))
            
            # 成功/失败
            success = record.get('success_count', 0)
            fail = record.get('fail_count', 0)
            failed_images = record.get('failed_images', [])
            if fail > 0 or len(failed_images) > 0:
                text = f"{success} 成功 / {fail} 失败 ({len(failed_images)} 待重试)"
            else:
                text = f"{success} 成功"
            table.setItem(row, 3, QTableWidgetItem(text))
            
            # 完成时间
            completed_at = record.get('completed_at', '')[:19]
            table.setItem(row, 4, QTableWidgetItem(completed_at))
            
            # 操作按钮
            btn_layout = QHBoxLayout()
            
            # 重试按钮（仅当有失败图片时）
            if len(failed_images) > 0:
                btn_retry = QPushButton("重试失败")
                btn_retry.setFixedWidth(80)
                artwork_id = record.get('artwork_id')
                btn_retry.clicked.connect(lambda checked, aid=artwork_id: self._retry_task_failed(aid))
                btn_layout.addWidget(btn_retry)
            
            btn_widget = QWidget()
            btn_widget.setLayout(btn_layout)
            table.setCellWidget(row, 5, btn_widget)
        
        layout.addWidget(table)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_clear = QPushButton("清空历史")
        btn_clear.clicked.connect(lambda: self._clear_history(dialog))
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.close)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        dialog.exec()

    def _clear_history(self, parent_dialog):
        """清空历史记录"""
        reply = QMessageBox.question(
            parent_dialog,
            "确认清空",
            "确定要清空所有下载历史记录吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.history.clear_all()
            parent_dialog.close()
            QMessageBox.information(self, "成功", "历史记录已清空")

    def on_retry_failed(self):
        """重试所有有失败图片的任务"""
        # 获取所有有失败图片的历史记录
        all_history = self.history.get_all_history()
        tasks_with_failures = []
        
        for record in all_history:
            failed_images = record.get('failed_images', [])
            if len(failed_images) > 0:
                tasks_with_failures.append(record)
        
        if not tasks_with_failures:
            QMessageBox.information(
                self,
                "无待重试任务",
                "当前没有需要重试的失败图片！"
            )
            return
        
        # 显示待重试列表并让用户选择
        reply = QMessageBox.question(
            self,
            "重试失败图片",
            f"发现 {len(tasks_with_failures)} 个任务有待重试的失败图片。\n\n"
            f"是否为这些任务创建新的下载任务？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # 为每个有失败的任务创建新任务
        added_count = 0
        for record in tasks_with_failures:
            from models.task_model import TaskStatus
            
            task = DownloadTask(
                artwork_url=record.get('artwork_url', ''),
                first_image_url=record.get('first_image_url', ''),
                output_dir=record.get('output_dir', ''),
                artwork_id=record.get('artwork_id', ''),
                url_template=record.get('url_template', ''),
                status=TaskStatus.PENDING
            )
            
            if self.engine.add_task(task):
                added_count += 1
                self._log(f"🔄 创建重试任务: {record.get('title', task.artwork_id)}")
        
        if added_count > 0:
            self._log(f"🔄 共创建 {added_count} 个重试任务，请手动开始下载")
            QMessageBox.information(
                self,
                "已创建重试任务",
                f"已创建 {added_count} 个重试任务！\n\n请点击「全部开始」进行下载。"
            )

    def _retry_task_failed(self, artwork_id: str):
        """重试指定任务的失败图片"""
        record = self.history.get_task_history(artwork_id)
        if not record:
            return
        
        failed_images = record.get('failed_images', [])
        if not failed_images:
            QMessageBox.information(self, "提示", "该任务没有失败的图片")
            return
        
        reply = QMessageBox.question(
            self,
            "重试失败图片",
            f"作品「{record.get('title', artwork_id)}」有 {len(failed_images)} 张失败的图片。\n\n"
            f"是否创建新的下载任务来重试这些图片？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        from models.task_model import TaskStatus
        task = DownloadTask(
            artwork_url=record.get('artwork_url', ''),
            first_image_url=record.get('first_image_url', ''),
            output_dir=record.get('output_dir', ''),
            artwork_id=artwork_id,
            url_template=record.get('url_template', ''),
            status=TaskStatus.PENDING
        )
        
        if self.engine.add_task(task):
            self._log(f"🔄 创建重试任务: {record.get('title', artwork_id)} ({len(failed_images)} 张待重试)")
            QMessageBox.information(self, "成功", "已创建重试任务，请点击「全部开始」下载")

    def on_settings(self):
        """打开设置对话框"""
        QMessageBox.information(self, "设置", "设置功能即将推出...")

    def on_about(self):
        """关于对话框"""
        QMessageBox.about(
            self,
            "关于",
            "<h3>Pixiv 图片批量下载器</h3>"
            "<p>版本: 1.0.0</p>"
            "<p>一个简单易用的 Pixiv 批量图片下载工具</p>"
            "<p>支持多任务并发、实时进度、断点续传</p>"
            "<p><b>提示:</b> 使用前请确保已配置好网络代理</p>"
        )

    def on_show_usage(self):
        """显示使用说明"""
        usage_text = """
<h3>Pixiv 图片批量下载器 - 使用说明</h3>

<h4>1. 准备工作</h4>
<ul>
<li>确保可以访问 Pixiv 网站（需要科学上网）</li>
<li>建议先登录账号以获取完整权限</li>
</ul>

<h4>2. 登录方式</h4>
<ol>
<li>点击工具栏的登录状态或 菜单 → 工具 → 登录</li>
<li>推荐使用 Cookie 导入方式：</li>
<ul>
<li>在浏览器中登录 pixiv.net</li>
<li>按 F12 打开开发者工具</li>
<li>切换到 Network 标签，刷新页面</li>
<li>点击任意请求，找到 Request Headers 中的 Cookie</li>
<li>复制完整的 Cookie 字符串粘贴到应用中</li>
</ul>
</ol>

<h4>3. 添加下载任务</h4>
<ol>
<li>点击 "+ 新建任务" 按钮</li>
<li>填写以下信息：</li>
<ul>
<li><b>作品链接</b>: Pixiv 作品页面 URL<br>
示例: https://www.pixiv.net/artworks/137875526</li>
<li><b>第一张图片地址</b>: 作品的第一张图片下载链接<br>
（右键图片 → 复制图片地址）</li>
<li><b>保存目录</b>: 图片保存的位置</li>
</ul>
<li>点击确定添加任务</li>
</ol>

<h4>4. 开始下载</h4>
<ol>
<li>添加完任务后，点击 "全部开始"</li>
<li>可以在任务列表中查看每个任务的进度</li>
<li>支持暂停、停止单个任务</li>
<li>支持同时运行多个任务（默认3个）</li>
</ol>

<h4>5. 断点续传</h4>
<p>如果下载中断，只需重新添加相同的任务，程序会自动跳过已下载的图片。</p>

<h4>提示</h4>
<ul>
<li>程序会自动清理目录名中的非法字符</li>
<li>如果遇到 403 错误，请检查 Cookie 是否有效</li>
<li>建议不要同时下载过多任务，以免被限流</li>
</ul>
        """
        QMessageBox.information(self, "使用说明", usage_text)

    def on_import_tasks(self):
        """导入任务列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入任务列表", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if file_path:
            try:
                import json
                with open(file_path, 'r', encoding='utf-8') as f:
                    tasks_data = json.load(f)

                count = 0
                for data in tasks_data:
                    task = DownloadTask.from_dict(data)
                    if self.engine.add_task(task):
                        count += 1

                self._log(f"📥 导入了 {count} 个任务")
                QMessageBox.information(self, "成功", f"成功导入 {count} 个任务")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入失败: {str(e)}")

    def on_export_tasks(self):
        """导出任务列表"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出任务列表", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if file_path:
            try:
                import json
                tasks_data = [task.to_dict() for task in self.engine.tasks]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(tasks_data, f, ensure_ascii=False, indent=2)

                self._log(f"📤 导出了 {len(tasks_data)} 个任务")
                QMessageBox.information(self, "成功", f"成功导出 {len(tasks_data)} 个任务")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def closeEvent(self, event):
        """关闭窗口事件"""
        # 检查是否有正在运行的任务
        running_count = self.engine.get_active_count()
        if running_count > 0:
            reply = QMessageBox.question(
                self, "确认退出",
                f"还有 {running_count} 个任务正在下载，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            # 停止所有任务
            self.engine.stop_all()

        # 保存窗口位置
        self._save_window_geometry()

        event.accept()
