"""
Pixiv 下载任务数据模型
定义下载任务的所有数据结构和状态枚举
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional
import uuid


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"              # 等待中
    DOWNLOADING = "downloading"      # 下载中
    PAUSED = "paused"                # 已暂停
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"                # 失败
    STOPPED = "stopped"              # 已停止

    @property
    def display_name(self) -> str:
        """获取状态显示名称"""
        names = {
            TaskStatus.PENDING: "等待中",
            TaskStatus.DOWNLOADING: "下载中",
            TaskStatus.PAUSED: "已暂停",
            TaskStatus.COMPLETED: "已完成",
            TaskStatus.FAILED: "失败",
            TaskStatus.STOPPED: "已停止"
        }
        return names.get(self, self.value)

    @property
    def icon(self) -> str:
        """获取状态图标字符"""
        icons = {
            TaskStatus.PENDING: "○",
            TaskStatus.DOWNLOADING: "⬇",
            TaskStatus.PAUSED: "⏸",
            TaskStatus.COMPLETED: "✓",
            TaskStatus.FAILED: "✕",
            TaskStatus.STOPPED: "■"
        }
        return icons.get(self, "?")


@dataclass
class DownloadProgress:
    """下载进度信息"""
    current_image: int = 0           # 当前进度（第几张图片）
    total_images: int = 0            # 总图片数（预估，0表示未知）
    downloaded_size: int = 0         # 已下载大小（字节）
    total_size: int = 0              # 总大小（字节）
    speed: float = 0.0               # 当前速度 MB/s
    success_count: int = 0           # 成功下载数
    fail_count: int = 0              # 失败数

    @property
    def progress_percent(self) -> float:
        """计算进度百分比"""
        if self.total_images > 0:
            return (self.current_image / self.total_images) * 100
        return 0.0

    @property
    def speed_display(self) -> str:
        """格式化速度显示"""
        if self.speed >= 1:
            return f"{self.speed:.1f} MB/s"
        elif self.speed > 0:
            return f"{self.speed * 1024:.0f} KB/s"
        else:
            return "-"


@dataclass
class TaskSettings:
    """任务下载设置"""
    max_retries: int = 3              # 最大重试次数
    timeout: int = 30                 # 超时时间（秒）
    interval: float = 1.0             # 请求间隔（秒）
    max_pages: int = 200              # 最大页数


@dataclass
class DownloadTask:
    """
    下载数据模型

    表示一个完整的 Pixiv 作品下载任务
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 任务唯一 ID
    artwork_url: str = ""               # 作品页面 URL
    first_image_url: str = ""           # 第一张图片 URL
    output_dir: str = ""                # 输出目录
    artwork_id: str = ""                # 作品 ID（从URL解析）
    url_template: str = ""              # URL 模板（从第一张图片URL解析）
    status: TaskStatus = TaskStatus.PENDING  # 任务状态
    progress: DownloadProgress = field(default_factory=DownloadProgress)  # 下载进度
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    settings: TaskSettings = field(default_factory=TaskSettings)  # 下载设置
    error_message: str = ""             # 错误信息
    failed_images: list = field(default_factory=list)  # 失败的图片 URL 列表

    @property
    def artwork_name(self) -> str:
        """从输出目录提取作品名称"""
        import os
        if self.output_dir:
            return os.path.basename(self.output_dir)
        return f"作品 {self.artwork_id}"

    def update_progress(self, **kwargs):
        """更新进度信息"""
        for key, value in kwargs.items():
            if hasattr(self.progress, key):
                setattr(self.progress, key, value)

    def to_dict(self) -> dict:
        """转换为字典（用于序列化）"""
        return {
            'id': self.id,
            'artwork_url': self.artwork_url,
            'first_image_url': self.first_image_url,
            'output_dir': self.output_dir,
            'artwork_id': self.artwork_id,
            'url_template': self.url_template,
            'status': self.status.value,
            'progress': {
                'current_image': self.progress.current_image,
                'total_images': self.progress.total_images,
                'downloaded_size': self.progress.downloaded_size,
                'total_size': self.progress.total_size,
                'speed': self.progress.speed,
                'success_count': self.progress.success_count,
                'fail_count': self.progress.fail_count
            },
            'created_at': self.created_at.isoformat(),
            'settings': {
                'max_retries': self.settings.max_retries,
                'timeout': self.settings.timeout,
                'interval': self.settings.interval,
                'max_pages': self.settings.max_pages
            },
            'error_message': self.error_message,
            'failed_images': self.failed_images
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DownloadTask':
        """从字典创建实例（用于反序列化）"""
        task = cls(
            id=data.get('id', str(uuid.uuid4())),
            artwork_url=data.get('artwork_url', ''),
            first_image_url=data.get('first_image_url', ''),
            output_dir=data.get('output_dir', ''),
            artwork_id=data.get('artwork_id', ''),
            url_template=data.get('url_template', ''),
            status=TaskStatus(data.get('status', 'pending')),
            error_message=data.get('error_message', ''),
            failed_images=data.get('failed_images', [])
        )

        # 恢复进度
        if 'progress' in data:
            p = data['progress']
            task.progress = DownloadProgress(
                current_image=p.get('current_image', 0),
                total_images=p.get('total_images', 0),
                downloaded_size=p.get('downloaded_size', 0),
                total_size=p.get('total_size', 0),
                speed=p.get('speed', 0.0),
                success_count=p.get('success_count', 0),
                fail_count=p.get('fail_count', 0)
            )

        # 恢复设置
        if 'settings' in data:
            s = data['settings']
            task.settings = TaskSettings(
                max_retries=s.get('max_retries', 3),
                timeout=s.get('timeout', 30),
                interval=s.get('interval', 1.0),
                max_pages=s.get('max_pages', 200)
            )

        # 恢复创建时间
        if 'created_at' in data:
            try:
                task.created_at = datetime.fromisoformat(data['created_at'])
            except:
                pass

        return task
