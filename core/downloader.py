"""
Pixiv 图片下载引擎
提供多线程、带进度的图片下载功能

主要组件：
- DownloadWorker: 单个任务的下载工作线程
- DownloadEngine: 管理多个下载任务
"""

import os
import time
import urllib3
from typing import Optional, List, Callable
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal, QObject

import requests

# 导入项目模块
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.task_model import DownloadTask, TaskStatus, DownloadProgress, TaskSettings
from core.url_parser import URLParser
from utils.file_utils import ensure_directory, file_exists, clean_dirname

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DownloadWorker(QThread):
    """
    单个 Pixiv 作品的下载工作线程

    在后台线程中执行下载任务，通过信号报告进度和状态。
    支持暂停、停止操作。

    使用方式:
        worker = DownloadWorker(task, session)
        worker.progress_updated.connect(update_progress)
        worker.finished.connect(on_finished)
        worker.start()
    """

    # 信号定义
    progress_updated = pyqtSignal(str, int, int)       # task_id, current, total
    speed_updated = pyqtSignal(str, float)              # task_id, speed (MB/s)
    image_downloaded = pyqtSignal(str, str, bool)       # task_id, filename, success
    status_changed = pyqtSignal(str, str)               # task_id, new_status
    error_occurred = pyqtSignal(str, str)              # task_id, error_message
    finished_signal = pyqtSignal(str)                   # task_id
    log_message = pyqtSignal(str, str)                  # task_id, message

    def __init__(self, task: DownloadTask, session: requests.Session):
        """
        初始化下载工作线程

        Args:
            task: 下载数据模型
            session: 已认证的 requests.Session
        """
        super().__init__()
        self.task = task
        self.session = session
        self._should_stop = False
        self._should_pause = False
        self._is_running = False

    def run(self):
        """主下载循环 - 在子线程中执行"""
        self._is_running = True
        self._should_stop = False
        self._should_pause = False

        task = self.task
        settings = task.settings

        # 更新状态为下载中
        task.status = TaskStatus.DOWNLOADING
        self.status_changed.emit(task.id, TaskStatus.DOWNLOADING.value)
        self.log_message.emit(task.id, f"开始下载作品: {task.artwork_id}")

        try:
            # 确保输出目录存在
            output_dir = task.output_dir
            if not ensure_directory(output_dir):
                raise Exception(f"无法创建目录: {output_dir}")

            # 准备请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                              '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.pixiv.net/',
            }

            success_count = 0
            fail_count = 0
            start_time = time.time()
            last_speed_update = start_time
            downloaded_bytes = 0

            # 统计已存在的文件（断点续传）
            for i in range(settings.max_pages):
                filename = f"{task.artwork_id}_p{i}.jpg"
                filepath = os.path.join(output_dir, filename)
                if file_exists(filepath):
                    success_count += 1

            # 从成功数开始继续（如果有的话）
            start_page = success_count
            task.progress.current_image = start_page
            task.progress.success_count = start_count = success_count

            self.log_message.emit(task.id,
                                  f"发现已有 {start_page} 张图片，从第 {start_page} 张继续")

            # 主下载循环
            for i in range(start_page, settings.max_pages):
                # 检查是否应该停止
                if self._should_stop:
                    task.status = TaskStatus.STOPPED
                    self.status_changed.emit(task.id, TaskStatus.STOPPED.value)
                    self.log_message.emit(task.id, "用户停止了下载")
                    break

                # 检查是否暂停
                while self._should_pause and not self._should_stop:
                    time.sleep(0.5)

                if self._should_stop:
                    break

                # 构建文件名和路径
                filename = f"{task.artwork_id}_p{i}.jpg"
                filepath = os.path.join(output_dir, filename)

                # 断点续传检查
                if file_exists(filepath):
                    task.progress.success_count += 1
                    task.progress.current_image = i + 1
                    continue

                # 构建下载 URL
                url = URLParser.build_url(task.url_template, i)
                self.log_message.emit(task.id, f"正在下载 [{i+1}/{settings.max_pages}]: {filename}")

                # 尝试下载（带重试）
                downloaded = False
                for retry in range(settings.max_retries):
                    if self._should_stop:
                        break

                    try:
                        # 发送请求
                        resp = self.session.get(
                            url,
                            headers=headers,
                            timeout=settings.timeout,
                            verify=False,
                            stream=True
                        )

                        # 检查响应状态
                        if resp.status_code == 200:
                            content_length = len(resp.content)

                            # 写入文件
                            with open(filepath, 'wb') as f:
                                f.write(resp.content)

                            downloaded_bytes += content_length
                            downloaded = True
                            task.progress.success_count += 1
                            task.progress.current_image = i + 1
                            task.progress.downloaded_size += content_length

                            # 发送下载完成信号
                            self.image_downloaded.emit(task.id, filename, True)
                            self.log_message.emit(task.id, f"✅ 完成: {filename}")
                            break

                        elif resp.status_code == 404:
                            # 图片不存在，说明已经下载完所有图片
                            task.status = TaskStatus.COMPLETED

                            # 更新最终进度：总数 = 实际成功数
                            task.progress.total_images = task.progress.success_count
                            task.progress.speed = 0.0

                            self.log_message.emit(
                                task.id,
                                f"✅ 作品下载完成！共 {task.progress.success_count} 张图片"
                            )
                            self.status_changed.emit(task.id, TaskStatus.COMPLETED.value)
                            self.progress_updated.emit(task.id, task.progress.current_image, task.progress.total_images)
                            self.speed_updated.emit(task.id, 0.0)
                            self.finished_signal.emit(task.id)
                            return

                        else:
                            # 其他错误，可能需要重试
                            if retry < settings.max_retries - 1:
                                wait_time = (retry + 1) * 2
                                self.log_message.emit(
                                    task.id,
                                    f"❌ HTTP {resp.status_code}, 等待 {wait_time}s 后重试..."
                                )
                                time.sleep(wait_time)
                            else:
                                task.progress.fail_count += 1
                                # 记录失败的图片 URL
                                if image_url not in task.failed_images:
                                    task.failed_images.append(image_url)
                                self.image_downloaded.emit(task.id, filename, False)
                                self.error_occurred.emit(
                                    task.id,
                                    f"下载失败: {filename} (HTTP {resp.status_code})"
                                )

                    except requests.exceptions.Timeout:
                        if retry < settings.max_retries - 1:
                            wait_time = (retry + 1) * 3
                            self.log_message.emit(
                                task.id,
                                f"⏱ 超时, 等待 {wait_time}s 后重试..."
                            )
                            time.sleep(wait_time)
                        else:
                            task.progress.fail_count += 1
                            # 记录失败的图片 URL
                            if image_url not in task.failed_images:
                                task.failed_images.append(image_url)
                            self.error_occurred.emit(task.id, f"超时: {filename}")

                    except Exception as e:
                        error_msg = str(e)[:100]
                        if retry < settings.max_retries - 1:
                            wait_time = (retry + 1) * 3
                            self.log_message.emit(
                                task.id,
                                f"❌ 错误: {error_msg}, 等待 {wait_time}s 后重试..."
                            )
                            time.sleep(wait_time)
                        else:
                            task.progress.fail_count += 1
                            # 记录失败的图片 URL
                            if image_url not in task.failed_images:
                                task.failed_images.append(image_url)
                            self.error_occurred.emit(task.id, f"错误: {error_msg}")

                # 如果本次未下载成功
                if not downloaded and not self._should_stop:
                    fail_count += 1
                    time.sleep(1)

                # 更新进度
                task.progress.total_images = min(i + 10, settings.max_pages)  # 预估总数
                self.progress_updated.emit(
                    task.id,
                    task.progress.current_image,
                    task.progress.total_images
                )

                # 计算并更新速度（每秒更新一次）
                current_time = time.time()
                if current_time - last_speed_update >= 1.0:
                    elapsed = current_time - last_speed_update
                    if elapsed > 0:
                        speed = (downloaded_bytes / (1024 * 1024)) / elapsed  # MB/s
                        task.progress.speed = speed
                        self.speed_updated.emit(task.id, speed)
                    downloaded_bytes = 0
                    last_speed_update = current_time

                # 请求间隔
                if i < settings.max_pages - 1:
                    time.sleep(settings.interval)

            # 正常完成（没有提前退出）
            if not self._should_stop and task.status == TaskStatus.DOWNLOADING:
                task.status = TaskStatus.COMPLETED

                # 更新最终进度：总数 = 实际成功数（精确值）
                task.progress.total_images = task.progress.success_count
                task.progress.speed = 0.0  # 完成后速度归零

                # 发送最终状态更新
                self.status_changed.emit(task.id, TaskStatus.COMPLETED.value)
                self.progress_updated.emit(
                    task.id,
                    task.progress.current_image,
                    task.progress.total_images
                )
                self.speed_updated.emit(task.id, 0.0)

                self.log_message.emit(
                    task.id,
                    f"🎉 下载完成！成功: {task.progress.success_count}, 失败: {task.progress.fail_count}"
                )

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            self.status_changed.emit(task.id, TaskStatus.FAILED.value)
            self.error_occurred.emit(task.id, f"致命错误: {str(e)}")
            self.log_message.emit(task.id, f"❌ 致命错误: {e}")

        finally:
            self._is_running = False
            self.finished_signal.emit(task.id)

    def stop(self):
        """停止下载"""
        self._should_stop = True
        self.log_message.emit(self.task.id, "正在停止...")

    def pause(self):
        """暂停下载"""
        self._should_pause = True
        self.status_changed.emit(self.task.id, TaskStatus.PAUSED.value)
        self.log_message.emit(self.task.id, "已暂停")

    def resume(self):
        """恢复下载"""
        self._should_pause = False
        self.status_changed.emit(self.task.id, TaskStatus.DOWNLOADING.value)
        self.log_message.emit(self.task.id, "继续下载...")

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running


