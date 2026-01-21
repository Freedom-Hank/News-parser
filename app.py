import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import plotly.express as px
import os
from datetime import datetime, timedelta
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import ast


# --- 1. 初始化 Firebase (只執行一次) ---
# Streamlit 會在每次互動時重跑整個腳本，所以要檢查是否已經初始化
if not firebase_admin._apps:
    # 1. 優先嘗試從 Streamlit Secrets 讀取 (雲端模式)
    if "firebase" in st.secrets:
        # 這裡的 "firebase" 對應到 Secrets 裡面的 [firebase]
        key_dict = dict(st.secrets["firebase"])
        
        if "\\n" in key_dict["private_key"]:
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        
        cred = credentials.Certificate(key_dict)
    
    # 2. 如果沒有環境變數，則嘗試讀取本地檔案 (給你自己開發用)
    elif os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
    
    else:
        st.error("找不到 Firebase 金鑰！")
        st.stop()

    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. 資料讀取與快取 (Cache) ---
# 使用 @st.cache_data 避免每次按按鈕都重新去 Firebase 撈資料 (省流量、加速)
@st.cache_data(ttl=600) 
def load_hybrid_data():
    """
    1. 讀取 GitHub 上的 CSV (歷史資料)
    2. 讀取 Firebase (最新資料)
    3. 合併回傳
    """
    # --- Part A: 讀取歷史 CSV (本地檔案) ---
    csv_file = "news_history.csv"
    
    if os.path.exists(csv_file):
        try:
            history_df = pd.read_csv(csv_file)
            # 確保日期欄位是 datetime 物件，方便後面比較
            history_df['date_obj'] = pd.to_datetime(history_df['date_str'])
            last_date_in_csv = history_df['date_str'].max()
            print(f"📂 [CSV] 載入歷史資料: {len(history_df)} 筆 (更新至 {last_date_in_csv})")
        except Exception as e:
            print(f"❌ 讀取 CSV 失敗: {e}")
            history_df = pd.DataFrame()
            last_date_in_csv = "2025-11-01" # 預設起點
    else:
        print("⚠️ 找不到 CSV 檔案，將只抓取 Firebase 資料")
        history_df = pd.DataFrame()
        last_date_in_csv = "2025-11-01"

    # --- Part B: 抓取 Firebase 新資料 ---
    # 只抓 CSV 最後一天 "之後" 的資料
    print(f"📡 [Firebase] 正在檢查 {last_date_in_csv} 之後的新聞...")
    
    try:
        docs = (
            db.collection("news")
            .where("date_str", ">", last_date_in_csv)
            .stream()
        )
        new_data = [doc.to_dict() for doc in docs]
        print(f"✅ [Firebase] 抓到新資料: {len(new_data)} 筆")
    except Exception as e:
        print(f"❌ Firebase 讀取錯誤: {e}")
        new_data = []

    # --- Part C: 合併 ---
    if new_data:
        new_df = pd.DataFrame(new_data)
        new_df['date_obj'] = pd.to_datetime(new_df['date_str'])
        
        # 把舊的跟新的接起來
        if not history_df.empty:
            full_df = pd.concat([history_df, new_df], ignore_index=True)
        else:
            full_df = new_df
            
        # 雙重保險：依連結去重複 (防止 CSV 跟 Firebase 重疊)
        full_df = full_df.drop_duplicates(subset=['link'], keep='last')
        return full_df
    else:
        return history_df

