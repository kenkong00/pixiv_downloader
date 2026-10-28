"""
Civitai 任务对话框
用于创建 Civitai 图片下载任务
"""

import os
import sys
import re
import threading
import urllib3

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QFormLayout,
    QGroupBox, QMessageBox, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.config import Config
from utils.file_utils import clean_dirname

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CivitaiTaskDialog(QDialog):
    """Civitai 下载任务对话框"""

    # 信号：页面信息获取完成
    page_info_ready = pyqtSignal(str, str, str)  # model_name, version_name, resolved_version_id
    # 信号：单张图片信息获取完成
    image_info_ready = pyqtSignal(str, str, str)  # image_id, image_url, image_name

    def __init__(self, config: Config, parent=None, auth=None, prefilled_url: str = ""):
        super().__init__(parent)
        self.config = config
        self.auth = auth  # CivitaiAuth 实例
        self.task_data = None  # 返回的任务数据 dict
        self._model_name = ""  # 获取到的模型名称
        self._version_name = ""  # 获取到的版本名称
        self._resolved_version_id = ""  # 最终解析到的版本 ID（优先 URL 中的，否则自动获取）
        self._is_single_image = False  # 是否单张图片模式
        self._single_image_url = ""  # 单张图片的下载 URL
        self._fetch_lock = threading.Lock()
        self._last_fetched_url = ""

        self.setWindowTitle("新建 Civitai 下载任务")
        self.setMinimumWidth(600)
        self.setModal(True)

        self._init_ui()

        # 连接信号
        self.page_info_ready.connect(self._on_page_info_ready)
        self.image_info_ready.connect(self._on_image_info_ready)

        # 预填充 URL
        if prefilled_url:
            self.txt_model_url.setText(prefilled_url)

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ===== 基本信息 =====
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)

        # 模型页面链接
        self.txt_model_url = QLineEdit()
        self.txt_model_url.setPlaceholderText(
            "https://civitai.red/models/xxxxx?modelVersionId=xxxxx"
        )
        self.txt_model_url.textChanged.connect(self._on_url_changed)
        basic_layout.addRow("模型链接 *:", self.txt_model_url)

        # 解析提示
        self.lbl_parse_hint = QLabel("")
        self.lbl_parse_hint.setStyleSheet("color: #0066cc; font-size: 11px;")
        self.lbl_parse_hint.setWordWrap(True)
        basic_layout.addRow("", self.lbl_parse_hint)

        layout.addWidget(basic_group)

        # ===== 保存目录 =====
        dir_group = QGroupBox("保存目录")
        dir_layout = QVBoxLayout(dir_group)

        input_row = QHBoxLayout()
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setPlaceholderText("选择或输入要保存到的目录路径")
        input_row.addWidget(self.txt_output_dir)

        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._on_browse_directory)
        btn_browse.setFixedWidth(70)
        input_row.addWidget(btn_browse)
        dir_layout.addLayout(input_row)

        self.lbl_default_dir = QLabel()
        self.lbl_default_dir.setStyleSheet("color: #888; font-size: 10px;")
        self.lbl_default_dir.setWordWrap(True)
        dir_layout.addWidget(self.lbl_default_dir)

        layout.addWidget(dir_group)

        # ===== 高级选项 =====
        advanced_group = QGroupBox("高级选项")
        advanced_layout = QFormLayout(advanced_group)

        self.spin_max_pages = QSpinBox()
        self.spin_max_pages.setRange(1, 50)
        self.spin_max_pages.setValue(10)
        self.spin_max_pages.setToolTip("最大获取页数（每页约20张图片）")
        advanced_layout.addRow("最大页数:", self.spin_max_pages)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 30)
        self.spin_interval.setValue(2)
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setToolTip("两次请求之间的间隔，避免被限流")
        advanced_layout.addRow("请求间隔:", self.spin_interval)

        layout.addWidget(advanced_group)

        # ===== 按钮区域 =====
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_ok = QPushButton("确定")
        btn_ok.setMinimumWidth(100)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept_if_valid)
        btn_layout.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumWidth(80)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        self._init_default_directory()

    def _on_url_changed(self, text: str):
        if not text.strip():
            self.lbl_parse_hint.setText("")
            self.lbl_default_dir.setText("")
            return

        # 检测是否是单张图片链接 /images/数字
        image_match = re.search(r'/images/(\d+)', text)
        if image_match:
            self._is_single_image = True
            image_id = image_match.group(1)
            # 隐藏高级选项（单张图片不需要）
            self.spin_max_pages.setEnabled(False)
            self.spin_interval.setEnabled(False)

            self.lbl_parse_hint.setText(f"⏳ 正在获取图片信息...")
            self.lbl_parse_hint.setStyleSheet("color: #0066cc; font-size: 11px;")

            domain = self._extract_domain(text)
            self._fetch_image_info_async(domain, image_id)
            return

        # 检测是否是批量模型链接 /models/数字
        model_match = re.search(r'/models/(\d+)', text)
        if not model_match:
            self.lbl_parse_hint.setText("❌ 无法识别 URL，请提供 /models/数字 或 /images/数字 的链接")
            self.lbl_parse_hint.setStyleSheet("color: red; font-size: 11px;")
            return

        self._is_single_image = False
        self.spin_max_pages.setEnabled(True)
        self.spin_interval.setEnabled(True)

        model_id = model_match.group(1)
        version_match = re.search(r'modelVersionId=(\d+)', text)
        version_id = version_match.group(1) if version_match else ""

        if version_id:
            self.lbl_parse_hint.setText(f"⏳ 正在获取模型信息...")
        else:
            self.lbl_parse_hint.setText(f"⏳ 正在获取模型信息（自动查找默认版本）...")
        self.lbl_parse_hint.setStyleSheet("color: #0066cc; font-size: 11px;")

        # 异步获取页面信息
        domain = self._extract_domain(text)
        self._fetch_page_info_async(domain, model_id, version_id)

    def _extract_domain(self, url: str) -> str:
        """从 URL 中提取域名"""
        match = re.search(r'https?://([^/]+)', url)
        return match.group(1) if match else 'civitai.red'

    def _fetch_page_info_async(self, domain: str, model_id: str, version_id: str):
        """异步获取模型名称和版本名称（如果 version_id 为空，自动获取默认版本）"""
        fetch_key = f"{domain}:{model_id}:{version_id}"
        if fetch_key == self._last_fetched_url:
            return
        self._last_fetched_url = fetch_key

        def fetch():
            import requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/json',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }

            model_name = ""
            version_name = ""
            resolved_version_id = version_id

            session = self.auth.get_session() if self.auth else None

            try:
                # 从 HTML 页面获取模型名称
                page_url = f"https://{domain}/models/{model_id}"
                if session:
                    resp = session.get(page_url, headers=headers, timeout=15, verify=False)
                else:
                    resp = requests.get(page_url, headers=headers, timeout=15, verify=False)

                if resp.status_code == 200:
                    html = resp.text
                    # 提取 <h1> 标签中的模型名称
                    h1_match = re.search(
                        r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>',
                        html, re.DOTALL
                    )
                    if not h1_match:
                        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
                    if h1_match:
                        raw_name = h1_match.group(1).strip()
                        raw_name = re.sub(r'<[^>]+>', '', raw_name)
                        raw_name = raw_name.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#x27;', "'")
                        model_name = raw_name.strip()
                        print(f"[Civitai] 获取到模型名称: {model_name}")
            except Exception as e:
                print(f"[Civitai] 获取模型名称失败: {e}")

            # 如果没有 version_id，先获取默认版本
            if not resolved_version_id:
                try:
                    model_api_url = f"https://{domain}/api/v1/models/{model_id}"
                    headers['Accept'] = 'application/json'
                    if session:
                        resp = session.get(model_api_url, headers=headers, timeout=15, verify=False)
                    else:
                        resp = requests.get(model_api_url, headers=headers, timeout=15, verify=False)

                    if resp.status_code == 200:
                        data = resp.json()
                        versions = data.get('modelVersions', [])
                        if versions:
                            # 取第一个版本（默认版本）
                            first_version = versions[0]
                            resolved_version_id = str(first_version.get('id', ''))
                            version_name = first_version.get('name', '')
                            print(f"[Civitai] 自动获取默认版本: {resolved_version_id} ({version_name})")
                except Exception as e:
                    print(f"[Civitai] 获取默认版本失败: {e}")
            else:
                # 有 version_id，获取版本名称
                try:
                    api_url = f"https://{domain}/api/v1/model-versions/{resolved_version_id}"
                    headers['Accept'] = 'application/json'
                    if session:
                        resp = session.get(api_url, headers=headers, timeout=15, verify=False)
                    else:
                        resp = requests.get(api_url, headers=headers, timeout=15, verify=False)

                    if resp.status_code == 200:
                        data = resp.json()
                        version_name = data.get('name', '')
                        print(f"[Civitai] 获取到版本名称: {version_name}")
                except Exception as e:
                    print(f"[Civitai] 获取版本名称失败: {e}")

            self.page_info_ready.emit(model_name, version_name, resolved_version_id)

        threading.Thread(target=fetch, daemon=True).start()

    def _fetch_image_info_async(self, domain: str, image_id: str):
        """异步获取单张图片信息"""
        fetch_key = f"image:{domain}:{image_id}"
        if fetch_key == self._last_fetched_url:
            return
        self._last_fetched_url = fetch_key

        def fetch():
            import requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json,text/html',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }

            image_url = ""
            image_name = f"image_{image_id}"

            session = self.auth.get_session() if self.auth else None

            # 方法1：尝试 RESTful API 路径 /api/v1/images/{image_id}
            for api_domain in [domain, 'civitai.com', 'civitai.red']:
                if image_url:
                    break
                try:
                    api_url = f"https://{api_domain}/api/v1/images/{image_id}"
                    if session:
                        resp = session.get(api_url, headers=headers, timeout=15, verify=False)
                    else:
                        resp = requests.get(api_url, headers=headers, timeout=15, verify=False)

                    if resp.status_code == 200:
                        data = resp.json()
                        # 可能直接返回单个对象
                        if isinstance(data, dict):
                            url = data.get('url', '') or data.get('imageUrl', '')
                            if url:
                                if not url.startswith('http'):
                                    url = 'https://image.civitai.com' + url
                                image_url = url
                                print(f"[Civitai] 通过 REST API 获取到图片: {image_url[:80]}...")
                                break
                        # 也可能返回 items 列表
                        items = data.get('items', [])
                        if items:
                            item = items[0]
                            url = item.get('url', '') or item.get('imageUrl', '')
                            if url:
                                if not url.startswith('http'):
                                    url = 'https://image.civitai.com' + url
                                image_url = url
                                print(f"[Civitai] 通过 API 获取到图片: {image_url[:80]}...")
                                break
                except Exception as e:
                    print(f"[Civitai] API 请求失败 ({api_domain}): {e}")

            # 方法2：尝试 query 参数
            if not image_url:
                for api_domain in [domain, 'civitai.com', 'civitai.red']:
                    try:
                        api_url = f"https://{api_domain}/api/v1/images?imageId={image_id}"
                        if session:
                            resp = session.get(api_url, headers=headers, timeout=15, verify=False)
                        else:
                            resp = requests.get(api_url, headers=headers, timeout=15, verify=False)

                        if resp.status_code == 200:
                            data = resp.json()
                            items = data.get('items', [])
                            if items:
                                item = items[0]
                                url = item.get('url', '') or item.get('imageUrl', '')
                                if url:
                                    if not url.startswith('http'):
                                        url = 'https://image.civitai.com' + url
                                    image_url = url
                                    print(f"[Civitai] 通过 query API 获取到图片: {image_url[:80]}...")
                                    break
                    except Exception as e:
                        print(f"[Civitai] API 请求失败: {e}")

            # 方法3：从 HTML 页面提取真实图片 URL（解析 __NEXT_DATA__）
            if not image_url:
                try:
                    page_url = f"https://{domain}/images/{image_id}"
                    if session:
                        resp = session.get(page_url, headers=headers, timeout=15, verify=False)
                    else:
                        resp = requests.get(page_url, headers=headers, timeout=15, verify=False)

                    if resp.status_code == 200:
                        html = resp.text
                        # 解析 __NEXT_DATA__ 获取真实图片 URL
                        next_data_match = re.search(
                            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                            html, re.DOTALL
                        )
                        if next_data_match:
                            import json as json_module
                            try:
                                next_data = json_module.loads(next_data_match.group(1))
                                # 遍历查找图片 URL
                                image_props = next_data.get('props', {}).get('pageProps', {})
                                image_data = image_props.get('image', {})
                                if isinstance(image_data, dict):
                                    # 尝试多种可能的字段名
                                    url = image_data.get('url') or image_data.get('imageUrl') or image_data.get('src')
                                    if url and not url.startswith('http'):
                                        url = 'https://image.civitai.com' + url
                                    if url and not url.endswith('.svg') and 'civitai.com/api/og' not in url:
                                        image_url = url
                                        print(f"[Civitai] 通过 __NEXT_DATA__ 获取到图片: {image_url[:80]}...")

                                # 也尝试从 files 中获取
                                if not image_url:
                                    files = image_data.get('files', [])
                                    for f in files if isinstance(files, list) else []:
                                        url = f.get('url', '')
                                        if url and 'civitai.com/api/og' not in url:
                                            image_url = url
                                            break
                            except Exception as e:
                                print(f"[Civitai] __NEXT_DATA__ 解析失败: {e}")

                        # 备用：找 image.civitai.com 或 image-b2.civitai.com 的链接
                        if not image_url:
                            direct_match = re.search(
                                r'https?://image[^"\']*\.civitai\.com/[^"\'\s]+',
                                html
                            )
                            if direct_match:
                                url = direct_match.group(0)
                                if 'civitai.com/api/og' not in url:
                                    image_url = url
                                    print(f"[Civitai] 通过图片链接匹配获取: {image_url[:80]}...")
                except Exception as e:
                    print(f"[Civitai] HTML 页面获取失败: {e}")

            # 从 URL 中提取文件名
            if image_url:
                url_filename = os.path.basename(image_url.split('?')[0])
                if url_filename and '.' in url_filename:
                    image_name = url_filename.rsplit('.', 1)[0]

            self.image_info_ready.emit(image_id, image_url, image_name)

        threading.Thread(target=fetch, daemon=True).start()

    def _on_image_info_ready(self, image_id: str, image_url: str, image_name: str):
        """单张图片信息获取完成的回调（主线程）"""
        self._single_image_url = image_url

        if image_url:
            self.lbl_parse_hint.setText(f"✅ 单张图片: {image_name}")
            self.lbl_parse_hint.setStyleSheet("color: green; font-size: 11px;")
        else:
            self.lbl_parse_hint.setText(f"⚠️ 图片信息获取失败，将尝试直接下载")
            self.lbl_parse_hint.setStyleSheet("color: orange; font-size: 11px;")

        # 下载目录：civitai/images/（统一不分子目录）
        default_base = self._get_default_download_dir()
        default_dir = os.path.join(default_base, 'images')
        self.lbl_default_dir.setText(f"默认: {default_dir}")

        if not self.txt_output_dir.text().strip():
            self.txt_output_dir.setText(default_dir)

    def _on_page_info_ready(self, model_name: str, version_name: str, resolved_version_id: str):
        """页面信息获取完成的回调（主线程）"""
        self._model_name = model_name
        self._version_name = version_name
        self._resolved_version_id = resolved_version_id

        text = self.txt_model_url.text().strip()
        version_match = re.search(r'modelVersionId=(\d+)', text)
        model_match = re.search(r'/models/(\d+)', text)

        version_id = resolved_version_id or (version_match.group(1) if version_match else "")
        model_id = model_match.group(1) if model_match else version_id

        # 构建目录名
        parts = []
        if model_name:
            parts.append(model_name)
        if version_name:
            parts.append(version_name)
        if not parts:
            parts.append(f"civitai_{model_id}_v{version_id}")

        dir_name = "_".join(parts)
        # 清理目录名中的非法字符
        dir_name = clean_dirname(dir_name)

        # 更新提示
        hint_text = f"✅ 模型: {model_name or '未知'}"
        if version_name:
            hint_text += f" | 版本: {version_name}"
        if not version_match and resolved_version_id:
            hint_text += f" (自动获取)"
        self.lbl_parse_hint.setText(hint_text)
        self.lbl_parse_hint.setStyleSheet("color: green; font-size: 11px;")

        # 更新目录
        default_base = self._get_default_download_dir()
        full_dir = os.path.join(default_base, dir_name)
        self.lbl_default_dir.setText(f"默认: {full_dir}")

        # 自动填充保存目录
        if not self.txt_output_dir.text().strip():
            self.txt_output_dir.setText(full_dir)

    def _get_default_download_dir(self):
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        downloads_dir = os.path.join(app_dir, 'downloads', 'civitai')
        os.makedirs(downloads_dir, exist_ok=True)
        return downloads_dir

    def _init_default_directory(self):
        default_dir = self._get_default_download_dir()
        self.lbl_default_dir.setText(f"默认: {default_dir}")

    def _on_browse_directory(self):
        current_dir = self.txt_output_dir.text().strip()
        if not current_dir:
            current_dir = self._get_default_download_dir()

        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录", current_dir)
        if dir_path:
            self.txt_output_dir.setText(dir_path)

    def accept_if_valid(self):
        model_url = self.txt_model_url.text().strip()
        output_dir = self.txt_output_dir.text().strip()

        if not model_url:
            QMessageBox.warning(self, "错误", "请填写模型链接！")
            self.txt_model_url.setFocus()
            return

        if not output_dir:
            QMessageBox.warning(self, "错误", "请选择或输入保存目录！")
            self.txt_output_dir.setFocus()
            return

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "创建目录失败", f"无法创建保存目录：\n\n{output_dir}\n\n错误：{str(e)}")
                return

        # 单张图片模式
        if self._is_single_image:
            image_match = re.search(r'/images/(\d+)', model_url)
            image_id = image_match.group(1) if image_match else ""
            self.task_data = {
                'is_single_image': True,
                'image_url': self._single_image_url,
                'image_id': image_id,
                'output_dir': output_dir,
                'model_url': model_url,
            }
            self.accept()
            return

        # 批量模型模式
        version_match = re.search(r'modelVersionId=(\d+)', model_url)
        if version_match:
            version_id = version_match.group(1)
        elif self._resolved_version_id:
            version_id = self._resolved_version_id
        else:
            QMessageBox.warning(
                self, "错误",
                "无法获取版本信息！\n\n"
                "请确保 URL 中包含 ?modelVersionId=数字，\n"
                "或等待页面信息自动获取完成后再点击确定。"
            )
            self.txt_model_url.setFocus()
            return

        self.task_data = {
            'is_single_image': False,
            'model_url': model_url,
            'version_id': version_id,
            'output_dir': output_dir,
            'max_pages': self.spin_max_pages.value(),
            'interval': self.spin_interval.value(),
        }
        self.accept()

    def get_task_data(self) -> dict:
        return self.task_data