class DownloadEngine(QObject):
    """
    下载引擎 - 管理多个并发下载任务

    功能：
    - 任务队列管理
    - 并发控制
    - 统一调度
    - 全局状态管理

    使用方式:
        engine = DownloadEngine(max_concurrent=3)
        engine.add_task(task)
        engine.start_all()
    """

    # 信号定义
    task_added = pyqtSignal(object)              # DownloadTask
    task_removed = pyqtSignal(str)               # task_id
    all_completed = pyqtSignal()                 # 所有任务完成
    stats_updated = pyqtSignal(int, int, int)    # total, downloading, completed

    # 新增：单个任务的详细状态信号（用于 UI 实时更新）
    task_progress_updated = pyqtSignal(str, int, int)   # task_id, current, total
    task_speed_updated = pyqtSignal(str, float)        # task_id, speed MB/s
    task_image_downloaded = pyqtSignal(str, str, bool) # task_id, filename, success
    task_status_changed = pyqtSignal(str, str)         # task_id, status value
    task_error = pyqtSignal(str, str)                   # task_id, error message
    task_finished = pyqtSignal(str)                     # task_id
    task_log = pyqtSignal(str, str)                      # task_id, message

    def __init__(self, max_concurrent: int = 3, session: Optional[requests.Session] = None):
        """
        初始化下载引擎

        Args:
            max_concurrent: 最大同时下载数
            session: 已认证的 Session 对象
        """
        super().__init__()
        self.max_concurrent = max_concurrent
        self.session = session
        self.tasks: List[DownloadTask] = []
        self.workers: dict = {}  # task_id -> DownloadWorker
        self._task_queue: List[str] = []  # 待处理任务 ID 队列

    def set_session(self, session: requests.Session):
        """设置认证 Session"""
        self.session = session

    def add_task(self, task: DownloadTask) -> bool:
        """
        添加下载任务到队列

        Args:
            task: 下载数据模型

        Returns:
            是否添加成功
        """
        # 检查是否已存在相同任务
        for t in self.tasks:
            if t.artwork_id == task.artwork_id and t.status != TaskStatus.COMPLETED:
                print(f"任务已存在: {task.artwork_id}")
                return False

        self.tasks.append(task)
        self._task_queue.append(task.id)
        self.task_added.emit(task)
        self._update_stats()

        print(f"任务已添加: {task.artwork_id} ({task.artwork_name})")
        return True

    def remove_task(self, task_id: str) -> bool:
        """
        移除任务

        Args:
            task_id: 任务 ID

        Returns:
            是否移除成功
        """
        # 如果正在运行，先停止
        if task_id in self.workers:
            self.stop_task(task_id)

        # 从列表中移除
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                self.tasks.pop(i)
                if task_id in self._task_queue:
                    self._task_queue.remove(task_id)
                self.task_removed.emit(task_id)
                self._update_stats()
                return True

        return False

    def start_task(self, task_id: str) -> bool:
        """
        启动单个任务

        Args:
            task_id: 任务 ID

        Returns:
            是否启动成功
        """
        task = self._find_task(task_id)
        if not task:
            return False

        if task_id in self.workers and self.workers[task_id].is_running:
            print(f"任务正在运行: {task_id}")
            return False

        if not self.session:
            print("错误: 未设置 Session")
            return False

        # 创建工作线程
        worker = DownloadWorker(task, self.session)

        # 连接信号
        worker.progress_updated.connect(self._on_progress_updated)
        worker.speed_updated.connect(self._on_speed_updated)
        worker.image_downloaded.connect(self._on_image_downloaded)
        worker.status_changed.connect(self._on_status_changed)
        worker.error_occurred.connect(self._on_error_occurred)
        worker.finished_signal.connect(self._on_worker_finished)
        worker.log_message.connect(self._on_log_message)

        # 保存引用
        self.workers[task_id] = worker

        # 启动线程
        worker.start()
        return True

    def start_all(self):
        """启动所有等待中的任务"""
        pending_tasks = [t for t in self.tasks if t.status == TaskStatus.PENDING]

        started = 0
        for task in pending_tasks[:self.max_concurrent]:
            if self.start_task(task.id):
                started += 1

        if started > 0:
            print(f"启动了 {started} 个任务")
        else:
            print("没有可启动的任务")

    def pause_task(self, task_id: str):
        """暂停指定任务"""
        if task_id in self.workers:
            self.workers[task_id].pause()

    def resume_task(self, task_id: str):
        """恢复指定任务"""
        if task_id in self.workers:
            self.workers[task_id].resume()

    def stop_task(self, task_id: str):
        """停止指定任务"""
        if task_id in self.workers:
            worker = self.workers[task_id]
            worker.stop()
            # 等待线程结束
            if worker.isRunning():
                worker.wait(3000)  # 等待最多3秒
            del self.workers[task_id]

    def stop_all(self):
        """停止所有正在运行的任务"""
        for task_id in list(self.workers.keys()):
            self.stop_task(task_id)
        print("所有任务已停止")

    def get_active_count(self) -> int:
        """获取当前活动（下载中）的任务数量"""
        return len([w for w in self.workers.values() if w.is_running])

    def _find_task(self, task_id: str) -> Optional[DownloadTask]:
        """根据 ID 查找任务"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def _update_stats(self):
        """更新统计信息并发射信号"""
        total = len(self.tasks)
        downloading = sum(1 for t in self.tasks if t.status == TaskStatus.DOWNLOADING)
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        self.stats_updated.emit(total, downloading, completed)

    # ===== 信号处理方法（转发 worker 信号到 engine 信号）=====

    def _on_progress_updated(self, task_id: str, current: int, total: int):
        """处理进度更新 - 转发信号"""
        # 更新任务对象的进度
        task = self._find_task(task_id)
        if task:
            task.progress.current_image = current
            if total > 0:
                task.progress.total_images = total
        # 发射信号给 UI
        self.task_progress_updated.emit(task_id, current, total)

    def _on_speed_updated(self, task_id: str, speed: float):
        """处理速度更新 - 转发信号"""
        # 更新任务对象的速度
        task = self._find_task(task_id)
        if task:
            task.progress.speed = speed
        # 发射信号给 UI
        self.task_speed_updated.emit(task_id, speed)

    def _on_image_downloaded(self, task_id: str, filename: str, success: bool):
        """处理单张图片下载完成 - 转发信号"""
        # 发射信号给 UI
        self.task_image_downloaded.emit(task_id, filename, success)

    def _on_status_changed(self, task_id: str, status: str):
        """处理任务状态变化 - 转发信号"""
        # 更新任务对象的状态
        task = self._find_task(task_id)
        if task:
            task.status = TaskStatus(status)
        # 发射信号给 UI
        self.task_status_changed.emit(task_id, status)
        # 更新统计
        self._update_stats()

    def _on_error_occurred(self, task_id: str, error: str):
        """处理错误 - 转发信号"""
        print(f"[{task_id}] 错误: {error}")
        # 发射信号给 UI
        self.task_error.emit(task_id, error)

    def _on_worker_finished(self, task_id: str):
        """处理工作线程结束 - 转发信号"""
        if task_id in self.workers:
            del self.workers[task_id]

        # 发射任务完成信号
        self.task_finished.emit(task_id)

        # 更新统计
        self._update_stats()

        # 检查是否还有待处理的任务
        active_count = self.get_active_count()
        pending_count = sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

        if active_count < self.max_concurrent and pending_count > 0:
            # 自动启动下一个任务
            for task in self.tasks:
                if task.status == TaskStatus.PENDING:
                    self.start_task(task.id)
                    break

        # 检查是否全部完成
        if active_count == 0 and pending_count == 0:
            self.all_completed.emit()

    def _on_log_message(self, task_id: str, message: str):
        """处理日志消息 - 转发信号"""
        print(f"[{task_id}] {message}")
        # 发射信号给 UI
        self.task_log.emit(task_id, message)