# --- 3. 介面開始 ---
st.set_page_config(
    page_title="ETtoday 新聞輿情戰情室",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === 標題與簡介 ===
st.title("📰 ETtoday 新聞輿情戰情室")
st.markdown("---")

# ==========================================
# 1. 側邊欄 Part A：日期選擇
# ==========================================
with st.sidebar:
    st.header("⚙️ 篩選控制")
    
    # 設定預設值
    default_start = datetime.now().date() - timedelta(days=7)
    default_end = datetime.now().date()

    # 日期選擇器
    date_range = st.date_input(
        "📅 選擇資料日期區間", 
        (default_start, default_end), 
        max_value=datetime.now().date()
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
        
        days_diff = (end_date - start_date).days
    else:
        st.info("請選擇結束日期")
        st.stop() # 這裡停住，等待使用者選完日期

# ==========================================
# 2. 核心動作：載入資料
# ==========================================
# 步驟 1: 先拿到 "完整資料庫" (這步有快取保護)
full_df = load_hybrid_data()

# 步驟 2: 根據使用者選的日期，在 "記憶體中" 切割資料
if not full_df.empty:
    # 這裡要做日期過濾，因為 load_hybrid_data 現在回傳的是從 11月 至今的所有資料
    # 我們要把 start_date, end_date 轉成 datetime 才能跟 date_obj 比較
    mask = (full_df['date_obj'].dt.date >= start_date) & (full_df['date_obj'].dt.date <= end_date)
    df = full_df[mask]
else:
    df = pd.DataFrame()

# 防呆：如果 df 是空的
if df.empty:
    st.warning(f"⚠️ 在 {start_date} 到 {end_date} 之間找不到新聞資料。")
    st.stop()
# ==========================================
# 3. 側邊欄 Part B：類別與記者篩選
# ==========================================
with st.sidebar:
    # --- 類別篩選 ---
    st.write("---")
    st.write("🏷️ 新聞類別篩選")
    
    all_categories = sorted(df['category'].unique())
    
    if "selected_cats" not in st.session_state:
        st.session_state["selected_cats"] = all_categories

    def select_all():
        st.session_state["selected_cats"] = all_categories

    def deselect_all():
        st.session_state["selected_cats"] = []

    col1, col2 = st.columns(2)
    with col1:
        st.button("✅ 全選", on_click=select_all, use_container_width=True)
    with col2:
        st.button("❌ 清空", on_click=deselect_all, use_container_width=True)

    selected_cats = st.multiselect(
        "請選擇類別：",
        options=all_categories,
        key="selected_cats"
    )
    
    # --- 記者篩選 ---
    st.write("---")
    st.write("🎤 記者篩選")
    
    all_reporters = sorted(df['reporter'].astype(str).unique())
    
    selected_reporters = st.multiselect(
        "搜尋或選擇記者 (留空即顯示全部)：",
        options=all_reporters,
        default=[]
    )
    
    # --- 計算過濾後的結果 (給 Metric 使用) ---
    mask = df['category'].isin(selected_cats)
    
    if selected_reporters:
        mask = mask & (df['reporter'].isin(selected_reporters))
            
    filtered_count = df[mask].shape[0]
    total_count = df.shape[0]

    # --- 顯示指標卡 ---
    st.markdown("---")
    st.metric(
        label="📊 資料筆數狀態",
        value=f"{filtered_count} 筆",
        delta=f"本區間總庫存: {total_count} 筆",
        delta_color="off"
    )
    st.caption("資料來源：ETtoday")

# ==========================================
# 4. 主畫面資料過濾 (產生全域 filtered_df 給圖表用)
# ==========================================
mask = df['category'].isin(selected_cats)

if selected_reporters:
    mask = mask & (df['reporter'].isin(selected_reporters))

filtered_df = df[mask]

# === 關鍵指標區 (KPI Metrics) ===
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("總文章數", f"{len(filtered_df)} 篇")
with col2:
    # 算出最活躍記者
    valid_reporters = filtered_df[filtered_df['reporter'] != 'Unknown']

    if not valid_reporters.empty:
        top_reporter = valid_reporters['reporter'].mode()[0]
    else:
        top_reporter = "N/A"
    st.metric("🔥 最活躍記者", top_reporter)
with col3:
    st.metric("涵蓋類別數", f"{filtered_df['category'].nunique()} 類")
with col4:
    st.metric("⭐ 關鍵詞焦點", "請看下方分析")

st.markdown("---")

# === 主內容分頁 ===
tab1, tab2, tab3, tab4 = st.tabs(["📈 趨勢總覽", "☁️ 關鍵詞雲", "🏆 記者戰力榜", "📊 戰力分析與資料庫"])

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
    st.subheader("熱門關鍵詞文字雲")
    # 這裡需要把所有 keywords 串接起來
    all_words = []
    if 'keywords' in filtered_df.columns:
        for k in filtered_df['keywords']:
            if k is None:
                continue
                
            # 狀況 1: 它是 list (從 Firebase 直接來)
            if isinstance(k, list):
                all_words.extend(k)
                
            # 狀況 2: 它是 string (從 CSV 讀取，格式像 "['a', 'b']")
            elif isinstance(k, str):
                try:
                    # 嘗試解析字串列表
                    parsed = ast.literal_eval(k)
                    if isinstance(parsed, list):
                        all_words.extend(parsed)
                    else:
                        all_words.append(k) # 解析出來不是 list，就當單字
                except:
                    # 解析失敗，就直接當作一個單字
                    all_words.append(k)
    else:
        st.error("資料中找不到 'keywords' 欄位，請檢查爬蟲資料")
        
    if all_words:
        text = " ".join(all_words)
        
        # 設定字型檔名
        font_path = "NotoSansTC-VariableFont_wght.ttf" 
        
        import os
        if not os.path.exists(font_path):
            st.warning("⚠️ 警告：找不到中文字型檔，文字雲可能顯示為方塊。請上傳 .otf/.ttf 檔案。")
            use_font = None # 使用預設
        else:
            use_font = font_path

        # 建立文字雲物件，並指定 font_path
        wc = WordCloud(
            font_path=use_font,
            width=1200, 
            height=800, 
            background_color="black",

            max_words=200,
            colormap='viridis',
            prefer_horizontal=0.9,
            relative_scaling=0.5,

            margin=10,
        ).generate(text)

        # 畫圖
        fig, ax = plt.subplots()
        ax.imshow(wc, interpolation='bilinear')
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.info("無關鍵詞資料")

with tab3:
    st.subheader("記者產量 Top 20")
    reporter_counts = filtered_df['reporter'].value_counts().head(20).reset_index()
    reporter_counts.columns = ['記者', '文章數']
    reporter_counts = reporter_counts[reporter_counts['記者'] != 'Unknown']
    
    fig_bar = px.bar(reporter_counts, x='文章數', y='記者', orientation='h', color='文章數')
    fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}) # 讓長條圖由大排到小
    st.plotly_chart(fig_bar, use_container_width=True)

