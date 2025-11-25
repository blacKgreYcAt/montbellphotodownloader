import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import re
import zipfile
import time
import random
from urllib.parse import urljoin, urlparse
import io

# --- 頁面設定與 iOS 風格 CSS ---
st.set_page_config(page_title="Montbell 下載器", page_icon="🏔️", layout="centered")

# iOS 深色風格 + 大按鈕 CSS
st.markdown("""
<style>
    /* 強制深色背景與字體 */
    .stApp {
        background-color: #000000;
        color: #FFFFFF;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* 輸入框圓角化 */
    .stTextInput > div > div > input {
        border-radius: 12px;
        background-color: #1C1C1E;
        color: white;
        border: 1px solid #333;
    }
    
    /* 數字輸入框 */
    .stNumberInput > div > div > input {
        border-radius: 12px;
        background-color: #1C1C1E;
        color: white;
    }

    /* 主要按鈕 (iOS Blue) - 大 Icon 風格 */
    .stButton > button {
        width: 100%;
        height: 60px;
        border-radius: 14px;
        background-color: #0A84FF;
        color: white;
        font-weight: bold;
        font-size: 18px;
        border: none;
        transition: transform 0.1s;
    }
    .stButton > button:hover {
        background-color: #0070E0;
        transform: scale(0.98);
    }
    .stButton > button:active {
        background-color: #005BB5;
    }

    /* 下載按鈕 (iOS Green) */
    .stDownloadButton > button {
        width: 100%;
        height: 60px;
        border-radius: 14px;
        background-color: #30D158;
        color: black;
        font-weight: bold;
        font-size: 18px;
        border: none;
    }
    .stDownloadButton > button:hover {
        background-color: #28C14D;
    }

    /* 進度條顏色 */
    .stProgress > div > div > div > div {
        background-color: #0A84FF;
    }
    
    /* 卡片式容器 */
    .css-1r6slb0 {
        background-color: #1C1C1E;
        border-radius: 16px;
        padding: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 核心邏輯類別 (改寫為無狀態函數) ---

def get_headers(referer=None):
    return {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Referer': referer if referer else 'https://webshop.montbell.jp/',
        'Connection': 'keep-alive',
    }

def extract_images_from_html(soup, base_url):
    """從HTML頁面提取圖片URL"""
    image_urls = []
    
    # 1. fancy_largelink
    for link in soup.select('a.fancy_largelink'):
        hd_img_url = link.get('href')
        if hd_img_url:
            image_urls.append(urljoin(base_url, hd_img_url))
        
        img_tag = link.select_one('img')
        if img_tag and img_tag.get('src'):
            image_urls.append(urljoin(base_url, img_tag.get('src')))
            
    # 2. 隱藏區域
    for img in soup.select('#img_hidden_pre img, #img_hidden_later img'):
        if img.get('src'):
            image_urls.append(urljoin(base_url, img.get('src')))

    # 3. 主圖
    main_img = soup.select_one('#largelinkImg')
    if main_img and main_img.get('src'):
        image_urls.append(urljoin(base_url, main_img.get('src')))

    # 4. 縮略圖與其高解析版本
    for img in soup.select('.cutImglArea img'):
        img_url = img.get('src')
        if img_url:
            full_url = urljoin(base_url, img_url)
            image_urls.append(full_url)
            # 嘗試猜測高解析度路徑
            if '/cut_c/' in full_url:
                image_urls.append(full_url.replace('/cut_c/', '/cut_k/').replace('cc_', 'ck_'))
            elif '/prod_c/' in full_url:
                image_urls.append(full_url.replace('/prod_c/', '/prod_k/').replace('c_', 'k_'))

    # 去重並過濾
    return list(set(url for url in image_urls if url.startswith(('http', '//'))))

def extract_images_from_js(soup, base_url):
    """從JavaScript提取圖片URL"""
    image_urls = []
    scripts = soup.find_all('script')
    
    image_data = {}
    image_paths = {}
    
    for script in scripts:
        script_text = script.string
        if script_text and ('cimages' in script_text or 'kimages' in script_text):
            for line in script_text.split('\n'):
                # 提取檔名
                c_match = re.search(r"cimages\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if c_match:
                    k, v = c_match.groups()
                    image_data.setdefault(k, {})['cimage'] = v
                
                k_match = re.search(r"kimages\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if k_match:
                    k, v = k_match.groups()
                    image_data.setdefault(k, {})['kimage'] = v
                
                # 提取路徑
                cp_match = re.search(r"cimage_paths\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if cp_match:
                    k, v = cp_match.groups()
                    image_paths[f'cimage_paths_{k}'] = v
                
                kp_match = re.search(r"kimage_paths\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if kp_match:
                    k, v = kp_match.groups()
                    image_paths[f'kimage_paths_{k}'] = v

    for key, data in image_data.items():
        if 'cimage' in data:
            path = image_paths.get(f'cimage_paths_{key}', '/common/images/product/prod_c')
            image_urls.append(urljoin(base_url, f"{path}/{data['cimage']}"))
        if 'kimage' in data:
            path = image_paths.get(f'kimage_paths_{key}', '/common/images/product/prod_k')
            image_urls.append(urljoin(base_url, f"{path}/{data['kimage']}"))
            
    return list(set(image_urls))

# --- UI 介面 ---

st.title("🏔️ Montbell 圖片下載器")
st.caption("Excel 批量下載工具 | iOS Dark Mode Edition")

# 1. 側邊欄設定
with st.expander("⚙️ 設定 (Settings)", expanded=False):
    domain = st.text_input("網站域名", value="https://webshop.montbell.jp")
    delay = st.number_input("請求延遲 (秒)", min_value=1, max_value=10, value=2)

# 2. 檔案上傳
uploaded_file = st.file_uploader("📂 請上傳 Excel 檔案", type=['xlsx', 'xls'])

# 狀態變數
if 'download_done' not in st.session_state:
    st.session_state.download_done = False
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'log_messages' not in st.session_state:
    st.session_state.log_messages = []

# 3. 執行邏輯
if uploaded_file is not None:
    st.info(f"已讀取: {uploaded_file.name}")
    
    # 讀取 Excel 預覽
    try:
        df = pd.read_excel(uploaded_file)
        st.dataframe(df.head(), height=150)
    except Exception as e:
        st.error(f"讀取 Excel 失敗: {e}")
        st.stop()

    # 開始下載按鈕
    if st.button("🚀 開始執行下載", key="start_btn"):
        st.session_state.log_messages = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_area = st.empty()
        
        # 準備記憶體 ZIP
        zip_buffer = io.BytesIO()
        
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # 欄位識別
                model_col = next((c for c in df.columns if any(x in str(c).lower() for x in ['型號', 'model', 'id'])), df.columns[0])
                url_col = next((c for c in df.columns if any(x in str(c).lower() for x in ['網址', 'url', 'link'])), None)
                
                total = len(df)
                downloaded_count = 0
                
                for idx, row in df.iterrows():
                    model_id = str(row[model_col]).strip()
                    if not model_id or model_id.lower() == 'nan': continue
                    
                    status_text.text(f"正在處理: {model_id} ({idx+1}/{total})")
                    progress_bar.progress((idx + 1) / total)
                    
                    # 決定 URL
                    target_urls = []
                    if url_col and pd.notna(row[url_col]):
                        u = str(row[url_col]).strip()
                        if u.startswith('http'): target_urls.append(u)
                        
                    # 搜尋模式
                    if not target_urls:
                        search_url = f"{domain}/goods/list_search.php"
                        params = {'top_sk': model_id}
                        try:
                            time.sleep(delay)
                            resp = requests.get(search_url, params=params, headers=get_headers())
                            soup = BeautifulSoup(resp.content, 'html.parser')
                            for link in soup.find_all('a', href=True):
                                if 'goods/detail.php' in link['href']:
                                    target_urls.append(urljoin(search_url, link['href']))
                            
                            # 若直接跳轉
                            if not target_urls and 'goods/detail.php' in resp.url:
                                target_urls.append(resp.url)
                        except Exception as e:
                            st.session_state.log_messages.append(f"❌ {model_id} 搜尋錯誤: {e}")

                    # 處理每個商品頁
                    img_urls = []
                    for p_url in target_urls[:1]: # 限制取第一個匹配商品
                        try:
                            time.sleep(delay)
                            resp = requests.get(p_url, headers=get_headers())
                            s = BeautifulSoup(resp.content, 'html.parser')
                            img_urls.extend(extract_images_from_html(s, p_url))
                            img_urls.extend(extract_images_from_js(s, p_url))
                        except Exception as e:
                            pass
                    
                    img_urls = list(set(img_urls))
                    
                    if not img_urls:
                        st.session_state.log_messages.append(f"⚠️ {model_id}: 未找到圖片")
                        continue

                    # 下載圖片並寫入 ZIP
                    model_img_count = 0
                    for i, img_url in enumerate(img_urls):
                        try:
                            time.sleep(0.5)
                            img_resp = requests.get(img_url, headers=get_headers(p_url), timeout=10)
                            if img_resp.status_code == 200 and 'image' in img_resp.headers.get('Content-Type', ''):
                                # 檔名處理
                                parsed = urlparse(img_url)
                                fname = os.path.basename(parsed.path)
                                if not fname: fname = f"{model_id}_{i}.jpg"
                                
                                # 寫入 ZIP (路徑: 型號/檔名)
                                zip_file.writestr(f"{model_id}/{fname}", img_resp.content)
                                model_img_count += 1
                        except:
                            pass
                    
                    if model_img_count > 0:
                        downloaded_count += model_img_count
                        st.session_state.log_messages.append(f"✅ {model_id}: 下載 {model_img_count} 張")
                    
                    # 顯示最新幾筆日誌
                    log_area.code("\n".join(st.session_state.log_messages[-5:]))

            # 完成處理
            st.session_state.zip_buffer = zip_buffer
            st.session_state.download_done = True
            st.success(f"🎉 處理完成！共下載 {downloaded_count} 張圖片")
            
        except Exception as e:
            st.error(f"發生嚴重錯誤: {e}")

# 4. 下載按鈕 (處理完成後出現)
if st.session_state.download_done and st.session_state.zip_buffer:
    st.markdown("---")
    st.write("### ✅ 檔案已準備好")
    
    # 重置指針到開頭
    st.session_state.zip_buffer.seek(0)
    
    st.download_button(
        label="📥 下載圖片壓縮檔 (ZIP)",
        data=st.session_state.zip_buffer,
        file_name="montbell_images.zip",
        mime="application/zip"
    )

    if st.button("清除重來"):
        st.session_state.download_done = False
        st.session_state.zip_buffer = None
        st.experimental_rerun()