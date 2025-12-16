import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
import pandas as pd
import plotly.express as px
import os
import json
from wordcloud import WordCloud
import matplotlib.pyplot as plt


# --- 1. 初始化 Firebase (只執行一次) ---
# Streamlit 會在每次互動時重跑整個腳本，所以要檢查是否已經初始化
if not firebase_admin._apps:
    # 1. 優先嘗試從 Streamlit Secrets 讀取 (雲端模式)
    if "firebase" in st.secrets:
        # 這裡的 "firebase" 對應到 Secrets 裡面的 [firebase]
        key_dict = json.loads(st.secrets["firebase"]["credentials_json"])
        cred = credentials.Certificate(key_dict)
    
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
st.set_page_config(
    page_title="ETtoday 新聞輿情戰情室",
    page_icon="📰",
    layout="wide", # 寬螢幕模式
    initial_sidebar_state="expanded"
)

# === 標題與簡介 ===
st.title("📰 ETtoday 新聞輿情戰情室")
st.markdown("---")

# 載入資料
df = load_data()
if df.empty:
    st.warning("目前沒有資料，請確認資料庫狀態。")
    st.stop()

# === 側邊欄：全域控制中心 ===
with st.sidebar:
    st.header("⚙️ 篩選控制")
    
    # 1. 日期篩選
    if 'date_obj' in df.columns:
        min_date = df['date_obj'].min().date()
        max_date = df['date_obj'].max().date()
        date_range = st.date_input("📅 選擇日期區間", [min_date, max_date])
    
    # 2. 類別篩選 (多選)
    all_categories = sorted(df['category'].unique())
    selected_cats = st.multiselect("🏷️ 選擇新聞類別", all_categories, default=all_categories)
    
    st.info(f"資料來源：ETtoday\n總筆數：{len(df)} 筆")

# === 資料過濾邏輯 ===
# 根據使用者的篩選條件產生 filtered_df
mask = df['category'].isin(selected_cats)
if len(date_range) == 2:
    mask = mask & (df['date_obj'].dt.date >= date_range[0]) & (df['date_obj'].dt.date <= date_range[1])

filtered_df = df[mask]

# === 關鍵指標區 (KPI Metrics) ===
# 用三欄排版顯示大數字
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("總文章數", f"{len(filtered_df)} 篇")
with col2:
    # 算出最活躍記者
    top_reporter = filtered_df['reporter'].mode()[0] if not filtered_df.empty else "N/A"
    st.metric("🔥 最活躍記者", top_reporter)
with col3:
    st.metric("涵蓋類別數", f"{filtered_df['category'].nunique()} 類")
with col4:
    # 算出出現最多的關鍵詞
    # (這裡簡化處理，實際建議拉出來算)
    st.metric("⭐ 關鍵詞焦點", "請看下方分析")

st.markdown("---")

# === 主內容分頁 ===
tab1, tab2, tab3, tab4 = st.tabs(["📈 趨勢總覽", "🏆 記者戰力榜", "☁️ 關鍵詞雲", "🗃️ 詳細資料庫"])

with tab1:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.subheader("各類別新聞數量佔比")
        cat_counts = filtered_df['category'].value_counts().reset_index()
        cat_counts.columns = ['類別', '數量']
        fig_pie = px.pie(cat_counts, values='數量', names='類別', hole=0.4) # 甜甜圈圖比較潮
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_b:
        st.subheader("每日文章量趨勢")
        # 依日期分組統計
        daily_counts = filtered_df.groupby(filtered_df['date_obj'].dt.date).size().reset_index(name='文章數')
        fig_line = px.line(daily_counts, x='date_obj', y='文章數', markers=True)
        st.plotly_chart(fig_line, use_container_width=True)

with tab2:
    st.subheader("記者產量 Top 20")
    reporter_counts = filtered_df['reporter'].value_counts().head(20).reset_index()
    reporter_counts.columns = ['記者', '文章數']
    reporter_counts = reporter_counts[reporter_counts['記者'] != 'Unknown']
    
    fig_bar = px.bar(reporter_counts, x='文章數', y='記者', orientation='h', color='文章數')
    fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}) # 讓長條圖由大排到小
    st.plotly_chart(fig_bar, use_container_width=True)

with tab3:
    st.subheader("熱門關鍵詞文字雲")
    # 這裡需要把所有 keywords 串接起來
    all_words = []
    for k in filtered_df['keywords']:
        if isinstance(k, list): all_words.extend(k)
    
    if all_words:
        # 設定中文字型路徑 (Streamlit Cloud 上可能預設不支援中文，這部分在雲端要另外處理字型檔)
        # 本機測試可以直接跑
        text = " ".join(all_words)
        
        # 簡單做個文字雲
        wc = WordCloud(font_path=None, width=800, height=400, background_color="white").generate(text)
        
        # 用 matplotlib 畫出來
        fig, ax = plt.subplots()
        ax.imshow(wc, interpolation='bilinear')
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.info("無關鍵詞資料")

with tab4:
    st.subheader("資料瀏覽")
    
    # 使用 dataframe 並設定 Link 欄位為按鈕格式
    st.dataframe(
        filtered_df[['date_str', 'category', 'reporter', 'title', 'link']],
        column_config={
            "link": st.column_config.LinkColumn("閱讀全文", display_text="點擊前往"),
            "date_str": "發布時間",
            "category": "分類",
            "reporter": "記者",
            "title": "標題"
        },
        use_container_width=True,
        hide_index=True
    )