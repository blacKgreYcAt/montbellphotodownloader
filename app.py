import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import re
import zipfile
import time
import math
import random
from urllib.parse import urljoin, urlparse
import io

# --- 頁面設定 ---
st.set_page_config(page_title="Montbell 下載器 (原版核心)", page_icon="🏔️", layout="centered")

# --- iOS 風格 CSS (僅視覺，不影響邏輯) ---
st.markdown("""
<style>
    .stApp { background-color: #000000; color: #FFFFFF; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif; }
    .stTextInput > div > div > input, .stNumberInput > div > div > input, .stSelectbox > div > div > div { border-radius: 12px; background-color: #1C1C1E; color: white; border: 1px solid #333; }
    div.stButton > button { width: 100%; aspect-ratio: 1 / 1; border-radius: 22px; background: linear-gradient(145deg, #0A84FF, #0070E0); color: white; font-weight: 600; font-size: 20px; border: none; box-shadow: 0 4px 15px rgba(0,0,0,0.3); margin-bottom: 10px; display: flex; flex-direction: column; justify-content: center; align-items: center; }
    div.stButton > button:hover { transform: scale(0.97); background: linear-gradient(145deg, #0070E0, #005BB5); }
    div.stDownloadButton > button { width: 100%; height: 60px; border-radius: 14px; background-color: #30D158; color: black; font-weight: bold; font-size: 18px; border: none; }
    div.stDownloadButton > button:hover { background-color: #28C14D; }
    .stProgress > div > div > div > div { background-color: #0A84FF; }
    .stExpander { background-color: #1C1C1E; border-radius: 16px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 核心邏輯區 - 嚴格複製自原始 Python 腳本
# ==============================================================================

def get_original_headers(referer=None):
    """完全還原原始腳本的 Headers (使用電腦版 User-Agent)"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Referer': referer if referer else 'https://webshop.montbell.jp/',
        'Connection': 'keep-alive',
    }

def original_extract_images_from_html(soup, base_url):
    """
    [原始邏輯] 從HTML頁面提取圖片URL
    複製自: extract_images_from_html 方法
    """
    image_urls = []
    
    # 1. 從fancy_largelink元素提取圖片
    fancy_links = soup.select('a.fancy_largelink')
    if fancy_links:
        for link in fancy_links:
            # 高解析度圖片 (href)
            hd_img_url = link.get('href')
            if hd_img_url:
                if not hd_img_url.startswith(('http://', 'https://')):
                    hd_img_url = urljoin(base_url, hd_img_url)
                image_urls.append(hd_img_url)
            
            # 頁面顯示圖片 (img src)
            img_tag = link.select_one('img')
            if img_tag and img_tag.get('src'):
                img_url = img_tag.get('src')
                if not img_url.startswith(('http://', 'https://')):
                    img_url = urljoin(base_url, img_url)
                if img_url not in image_urls:
                    image_urls.append(img_url)
    
    # 2. 從隱藏區域獲取圖片
    hidden_imgs = soup.select('#img_hidden_pre img, #img_hidden_later img')
    for img in hidden_imgs:
        img_url = img.get('src')
        if img_url:
            if not img_url.startswith(('http://', 'https://')):
                img_url = urljoin(base_url, img_url)
            if img_url not in image_urls:
                image_urls.append(img_url)
    
    # 3. 獲取主圖
    main_img = soup.select_one('#largelinkImg')
    if main_img and main_img.get('src'):
        img_url = main_img.get('src')
        if not img_url.startswith(('http://', 'https://')):
            img_url = urljoin(base_url, img_url)
        if img_url not in image_urls:
            image_urls.append(img_url)
    
    # 4. 從縮略圖區域獲取圖片
    thumb_imgs = soup.select('.cutImglArea img')
    for img in thumb_imgs:
        img_url = img.get('src')
        if img_url:
            if not img_url.startswith(('http://', 'https://')):
                img_url = urljoin(base_url, img_url)
            
            if img_url not in image_urls:
                image_urls.append(img_url)
            
            # 嘗試獲取高解析度版本
            if '/cut_c/' in img_url:
                hd_img_url = img_url.replace('/cut_c/', '/cut_k/').replace('cc_', 'ck_')
                if hd_img_url not in image_urls:
                    image_urls.append(hd_img_url)
            elif '/prod_c/' in img_url:
                hd_img_url = img_url.replace('/prod_c/', '/prod_k/').replace('c_', 'k_')
                if hd_img_url not in image_urls:
                    image_urls.append(hd_img_url)
    
    # 5. 從所有img標籤提取圖片 (這是原版邏輯的最後一步)
    all_images = soup.select('img[src]')
    for img in all_images:
        img_url = img.get('src')
        if img_url and any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
            if not img_url.startswith(('http://', 'https://')):
                img_url = urljoin(base_url, img_url)
            if img_url not in image_urls:
                image_urls.append(img_url)
                
    return image_urls

