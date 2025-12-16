import os
import re
import hashlib
import logging
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timezone
from email.utils import format_datetime

# ================= 配置区域 =================

# 1. Navidrome 数据源地址
# 既然浏览器能访问，这里填你浏览器里能打开的那个地址
# 务必保留 /rest/getAlbumList，但去掉参数
SOURCE_API_URL = "https://public.music.s3xyseia.xyz//rest/getAlbumList"

# 2. RSS 公网展示前缀
# 用于生成 XML 里的封面图和跳转链接，通常就是你的域名
PUBLIC_BASE_URL = "https://public.music.s3xyseia.xyz/"

# 3. 输出文件名
OUTPUT_FILE = "./feed.xml"

# 4. 伪装设置 (模拟 Chrome)
FAKE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_albums():
    params = {
        "type": "newest", "size": "20", "v": "1.16.1", "c": "rss_gen", "f": "json"
    }
    try:
        # 忽略 SSL 警告 (verify=False) 可选，视你反代证书情况而定
        resp = requests.get(SOURCE_API_URL, params=params, headers=FAKE_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get('subsonic-response', {}).get('albumList', {}).get('album', [])
    except Exception as e:
        logger.error(f"Fetch Error: {e}")
        return []

def build_rss_tree(albums):
    """构建 XML 对象"""
    rss = ET.Element("rss", version="2.0", xmlns__media="http://search.yahoo.com/mrss/")
    channel = ET.SubElement(rss, "channel")
    
    ET.SubElement(channel, "title").text = "Navidrome Library"
    ET.SubElement(channel, "description").text = "Newest Albums"
    ET.SubElement(channel, "link").text = PUBLIC_BASE_URL
    ET.SubElement(channel, "generator").text = "Python-Navidrome-RSS"

    # 占位 lastBuildDate，稍后处理
    
    for album in albums:
        item = ET.SubElement(channel, "item")
        
        # Data
        aid = album.get('id')
        title = f"{album.get('name')} - {album.get('artist')}"
        cover_url = f"{PUBLIC_BASE_URL}/rest/getCoverArt?id={aid}&v=1.16.1&c=rss"
        link_url = f"{PUBLIC_BASE_URL}/#/album/{aid}/show"
        
        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link_url
        
        # GUID
        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = f"urn:navidrome:album:{aid}"
        
        # Enclosure
        ET.SubElement(item, "enclosure", url=cover_url, type="image/jpeg", length="0")
        
        # Description (HTML)
        desc = (
            f'<p><img src="{cover_url}" style="width:200px; border-radius:5px;"></p>'
            f'<p><strong>{album.get("artist")}</strong></p>'
            f'<p>{album.get("year", "")} {album.get("genre", "")}</p>'
        )
        ET.SubElement(item, "description").text = desc

    return rss

def prettify_xml(elem):
    """
    核心格式化函数：
    使用 minidom 将 ElementTree 转换为 漂亮的字符串 (Pretty String)
    """
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    # indent="\t" 使用制表符缩进，或者用 "  " (两空格)
    return reparsed.toprettyxml(indent="  ")

def smart_update(rss_tree):
    """
    智能更新逻辑：
    1. 提取当前 Tree 的所有 GUID。
    2. 读取磁盘上旧文件，正则提取 GUID。
    3. 如果 GUID 序列完全一致，说明没新砖，不写盘。
    """
    # 提取新 GUID 列表
    new_guids = [e.text for e in rss_tree.findall(".//guid")]
    
    should_write = True
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                old_content = f.read()
            # 正则粗暴提取旧文件 GUID，忽略 XML 格式差异
            old_guids = re.findall(r'<guid.*?>(.*?)</guid>', old_content)
            
            if old_guids == new_guids:
                logger.info("Content match (GUIDs). No update needed.")
                should_write = False
        except Exception:
            pass # 读取出错就强制覆写

    if should_write:
        # 确定要写了，插入时间戳
        channel = rss_tree.find("channel")
        date_node = ET.Element("lastBuildDate")
        date_node.text = format_datetime(datetime.now(timezone.utc))
        # 插入到 link 之后 (只是为了好看，顺序不重要)
        channel.insert(3, date_node)

        # === 重点：格式化 ===
        pretty_content = prettify_xml(rss_tree)
        
        # 去除 minidom 有时会产生的多余空行 (可选优化)
        # pretty_content = "\n".join([line for line in pretty_content.split('\n') if line.strip()])

        # 原子写入
        temp_file = f"{OUTPUT_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(pretty_content)
        
        os.replace(temp_file, OUTPUT_FILE)
        logger.info(f"Updated {OUTPUT_FILE} with new content.")

if __name__ == "__main__":
    data = fetch_albums()
    if data:
        tree = build_rss_tree(data)
        smart_update(tree)
    else:
        logger.warning("Empty data or error.")