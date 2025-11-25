import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import re
import zipfile
import time
import math
from urllib.parse import urljoin, urlparse
import io

# --- 頁面設定 ---
st.set_page_config(page_title="Montbell 下載器 Pro", page_icon="🏔️", layout="centered")

# --- iOS 風格 CSS ---
st.markdown("""
<style>
    /* 全域設定 */
    .stApp {
        background-color: #000000;
        color: #FFFFFF;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }

    /* 輸入框與選擇器 */
    .stTextInput > div > div > input, 
    .stNumberInput > div > div > input, 
    .stSelectbox > div > div > div {
        border-radius: 12px;
        background-color: #1C1C1E;
        color: white;
        border: 1px solid #333;
    }

    /* --- iOS App Icon 風格按鈕 --- */
    div.stButton > button {
        width: 100%;
        aspect-ratio: 1 / 1;
        border-radius: 22px;
        background: linear-gradient(145deg, #0A84FF, #0070E0);
        color: white;
        font-weight: 600;
        font-size: 20px;
        border: none;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        transition: all 0.2s ease;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        margin-bottom: 10px;
    }
    div.stButton > button:hover {
        transform: scale(0.97);
        box-shadow: 0 2px 10px rgba(0,0,0,0.5);
        background: linear-gradient(145deg, #0070E0, #005BB5);
    }
    
    /* 下載按鈕 (綠色) */
    div.stDownloadButton > button {
        width: 100%;
        height: 60px;
        border-radius: 14px;
        background-color: #30D158;
        color: black;
        font-weight: bold;
        font-size: 18px;
        border: none;
    }
    div.stDownloadButton > button:hover {
        background-color: #28C14D;
    }

    /* 進度條 */
    .stProgress > div > div > div > div {
        background-color: #0A84FF;
    }

    /* Expander 樣式 */
    .stExpander {
        background-color: #1C1C1E;
        border-radius: 16px;
    }
</style>
""", unsafe_allow_html=True)

# --- 核心邏輯 ---
def get_headers(referer=None):
    return {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': referer if referer else 'https://webshop.montbell.jp/',
        'Connection': 'keep-alive',
    }

def extract_images_from_html(soup, base_url):
    image_urls = []
    # 1. fancy_largelink
    for link in soup.select('a.fancy_largelink'):
        if link.get('href'): image_urls.append(urljoin(base_url, link.get('href')))
        img = link.select_one('img')
        if img and img.get('src'): image_urls.append(urljoin(base_url, img.get('src')))
    # 2. hidden & main
    for img in soup.select('#img_hidden_pre img, #img_hidden_later img, #largelinkImg'):
        if img.get('src'): image_urls.append(urljoin(base_url, img.get('src')))
    # 3. thumbnails
    for img in soup.select('.cutImglArea img'):
        if img.get('src'):
            full = urljoin(base_url, img.get('src'))
            image_urls.append(full)
            if '/cut_c/' in full: image_urls.append(full.replace('/cut_c/', '/cut_k/').replace('cc_', 'ck_'))
            elif '/prod_c/' in full: image_urls.append(full.replace('/prod_c/', '/prod_k/').replace('c_', 'k_'))
    return list(set(u for u in image_urls if u.startswith(('http', '//'))))

def extract_images_from_js(soup, base_url):
    image_urls = []
    scripts = soup.find_all('script')
    img_data, img_paths = {}, {}
    for s in scripts:
        if s.string and ('cimages' in s.string or 'kimages' in s.string):
            for line in s.string.split('\n'):
                if m := re.search(r"cimages\['([^']+)'\]\s*=\s*'([^']+)'", line): img_data.setdefault(m[1], {})['cimage'] = m[2]
                if m := re.search(r"kimages\['([^']+)'\]\s*=\s*'([^']+)'", line): img_data.setdefault(m[1], {})['kimage'] = m[2]
                if m := re.search(r"cimage_paths\['([^']+)'\]\s*=\s*'([^']+)'", line): img_paths[f'c_{m[1]}'] = m[2]
                if m := re.search(r"kimage_paths\['([^']+)'\]\s*=\s*'([^']+)'", line): img_paths[f'k_{m[1]}'] = m[2]
    for k, v in img_data.items():
        if 'cimage' in v: image_urls.append(urljoin(base_url, f"{img_paths.get(f'c_{k}', '/common/images/product/prod_c')}/{v['cimage']}"))
        if 'kimage' in v: image_urls.append(urljoin(base_url, f"{img_paths.get(f'k_{k}', '/common/images/product/prod_k')}/{v['kimage']}"))
    return list(set(image_urls))

def extract_color_code(filename):
    """
    從檔名提取顏色代碼
    假設格式: 1111222_NV.jpg -> NV
    """
    try:
        # 移除副檔名
        name_without_ext = os.path.splitext(filename)[0]
        # 如果包含底線，取最後一段
        if '_' in name_without_ext:
            parts = name_without_ext.split('_')
            # 排除像是 '1', '2' 這種流水號，如果最後一段是純數字，取倒數第二段
            last_part = parts[-1]
            if last_part.isdigit() and len(parts) > 1:
                return parts[-2]
            return last_part
    except:
        pass
    return None

# --- UI 介面 ---
st.title("🏔️ Montbell 下載器 Pro")
st.caption("自動生成顏色報表 | iOS Style")

