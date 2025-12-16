import os
import re
import time
import logging
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timezone
from email.utils import format_datetime

# --- 极简配置 ---
# 你的公网地址 (既用于抓数据，也用于生成链接)
BASE_URL = os.getenv("BASE_URL", "http://public.music.s3xyseia.xyz/").rstrip('/')
# 容器内输出路径
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "/output/feed.xml")
# 检查间隔 (默认30分钟)
INTERVAL = int(os.getenv("INTERVAL", "1800"))

# 伪装成浏览器 (配合你的 Nginx 反代策略)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("RSS")

def fetch_and_generate():
    # 1. Fetch: 直接访问公网地址
    api_url = f"{BASE_URL}/rest/getAlbumList"
    params = {"type": "newest", "size": "20", "v": "1.16.1", "c": "rss_bot", "f": "json"}
    
    try:
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        albums = resp.json().get('subsonic-response', {}).get('albumList', {}).get('album', [])
    except Exception as e:
        logger.error(f"Fetch Error: {e}")
        return

    if not albums: return

    # 2. Build XML
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Navidrome Updates"
    ET.SubElement(channel, "link").text = BASE_URL
    ET.SubElement(channel, "description").text = "New Albums"

    for album in albums:
        item = ET.SubElement(channel, "item")
        aid = album.get('id')
        
        # 链接生成
        link = f"{BASE_URL}/#/album/{aid}/show"
        cover = f"{BASE_URL}/rest/getCoverArt?id={aid}&v=1.16.1&c=rss"
        
        ET.SubElement(item, "title").text = f"{album.get('name')} - {album.get('artist')}"
        ET.SubElement(item, "link").text = link
        
        # GUID: 唯一标识
        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = f"urn:navidrome:album:{aid}"
        
        ET.SubElement(item, "enclosure", url=cover, type="image/jpeg", length="0")
        
        desc = (f'<p><img src="{cover}" style="width:200px; border-radius:4px;"></p>'
                f'<p><strong>{album.get("artist")}</strong></p>')
        ET.SubElement(item, "description").text = desc

    # 3. Smart Write (GUID Check + Pretty Print)
    # 确保输出目录存在
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # 生成 XML 对象
    new_guids = [e.text for e in rss.findall(".//guid")]
    should_write = True
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                # 粗暴正则比对 GUID，忽略格式差异
                if re.findall(r'<guid.*?>(.*?)</guid>', f.read()) == new_guids:
                    logger.info("No changes detected.")
                    should_write = False
        except: pass

    if should_write:
        # 插入时间戳
        ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
        
        # 格式化 (Pretty Print)
        raw = ET.tostring(rss, 'utf-8')
        pretty = minidom.parseString(raw).toprettyxml(indent="  ")
        # 清理空行
        pretty = "\n".join([L for L in pretty.split('\n') if L.strip()])
        
        # 原子写入
        tmp = f"{OUTPUT_FILE}.tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(pretty)
        os.replace(tmp, OUTPUT_FILE)
        logger.info(f"Updated: {OUTPUT_FILE}")

if __name__ == "__main__":
    logger.info(f"Starting RSS Service. Target: {BASE_URL}")
    while True:
        fetch_and_generate()
        time.sleep(INTERVAL)