with tab4:
    # 如果使用者有選記者，才顯示詳細分析
    if selected_reporters:
        st.subheader(f"📊 記者戰力分析：{'、'.join(selected_reporters)}")
        
        if not filtered_df.empty:
            sub_t1, sub_t2 = st.tabs(["📊 領域分布", "📈 發文趨勢"])
            
            with sub_t1:
                reporter_stats = filtered_df.groupby(['reporter', 'category']).size().reset_index(name='count')
                fig_cat = px.bar(
                    reporter_stats, x="reporter", y="count", color="category",
                    title="發稿領域分布", text="count",
                    labels={"reporter": "記者", "count": "篇數", "category": "類別"}
                )
                st.plotly_chart(fig_cat, use_container_width=True)

            with sub_t2:
                daily_stats = filtered_df.groupby([filtered_df['date_obj'].dt.date, 'reporter']).size().reset_index(name='count')
                daily_stats.columns = ['date', 'reporter', 'count']
                fig_trend = px.line(
                    daily_stats, x='date', y='count', color='reporter', markers=True,
                    title="每日發文數量走勢",
                    labels={"date": "日期", "count": "篇數", "reporter": "記者"}
                )
                st.plotly_chart(fig_trend, use_container_width=True)
            
            st.markdown("---")
        else:
            st.warning("⚠️ 該記者在此篩選條件下無發文紀錄。")

    st.subheader(f"📝 詳細文章列表 (共 {len(filtered_df)} 筆)")
    
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