# 1. 檔案上傳
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
        
        # 2. 分批選擇器
        col1, col2 = st.columns([2, 1])
        with col1:
            batch_options = [f"📦 第 {i+1} 批 (型號 {i*BATCH_SIZE+1} - {min((i+1)*BATCH_SIZE, total_items)})" for i in range(total_batches)]
            selected_batch_str = st.selectbox("選擇批次", batch_options)
            batch_index = int(selected_batch_str.split(' ')[1]) - 1
            start_idx = batch_index * BATCH_SIZE
            end_idx = min((batch_index + 1) * BATCH_SIZE, total_items)
            batch_df = df.iloc[start_idx:end_idx]
            
        with col2:
            st.metric("本批數量", f"{len(batch_df)}")

        with st.expander("⚙️ 進階設定"):
            domain = st.text_input("域名", "https://webshop.montbell.jp")
            delay = st.number_input("延遲(秒)", 1, 10, 2)

        st.write("---")

        # 3. 執行按鈕
        b_col1, b_col2, b_col3 = st.columns([1, 2, 1])
        start_process = False
        with b_col2:
            if st.button(f"🚀\n開始下載\n本批次", key="run_batch"):
                start_process = True

        # 4. 處理邏輯
        if start_process:
            progress_bar = st.progress(0)
            status_text = st.empty()
            log_area = st.empty()
            logs = []
            
            # 報表資料列表
            report_data = []
            
            zip_buffer = io.BytesIO()
            download_count = 0
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                
                # 遍歷批次
                for i, (orig_idx, row) in enumerate(batch_df.iterrows()):
                    model_id = str(row[model_col]).strip()
                    if not model_id or model_id == 'nan': continue
                    
                    # 更新進度
                    progress = (i + 1) / len(batch_df)
                    progress_bar.progress(progress)
                    status_text.text(f"正在處理: {model_id}")
                    
                    # 獲取 URLs (同前次邏輯)
                    target_urls = []
                    if url_col and pd.notna(row[url_col]):
                        u = str(row[url_col]).strip()
                        if u.startswith('http'): target_urls.append(u)
                    
                    if not target_urls:
                        try:
                            time.sleep(delay)
                            resp = requests.get(f"{domain}/goods/list_search.php", params={'top_sk': model_id}, headers=get_headers())
                            soup = BeautifulSoup(resp.content, 'html.parser')
                            for l in soup.find_all('a', href=True):
                                if 'goods/detail.php' in l['href']: target_urls.append(urljoin(resp.url, l['href']))
                            if not target_urls and 'goods/detail.php' in resp.url: target_urls.append(resp.url)
                        except: pass
                    
                    img_urls = []
                    for u in target_urls[:1]:
                        try:
                            time.sleep(delay)
                            r = requests.get(u, headers=get_headers())
                            s = BeautifulSoup(r.content, 'html.parser')
                            img_urls.extend(extract_images_from_html(s, u))
                            img_urls.extend(extract_images_from_js(s, u))
                        except: pass
                    
                    img_urls = list(set(img_urls))
                    
                    # 開始下載並收集顏色
                    item_colors = set()
                    item_img_count = 0
                    
                    for idx_img, url in enumerate(img_urls):
                        try:
                            time.sleep(0.5)
                            ir = requests.get(url, headers=get_headers(), timeout=10)
                            if ir.status_code == 200:
                                # 決定檔名
                                parsed_path = urlparse(url).path
                                fname = os.path.basename(parsed_path)
                                if not fname: fname = f"{model_id}_{idx_img}.jpg"
                                
                                # 寫入 ZIP
                                zf.writestr(f"{model_id}/{fname}", ir.content)
                                item_img_count += 1
                                
                                # 提取顏色
                                color = extract_color_code(fname)
                                if color:
                                    item_colors.add(color)
                        except: pass
                    
                    # 記錄到報表
                    colors_str = ",".join(sorted(list(item_colors))) if item_colors else "無/未識別"
                    
                    report_data.append({
                        "商品型號": model_id,
                        "圖片數量": item_img_count,
                        "已取得顏色": colors_str,
                        "狀態": "成功" if item_img_count > 0 else "失敗/無圖片"
                    })
                    
                    if item_img_count > 0:
                        download_count += item_img_count
                        logs.append(f"✅ {model_id}: {item_img_count} 張 ({colors_str})")
                    else:
                        logs.append(f"⚠️ {model_id}: 無圖片")
                    log_area.code("\n".join(logs[-3:]))

                # --- 生成 Excel 報表並寫入 ZIP ---
                if report_data:
                    df_report = pd.DataFrame(report_data)
                    with io.BytesIO() as excel_buffer:
                        # 使用 ExcelWriter 引擎
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            df_report.to_excel(writer, index=False, sheet_name='下載摘要')
                        
                        # 將 Excel 存入 ZIP 根目錄
                        zf.writestr(f"報表_第{batch_index+1}批.xlsx", excel_buffer.getvalue())
                    logs.append(f"📊 已生成報表: 報表_第{batch_index+1}批.xlsx")
                    log_area.code("\n".join(logs[-3:]))

            # 完成
            status_text.text("✅ 本批次處理完成！")
            progress_bar.progress(100)
            zip_buffer.seek(0)
            
            st.success(f"🎉 成功打包 {download_count} 張圖片 (內含 Excel 報表)")
            
            st.download_button(
                label=f"📥 下載第 {batch_index+1} 批壓縮檔 (ZIP+Excel)",
                data=zip_buffer,
                file_name=f"montbell_batch_{batch_index+1}_report.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"執行錯誤: {e}")