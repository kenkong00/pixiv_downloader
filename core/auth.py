"""
Pixiv 认证模块
管理用户登录、Cookie/Session 维护
"""

import os
import json
import time
from typing import Optional, Dict, Any
from pathlib import Path

import requests
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class PixivAuth:
    """
    Pixiv 认证管理器

    提供以下功能：
    - 通过 Cookie 导入进行认证
    - Cookie 的保存和加载
    - Session 管理
    - 登录状态检查

    推荐使用方式：
    1. 用户在浏览器登录 Pixiv
    2. 使用浏览器开发者工具导出 Cookie（主要是 PHPSESSID）
    3. 在应用中导入 Cookie
    """

    # 默认请求头
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.pixiv.net/',
    }

    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化认证管理器

        Args:
            config_dir: 配置目录，用于存储 Cookie 文件
        """
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')

        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.cookie_file = self.config_dir / 'cookies.json'
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.session.verify = False

        self._is_logged_in = False
        self._login_time: Optional[float] = None
        self._user_info: Optional[Dict] = None

        # 尝试加载已保存的 Cookie
        self._load_cookies()

    @property
    def is_logged_in(self) -> bool:
        """是否已登录"""
        return self._is_logged_in

    @property
    def user_info(self) -> Optional[Dict]:
        """获取当前用户信息"""
        return self._user_info

    def get_session(self) -> requests.Session:
        """
        获取已配置好认证信息的 Session 对象

        Returns:
            requests.Session 实例，已包含必要的 Headers 和 Cookies
        """
        return self.session

    def get_headers(self) -> Dict[str, str]:
        """
        获取包含认证信息的请求头字典

        用于需要自定义请求的场景

        Returns:
            请求头字典
        """
        headers = self.DEFAULT_HEADERS.copy()
        return headers

    def login_by_cookie_string(self, cookie_string: str) -> bool:
        """
        通过 Cookie 字符串导入进行登录

        支持的格式：
        - "key1=value1; key2=value2"
        - 浏览器导出的原始 Cookie 字符串

        Args:
            cookie_string: Cookie 字符串

        Returns:
            是否登录成功

        示例:
            >>> auth.login_by_cookie_string("PHPSESSID=xxxxx; ...")
            True
        """
        try:
            # 解析 Cookie 字符串
            cookies = {}
            for item in cookie_string.split(';'):
                item = item.strip()
                if '=' in item:
                    key, value = item.split('=', 1)
                    cookies[key.strip()] = value.strip()

            if not cookies:
                return False

            # 设置到 Session
            self.session.cookies.update(cookies)

            # 验证登录状态
            if self._verify_login():
                self._save_cookies()
                return True
            else:
                print("Cookie 验证失败")
                return False

        except Exception as e:
            print(f"Cookie 导入错误: {e}")
            return False

    def login_by_cookies_dict(self, cookies: Dict[str, str]) -> bool:
        """
        通过 Cookie 字典进行登录

        Args:
            cookies: Cookie 字典 {name: value}

        Returns:
            是否登录成功
        """
        try:
            self.session.cookies.update(cookies)

            if self._verify_login():
                self._save_cookies()
                return True
            else:
                return False

        except Exception as e:
            print(f"Cookie 设置错误: {e}")
            return False

    def set_proxy(self, proxy_url: Optional[str] = None):
        """
        设置代理服务器

        Args:
            proxy_url: 代理 URL，如 "http://127.0.0.1:7890"
                       如果为 None 则清除代理设置
        """
        if proxy_url:
            self.session.proxies = {
                'http': proxy_url,
                'https': proxy_url,
            }
        else:
            self.session.proxies = {}

    def _verify_login(self) -> bool:
        """
        验证当前 Session 是否已成功登录

        通过访问需要登录的页面来验证

        Returns:
            是否验证通过
        """
        try:
            # 访问个人主页或登录检测接口
            test_urls = [
                'https://www.pixiv.net/setting_user.php',
                'https://www.pixiv.net/',
            ]

            for url in test_urls:
                try:
                    resp = self.session.get(
                        url,
                        timeout=15,
                        allow_redirects=True
                    )

                    # 检查是否被重定向到登录页面
                    if resp.url and 'login' in resp.url.lower():
                        continue

                    # 检查响应内容
                    if resp.status_code == 200:
                        if 'pixiv.user.id' in resp.text or 'logout' in resp.text.lower():
                            self._is_logged_in = True
                            self._login_time = time.time()
                            return True

                        # 简单判断：如果能正常访问首页且没有明显的未登录标记
                        if len(resp.content) > 10000:
                            self._is_logged_in = True
                            self._login_time = time.time()
                            return True

                except Exception as e:
                    print(f"验证请求失败 ({url}): {e}")
                    continue

            self._is_logged_in = False
            return False

        except Exception as e:
            print(f"登录验证异常: {e}")
            self._is_logged_in = False
            return False

    def _save_cookies(self):
        """保存 Cookie 到本地文件"""
        try:
            # 使用 items() 迭代避免重复 cookie 名冲突
            cookies_dict = {}
            for cookie in self.session.cookies:
                cookies_dict[cookie.name] = cookie.value
            data = {
                'cookies': cookies_dict,
                'saved_time': time.time(),
                'headers': dict(self.session.headers),
            }

            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"Cookie 已保存到: {self.cookie_file}")

        except Exception as e:
            print(f"保存 Cookie 失败: {e}")

    def _load_cookies(self) -> bool:
        """
        从本地加载 Cookie

        Returns:
            是否加载成功
        """
        if not self.cookie_file.exists():
            return False

        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查 Cookie 是否过期（30天）
            saved_time = data.get('saved_time', 0)
            if time.time() - saved_time > 30 * 24 * 3600:
                print("Cookie 可能已过期（超过30天）")

            # 加载 Cookies
            cookies = data.get('cookies', {})
            if cookies:
                self.session.cookies.update(cookies)

            # 加载自定义 Headers
            headers = data.get('headers', {})
            if headers:
                self.session.headers.update(headers)

            print(f"已从本地加载 Cookie: {len(cookies)} 个")

            # 尝试验证
            if self._verify_login():
                return True
            else:
                print("已保存的 Cookie 无效，需要重新登录")
                return False

        except Exception as e:
            print(f"加载 Cookie 失败: {e}")
            return False

    def logout(self):
        """登出并清除所有认证信息"""
        try:
            # 清除 Session
            self.session.close()
            self.session = requests.Session()
            self.session.headers.update(self.DEFAULT_HEADERS)
            self.session.verify = False

            # 删除 Cookie 文件
            if self.cookie_file.exists():
                self.cookie_file.unlink()

            # 重置状态
            self._is_logged_in = False
            self._login_time = None
            self._user_info = None

            print("已登出")

        except Exception as e:
            print(f"登出出错: {e}")

    def check_login_status(self) -> bool:
        """
        手动检查登录状态

        Returns:
            当前是否处于登录状态
        """
        return self._verify_login()

    def export_cookies_for_browser(self) -> str:
        """
        导出为浏览器可用的 Cookie 格式字符串

        Returns:
            Cookie 字符串（"key1=value1; key2=value2"）
        """
        cookies = []
        for name, value in self.session.cookies.items():
            cookies.append(f"{name}={value}")
        return "; ".join(cookies)

    def __repr__(self) -> str:
        status = "已登录" if self._is_logged_in else "未登录"
        return f"PixivAuth(status={status})"
