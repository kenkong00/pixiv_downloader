"""
登录对话框
提供 Pixiv 和 Civitai 账号认证功能（主要通过 Cookie 导入）
"""

import os
import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QWidget, QTextEdit, QGroupBox,
    QMessageBox, QCheckBox, QFormLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# 导入项目模块
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.auth import PixivAuth
from core.civitai_auth import CivitaiAuth


class LoginDialog(QDialog):
    """
    登录对话框

    提供两种站点的登录：
    1. Pixiv - Cookie 导入
    2. Civitai - Cookie 导入
    """

    def __init__(self, pixiv_auth: PixivAuth, civitai_auth: CivitaiAuth = None, parent=None):
        super().__init__(parent)

        self.pixiv_auth = pixiv_auth
        self.civitai_auth = civitai_auth
        self.setWindowTitle("账号登录")
        self.setMinimumWidth(550)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)

        # ===== 标题区域 =====
        title_label = QLabel("账号登录设置")
        title_label.setFont(QFont("", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 说明文字
        info_label = QLabel(
            "💡 提示: 需要科学上网才能正常访问\n"
            "推荐使用 Cookie 导入方式，简单且稳定"
        )
        info_label.setStyleSheet("color: #666; padding: 10px;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        # ===== 站点选择 Tab =====
        self.site_tabs = QTabWidget()
        layout.addWidget(self.site_tabs)

        # Pixiv Tab
        self.pixiv_tab = QWidget()
        self._create_pixiv_tab()
        self.site_tabs.addTab(self.pixiv_tab, "Pixiv")

        # Civitai Tab
        if self.civitai_auth:
            self.civitai_tab = QWidget()
            self._create_civitai_tab()
            self.site_tabs.addTab(self.civitai_tab, "Civitai")

        # ===== 当前状态显示 =====
        status_group = QGroupBox("当前状态")
        status_layout = QVBoxLayout(status_group)

        # Pixiv 状态
        self.lbl_pixiv_status = QLabel("Pixiv: 未登录")
        if self.pixiv_auth.is_logged_in:
            self.lbl_pixiv_status.setText("Pixiv: ✅ 已登录")
            self.lbl_pixiv_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_pixiv_status.setText("Pixiv: ❌ 未登录")
            self.lbl_pixiv_status.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.lbl_pixiv_status)

        # Civitai 状态
        if self.civitai_auth:
            self.lbl_civitai_status = QLabel("Civitai: 未登录")
            if self.civitai_auth.is_logged_in:
                self.lbl_civitai_status.setText("Civitai: ✅ 已登录")
                self.lbl_civitai_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.lbl_civitai_status.setText("Civitai: ❌ 未登录")
                self.lbl_civitai_status.setStyleSheet("color: red; font-weight: bold;")
            status_layout.addWidget(self.lbl_civitai_status)

        layout.addWidget(status_group)

        # ===== 按钮区域 =====
        btn_layout = QHBoxLayout()

        self.btn_verify = QPushButton("验证登录状态")
        self.btn_verify.clicked.connect(self.on_verify)
        btn_layout.addWidget(self.btn_verify)

        btn_layout.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _create_pixiv_tab(self):
        """创建 Pixiv 登录标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 说明
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(150)
        help_text.setHtml("""
<h4>如何获取 Pixiv Cookie：</h4>
<ol>
<li>在浏览器中访问 <b>pixiv.net</b> 并登录</li>
<li>按 <b>F12</b> 打开开发者工具</li>
<li>切换到 <b>Network</b>（网络）标签</li>
<li>刷新页面（F5）</li>
<li>点击任意一个请求</li>
<li>在 <b>Headers</b> 中找到 <b>Cookie:</b> 行</li>
<li>复制冒号后面的完整内容</li>
</ol>
        """)
        help_text.setStyleSheet("font-size: 12px;")
        layout.addWidget(help_text)

        # 输入框
        form = QFormLayout()
        self.txt_pixiv_cookie = QLineEdit()
        self.txt_pixiv_cookie.setPlaceholderText("粘贴从浏览器复制的完整 Cookie 字符串...")
        self.txt_pixiv_cookie.setMinimumHeight(80)
        form.addRow("Cookie 字符串:", self.txt_pixiv_cookie)
        layout.addLayout(form)

        # 导入按钮
        btn_import = QPushButton("📥 导入 Cookie 并登录")
        btn_import.setMinimumHeight(40)
        btn_import.setStyleSheet("font-weight: bold; font-size: 13px;")
        btn_import.clicked.connect(self.on_import_pixiv_cookie)
        layout.addWidget(btn_import)

        # 快捷操作
        quick_layout = QHBoxLayout()
        btn_from_clipboard = QPushButton("📋 从剪贴板粘贴")
        btn_from_clipboard.clicked.connect(lambda: self._paste_to(self.txt_pixiv_cookie))
        quick_layout.addWidget(btn_from_clipboard)
        btn_clear = QPushButton("🗑 清空")
        btn_clear.clicked.connect(lambda: self.txt_pixiv_cookie.clear())
        quick_layout.addWidget(btn_clear)
        layout.addLayout(quick_layout)

        # 登出按钮
        btn_logout = QPushButton("登出 Pixiv")
        btn_logout.clicked.connect(self.on_logout_pixiv)
        layout.addWidget(btn_logout)

        layout.addStretch()
        self.pixiv_tab.setLayout(widget.layout())

    def _create_civitai_tab(self):
        """创建 Civitai 登录标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 说明
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(150)
        help_text.setHtml("""
<h4>如何获取 Civitai Cookie：</h4>
<ol>
<li>在浏览器中访问 <b>civitai.com</b>（或 civitai.red）并登录</li>
<li>按 <b>F12</b> 打开开发者工具</li>
<li>切换到 <b>Network</b>（网络）标签</li>
<li>刷新页面（F5）</li>
<li>点击任意一个请求</li>
<li>在 <b>Headers</b> 中找到 <b>Cookie:</b> 行</li>
<li>复制冒号后面的完整内容</li>
</ol>
        """)
        help_text.setStyleSheet("font-size: 12px;")
        layout.addWidget(help_text)

        # 输入框
        form = QFormLayout()
        self.txt_civitai_cookie = QLineEdit()
        self.txt_civitai_cookie.setPlaceholderText("粘贴从浏览器复制的完整 Cookie 字符串...")
        self.txt_civitai_cookie.setMinimumHeight(80)
        form.addRow("Cookie 字符串:", self.txt_civitai_cookie)
        layout.addLayout(form)

        # 导入按钮
        btn_import = QPushButton("📥 导入 Cookie 并登录")
        btn_import.setMinimumHeight(40)
        btn_import.setStyleSheet("font-weight: bold; font-size: 13px;")
        btn_import.clicked.connect(self.on_import_civitai_cookie)
        layout.addWidget(btn_import)

        # 快捷操作
        quick_layout = QHBoxLayout()
        btn_from_clipboard = QPushButton("📋 从剪贴板粘贴")
        btn_from_clipboard.clicked.connect(lambda: self._paste_to(self.txt_civitai_cookie))
        quick_layout.addWidget(btn_from_clipboard)
        btn_clear = QPushButton("🗑 清空")
        btn_clear.clicked.connect(lambda: self.txt_civitai_cookie.clear())
        quick_layout.addWidget(btn_clear)
        layout.addLayout(quick_layout)

        # 登出按钮
        btn_logout = QPushButton("登出 Civitai")
        btn_logout.clicked.connect(self.on_logout_civitai)
        layout.addWidget(btn_logout)

        layout.addStretch()
        self.civitai_tab.setLayout(widget.layout())

    def _paste_to(self, line_edit: QLineEdit):
        """从剪贴板粘贴到指定输入框"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            line_edit.setText(text)
        else:
            QMessageBox.information(self, "提示", "剪贴板为空")

    def on_import_pixiv_cookie(self):
        """导入 Pixiv Cookie 字符串"""
        cookie_string = self.txt_pixiv_cookie.text().strip()

        if not cookie_string:
            QMessageBox.warning(self, "错误", "请输入 Cookie 字符串！")
            return

        success = self.pixiv_auth.login_by_cookie_string(cookie_string)

        if success:
            QMessageBox.information(self, "成功", "✅ Pixiv Cookie 导入成功！")
            self._update_status_display()
        else:
            QMessageBox.critical(self, "失败", "❌ Pixiv Cookie 导入失败！\n请检查 Cookie 是否有效。")

    def on_import_civitai_cookie(self):
        """导入 Civitai Cookie 字符串"""
        cookie_string = self.txt_civitai_cookie.text().strip()

        if not cookie_string:
            QMessageBox.warning(self, "错误", "请输入 Cookie 字符串！")
            return

        success = self.civitai_auth.login_by_cookie_string(cookie_string)

        if success:
            QMessageBox.information(self, "成功", "✅ Civitai Cookie 导入成功！")
            self._update_status_display()
        else:
            QMessageBox.critical(self, "失败", "❌ Civitai Cookie 导入失败！\n请检查 Cookie 是否有效。")

    def on_verify(self):
        """验证当前选中站点的登录状态"""
        current_tab = self.site_tabs.currentIndex()
        if current_tab == 0:
            # Pixiv
            is_valid = self.pixiv_auth.check_login_status()
            if is_valid:
                QMessageBox.information(self, "验证结果", "✅ Pixiv 登录状态有效！")
            else:
                QMessageBox.warning(self, "验证结果", "❌ Pixiv 登录状态无效或已过期！")
        elif current_tab == 1 and self.civitai_auth:
            # Civitai
            is_valid = self.civitai_auth.check_login_status()
            if is_valid:
                QMessageBox.information(self, "验证结果", "✅ Civitai 登录状态有效！")
            else:
                QMessageBox.warning(self, "验证结果", "❌ Civitai 登录状态无效或已过期！")

        self._update_status_display()

    def on_logout_pixiv(self):
        """登出 Pixiv"""
        reply = QMessageBox.question(
            self, "确认登出",
            "确定要登出 Pixiv 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.pixiv_auth.logout()
            self._update_status_display()
            QMessageBox.information(self, "已登出", "Pixiv 已成功登出。")

    def on_logout_civitai(self):
        """登出 Civitai"""
        reply = QMessageBox.question(
            self, "确认登出",
            "确定要登出 Civitai 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.civitai_auth.logout()
            self._update_status_display()
            QMessageBox.information(self, "已登出", "Civitai 已成功登出。")

    def _update_status_display(self):
        """更新状态显示"""
        if self.pixiv_auth.is_logged_in:
            self.lbl_pixiv_status.setText("Pixiv: ✅ 已登录")
            self.lbl_pixiv_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.lbl_pixiv_status.setText("Pixiv: ❌ 未登录")
            self.lbl_pixiv_status.setStyleSheet("color: red; font-weight: bold;")

        if self.civitai_auth:
            if self.civitai_auth.is_logged_in:
                self.lbl_civitai_status.setText("Civitai: ✅ 已登录")
                self.lbl_civitai_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.lbl_civitai_status.setText("Civitai: ❌ 未登录")
                self.lbl_civitai_status.setStyleSheet("color: red; font-weight: bold;")
