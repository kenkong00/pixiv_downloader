"""
新建任务对话框
用于创建新的 Pixiv 图片下载任务
"""

import os
import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QMessageBox, QFileDialog, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# 导入项目模块
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.task_model import DownloadTask, TaskSettings
from models.config import Config
from core.url_parser import URLParser
from utils.file_utils import clean_dirname


class TaskDialog(QDialog):
    """
    新建任务对话框

    收集用户输入的下载任务信息：
    - 作品页面 URL
    - 第一张图片 URL
    - 输出目录
    - 高级选项
    """

    def __init__(self, config: Config, parent=None, auth=None):
        super().__init__(parent)

        self.config = config
        self.auth = auth  # PixivAuth 实例，用于自动抓取
        self.task: DownloadTask = None
        self._fetching = False  # 防止重复请求

        self.setWindowTitle("新建下载任务")
        self.setMinimumWidth(600)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)

        # ===== 基本信息 =====
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)

        # 作品链接
        self.txt_artwork_url = QLineEdit()
        self.txt_artwork_url.setPlaceholderText(
            "https://www.pixiv.net/artworks/xxxxxxxxx"
        )
        self.txt_artwork_url.textChanged.connect(self._on_artwork_url_changed)
        basic_layout.addRow("作品链接 *:", self.txt_artwork_url)

        # 解析提示
        self.lbl_parse_hint = QLabel("")
        self.lbl_parse_hint.setStyleSheet("color: #0066cc; font-size: 11px;")
        self.lbl_parse_hint.setWordWrap(True)
        basic_layout.addRow("", self.lbl_parse_hint)

        # 第一张图片地址
        self.txt_first_image_url = QLineEdit()
        self.txt_first_image_url.setPlaceholderText(
            "https://i.pximg.net/img-master/img/.../xxx_p0_master1200.jpg"
        )
        self.txt_first_image_url.textChanged.connect(self._on_image_url_changed)
        basic_layout.addRow("第一张图片地址 *:", self.txt_first_image_url)

        # 图片解析提示
        self.lbl_image_hint = QLabel("")
        self.lbl_image_hint.setStyleSheet("color: #0066cc; font-size: 11px;")
        self.lbl_image_hint.setWordWrap(True)
        basic_layout.addRow("", self.lbl_image_hint)

        layout.addWidget(basic_group)

        # ===== 保存目录 =====
        dir_group = QGroupBox("保存目录")
        dir_layout = QVBoxLayout(dir_group)

        # 第一行：输入框 + 浏览按钮
        input_row = QHBoxLayout()
        self.txt_output_dir = QLineEdit()
        last_dir = self.config.get('download', 'save_last_directory', '')
        if last_dir:
            self.txt_output_dir.setText(last_dir)
        else:
            self.txt_output_dir.setPlaceholderText(
                "选择或输入要保存到的目录路径"
            )

        input_row.addWidget(self.txt_output_dir)

        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._on_browse_directory)
        btn_browse.setFixedWidth(70)
        input_row.addWidget(btn_browse)
        dir_layout.addLayout(input_row)

        # 第二行：默认目录提示（单独一行）
        self.lbl_default_dir = QLabel()
        self.lbl_default_dir.setStyleSheet("color: #888; font-size: 10px;")
        self.lbl_default_dir.setWordWrap(True)
        dir_layout.addWidget(self.lbl_default_dir)

        layout.addWidget(dir_group)

        # ===== 高级选项（可折叠）=====
        advanced_group = QGroupBox("高级选项")
        advanced_layout = QFormLayout(advanced_group)

        # 并发数
        self.spin_max_pages = QSpinBox()
        self.spin_max_pages.setRange(1, 1000)
        self.spin_max_pages.setValue(200)
        self.spin_max_pages.setToolTip("最大尝试下载的页数（实际会自动在遇到404时停止）")
        advanced_layout.addRow("最大页数:", self.spin_max_pages)

        # 重试次数
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(0, 10)
        self.spin_retries.setValue(3)
        advanced_layout.addRow("重试次数:", self.spin_retries)

        # 超时时间
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(5, 120)
        self.spin_timeout.setValue(30)
        self.spin_timeout.setSuffix(" 秒")
        advanced_layout.addRow("超时时间:", self.spin_timeout)

        # 请求间隔
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setRange(0.1, 10.0)
        self.spin_interval.setValue(1.0)
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setSingleStep(0.1)
        self.spin_interval.setToolTip("两次请求之间的间隔，避免被限流")
        advanced_layout.addRow("请求间隔:", self.spin_interval)

        layout.addWidget(advanced_group)

        # ===== 按钮区域 =====
        btn_layout = QHBoxLayout()

        btn_auto_fill = QPushButton("🔗 从链接自动填充")
        btn_auto_fill.setToolTip("如果只填了作品链接，尝试自动获取第一张图片URL")
        btn_auto_fill.clicked.connect(self._on_auto_fill)
        btn_layout.addWidget(btn_auto_fill)

        btn_layout.addStretch()

        btn_ok = QPushButton("✅ 确定")
        btn_ok.setMinimumWidth(100)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept_if_valid)
        btn_layout.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumWidth(80)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        # 设置 Tab 顺序
        self.setTabOrder(self.txt_artwork_url, self.txt_first_image_url)
        self.setTabOrder(self.txt_first_image_url, self.txt_output_dir)

        # 初始化默认下载目录
        self._init_default_directory()

    def _on_artwork_url_changed(self, text: str):
        """处理作品链接变化 - 自动尝试获取第一张图片地址"""
        # 先尝试标准解析
        result = URLParser.parse_artwork_url(text)

        if result:
            artwork_id = result['artwork_id']
            self.lbl_parse_hint.setText(f"✅ 已识别作品 ID: {artwork_id}")
            self.lbl_parse_hint.setStyleSheet("color: green; font-size: 11px;")

            # 更新默认目录名
            default_name = f"pixiv\\作品_{artwork_id}"
            self.lbl_default_dir.setText(f"默认: {default_name}")

            # 如果图片地址为空，自动尝试抓取第一张图片地址
            if not self.txt_first_image_url.text().strip() and self.auth and self.auth.is_logged_in:
                self._schedule_auto_fetch(text)

        elif text.strip():
            # 备用方案：尝试从 URL 中提取数字 ID（更宽松的匹配）
            import re

            # 清理 URL
            clean_text = text.strip()
            # 去除常见干扰字符
            clean_text = re.sub(r'[|,;\s\'"<>\[\]{}()]', '', clean_text)

            # 尝试多种模式提取 artwork ID
            patterns = [
                r'/artworks/(\d+)',                    # 标准格式
                r'illust_id=(\d+)',                     # 旧格式参数
                r'pixiv.*/(\d{6,})',                   # 任何 pixiv 域名后的 6 位以上数字
                r'artworks[=/](\d+)',                  # artworks 后的数字
            ]

            extracted_id = None
            for pattern in patterns:
                match = re.search(pattern, clean_text)
                if match:
                    extracted_id = match.group(1)
                    break

            if extracted_id:
                self.lbl_parse_hint.setText(
                    f"✅ 已识别作品 ID: {extracted_id} (智能提取)"
                )
                self.lbl_parse_hint.setStyleSheet("color: green; font-size: 11px;")
                default_name = f"pixiv\\作品_{extracted_id}"
                self.lbl_default_dir.setText(f"默认: {default_name}")

                # 同样尝试自动抓取
                if not self.txt_first_image_url.text().strip() and self.auth and self.auth.is_logged_in:
                    self._schedule_auto_fetch(text)
            else:
                valid, msg = URLParser.validate_url(text)
                if not valid:
                    self.lbl_parse_hint.setText(f"❌ {msg}")
                    self.lbl_parse_hint.setStyleSheet("color: red; font-size: 11px;")
                else:
                    # 显示调试信息：URL 长度和前 50 个字符
                    debug_info = f"⚠️ 无法识别 (长度:{len(text)})"
                    if len(text) > 0:
                        # 显示清理后的前 30 个字符，帮助用户发现问题
                        display_text = repr(text[:50])
                        debug_info += f"\n内容预览: {display_text}"
                    self.lbl_parse_hint.setText(debug_info)
                    self.lbl_parse_hint.setStyleSheet("color: orange; font-size: 10px;")
                    self.lbl_default_dir.setText("")
        else:
            self.lbl_parse_hint.setText("")
            self.lbl_default_dir.setText("")

    def _schedule_auto_fetch(self, artwork_url: str):
        """延迟触发自动抓取（避免每次按键都请求）"""
        from PyQt6.QtCore import QTimer

        # 取消之前的定时器（如果有）
        if hasattr(self, '_auto_fetch_timer') and self._auto_fetch_timer:
            self._auto_fetch_timer.stop()

        # 创建新的定时器，800ms 后执行
        self._auto_fetch_timer = QTimer()
        self._auto_fetch_timer.setSingleShot(True)
        self._auto_fetch_timer.timeout.connect(lambda: self._do_auto_fetch(artwork_url))
        self._auto_fetch_timer.start(800)

    def _do_auto_fetch(self, artwork_url: str):
        """执行自动抓取 - 在后台线程中运行"""
        if self._fetching:
            return

        print(f"[TaskDialog] _do_auto_fetch 开始: {artwork_url}")
        print(f"[TaskDialog] auth 存在: {self.auth is not None}")
        print(f"[TaskDialog] 已登录: {self.auth.is_logged_in if self.auth else 'N/A'}")

        self._fetching = True
        self.lbl_parse_hint.setText(
            f"✅ 已识别作品 ID | 🔄 正在自动获取图片地址..."
        )
        self.lbl_parse_hint.setStyleSheet("color: #0066cc; font-size: 11px;")

        # 使用 QThread 在后台执行网络请求
        from PyQt6.QtCore import QThread, pyqtSignal as pyqtSignalThread

        class FetchWorker(QThread):
            finished = pyqtSignalThread(object)  # 解析结果或 None

            def __init__(self, url, session):
                super().__init__()
                self.url = url
                self.session = session

            def run(self):
                try:
                    result = URLParser.fetch_first_image_from_artwork(self.url, self.session)
                    self.finished.emit(result)
                except Exception as e:
                    print(f"[AutoFetch] 错误: {e}")
                    self.finished.emit(None)

        # 启动工作线程
        session = self.auth.get_session() if self.auth else None
        self._fetch_worker = FetchWorker(artwork_url, session)
        self._fetch_worker.finished.connect(self._on_auto_fetch_completed)
        self._fetch_worker.start()

    def _on_auto_fetch_completed(self, result):
        """自动抓取完成回调"""
        self._fetching = False

        if result and result.get('base_url'):
            # 获取成功，填充到输入框
            artwork_id = result['artwork_id']
            source_format = result.get('source_format', 'master')
            title = result.get('title', '')

            # 构建第一张图片的 master 地址用于显示
            first_master_url = URLParser.build_first_image_master_url(
                artwork_id,
                result.get('date_path'),
                result.get('hash')
            )

            # 填充图片地址（不触发信号循环）
            self.txt_first_image_url.blockSignals(True)
            self.txt_first_image_url.setText(first_master_url)
            self.txt_first_image_url.blockSignals(False)

            # 如果有标题，始终用标题作为默认目录名（每次新建任务都是新作品）
            if title:
                from utils.file_utils import clean_dirname
                clean_title = clean_dirname(title)

                # 获取默认下载目录
                default_base_dir = self._get_default_download_dir()
                full_dir = os.path.join(default_base_dir, clean_title) if default_base_dir else f"pixiv\\{clean_title}"

                self.txt_output_dir.blockSignals(True)
                self.txt_output_dir.setText(full_dir)
                self.txt_output_dir.blockSignals(False)

                # 更新默认目录提示
                self.lbl_default_dir.setText(f"📂 默认保存到: {full_dir}")

            # 更新提示
            format_note = ""
            if source_format == 'original':
                format_note = " (原始格式→已转换)"

            hint_text = f"✅ 已识别作品 ID: {artwork_id} | ✅ 自动获取图片地址成功{format_note}"
            if title:
                hint_text += f"\n📁 标题: {title}"

            self.lbl_parse_hint.setText(hint_text)
            self.lbl_parse_hint.setStyleSheet("color: green; font-size: 11px;")

            # 同时更新图片解析提示
            self.lbl_image_hint.setText(
                f"✅ 已识别图片模板 (ID: {artwork_id}, 自动获取)"
            )
            self.lbl_image_hint.setStyleSheet("color: green; font-size: 11px;")
        else:
            # 获取失败，提示用户手动输入
            current_text = self.lbl_parse_hint.text()
            if "已识别" in current_text:
                # 保留作品 ID 识别结果，追加获取失败提示
                self.lbl_parse_hint.setText(
                    f"{current_text} | ⚠️ 无法自动获取图片地址，请手动填写"
                )
                self.lbl_parse_hint.setStyleSheet("color: orange; font-size: 10px;")

    def _get_default_download_dir(self):
        """获取默认下载目录"""
        # 优先使用配置中的默认下载目录
        configured_dir = self.config.get('download.default_download_dir', '')
        if configured_dir and os.path.isdir(configured_dir):
            return configured_dir

        # 使用上次使用的目录的父目录
        last_dir = self.config.get('download.save_last_directory', '')
        if last_dir and os.path.isdir(os.path.dirname(last_dir)):
            return os.path.dirname(last_dir)

        # 默认：程序目录下的 downloads/pixiv
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        downloads_dir = os.path.join(app_dir, 'downloads', 'pixiv')

        # 确保目录存在
        os.makedirs(downloads_dir, exist_ok=True)

        return downloads_dir

    def _init_default_directory(self):
        """初始化默认下载目录"""
        default_dir = self._get_default_download_dir()
        self.lbl_default_dir.setText(f"默认: {default_dir}")

    def _on_image_url_changed(self, text: str):
        """处理图片 URL 变化 - 智能识别 master/original 格式并自动联动"""
        # 使用智能解析（同时支持 img-master 和 img-original 格式）
        result = URLParser.smart_parse_image_url(text)

        # 调试输出
        print(f"[TaskDialog] _on_image_url_changed 输入: {text[:60] if text else '空'}...")
        print(f"[TaskDialog] smart_parse_image_url 结果: {result}")

        if result:
            artwork_id = result['artwork_id']
            has_hash = bool(result.get('hash'))
            source_format = result.get('source_format', 'master')

            # 构建提示信息
            if source_format == 'original':
                hint = f"✅ 已识别图片 (ID: {artwork_id}, 原始格式 → 已转换为下载格式)"
                # 自动将输入框内容转换为标准 master 格式（显示给用户看）
                first_master_url = URLParser.build_first_image_master_url(
                    artwork_id,
                    result.get('date_path'),
                    result.get('hash')
                )
                # 更新输入框为标准格式（用户可以看到转换结果）
                self.txt_first_image_url.blockSignals(True)
                self.txt_first_image_url.setText(first_master_url)
                self.txt_first_image_url.blockSignals(False)
            else:
                hint = f"✅ 已识别图片模板 (ID: {artwork_id}"
                if has_hash:
                    hint += f", 带 Hash)"
                else:
                    hint += ")"

            self.lbl_image_hint.setText(hint)
            self.lbl_image_hint.setStyleSheet("color: green; font-size: 11px;")

            # 如果作品链接为空，自动填充
            if not self.txt_artwork_url.text().strip():
                self.txt_artwork_url.blockSignals(True)
                self.txt_artwork_url.setText(URLParser.build_artwork_url(artwork_id))
                self.txt_artwork_url.blockSignals(False)

                # 触发作品链接的验证更新
                self._on_artwork_url_changed(self.txt_artwork_url.text())

        elif text.strip():
            valid, msg = URLParser.validate_url(text)
            if not valid:
                self.lbl_image_hint.setText(f"❌ {msg}")
                self.lbl_image_hint.setStyleSheet("color: red; font-size: 11px;")
            else:
                self.lbl_image_hint.setText("⚠️ 无法识别为有效的 Pixiv 图片 URL")
                self.lbl_image_hint.setStyleSheet("color: orange; font-size: 11px;")
        else:
            self.lbl_image_hint.setText("")

    def _on_browse_directory(self):
        """浏览选择目录"""
        current_dir = self.txt_output_dir.text().strip()

        # 如果当前为空，使用上次使用的目录
        if not current_dir:
            current_dir = self.config.get('download', 'save_last_directory', '')

        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择保存目录",
            current_dir
        )

        if dir_path:
            self.txt_output_dir.setText(dir_path)
            # 保存为下次默认
            self.config.set('download', 'save_last_directory', dir_path)

    def _on_auto_fill(self):
        """自动填充（仅基于作品链接生成示例）"""
        artwork_url = self.txt_artwork_url.text().strip()

        if not artwork_url:
            QMessageBox.warning(self, "提示", "请先填写作品链接！")
            return

        result = URLParser.parse_artwork_url(artwork_url)
        if not result:
            QMessageBox.warning(self, "错误", "无法识别作品链接！")
            return

        artwork_id = result['artwork_id']

        # 显示帮助信息
        QMessageBox.information(
            self,
            "如何获取第一张图片地址",
            f"<h3>作品 ID: {artwork_id}</h3>"
            "<p>请按以下步骤获取第一张图片的下载地址：</p>"
            "<ol>"
            "<li>在浏览器中打开作品页面</li>"
            "<li>右键点击第一张图片</li>"
            "<li>选择「复制图片地址」或「复制图像地址」</li>"
            "<li>将地址粘贴到「第一张图片地址」框中</li>"
            "</ol>"
            "<p><b>注意：</b>必须提供正确的第一张图片地址才能下载。</p>"
        )

    def accept_if_valid(self):
        """验证并接受对话框"""
        # 验证必填字段
        artwork_url = self.txt_artwork_url.text().strip()
        first_image_url = self.txt_first_image_url.text().strip()
        output_dir = self.txt_output_dir.text().strip()

        # 验证作品链接
        if not artwork_url:
            QMessageBox.warning(self, "错误", "请填写作品链接！")
            self.txt_artwork_url.setFocus()
            return

        # 使用智能解析（与实时验证保持一致）
        artwork_result = URLParser.parse_artwork_url(artwork_url)

        # 如果标准解析失败，尝试智能备用方案
        if not artwork_result:
            import re
            clean_text = artwork_url.strip()
            clean_text = re.sub(r'[|,;\s\'"<>\[\]{}()]', '', clean_text)

            patterns = [
                r'/artworks/(\d+)',
                r'illust_id=(\d+)',
                r'pixiv.*/(\d{6,})',
                r'artworks[=/](\d+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, clean_text)
                if match:
                    artwork_result = {'artwork_id': match.group(1)}
                    break

        if not artwork_result:
            QMessageBox.warning(self, "错误", "无法识别的作品链接格式！\n\n请确保链接包含 pixiv.net/artworks/ 和作品 ID 数字。")
            self.txt_artwork_url.setFocus()
            return

        # 验证第一张图片地址（支持 img-master 和 img-original 两种格式）
        if not first_image_url:
            QMessageBox.warning(self, "错误", "请填写第一张图片地址！")
            self.txt_first_image_url.setFocus()
            return

        image_result = URLParser.smart_parse_image_url(first_image_url)
        if not image_result:
            QMessageBox.warning(
                self, "错误",
                "无法识别的第一张图片地址格式！\n\n"
                "支持格式：\n"
                "• img-master: ..._p0_master1200.jpg\n"
                "• img-original: ..._p0.jpg（自动转换）"
            )
            self.txt_first_image_url.setFocus()
            return

        # 验证输出目录
        if not output_dir:
            QMessageBox.warning(self, "错误", "请选择或输入保存目录！")
            self.txt_output_dir.setFocus()
            return

        # 自动创建不存在的目录
        import os as _os
        if not _os.path.exists(output_dir):
            try:
                _os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    self, "创建目录失败",
                    f"无法创建保存目录：\n\n{output_dir}\n\n错误信息：{str(e)}\n\n"
                    f"请检查路径是否包含非法字符或权限不足。"
                )
                return

        # 创建任务对象
        self.task = DownloadTask(
            artwork_url=artwork_url,
            first_image_url=first_image_url,
            output_dir=output_dir,
            artwork_id=image_result['artwork_id'],
            url_template=image_result['base_url'],
            settings=TaskSettings(
                max_retries=self.spin_retries.value(),
                timeout=self.spin_timeout.value(),
                interval=self.spin_interval.value(),
                max_pages=self.spin_max_pages.value(),
            )
        )

        # 接受对话框
        self.accept()

    def get_task(self) -> DownloadTask:
        """获取创建的任务对象"""
        return self.task
