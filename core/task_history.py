"""
下载任务历史记录管理
用于持久化保存已完成的任务，避免重复下载
"""

import json
import os
from datetime import datetime
from typing import List, Optional
from models.task_model import DownloadTask


class TaskHistory:
    """任务历史记录管理器"""
    
    def __init__(self, history_file: str = None):
        """
        初始化历史记录管理器
        
        Args:
            history_file: 历史记录文件路径，默认为程序目录下的 data/history.json
        """
        if history_file is None:
            # 默认保存在程序目录下的 data 文件夹
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(app_dir, 'data')
            os.makedirs(data_dir, exist_ok=True)
            self.history_file = os.path.join(data_dir, 'download_history.json')
        else:
            self.history_file = history_file
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        
        # 加载历史记录
        self.history: List[dict] = []
        self._load()
    
    def _load(self):
        """从文件加载历史记录"""
        if not os.path.exists(self.history_file):
            return
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                self.history = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[TaskHistory] 加载历史记录失败: {e}")
            self.history = []
    
    def _save(self):
        """保存历史记录到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[TaskHistory] 保存历史记录失败: {e}")
    
    def add_task(self, task: DownloadTask):
        """
        添加任务到历史记录
        
        如果该 artwork_id 已存在，则更新记录（保留最新的）
        """
        record = {
            'artwork_id': task.artwork_id,
            'artwork_url': task.artwork_url,
            'first_image_url': task.first_image_url,
            'output_dir': task.output_dir,
            'url_template': task.url_template,
            'title': task.artwork_name,
            'status': task.status.value,
            'success_count': task.progress.success_count,
            'fail_count': task.progress.fail_count,
            'failed_images': getattr(task, 'failed_images', []),
            'completed_at': datetime.now().isoformat(),
            'created_at': task.created_at.isoformat() if task.created_at else ''
        }
        
        # 检查是否已存在，存在则更新
        existing_idx = None
        for i, h in enumerate(self.history):
            if h.get('artwork_id') == task.artwork_id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            self.history[existing_idx] = record
        else:
            # 插入到列表开头（最新在前）
            self.history.insert(0, record)
        
        # 限制历史记录数量，最多保存 500 条
        if len(self.history) > 500:
            self.history = self.history[:500]
        
        self._save()
    
    def is_downloaded(self, artwork_id: str) -> bool:
        """检查指定作品是否已经下载过（且成功）"""
        for h in self.history:
            if h.get('artwork_id') == artwork_id and h.get('status') == 'completed':
                return True
        return False
    
    def get_task_history(self, artwork_id: str) -> Optional[dict]:
        """获取指定作品的历史记录"""
        for h in self.history:
            if h.get('artwork_id') == artwork_id:
                return h
        return None
    
    def get_all_history(self) -> List[dict]:
        """获取所有历史记录（按时间倒序）"""
        return self.history
    
    def get_failed_images(self, artwork_id: str) -> List[str]:
        """获取指定作品的失败图片列表"""
        record = self.get_task_history(artwork_id)
        if record:
            return record.get('failed_images', [])
        return []
    
    def remove_history(self, artwork_id: str):
        """删除指定作品的历史记录"""
        self.history = [h for h in self.history if h.get('artwork_id') != artwork_id]
        self._save()
    
    def clear_all(self):
        """清空所有历史记录"""
        self.history = []
        self._save()
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        total = len(self.history)
        completed = sum(1 for h in self.history if h.get('status') == 'completed')
        failed = sum(1 for h in self.history if h.get('status') == 'failed')
        total_images = sum(h.get('success_count', 0) + h.get('fail_count', 0) for h in self.history)
        
        return {
            'total_tasks': total,
            'completed_tasks': completed,
            'failed_tasks': failed,
            'total_images': total_images
        }
