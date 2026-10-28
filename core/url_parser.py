"""
Pixiv URL 解析工具
负责解析 Pixiv 作品页面 URL 和图片下载 URL
"""

import re
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse


class URLParser:
    """
    Pixiv URL 解析器

    提供解析 Pixiv 各种 URL 格式的静态方法
    """

    # 正则表达式模式
    ARTWORK_URL_PATTERN = re.compile(
        r'pixiv\.net/(?:artworks/(\d+)|member_illust\.php\?illust_id=(\d+))'
    )

    # img-master 格式（下载用）
    IMAGE_URL_PATTERN = re.compile(
        r'https?://i\.pximg\.net/img-master/img/'
        r'(?P<date_path>\d{4}/\d{2}/\d{2}/\d{2}/\d{2}/\d{2})/'
        r'(?P<artwork_id>\d+)(?:-(?P<hash>[a-f0-9]+))?_p(?P<page>\d+)_master1200\.jpg'
    )

    # img-original 格式（浏览器复制）
    ORIGINAL_IMAGE_URL_PATTERN = re.compile(
        r'https?://i\.pximg\.net/img-original/img/'
        r'(?P<date_path>\d{4}/\d{2}/\d{2}/\d{2}/\d{2}/\d{2})/'
        r'(?P<artwork_id>\d+)(?:-(?P<hash>[a-f0-9]+))?_p(?P<page>\d+)\.(?:jpg|png)'
    )

    # 通用图片 URL 模式（匹配任何 pximg.net 图片 URL）
    GENERIC_IMAGE_URL_PATTERN = re.compile(
        r'https?://i\.pximg\.net/(?:img-master|img-original)/img/'
        r'(?P<date_path>\d{4}/\d{2}/\d{2}/\d{2}/\d{2}/\d{2})/'
        r'(?P<artwork_id>\d+)(?:-(?P<hash>[a-f0-9]+))?_p(?P<page>\d+)'
        r'(?:_master1200)?(?:\.(?:jpg|png))?'
    )

    # 需要清理的特殊字符（URL 末尾常见）
    TRIM_CHARS = ' \t\n\r|,;\'"<>{}[]()'

    @staticmethod
    def _clean_url(url: str) -> str:
        """
        清理 URL 字符串

        去除首尾空白、特殊字符和不可见的 Unicode 控制字符

        Args:
            url: 原始 URL

        Returns:
            清理后的 URL
        """
        if not url:
            return url

        # 去除首尾空白和特殊字符
        url = url.strip(URLParser.TRIM_CHARS)

        # 去除 Unicode 零宽字符和其他不可见控制字符
        # 包括：零宽空格、零宽连接符、左右标记、方向格式化字符等
        url = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff\u202a-\u202e\u2060-\u206f]', '', url)
        # 去除其他 C0/C1 控制字符（保留换行、回车、制表符）
        url = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', url)

        return url

    @staticmethod
    def _ensure_protocol(url: str) -> str:
        """
        确保 URL 有协议前缀

        如果缺少 http:// 或 https://，自动添加 https://

        Args:
            url: 可能缺少协议的 URL

        Returns:
            完整的 URL
        """
        if not url:
            return url

        # 如果已经包含协议，直接返回
        if url.startswith('http://') or url.startswith('https://'):
            return url

        # 如果以 i.pximg.net 或 pixiv.net 开头，添加 https://
        if url.startswith('i.pximg.net') or url.startswith('www.pixiv.net') or url.startswith('pixiv.net'):
            return f"https://{url}"

        # 其他情况也尝试添加 https://
        if '.' in url and '/' in url:
            return f"https://{url}"

        return url

    @staticmethod
    def parse_artwork_url(url: str) -> Optional[Dict[str, str]]:
        """
        解析作品页面 URL

        支持的格式：
        - https://www.pixiv.net/artworks/137875526
        - https://pixiv.net/artworks/137875526
        - https://www.pixiv.net/member_illust.php?illust_id=137875526

        Args:
            url: 作品页面 URL

        Returns:
            包含 artwork_id 的字典，解析失败返回 None

        示例:
            >>> URLParser.parse_artwork_url("https://www.pixiv.net/artworks/137875526")
            {'artwork_id': '137875526'}
        """
        if not url:
            return None

        # 清理 URL（去除首尾特殊字符）
        url = URLParser._clean_url(url)

        match = URLParser.ARTWORK_URL_PATTERN.search(url)
        if match:
            # 两个捕获组：group(1) 是 artworks/ID，group(2) 是 illust_id=ID
            artwork_id = match.group(1) or match.group(2)
            if artwork_id:
                return {'artwork_id': artwork_id}

        return None

    @staticmethod
    def parse_image_url(url: str) -> Optional[Dict[str, str]]:
        """
        解析第一张图片 URL，提取模板信息

        支持的格式（两种）：

        格式1 - 带 hash:
            https://i.pximg.net/img-master/img/2025/11/25/14/21/03/137875526-75700582aa954224351620346e0cea3d_p0_master1200.jpg

        格式2 - 不带 hash:
            https://i.pximg.net/img-master/img/2026/05/24/12/42/31/145150074_p0_master1200.jpg

        Args:
            url: 第一张图片的完整 URL（可以缺少协议前缀）

        Returns:
            包含以下键的字典：
            - base_url: URL 模板（用 {} 替换页码）
            - artwork_id: 作品 ID
            - hash: hash 值（可能为空）
            - date_path: 日期路径
            解析失败返回 None

        示例:
            >>> result = URLParser.parse_image_url("https://i.pximg.net/.../137875526-xxx_p0_master1200.jpg")
            >>> result['base_url']
            'https://i.pximg.net/img-master/img/2025/11/25/14/21/03/137875526-xxx_p{}_master1200.jpg'
        """
        if not url:
            return None

        # 清理 URL（去除首尾特殊字符）
        url = URLParser._clean_url(url)

        # 确保有协议前缀
        url = URLParser._ensure_protocol(url)

        match = URLParser.IMAGE_URL_PATTERN.search(url)
        if match:
            groups = match.groupdict()
            artwork_id = groups['artwork_id']
            hash_part = groups.get('hash', '') or ''
            date_path = groups['date_path']

            # 构建 URL 模板
            if hash_part:
                # 格式1：带 hash
                base_url = (
                    f"https://i.pximg.net/img-master/img/{date_path}/"
                    f"{artwork_id}-{hash_part}_p{{}}_master1200.jpg"
                )
            else:
                # 格式2：不带 hash
                base_url = (
                    f"https://i.pximg.net/img-master/img/{date_path}/"
                    f"{artwork_id}_p{{}}_master1200.jpg"
                )

            return {
                'base_url': base_url,
                'artwork_id': artwork_id,
                'hash': hash_part,
                'date_path': date_path,
            }

        return None

    @staticmethod
    def parse_original_image_url(url: str) -> Optional[Dict[str, str]]:
        """
        解析 img-original 格式的图片 URL（浏览器右键复制）

        支持格式：
            https://i.pximg.net/img-original/img/2025/11/22/03/01/47/137741748_p0.jpg

        Args:
            url: img-original 格式的图片 URL

        Returns:
            解析结果字典（同 parse_image_url 格式）
        """
        if not url:
            return None

        url = URLParser._clean_url(url)
        url = URLParser._ensure_protocol(url)

        match = URLParser.ORIGINAL_IMAGE_URL_PATTERN.search(url)
        if match:
            groups = match.groupdict()
            artwork_id = groups['artwork_id']
            hash_part = groups.get('hash', '') or ''
            date_path = groups['date_path']

            # 构建 img-master 格式的下载模板
            if hash_part:
                base_url = (
                    f"https://i.pximg.net/img-master/img/{date_path}/"
                    f"{artwork_id}-{hash_part}_p{{}}_master1200.jpg"
                )
            else:
                base_url = (
                    f"https://i.pximg.net/img-master/img/{date_path}/"
                    f"{artwork_id}_p{{}}_master1200.jpg"
                )

            # 同时返回原始 original URL 的 p0 版本
            original_p0_url = (
                f"https://i.pximg.net/img-original/img/{date_path}/"
                f"{f'{artwork_id}-{hash_part}' if hash_part else artwork_id}_p0.jpg"
            )

            return {
                'base_url': base_url,
                'artwork_id': artwork_id,
                'hash': hash_part,
                'date_path': date_path,
                'original_url': original_p0_url,  # 原始 original 格式
                'source_format': 'original',  # 标记来源格式
            }

        return None

    @staticmethod
    def smart_parse_image_url(url: str) -> Optional[Dict[str, str]]:
        """
        智能解析图片 URL - 自动识别 img-master 或 img-original 格式

        优先尝试：
        1. img-master 格式
        2. img-original 格式（自动转换为 master）

        Args:
            url: 任意格式的 Pixiv 图片 URL

        Returns:
            统一格式的解析结果（始终包含 master 模板）
        """
        # 先尝试 master 格式
        result = URLParser.parse_image_url(url)
        if result:
            result['source_format'] = 'master'
            return result

        # 再尝试 original 格式
        result = URLParser.parse_original_image_url(url)
        if result:
            return result

        return None

    @staticmethod
    def build_artwork_url(artwork_id: str) -> str:
        """
        根据作品 ID 构建作品页面 URL

        Args:
            artwork_id: 作品 ID

        Returns:
            完整的作品页面 URL
        """
        return f"https://www.pixiv.net/artworks/{artwork_id}"

    @staticmethod
    def build_first_image_master_url(artwork_id: str, date_path: Optional[str] = None, hash_str: Optional[str] = None) -> str:
        """
        构建第一张图片的 img-master 下载地址（用于显示在输入框）

        如果没有 date_path，使用占位符提示用户需要完整地址

        Args:
            artwork_id: 作品 ID
            date_path: 日期路径（可选）
            hash_str: hash 值（可选）

        Returns:
            第一张图片的 master1200 地址或占位符
        """
        if date_path:
            if hash_str:
                return f"https://i.pximg.net/img-master/img/{date_path}/{artwork_id}-{hash_str}_p0_master1200.jpg"
            else:
                return f"https://i.pximg.net/img-master/img/{date_path}/{artwork_id}_p0_master1200.jpg"
        else:
            # 无法确定日期路径，返回带占位符的示例
            return f"https://i.pximg.net/img-master/img/YYYY/MM/DD/HH/mm/ss/{artwork_id}_p0_master1200.jpg"

    @staticmethod
    def fetch_first_image_from_artwork(artwork_url: str, session=None) -> Optional[Dict[str, str]]:
        """
        从 Pixiv 作品页面自动获取第一张图片的下载地址

        通过访问 Pixiv AJAX API 获取作品详情，提取第一张图片的 original URL，
        然后转换为 img-master 格式用于下载。

        Args:
            artwork_url: 作品页面 URL（如 https://www.pixiv.net/artworks/123456）
            session: 已认证的 requests.Session（可选，用于带 Cookie 请求）

        Returns:
            解析结果字典（同 smart_parse_image_url 格式），失败返回 None
        """
        import requests as _requests

        if not artwork_url:
            return None

        # 清理 URL
        artwork_url = URLParser._clean_url(artwork_url)
        artwork_url = URLParser._ensure_protocol(artwork_url)

        # 提取 artwork_id
        result = URLParser.parse_artwork_url(artwork_url)
        if not result:
            print(f"[URLParser] 无法从 URL 提取 artwork_id: {artwork_url}")
            return None

        artwork_id = result['artwork_id']
        print(f"[URLParser] 开始获取作品 {artwork_id} 的图片地址...")

        try:
            # 使用提供的 session 或创建新的
            if session is not None:
                req_session = session
            else:
                req_session = _requests.Session()
                req_session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json',
                    'Referer': f'https://www.pixiv.net/artworks/{artwork_id}',
                    'Origin': 'https://www.pixiv.net',
                })
                req_session.verify = False

            # 使用 Pixiv AJAX API 获取作品详情（已验证可用）
            api_url = f'https://www.pixiv.net/ajax/illust/{artwork_id}'
            
            print(f"[URLParser] 请求 API: {api_url}")
            resp = req_session.get(api_url, timeout=15)
            print(f"[URLParser] API 响应状态码: {resp.status_code}")

            if resp.status_code != 200:
                print(f"[URLParser] API 请求失败，状态码: {resp.status_code}")
                return None

            data = resp.json()

            # 检查错误
            if data.get('error', False):
                print(f"[URLParser] API 返回错误: {data.get('message', '未知错误')}")
                return None

            # 提取 body.urls.original
            body = data.get('body', {})
            if not isinstance(body, dict):
                print(f"[URLParser] body 不是字典类型")
                return None

            urls = body.get('urls', {})
            if not isinstance(urls, dict):
                print(f"[URLParser] urls 不是字典类型")
                return None

            first_image_url = urls.get('original')
            
            if not first_image_url:
                # 尝试 regular 作为备选
                first_image_url = urls.get('regular') or urls.get('small')
                print(f"[URLParser] 未找到 original，尝试使用: {first_image_url}")

            if not first_image_url:
                print(f"[URLParser] 无法从 API 响应中提取图片 URL")
                print(f"[URLParser] 可用的 URLs keys: {list(urls.keys())}")
                return None

            print(f"[URLParser] 成功获取图片 URL (来源: ajax_api)")
            print(f"[URLParser] 原始 URL: {first_image_url[:80]}...")

            # 使用智能解析处理获取到的 URL（支持 original → master 转换）
            parse_result = URLParser.smart_parse_image_url(first_image_url)
            
            if parse_result:
                parse_result['fetched'] = True
                parse_result['fetch_method'] = 'ajax_api'
                
                # 额外：从 API 响应中获取作品标题（如果有）
                title = body.get('illustTitle', '') or body.get('title', '')
                if title:
                    parse_result['title'] = title
                
                print(f"[URLParser] 解析成功! base_url: {parse_result.get('base_url', '')[:60]}...")
                return parse_result
            
            print(f"[URLParser] smart_parse_image_url 失败")
            return None

        except Exception as e:
            print(f"[URLParser] 获取作品页面失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def build_url(template: str, page: int) -> str:
        """
        根据模板和页码构建完整的图片下载 URL

        Args:
            template: URL 模板（包含 {} 作为页码占位符）
            page: 页码（从 0 开始）

        Returns:
            完整的图片下载 URL

        示例:
            >>> URLParser.build_url(".../{}_p{}.jpg" % ("12345", "{}"), 0)
            'https://i.pximg.net/.../12345_p0.jpg'
        """
        return template.format(page)

    @staticmethod
    def validate_url(url: str) -> Tuple[bool, str]:
        """
        验证 URL 是否有效

        Args:
            url: 待验证的 URL

        Returns:
            (是否有效, 错误信息)

        示例:
            >>> URLParser.validate_url("https://www.pixiv.net/artworks/123")
            (True, "")
            >>> URLParser.validate_url("not a url")
            (False, "无效的 URL 格式")
        """
        if not url:
            return False, "URL 不能为空"

        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return False, "无效的 URL 格式"

            if result.scheme not in ['http', 'https']:
                return False, "URL 必须以 http 或 https 开头"

            return True, ""

        except Exception as e:
            return False, f"URL 解析错误: {str(e)}"

    @staticmethod
    def is_pixiv_artwork_url(url: str) -> bool:
        """
        检查是否是有效的 Pixiv 作品 URL

        Args:
            url: 待检查的 URL

        Returns:
            是否是有效的 Pixiv 作品 URL
        """
        return URLParser.parse_artwork_url(url) is not None

    @staticmethod
    def is_pixiv_image_url(url: str) -> bool:
        """
        检查是否是有效的 Pixiv 图片 URL

        Args:
            url: 待检查的 URL

        Returns:
            是否是有效的 Pixiv 图片 URL
        """
        return URLParser.parse_image_url(url) is not None

    @staticmethod
    def extract_artwork_id_from_image_url(url: str) -> Optional[str]:
        """
        从图片 URL 中提取作品 ID

        Args:
            url: 图片 URL

        Returns:
            作品 ID，提取失败返回 None
        """
        result = URLParser.parse_image_url(url)
        if result:
            return result['artwork_id']
        return None


# 便捷函数
def parse_artwork_url(url: str) -> Optional[Dict[str, str]]:
    """解析作品页面 URL 的便捷函数"""
    return URLParser.parse_artwork_url(url)


def parse_image_url(url: str) -> Optional[Dict[str, str]]:
    """解析图片 URL 的便捷函数"""
    return URLParser.parse_image_url(url)


def build_download_url(template: str, page: int) -> str:
    """构建下载 URL 的便捷函数"""
    return URLParser.build_url(template, page)
