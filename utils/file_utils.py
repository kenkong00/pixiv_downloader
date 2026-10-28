"""
文件和目录操作工具
提供安全的文件操作、目录名清理等功能
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple


# Windows 文件名非法字符
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*\x00-\x1F]'

# 需要特殊处理的字符（保留空格、中文等）
SPECIAL_CHARS_TO_REMOVE = ['·', '*', '?', '"', '|', '<', '>', '。', '.', '《', '》']


def clean_dirname(name: str) -> str:
    """
    清理目录名中的非法字符

    移除或替换不能用于文件名/目录名的字符，
    同时处理一些可能导致问题的特殊字符。

    Args:
        name: 原始目录名

    Returns:
        清理后的安全目录名

    示例:
        >>> clean_dirname('test/file:name')
        'testfilename'
        >>> clean_dirname('水月 只有红茶可以吗')
        '水月 只有红茶可以吗'
    """
    if not name:
        return "unnamed"

    # 移除特殊字符
    for char in SPECIAL_CHARS_TO_REMOVE:
        name = name.replace(char, '')

    # 使用正则移除其他非法字符
    name = re.sub(INVALID_FILENAME_CHARS, '', name)

    # 移除首尾空白和点号
    name = name.strip(' .')

    # 如果清理后为空，返回默认名称
    if not name:
        return "unnamed"

    # 截断过长的名称（Windows 限制为 255 字符）
    if len(name) > 200:
        name = name[:200]

    return name


def safe_filename(name: str, max_length: int = 200) -> str:
    """
    生成安全的文件名

    Args:
        name: 原始文件名
        max_length: 最大长度

    Returns:
        安全的文件名
    """
    # 获取扩展名
    name_base, ext = os.path.splitext(name)

    # 清理文件名主体
    name_base = clean_dirname(name_base)

    # 确保总长度不超过限制
    if len(name_base) + len(ext) > max_length:
        name_base = name_base[:max_length - len(ext)]

    return f"{name_base}{ext}" if ext else name_base


def ensure_directory(directory: str) -> bool:
    """
    确保目录存在，不存在则创建

    Args:
        directory: 目录路径

    Returns:
        是否成功创建或已存在

    示例:
        >>> ensure_directory("path/to/dir")
        True
    """
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"创建目录失败: {directory}, 错误: {e}")
        return False


def file_exists(filepath: str) -> bool:
    """检查文件是否存在"""
    return Path(filepath).exists()


def get_file_size(filepath: str) -> int:
    """
    获取文件大小（字节）

    Args:
        filepath: 文件路径

    Returns:
        文件大小，文件不存在返回 0
    """
    try:
        return Path(filepath).stat().st_size
    except:
        return 0


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小显示

    Args:
        size_bytes: 字节数

    Returns:
        格式化后的大小字符串

    示例:
        >>> format_file_size(1024)
        '1.00 KB'
        >>> format_file_size(1048576)
        '1.00 MB'
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def delete_file(filepath: str) -> bool:
    """
    安全删除文件

    Args:
        filepath: 文件路径

    Returns:
        是否删除成功
    """
    try:
        Path(filepath).unlink()
        return True
    except Exception as e:
        print(f"删除文件失败: {filepath}, 错误: {e}")
        return False


def list_files(directory: str, pattern: str = "*") -> List[str]:
    """
    列出目录下的所有文件

    Args:
        directory: 目录路径
        pattern: 文件匹配模式（如 *.jpg）

    Returns:
        文件路径列表
    """
    try:
        path = Path(directory)
        return [str(f) for f in path.glob(pattern) if f.is_file()]
    except Exception as e:
        print(f"列出文件失败: {directory}, 错误: {e}")
        return []


def count_files(directory: str, pattern: str = "*.jpg") -> int:
    """
    统计目录下匹配模式的文件数量

    Args:
        directory: 目录路径
        pattern: 匹配模式

    Returns:
        文件数量
    """
    return len(list_files(directory, pattern))


def get_available_space(path: str) -> int:
    """
    获取指定路径所在磁盘的可用空间（字节）

    Args:
        path: 路径

    Returns:
        可用空间字节数，获取失败返回 -1
    """
    try:
        if os.name == 'nt':  # Windows
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(path), None, None, ctypes.pointer(free_bytes)
            )
            return free_bytes.value
        else:  # Linux/Mac
            stat = os.statvfs(path)
            return stat.f_bavail * stat.f_frsize
    except:
        return -1


def check_disk_space(path: str, required_bytes: int) -> Tuple[bool, str]:
    """
    检查磁盘是否有足够的空间

    Args:
        path: 要写入的路径
        required_bytes: 需要的字节数

    Returns:
        (是否有足够空间, 提示信息)
    """
    available = get_available_space(path)
    if available == -1:
        return True, "无法获取磁盘空间信息"

    if available < required_bytes:
        return False, f"磁盘空间不足！需要 {format_file_size(required_bytes)}，可用 {format_file_size(available)}"

    return True, ""


from typing import Tuple
