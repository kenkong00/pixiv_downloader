"""
快速测试 URL 解析功能
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from core.url_parser import URLParser

# 测试1: img-original 格式
print("=" * 60)
print("测试1: img-original 格式")
print("=" * 60)

url1 = "https://i.pximg.net/img-original/img/2025/07/26/21/25/03/133144034_p0.jpg"
print(f"输入: {url1}")

result = URLParser.parse_original_image_url(url1)
print(f"parse_original_image_url: {result}")

result2 = URLParser.smart_parse_image_url(url1)
print(f"smart_parse_image_url: {result2}")

# 测试2: 作品链接
print("\n" + "=" * 60)
print("测试2: 作品链接")
print("=" * 60)

url2 = "https://www.pixiv.net/artworks/133144034"
print(f"输入: {url2}")

result3 = URLParser.parse_artwork_url(url2)
print(f"parse_artwork_url: {result3}")

# 测试3: 直接正则匹配
import re
pattern = re.compile(r'pixiv\.net/(?:artworks/(\d+)|member_illust\.php\?illust_id=(\d+))')
match = pattern.search(url2)
print(f"直接正则匹配: {match}")
if match:
    print(f"group(1): {match.group(1)}, group(2): {match.group(2)}")

# 测试4: original 正则
orig_pattern = re.compile(
    r'https?://i\.pximg\.net/img-original/img/'
    r'(?P<date_path>\d{4}/\d{2}/\d{2}/\d{2}/\d{2}/\d{2})/'
    r'(?P<artwork_id>\d+)(?:-(?P<hash>[a-f0-9]+))?_p(?P<page>\d+)\.jpg'
)
match2 = orig_pattern.search(url1)
print(f"\noriginal正则匹配: {match2}")
if match2:
    print(f"groups: {match2.groups()}")
    print(f"date_path: {match2.group('date_path')}")
    print(f"artwork_id: {match2.group('artwork_id')}")
