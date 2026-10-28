"""
Civitai 图片下载工作线程
基于 download_civitai.py 逻辑，整合为 QThread
"""

import os
import re
import time
import requests
import urllib3

from PyQt6.QtCore import QThread, pyqtSignal

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CivitaiDownloadWorker(QThread):
    """Civitai 图片下载工作线程"""

    # API 域名列表（优先使用 civitai.red，备用 civitai.com）
    API_DOMAINS = ['civitai.red', 'civitai.com']

    # 信号定义
    progress_updated = pyqtSignal(str, int, int)       # task_id, current, total
    image_downloaded = pyqtSignal(str, str, bool)       # task_id, filename, success
    status_changed = pyqtSignal(str, str)               # task_id, status
    log_message = pyqtSignal(str, str)                  # task_id, message
    finished = pyqtSignal(str)                          # task_id
    error = pyqtSignal(str, str)                        # task_id, error_message

    def __init__(self, task_id: str, version_id: str, output_dir: str,
                 max_pages: int = 10, interval: int = 2,
                 session: requests.Session = None):
        super().__init__()
        self.task_id = task_id
        self.version_id = version_id
        self.output_dir = output_dir
        self.max_pages = max_pages
        self.interval = interval
        self.session = session or requests.Session()
        self._is_running = True
        self._is_paused = False

    def run(self):
        try:
            self._do_download()
        except Exception as e:
            self.error.emit(self.task_id, str(e))
        finally:
            self.finished.emit(self.task_id)

    def stop(self):
        self._is_running = False

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    def _wait_if_paused(self):
        while self._is_paused and self._is_running:
            time.sleep(0.5)

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': f'https://{self.API_DOMAINS[0]}/'
        }

    def _retry_request(self, url, headers, max_retries=3, timeout=60):
        for attempt in range(max_retries):
            try:
                self.log_message.emit(self.task_id, f"请求中... (尝试 {attempt + 1}/{max_retries})")
                resp = self.session.get(url, headers=headers, timeout=timeout, verify=False)
                return resp
            except Exception as e:
                self.log_message.emit(self.task_id, f"请求失败: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    self.log_message.emit(self.task_id, f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
        return None

    def _get_all_media(self):
        """获取所有媒体文件 URL"""
        all_media = []
        headers = self._get_headers()

        # 尝试多个域名
        for domain in self.API_DOMAINS:
            result = self._fetch_media_from_domain(domain, headers)
            if result:
                all_media = result
                break
            self.log_message.emit(self.task_id, f"域名 {domain} 失败，尝试下一个...")

        if not all_media:
            self.log_message.emit(self.task_id, "所有域名均失败，尝试不带认证的请求...")
            # 最后的尝试：不带 session
            result = self._fetch_media_from_domain('civitai.com', self._get_headers(), use_session=False)
            if result:
                all_media = result

        return all_media

    def _fetch_media_from_domain(self, domain: str, headers: dict, use_session: bool = True):
        """从指定域名获取媒体列表"""
        all_media = []

        base_url = f'https://{domain}/api/v1/images?modelVersionId={self.version_id}&limit=20&nsfw=X'
        cursor = None

        for page in range(1, self.max_pages + 1):
            self._wait_if_paused()
            if not self._is_running:
                break

            if cursor:
                url = base_url + f'&cursor={cursor}'
            else:
                url = base_url

            self.log_message.emit(self.task_id, f"正在获取第 {page}/{self.max_pages} 页 [{domain}]")
            self.status_changed.emit(self.task_id, f"获取图片列表 {page}/{self.max_pages}")

            if page > 1:
                time.sleep(self.interval)

            resp = self._retry_request(url, headers, max_retries=3, timeout=60)

            if resp is None:
                self.log_message.emit(self.task_id, "API请求失败，已达到最大重试次数")
                break

            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items', [])
                metadata = data.get('metadata', {})
                cursor = metadata.get('nextCursor')

                self.log_message.emit(self.task_id, f"找到 {len(items)} 个项目")

                for item in items:
                    if isinstance(item, dict):
                        item_url = item.get('url', '') or item.get('imageUrl', '')
                        item_type = item.get('type', 'image')
                        if item_url:
                            if not item_url.startswith('http'):
                                item_url = 'https://image.civitai.com' + item_url
                            all_media.append({"type": item_type, "url": item_url})

                if not cursor or not items:
                    break
            else:
                self.log_message.emit(self.task_id, f"API请求失败，状态码: {resp.status_code}")
                if page == 1:
                    # 第一页就失败，说明这个域名不可用
                    return None
                break

        # 补充 API - 模型版本详情
        try:
            url2 = f'https://{domain}/api/v1/model-versions/{self.version_id}'
            self.log_message.emit(self.task_id, "正在获取补充图片...")
            resp2 = self.session.get(url2, headers=headers, timeout=30, verify=False)
            if resp2.status_code == 200:
                data2 = resp2.json()
                images = data2.get('images', [])
                self.log_message.emit(self.task_id, f"补充找到 {len(images)} 个项目")
                for img in images:
                    if isinstance(img, dict):
                        item_url = img.get('url', '') or img.get('imageUrl', '')
                        if item_url:
                            if not item_url.startswith('http'):
                                item_url = 'https://image.civitai.com' + item_url
                            all_media.append({"type": "image", "url": item_url})
        except Exception as e:
            self.log_message.emit(self.task_id, f"补充 API 请求出错: {str(e)}")

        # 去重
        unique_media = []
        seen_urls = set()
        for media in all_media:
            if media['url'] not in seen_urls:
                seen_urls.add(media['url'])
                unique_media.append(media)

        return unique_media if unique_media else None

    def _download_media(self, media_item, headers=None):
        if headers is None:
            headers = {'User-Agent': 'Mozilla/5.0'}

        media_url = media_item['url']
        media_type = media_item['type']

        try:
            resp = self.session.get(media_url, headers=headers, timeout=60, stream=True, verify=False)
            if resp.status_code == 200:
                filename = os.path.basename(media_url.split('?')[0])

                if media_type == 'video' and not filename.endswith('.mp4'):
                    filename = filename + '.mp4'
                elif media_type == 'image':
                    content_type = resp.headers.get('Content-Type', '')
                    if not (filename.endswith('.png') or filename.endswith('.jpg') or filename.endswith('.jpeg')):
                        if 'png' in content_type.lower():
                            filename = filename + '.png'
                        else:
                            filename = filename + '.jpg'

                filepath = os.path.join(self.output_dir, filename)

                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                return True, filename
            else:
                return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def _do_download(self):
        self.log_message.emit(self.task_id, f"开始获取 Civitai 版本 {self.version_id} 的图片...")
        self.status_changed.emit(self.task_id, "downloading")

        # 确保目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 获取媒体列表
        media_list = self._get_all_media()
        total = len(media_list)
        self.log_message.emit(self.task_id, f"共找到 {total} 个媒体文件")
        self.progress_updated.emit(self.task_id, 0, total)

        if total == 0:
            self.status_changed.emit(self.task_id, "completed")
            self.log_message.emit(self.task_id, "没有找到任何媒体文件")
            return

        # 下载
        success_count = 0
        fail_count = 0
        download_headers = {'User-Agent': 'Mozilla/5.0'}

        for i, media_item in enumerate(media_list):
            self._wait_if_paused()
            if not self._is_running:
                break

            self.progress_updated.emit(self.task_id, i + 1, total)
            self.log_message.emit(self.task_id, f"下载 {i + 1}/{total}")

            success, info = self._download_media(media_item, download_headers)

            if success:
                success_count += 1
                self.image_downloaded.emit(self.task_id, info, True)
            else:
                fail_count += 1
                self.image_downloaded.emit(self.task_id, info, False)
                self.log_message.emit(self.task_id, f"失败: {info}")

            if i < total - 1:
                time.sleep(self.interval)

        self.status_changed.emit(self.task_id, "completed")
        self.log_message.emit(self.task_id, f"下载完成！成功: {success_count}, 失败: {fail_count}")


class CivitaiSingleImageWorker(QThread):
    """Civitai 单张图片下载工作线程"""

    progress_updated = pyqtSignal(str, int, int)
    image_downloaded = pyqtSignal(str, str, bool)
    status_changed = pyqtSignal(str, str)
    log_message = pyqtSignal(str, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str, str)

    def __init__(self, task_id: str, image_id: str, image_url: str,
                 output_dir: str, session: requests.Session = None):
        super().__init__()
        self.task_id = task_id
        self.image_id = image_id
        self.image_url = image_url
        self.output_dir = output_dir
        self.session = session or requests.Session()
        self._is_running = True

    def run(self):
        try:
            self._do_download()
        except Exception as e:
            self.error.emit(self.task_id, str(e))
        finally:
            self.finished.emit(self.task_id)

    def stop(self):
        self._is_running = False

    def _do_download(self):
        self.log_message.emit(self.task_id, f"开始下载单张图片...")
        self.status_changed.emit(self.task_id, "downloading")
        self.progress_updated.emit(self.task_id, 0, 1)

        os.makedirs(self.output_dir, exist_ok=True)

        download_url = self.image_url

        # 如果没有预先获取到 URL，尝试从 API 获取
        if not download_url:
            self.log_message.emit(self.task_id, "从 API 获取图片信息...")
            download_url = self._fetch_image_url()

        if not download_url:
            self.log_message.emit(self.task_id, "❌ 无法获取图片下载地址")
            self.status_changed.emit(self.task_id, "failed")
            return

        self.log_message.emit(self.task_id, f"下载: {download_url[:80]}...")

        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            resp = self.session.get(download_url, headers=headers, timeout=60, stream=True, verify=False)
            if resp.status_code == 200:
                filename = os.path.basename(download_url.split('?')[0])
                if not filename or '.' not in filename:
                    content_type = resp.headers.get('Content-Type', '')
                    ext = '.jpg'
                    if 'png' in content_type.lower():
                        ext = '.png'
                    filename = f"image_{self.image_id}{ext}"

                filepath = os.path.join(self.output_dir, filename)
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                self.progress_updated.emit(self.task_id, 1, 1)
                self.image_downloaded.emit(self.task_id, filename, True)
                self.log_message.emit(self.task_id, f"✅ 下载完成: {filename}")
                self.status_changed.emit(self.task_id, "completed")
            else:
                self.log_message.emit(self.task_id, f"❌ 下载失败: HTTP {resp.status_code}")
                self.status_changed.emit(self.task_id, "failed")
        except Exception as e:
            self.log_message.emit(self.task_id, f"❌ 下载失败: {str(e)}")
            self.status_changed.emit(self.task_id, "failed")

    def _fetch_image_url(self) -> str:
        """从 API 获取图片下载地址（多种方法尝试）"""
        # 方法1：RESTful API
        for domain in ['civitai.red', 'civitai.com']:
            try:
                api_url = f"https://{domain}/api/v1/images/{self.image_id}"
                headers = {
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'application/json',
                }
                resp = self.session.get(api_url, headers=headers, timeout=15, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        url = data.get('url', '') or data.get('imageUrl', '')
                        if url:
                            if not url.startswith('http'):
                                url = 'https://image.civitai.com' + url
                            return url
                    items = data.get('items', [])
                    if items:
                        url = items[0].get('url', '') or items[0].get('imageUrl', '')
                        if url and not url.startswith('http'):
                            url = 'https://image.civitai.com' + url
                        return url
            except Exception as e:
                self.log_message.emit(self.task_id, f"API 请求失败 ({domain}): {e}")

        # 方法2：query 参数
        for domain in ['civitai.red', 'civitai.com']:
            try:
                api_url = f"https://{domain}/api/v1/images?imageId={self.image_id}"
                headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
                resp = self.session.get(api_url, headers=headers, timeout=15, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get('items', [])
                    if items:
                        url = items[0].get('url', '') or items[0].get('imageUrl', '')
                        if url and not url.startswith('http'):
                            url = 'https://image.civitai.com' + url
                        return url
            except Exception as e:
                self.log_message.emit(self.task_id, f"API 请求失败: {e}")

        # 方法3：从 HTML 页面提取真实图片 URL（解析 __NEXT_DATA__）
        for domain in ['civitai.red', 'civitai.com']:
            try:
                page_url = f"https://{domain}/images/{self.image_id}"
                headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html'}
                resp = self.session.get(page_url, headers=headers, timeout=15, verify=False)
                if resp.status_code == 200:
                    import re, json as json_module
                    html = resp.text
                    # 解析 __NEXT_DATA__
                    next_data_match = re.search(
                        r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                        html, re.DOTALL
                    )
                    if next_data_match:
                        try:
                            next_data = json_module.loads(next_data_match.group(1))
                            image_props = next_data.get('props', {}).get('pageProps', {})
                            image_data = image_props.get('image', {})
                            if isinstance(image_data, dict):
                                url = image_data.get('url') or image_data.get('imageUrl') or image_data.get('src')
                                if url and not url.startswith('http'):
                                    url = 'https://image.civitai.com' + url
                                if url and 'civitai.com/api/og' not in url:
                                    return url
                                files = image_data.get('files', [])
                                for f in files if isinstance(files, list) else []:
                                    url = f.get('url', '')
                                    if url and 'civitai.com/api/og' not in url:
                                        return url
                        except Exception:
                            pass
                    # 备用：直接匹配 image.civitai.com 链接
                    direct_match = re.search(
                        r'https?://image[^"\']*\.civitai\.com/[^"\'\s]+',
                        html
                    )
                    if direct_match:
                        url = direct_match.group(0)
                        if 'civitai.com/api/og' not in url:
                            return url
            except Exception as e:
                self.log_message.emit(self.task_id, f"HTML 获取失败: {e}")

        return ""