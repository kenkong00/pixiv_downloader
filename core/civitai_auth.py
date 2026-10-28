"""
Civitai 认证模块
管理用户登录、Cookie/Session 维护
"""

import os
import json
import time
from typing import Optional, Dict, Any
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CivitaiAuth:
    """Civitai 认证管理器"""

    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://civitai.com/',
    }

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')

        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.cookie_file = self.config_dir / 'civitai_cookies.json'
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.session.verify = False

        self._is_logged_in = False
        self._login_time: Optional[float] = None

        self._load_cookies()

    @property
    def is_logged_in(self) -> bool:
        return self._is_logged_in

    def get_session(self) -> requests.Session:
        return self.session

    def login_by_cookie_string(self, cookie_string: str) -> bool:
        try:
            cookies = {}
            for item in cookie_string.split(';'):
                item = item.strip()
                if '=' in item:
                    key, value = item.split('=', 1)
                    cookies[key.strip()] = value.strip()

            if not cookies:
                return False

            self.session.cookies.update(cookies)

            if self._verify_login():
                self._save_cookies()
                return True
            else:
                print("Civitai Cookie 验证失败")
                return False

        except Exception as e:
            print(f"Civitai Cookie 导入错误: {e}")
            return False

    def login_by_cookies_dict(self, cookies: Dict[str, str]) -> bool:
        try:
            self.session.cookies.update(cookies)
            if self._verify_login():
                self._save_cookies()
                return True
            else:
                return False
        except Exception as e:
            print(f"Civitai Cookie 设置错误: {e}")
            return False

    def _verify_login(self) -> bool:
        """验证登录状态，尝试多个域名"""
        verify_urls = [
            'https://civitai.red/api/v1/account',
            'https://civitai.com/api/v1/account',
        ]
        
        for url in verify_urls:
            try:
                resp = self.session.get(
                    url,
                    timeout=15,
                    allow_redirects=True
                )
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if data.get('username'):
                            self._is_logged_in = True
                            self._login_time = time.time()
                            print(f"Civitai 登录成功: {data.get('username')} (via {url})")
                            return True
                    except Exception:
                        pass
            except Exception as e:
                print(f"Civitai 验证请求失败 ({url}): {e}")
                continue

        # 备用：尝试访问首页
        try:
            resp = self.session.get(
                'https://civitai.red/',
                timeout=15,
                allow_redirects=True
            )
            if resp.status_code == 200 and len(resp.content) > 1000:
                # 检查是否包含登录用户信息
                if 'username' in resp.text.lower() or 'signed-in' in resp.text.lower():
                    self._is_logged_in = True
                    self._login_time = time.time()
                    print("Civitai 登录成功（通过首页检测）")
                    return True
        except Exception as e:
            print(f"Civitai 首页验证失败: {e}")

        print("Civitai Cookie 验证失败")
        self._is_logged_in = False
        return False

    def _save_cookies(self):
        try:
            cookies_dict = {}
            for cookie in self.session.cookies:
                cookies_dict[cookie.name] = cookie.value
            data = {
                'cookies': cookies_dict,
                'saved_time': time.time(),
            }
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Civitai Cookie 已保存到: {self.cookie_file}")
        except Exception as e:
            print(f"保存 Civitai Cookie 失败: {e}")

    def _load_cookies(self) -> bool:
        if not self.cookie_file.exists():
            return False

        try:
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            saved_time = data.get('saved_time', 0)
            if time.time() - saved_time > 30 * 24 * 3600:
                print("Civitai Cookie 可能已过期（超过30天）")

            cookies = data.get('cookies', {})
            if cookies:
                self.session.cookies.update(cookies)

            print(f"已从本地加载 Civitai Cookie: {len(cookies)} 个")

            if self._verify_login():
                return True
            else:
                print("已保存的 Civitai Cookie 无效，需要重新登录")
                return False

        except Exception as e:
            print(f"加载 Civitai Cookie 失败: {e}")
            return False

    def logout(self):
        try:
            self.session.close()
            self.session = requests.Session()
            self.session.headers.update(self.DEFAULT_HEADERS)
            self.session.verify = False

            if self.cookie_file.exists():
                self.cookie_file.unlink()

            self._is_logged_in = False
            self._login_time = None
            print("Civitai 已登出")
        except Exception as e:
            print(f"Civitai 登出出错: {e}")

    def check_login_status(self) -> bool:
        return self._verify_login()