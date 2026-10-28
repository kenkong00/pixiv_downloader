"""
配置管理模块
负责应用程序配置的读取、保存和管理
"""

import os
import json
from typing import Any, Optional
from pathlib import Path


class Config:
    """
    应用程序配置管理器

    管理所有用户偏好和应用程序设置
    """

    # 默认配置值
    DEFAULTS = {
        # 通用设置
        'general': {
            'language': 'zh_CN',
            'theme': 'light',
            'auto_start': False,
            'minimize_to_tray': True,
            'close_to_tray': False,
        },

        # 下载设置
        'download': {
            'max_concurrent_tasks': 3,       # 最大并发任务数
            'default_max_retries': 3,          # 默认重试次数
            'default_timeout': 30,             # 默认超时时间(秒)
            'default_interval': 1.0,           # 默认请求间隔(秒)
            'default_max_pages': 200,          # 默认最大页数
            'save_last_directory': '',         # 上次使用的目录
            'default_download_dir': '',        # 默认下载目录（空则使用程序目录下的 downloads）
        },

        # 代理设置
        'proxy': {
            'enabled': False,
            'type': 'http',                    # http / socks5
            'host': '',
            'port': '',
            'username': '',
            'password': '',
        },

        # 认证设置
        'auth': {
            'remember_password': True,
            'auto_login': False,
            'cookie_file': 'cookies.json',
        },

        # 窗口设置
        'window': {
            'x': 100,
            'y': 100,
            'width': 1200,
            'height': 800,
            'maximized': False,
        },
    }

    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录，默认为应用所在目录下的 config 文件夹
        """
        if config_dir is None:
            # 默认配置目录：应用根目录下的 config
            config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')

        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / 'config.json'
        self._config: dict = {}

        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                # 合并默认配置和已保存配置
                self._config = self._deep_merge(self.DEFAULTS.copy(), saved_config)
            except Exception as e:
                print(f"加载配置失败: {e}")
                self._config = self.DEFAULTS.copy()
        else:
            self._config = self.DEFAULTS.copy()
            self._save_config()

    def _save_config(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """深度合并两个字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            section: 配置节名（如 'general', 'download' 等）
            key: 配置键名
            default: 默认值（如果配置不存在）

        Returns:
            配置值
        """
        return self._config.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any):
        """
        设置配置值

        Args:
            section: 配置节名
            key: 配置键名
            value: 配置值
        """
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        self._save_config()

    def get_section(self, section: str) -> dict:
        """
        获取整个配置节

        Args:
            section: 配置节名

        Returns:
            该节的所有配置项
        """
        return self._config.get(section, {}).copy()

    def set_section(self, section: str, values: dict):
        """
        设置整个配置节

        Args:
            section: 配置节名
            values: 配置字典
        """
        if section not in self._config:
            self._config[section] = {}
        self._config[section].update(values)
        self._save_config()

    def reset_to_defaults(self, section: Optional[str] = None):
        """
        重置配置为默认值

        Args:
            section: 要重置的配置节，如果为 None 则重置全部
        """
        if section is None:
            self._config = self.DEFAULTS.copy()
        elif section in self.DEFAULTS:
            self._config[section] = self.DEFAULTS[section].copy()
        self._save_config()

    @property
    def download_settings(self) -> dict:
        """获取下载相关设置的快捷方式"""
        return self.get_section('download')

    @property
    def proxy_settings(self) -> dict:
        """获取代理设置的快捷方式"""
        return self.get_section('proxy')

    @property
    def auth_settings(self) -> dict:
        """获取认证设置的快捷方式"""
        return self.get_section('auth')

    def __repr__(self) -> str:
        return f"Config(config_dir='{self.config_dir}')"
