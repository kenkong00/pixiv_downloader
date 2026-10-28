"""
测试从 Pixiv 作品页面自动获取第一张图片地址
"""
import sys
import os

# 清除模块缓存
for mod in list(sys.modules.keys()):
    if 'url_parser' in mod or 'pixiv_downloader' in mod:
        del sys.modules[mod]

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from core.auth import PixivAuth
import importlib

# 强制重新加载 url_parser
import core.url_parser as url_parser_module
importlib.reload(url_parser_module)
from core.url_parser import URLParser
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings()

def test_fetch():
    # 初始化认证（加载已保存的 Cookie）
    auth = PixivAuth()
    print(f"登录状态: {auth.is_logged_in}")

    if not auth.is_logged_in:
        print("错误: 未登录！请先导入 Cookie")
        return

    # 测试 URL
    test_url = "https://www.pixiv.net/artworks/131770672"
    print(f"\n正在测试: {test_url}")
    print("-" * 50)

    # 获取 session
    session = auth.get_session()
    print(f"Session cookies 数量: {len(session.cookies)}")

    # 测试 AJAX API
    print("\n--- 测试 AJAX API ---")
    import requests as _requests
    artwork_id = "131770672"

    api_url = f'https://www.pixiv.net/ajax/illust/{artwork_id}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': f'https://www.pixiv.net/artworks/{artwork_id}',
        'Origin': 'https://www.pixiv.net',
    }

    resp = session.get(api_url, headers=headers, timeout=15)
    print(f"API 状态码: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"API 响应 keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

        # 保存完整响应用于分析
        debug_dir = os.path.join(os.path.dirname(__file__), 'debug')
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, 'api_response.json'), 'w', encoding='utf-8') as f:
            import json
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n已保存 API 响应到: debug/api_response.json")

        # 尝试提取图片 URL
        body = data.get('body', data) if isinstance(data, dict) else {}
        urls = body.get('urls', {}) if isinstance(body, dict) else {}

        print(f"urls 字段: {urls}")
        print(f"original: {urls.get('original', '无')}")

        # 实际调用 fetch 函数
        print("\n--- 调用 fetch_first_image_from_artwork ---")
        try:
            # 先测试 parse_artwork_url
            print("测试 parse_artwork_url:")
            test_urls = [
                "https://www.pixiv.net/artworks/131770672",
                "pixiv.net/artworks/131770672",
                "https://www.pixiv.net/artworks/131770672#1",
            ]
            for url in test_urls:
                result = URLParser.parse_artwork_url(url)
                print(f"  {url[:50]}... -> {result}")

            # 直接测试正则表达式
            import re
            pattern = re.compile(r'pixiv\.net/(?:artworks|member_illust\.php\?illust_id)=(\d+)')
            test_str = "https://www.pixiv.net/artworks/131770672"
            match = pattern.search(test_str)
            print(f"\n直接测试正则: {match}")
            
            # 测试清理后的 URL
            cleaned = URLParser._clean_url(test_str)
            print(f"清理后 URL: {cleaned}")
            match2 = pattern.search(cleaned)
            print(f"清理后匹配: {match2}")

            # 直接测试核心逻辑
            import re
            artwork_id = "131770672"
            api_url = f'https://www.pixiv.net/ajax/illust/{artwork_id}'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': f'https://www.pixiv.net/artworks/{artwork_id}',
                'Origin': 'https://www.pixiv.net',
            }

            print(f"请求 API: {api_url}")
            resp = session.get(api_url, headers=headers, timeout=15)
            print(f"状态码: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                body = data.get('body', {})
                urls = body.get('urls', {})

                first_image_url = urls.get('original')
                print(f"提取到 original URL: {first_image_url}")

                if first_image_url:
                    # 测试 smart_parse
                    result = URLParser.smart_parse_image_url(first_image_url)
                    print(f"smart_parse 结果: {result}")
                else:
                    print("无法提取 original URL")

            result = URLParser.fetch_first_image_from_artwork(test_url, session)
            if result:
                print(f"\n[成功!] artwork_id: {result.get('artwork_id')}")
                print(f"base_url: {result.get('base_url', '')[:100]}...")
            else:
                print("[失败!] 无法自动获取")
        except Exception as e:
            print(f"[异常!] {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_fetch()
    input("\n按回车键退出...")