def original_extract_images_from_js(soup, base_url):
    """
    [原始邏輯] 從JavaScript提取圖片URL
    複製自: extract_images_from_js 方法
    """
    image_urls = []
    scripts = soup.find_all('script')
    
    image_data = {}
    image_paths = {}
    
    for script in scripts:
        script_text = script.string
        if script_text and ('cimages' in script_text or 'kimages' in script_text):
            # 提取圖片文件名和路徑
            for line in script_text.split('\n'):
                # 圖片文件名
                cimages_match = re.search(r"cimages\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if cimages_match:
                    key, value = cimages_match.groups()
                    if key not in image_data:
                        image_data[key] = {}
                    image_data[key]['cimage'] = value
                
                kimages_match = re.search(r"kimages\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if kimages_match:
                    key, value = kimages_match.groups()
                    if key not in image_data:
                        image_data[key] = {}
                    image_data[key]['kimage'] = value
                
                # 圖片路徑
                cimage_path_match = re.search(r"cimage_paths\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if cimage_path_match:
                    key, value = cimage_path_match.groups()
                    image_paths[f'cimage_paths_{key}'] = value
                
                kimage_path_match = re.search(r"kimage_paths\['([^']+)'\]\s*=\s*'([^']+)'", line)
                if kimage_path_match:
                    key, value = kimage_path_match.groups()
                    image_paths[f'kimage_paths_{key}'] = value
    
    # 構建完整URL
    if image_data:
        for key, data in image_data.items():
            # 高解析度圖片 (cimage)
            if 'cimage' in data:
                cimage_path = image_paths.get(f'cimage_paths_{key}', '/common/images/product/prod_c')
                cimage_url = f"{base_url}{cimage_path}/{data['cimage']}"
                # 修正：原始腳本這裡可能沒有做 urljoin，但為了保險起見我們做一下處理，如果原腳本依賴字串拼接則保持
                # 為了避免雙重 slash，這裡簡單處理
                cimage_url = cimage_url.replace('https://webshop.montbell.jp//', 'https://webshop.montbell.jp/') 
                image_urls.append(cimage_url)
            
            # 低解析度圖片 (kimage)
            if 'kimage' in data:
                kimage_path = image_paths.get(f'kimage_paths_{key}', '/common/images/product/prod_k')
                kimage_url = f"{base_url}{kimage_path}/{data['kimage']}"
                kimage_url = kimage_url.replace('https://webshop.montbell.jp//', 'https://webshop.montbell.jp/')
                image_urls.append(kimage_url)
                
    return image_urls

def extract_color_code(filename):
    """輔助功能：提取顏色代碼 (這是Web App新增的實用功能，保留)"""
    try:
        name_without_ext = os.path.splitext(filename)[0]
        if '_' in name_without_ext:
            parts = name_without_ext.split('_')
            last_part = parts[-1]
            if last_part.isdigit() and len(parts) > 1: return parts[-2]
            return last_part
    except: pass
    return None

# ==============================================================================
# UI 介面與主流程
# ==============================================================================

st.title("🏔️ Montbell 下載器 (原版核心)")
st.caption("v2.0 嚴格復刻原始 Python 邏輯 | iOS Style GUI")

uploaded_file = st.file_uploader("📂 上傳 Excel (含型號欄位)", type=['xlsx', 'xls'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        
        # 欄位偵測
        model_col = next((c for c in df.columns if any(x in str(c).lower() for x in ['型號', 'model', 'id'])), df.columns[0])
        url_col = next((c for c in df.columns if any(x in str(c).lower() for x in ['網址', 'url', 'link'])), None)
        
        total_items = len(df)
        BATCH_SIZE = 50
        total_batches = math.ceil(total_items / BATCH_SIZE)

        st.write("---")
        
        # 分批選擇器
        col1, col2 = st.columns([2, 1])
        with col1:
            batch_options = [f"📦 第 {i+1} 批 (型號 {i*BATCH_SIZE+1} - {min((i+1)*BATCH_SIZE, total_items)})" for i in range(total_batches)]
            selected_batch_str = st.selectbox("選擇批次", batch_options)
            try:
                batch_number = int(re.search(r'\d+', selected_batch_str).group())
                batch_index = batch_number - 1
            except: batch_index = 0
            start_idx = batch_index * BATCH_SIZE
            end_idx = min((batch_index + 1) * BATCH_SIZE, total_items)
            batch_df = df.iloc[start_idx:end_idx]
            
        with col2:
            st.metric("本批數量", f"{len(batch_df)}")

        with st.expander("⚙️ 進階設定"):
            domain = st.text_input("域名", "https://webshop.montbell.jp")
            delay = st.number_input("延遲(秒)", 1, 10, 2)

        st.write("---")

        # 執行按鈕
        b_col1, b_col2, b_col3 = st.columns([1, 2, 1])
        start_process = False
        with b_col2:
            if st.button(f"🚀\n開始下載\n本批次", key="run_batch"):
                start_process = True

        if start_process:
            progress_bar = st.progress(0)
            status_text = st.empty()
            log_area = st.empty()
            logs = []
            report_data = []
            zip_buffer = io.BytesIO()
            download_count = 0
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                
                # === 開始原始腳本的迭代邏輯 ===
                for i, (orig_idx, row) in enumerate(batch_df.iterrows()):
                    model_number = str(row[model_col]).strip()
                    if not model_number or model_number == 'nan': continue
                    
                    # 進度更新
                    progress = (i + 1) / len(batch_df)
                    progress_bar.progress(progress)
                    status_text.text(f"正在處理: {model_number}")
                    
                    product_links = []
                    search_url = None

                    # 1. 嘗試從 Excel 獲取 URL
                    if url_col and pd.notna(row[url_col]):
                        product_url = str(row[url_col]).strip()
                        if product_url and product_url.lower() != 'nan':
                            if not product_url.startswith(('http://', 'https://')):
                                product_url = urljoin(domain, product_url)
                            product_links.append(product_url)
                            search_url = domain
                    
                    # 2. 如果沒有 URL，執行搜尋 (原始邏輯)
                    if not product_links:
                        search_url = f"{domain}/goods/list_search.php"
                        params = {'top_sk': model_number}
                        
                        try:
                            time.sleep(delay)
                            # 使用原始 Headers
                            resp = requests.get(search_url, params=params, headers=get_original_headers())
                            
                            # 解析頁面 (原始邏輯：同時檢查 detail.php 和 disp.php)
                            soup = BeautifulSoup(resp.content, 'html.parser')
                            for link in soup.find_all('a', href=True):
                                href = link.get('href', '')
                                if 'goods/detail.php' in href or 'goods/disp.php' in href:
                                    product_links.append(urljoin(search_url, href))
                            
                            # 如果沒找到連結但頁面本身就是商品頁 (跳轉)
                            if not product_links and ('goods/detail.php' in resp.url or 'goods/disp.php' in resp.url):
                                product_links.append(resp.url)
                        except Exception as e:
                            logs.append(f"❌ {model_number} 搜尋失敗: {e}")

                    # 3. 處理商品頁面
                    relevant_images = []
                    # 原始腳本這裡只取前 3 個連結
                    for product_url in product_links[:3]:
                        try:
                            time.sleep(delay)
                            product_response = requests.get(product_url, headers=get_original_headers(search_url))
                            
                            if product_response.status_code != 200: continue
                            
                            product_soup = BeautifulSoup(product_response.content, 'html.parser')
                            
                            # === 調用原始提取函數 ===
                            html_images = original_extract_images_from_html(product_soup, product_url)
                            if html_images: relevant_images.extend(html_images)
                            
                            js_images = original_extract_images_from_js(product_soup, product_url)
                            if js_images: relevant_images.extend(js_images)
                            
                        except Exception as e:
                            pass
                    
                    # 去除重複URL
                    relevant_images = list(set(relevant_images))
                    
                    # 4. 下載圖片 (原始邏輯)
                    item_img_count = 0
                    item_colors = set()
                    
                    for img_idx, img_url in enumerate(relevant_images):
                        try:
                            time.sleep(delay / 2) # 原始腳本這裡有隨機延遲，Web版稍微固定一點
                            
                            headers = get_original_headers(product_url) # 使用原始 User-Agent
                            headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
                            
                            # 先 HEAD 檢查 (原始邏輯)
                            try:
                                head_response = requests.head(img_url, headers=headers, timeout=5)
                            except: continue # 如果 head 失敗就跳過
                            
                            if head_response.status_code == 200:
                                img_response = requests.get(img_url, headers=headers, stream=True)
                                content_type = img_response.headers.get('Content-Type', '')
                                
                                if 'image/' in content_type:
                                    parsed_url = urlparse(img_url)
                                    original_filename = os.path.basename(parsed_url.path)
                                    
                                    # 檔名處理
                                    if not original_filename:
                                        ext = '.' + content_type.split('/')[-1]
                                        original_filename = f"{model_number}_{img_idx+1}{ext}"
                                    
                                    original_filename = original_filename.split('?')[0]
                                    
                                    # 寫入 ZIP
                                    # 為了避免重名覆蓋，這裡做簡單的 unique 處理
                                    zip_path = f"{model_number}/{original_filename}"
                                    if zip_path in zf.namelist():
                                        name, ext = os.path.splitext(original_filename)
                                        zip_path = f"{model_number}/{name}_{img_idx}{ext}"
                                        
                                    zf.writestr(zip_path, img_response.content)
                                    item_img_count += 1
                                    
                                    # 收集顏色 (報表用)
                                    c = extract_color_code(original_filename)
                                    if c: item_colors.add(c)
                        except: pass
                    
                    # 記錄日誌
                    colors_str = ",".join(sorted(list(item_colors))) if item_colors else "無/未識別"
                    report_data.append({
                        "商品型號": model_number,
                        "圖片數量": item_img_count,
                        "已取得顏色": colors_str,
                        "狀態": "成功" if item_img_count > 0 else "失敗/無圖片"
                    })
                    
                    if item_img_count > 0:
                        download_count += item_img_count
                        logs.append(f"✅ {model_number}: {item_img_count} 張 ({colors_str})")
                    else:
                        logs.append(f"⚠️ {model_number}: 無圖片")
                    log_area.code("\n".join(logs[-3:]))

                # 生成 Excel
                if report_data:
                    df_report = pd.DataFrame(report_data)
                    with io.BytesIO() as excel_buffer:
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            df_report.to_excel(writer, index=False, sheet_name='下載摘要')
                        zf.writestr(f"報表_第{batch_index+1}批.xlsx", excel_buffer.getvalue())

            status_text.text("✅ 本批次處理完成！")
            progress_bar.progress(100)
            zip_buffer.seek(0)
            
            st.success(f"🎉 成功打包 {download_count} 張圖片")
            st.download_button(
                label=f"📥 下載第 {batch_index+1} 批壓縮檔",
                data=zip_buffer,
                file_name=f"montbell_batch_{batch_index+1}_original_logic.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"執行錯誤: {e}")