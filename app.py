import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
import pandas as pd
import plotly.express as px
import os

# --- 1. 初始化 Firebase (只執行一次) ---
# Streamlit 會在每次互動時重跑整個腳本，所以要檢查是否已經初始化
if not firebase_admin._apps:
    # 1. 優先嘗試讀取環境變數 (給 GitHub Actions 用)
    firebase_key_env = os.environ.get("FIREBASE_CREDENTIALS")
    
    if firebase_key_env:
        # 如果環境變數存在，將 JSON 字串轉回 Dict
        cred_dict = json.loads(firebase_key_env)
        cred = credentials.Certificate(cred_dict)
    
    # 2. 如果沒有環境變數，則嘗試讀取本地檔案 (給你自己開發用)
    elif os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
    
    else:
        raise FileNotFoundError("找不到 Firebase 金鑰！請設定環境變數或放入 json 檔。")

    initialize_app(cred)

db = firestore.client()

# --- 2. 資料讀取與快取 (Cache) ---
# 使用 @st.cache_data 避免每次按按鈕都重新去 Firebase 撈資料 (省流量、加速)
@st.cache_data(ttl=600) # 設定 10 分鐘過期
def load_data():
    docs = db.collection("news").stream()
    data = []
    for doc in docs:
        data.append(doc.to_dict())
    
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    
    # 確保日期欄位是 datetime 格式，方便篩選
    # 假設你的日期格式是 "2024-03-20 12:00" 或 "2024-03-20"
    df['date_obj'] = pd.to_datetime(df['date_str'], errors='coerce')
    return df

# --- 3. 介面開始 ---
st.set_page_config(page_title="新聞分析系統", layout="wide")
st.title("📰 新聞資料分析系統")

# 載入資料
with st.spinner('正在從 Firebase 載入資料...'):
    df = load_data()

if df.empty:
    st.error("⚠️ 資料庫是空的！請先執行爬蟲與上傳程式。")
    st.stop()

# --- 側邊欄：全域篩選器 ---
st.sidebar.header("🔍 篩選條件")

# 時間處理：確保有資料才抓日期
if 'date_obj' in df.columns and not df['date_obj'].isnull().all():
    min_date = df['date_obj'].min().date()
    max_date = df['date_obj'].max().date()
    
    start_date, end_date = st.sidebar.date_input(
        "選擇時間區間",
        [min_date, max_date],
        min_value=min_date,
        max_value=max_date
    )
    
    # 根據時間過濾
    mask = (df['date_obj'].dt.date >= start_date) & (df['date_obj'].dt.date <= end_date)
    filtered_df = df[mask]
else:
    st.sidebar.warning("日期格式解析失敗，顯示所有資料")
    filtered_df = df

st.sidebar.info(f"顯示筆數：{len(filtered_df)} / {len(df)}")

# --- 主畫面：定義 4 個分頁 ---
tab1, tab2, tab3, tab4 = st.tabs(["📊 總體概況", "🏆 記者分析", "🔑 關鍵詞分析", "🔎 資料瀏覽"])

# === Tab 1: 總體概況 ===
with tab1:
    st.header("新聞類別分布")
    if not filtered_df.empty:
        category_counts = filtered_df['category'].value_counts().reset_index()
        category_counts.columns = ['類別', '數量']
        fig_cat = px.pie(category_counts, values='數量', names='類別', title='新聞類別佔比')
        st.plotly_chart(fig_cat, use_container_width=True)
    else:
        st.info("此區間無資料")

# === Tab 2: 記者分析 ===
with tab2:
    if not filtered_df.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("🔥 活躍記者 Top 10")
            reporter_counts = filtered_df['reporter'].value_counts().head(10).reset_index()
            reporter_counts.columns = ['記者姓名', '文章數量']
            reporter_counts = reporter_counts[reporter_counts['記者姓名'] != 'Unknown']
            fig_rep = px.bar(reporter_counts, x='記者姓名', y='文章數量', color='文章數量')
            st.plotly_chart(fig_rep, use_container_width=True)

        with col2:
            st.subheader("🕵️ 記者屬性透視")
            reporters = sorted(filtered_df['reporter'].unique().tolist())
            if 'Unknown' in reporters: reporters.remove('Unknown')
            
            if reporters:
                selected_reporter = st.selectbox("選擇記者", reporters)
                rep_articles = filtered_df[filtered_df['reporter'] == selected_reporter]
                st.metric("文章數", len(rep_articles))
                st.write("關注領域：")
                st.bar_chart(rep_articles['category'].value_counts())
    else:
        st.info("此區間無資料")

# === Tab 3: 關鍵詞分析 ===
with tab3:
    st.header("熱門關鍵詞分析")
    if not filtered_df.empty and 'keywords' in filtered_df.columns:
        all_keywords = []
        for keywords in filtered_df['keywords']:
            if isinstance(keywords, list):
                all_keywords.extend(keywords)
        
        if all_keywords:
            from collections import Counter
            word_counts = Counter(all_keywords).most_common(20)
            words_df = pd.DataFrame(word_counts, columns=['關鍵詞', '出現次數'])
            fig_kw = px.bar(words_df, x='關鍵詞', y='出現次數', color='出現次數')
            st.plotly_chart(fig_kw, use_container_width=True)
        else:
            st.warning("沒有提取到關鍵詞")
    else:
        st.info("此區間無資料或缺少關鍵詞欄位")

# === Tab 4: 資料瀏覽 (之前沒東西就是這段有問題) ===
with tab4:
    st.header("詳細資料列表")
    
    # 這裡我們做一個切換開關，讓你可以看「篩選後」或「全部」資料
    show_all = st.checkbox("顯示所有資料 (忽略日期篩選)")
    
    display_df = df if show_all else filtered_df
    
    if not display_df.empty:
        # 只顯示重要欄位，避免表格太擠
        cols_to_show = ['date_str', 'category', 'reporter', 'title', 'keywords', 'link']
        
        # 確保這些欄位真的存在，避免報錯
        valid_cols = [c for c in cols_to_show if c in display_df.columns]
        
        st.dataframe(
            display_df[valid_cols],
            use_container_width=True,
            hide_index=True,
            height=600 # 設定高度，讓表格長一點
        )
    else:
        st.warning("⚠️ 目前列表是空的，請嘗試調整左側日期區間，或勾選「顯示所有資料」。")