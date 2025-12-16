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
        key_dict = dict(st.secrets["firebase"])
        
        # 🔧 補救措施：處理 private_key 的換行符號
        # 有時候 TOML 會把 \n 當成純文字，這裡把它變回真正的換行
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
   
   #--------------------------------------------------- 
    # 2. 類別篩選 (多選)
    st.write("---") # 分隔線
    st.write("🏷️ 新聞類別篩選")
    
    # 取得所有類別
    all_categories = sorted(df['category'].unique())
    
    # === 關鍵：使用 session_state 來記住現在選了什麼 ===
    # 初始化：如果還沒存過，預設全選
    if "selected_cats" not in st.session_state:
        st.session_state["selected_cats"] = all_categories

    # 定義按鈕的回呼函式 (Callback)
    def select_all():
        st.session_state["selected_cats"] = all_categories

    def deselect_all():
        st.session_state["selected_cats"] = [] # 清空列表

    # 建立兩顆按鈕並排
    col1, col2 = st.columns(2)
    with col1:
        st.button("✅ 全選", on_click=select_all, use_container_width=True)
    with col2:
        st.button("❌ 清空", on_click=deselect_all, use_container_width=True)

    # 顯示選單 (重點：key 要設對，才會跟上面的按鈕連動)
    selected_cats = st.multiselect(
        "請選擇類別：",
        options=all_categories,
        key="selected_cats"
    )
    
    #--------------------------------------------------- 
    # 3. 記者篩選
    st.write("---")
    st.write("🎤 記者篩選")
    
    # 取得所有記者名單 (排除沒名字的 Unknown 或是空值，看你想不想留)
    all_reporters = sorted(df['reporter'].astype(str).unique())
    
    # 建立選單 (預設為空)
    selected_reporters = st.multiselect(
        "搜尋或選擇記者 (留空即顯示全部)：",
        options=all_reporters,
        default=[] # 預設空陣列，代表不篩選
    )
    
    # --- 修正後的雙重過濾邏輯 ---
    if len(date_range) == 2:
        start_date, end_date = date_range
        
        # 基礎條件：日期 + 類別
        condition = (
            (df['category'].isin(selected_cats)) & 
            (df['date_obj'].dt.date >= start_date) & 
            (df['date_obj'].dt.date <= end_date)
        )
        
        # 疊加條件：如果有選記者，就多加這一條
        if selected_reporters:
            condition = condition & (df['reporter'].isin(selected_reporters))
            
        # 最終過濾
        filter_mask = condition
        filtered_df = df[filter_mask] # 算出最終資料表
        current_count = filtered_df.shape[0]
        
    else:
        current_count = 0
        filtered_df = pd.DataFrame()

    # 計算總資料筆數
    total_count = df.shape[0]

    #---------------------------------------------------
    # 4. 顯示美化的指標卡
    st.sidebar.markdown("---") # 分隔線
    st.sidebar.metric(
        label="📊 資料筆數狀態",
        value=f"{current_count} 筆",
        delta=f"總資料庫: {total_count} 筆",
        delta_color="off"
    )
    st.sidebar.caption(f"資料來源：ETtoday")

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
    valid_reporters = filtered_df[filtered_df['reporter'] != 'Unknown']

    if not valid_reporters.empty:
        top_reporter = valid_reporters['reporter'].mode()[0]
    else:
        top_reporter = "N/A"
    st.metric("🔥 最活躍記者", top_reporter)
with col3:
    st.metric("涵蓋類別數", f"{filtered_df['category'].nunique()} 類")
with col4:
    # 算出出現最多的關鍵詞
    # (這裡簡化處理，實際建議拉出來算)
    st.metric("⭐ 關鍵詞焦點", "請看下方分析")

st.markdown("---")

# === 主內容分頁 ===
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 趨勢總覽", "☁️ 關鍵詞雲", "🏆 記者戰力榜", "📊 記者戰力分析", "🗃️ 詳細資料庫"])

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
    for k in filtered_df['keywords']:
        if isinstance(k, list): all_words.extend(k)
        
    if all_words:
        text = " ".join(all_words)
        
        # 設定字型檔名
        font_path = "NotoSansTC-VariableFont_wght.ttf" 
        
        # 防呆機制：如果忘記上傳字型，改用預設 (雖然會變方塊，但至少不會報錯當機)
        import os
        if not os.path.exists(font_path):
            st.warning("⚠️ 警告：找不到中文字型檔，文字雲可能顯示為方塊。請上傳 .otf/.ttf 檔案。")
            use_font = None # 使用預設
        else:
            use_font = font_path

        # 建立文字雲物件，並指定 font_path
        wc = WordCloud(
            font_path=use_font,
            width=800, 
            height=400, 
            background_color="white"
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
    if selected_reporters:
        st.markdown("---")
        st.subheader(f"📊 記者發稿領域分析 ({len(selected_reporters)} 位)")
        
        # 1. 準備畫圖資料：計算每個類別有幾篇
        # GroupBy: 記者 + 類別 -> 計算篇數
        reporter_stats = filtered_df.groupby(['reporter', 'category']).size().reset_index(name='count')
        
        # 2. 使用 Plotly 畫堆疊長條圖
        import plotly.express as px
        
        fig_reporter = px.bar(
            reporter_stats,
            x="reporter",       # X軸：記者名字
            y="count",          # Y軸：文章數量
            color="category",   # 顏色：新聞類別 (這樣一眼就能看出成分)
            title="記者發稿類別分布圖",
            text="count",       # 在柱狀圖上顯示數字
            labels={"reporter": "記者", "count": "文章篇數", "category": "新聞類別"}
        )
        
        st.plotly_chart(fig_reporter, use_container_width=True)
        st.markdown("### 記者發稿數據表")
        st.dataframe(reporter_stats)

    else:
        # 如果沒選記者，就不特別顯示這個圖表，或是顯示全站的類別分布
        pass

with tab5:
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