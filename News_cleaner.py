import pandas as pd
import re
import json
import os
import jieba
import jieba.analyse

INPUT_FILE = "ettoday_raw_data.csv"
OUTPUT_JSON = "cleaned_news.json"

#定義「垃圾詞」黑名單 ---
# 這些詞雖然出現頻率高，但對分析沒幫助，要把它們過濾掉
# 1. 關鍵詞黑名單 (過濾掉沒意義的詞)
STOP_WORDS = {
    "記者", "報導", "翻攝", "圖文", "採訪", "綜合", "中心", "編輯", 
    "來源", "畫面", "曝光", "指出", "表示", "認為", "今日", "昨日",
    "台灣", "台北", "ETtoday", "新聞雲", "可以", "我們", "應該","一起",
    "這些", "那些", "非常", "非常", "很多", "看到", "知道", "時間",
    "地方", "事情", "問題", "原因", "方式", "方法", "情況", "情形",
    "活動", "公司", "政府", "民眾", "學生", "家人", "朋友", "生活", "工作",
    "社會", "文化", "經濟", "政治", "國際", "地區", "地點", "地球","世界",
    "新聞", "報導", "消息", "資訊", "資料", "內容", "標題", "文章","快訊",
    "影片", "圖片", "照片", "網友", "留言", "分享", "關注", "熱門",
}

# 2. 記者黑名單 (新增：提供、翻攝、取自...等圖片來源詞)
REPORTER_BLACKLIST = {
    # 媒體/單位名
    "7Car", "小七車觀點", "中央社", "外電", "報導", "整理", 
    "新聞雲", "中心", "編輯", "網搜", "社群", "小組",
    
    # 圖片/來源用語
    "提供", "翻攝", "示意圖", "截取", "取自", "畫面", "粉專", 
    "臉書", "IG", "Youtube", "民眾", "網友", "Facebook",

    # 新增：職稱與多餘資訊
    "攝影", "剪輯", "製作", "撰文", "專欄", "記者攝影", "記者剪輯",
    "記者撰文", "記者專欄","記者報導","記者整理","記者中心","記者網搜",
    "記者社群","記者小組"
}


def extract_keywords_from_text(text):
    if not text or pd.isna(text):
        return []
    
    raw_keywords = jieba.analyse.extract_tags(text, topK=50)
    
    filtered_keywords = []
    for w in raw_keywords:
        # --- 過濾邏輯 ---
        # 1. 必須不在黑名單
        # 2. 長度 > 1 (過濾單字)
        # 3. 不能是純數字 (新增功能，過濾 "20", "10")
        if w not in STOP_WORDS and len(w) > 1 and not w.isdigit():
            filtered_keywords.append(w)
    
    return filtered_keywords[:5] # 最後只取前 5 個

def extract_reporter(content):
    if pd.isna(content): return "Unknown"
    patterns = [
        r"記者(.*?)[／|/]", 
        r"文[／|/](.*?)[\s|，|。]",
        r"圖、文[／|/](.*?)\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            name = match.group(1).strip()
            # 排除明顯錯誤的結果
            
            # 1. 符號檢查：名字裡不該有標點符號
            if any(char in name for char in ["(", ")", "。", "、", "，", "！", "?", "【", "】", "／", "/", "；", ";", ":", "："]):
                continue
            
            # 2. 長度檢查：太短或太長都不像人名
            # 中文名通常 2-4 字，英文名(如 Kolas) 可能長一點，但不會太長
            if len(name) < 2 or len(name) > 10:
                continue

            # 3. 黑名單檢查 ：過濾掉常見的非人名詞
            if any(blk in name for blk in REPORTER_BLACKLIST):
                continue

            # 4. 雙重確認：有些奇怪的 "圖／" 會抓到非人名
            # 如果名字裡面有 "圖"，通常是抓錯了 (例如 "圖／記者...")
            if "圖" in name:
                continue

            return name
    return "Unknown"

def clean_data():
    print(f"🧹 開始讀取 raw data: {INPUT_FILE}")
    if not os.path.exists(INPUT_FILE):
        print("❌ 找不到 raw data，請先執行爬蟲！")
        return

    df = pd.read_csv(INPUT_FILE)
    df.drop_duplicates(subset=['link'], inplace=True)
    df.dropna(subset=['title', 'content'], inplace=True)
    
    print("🔍 正在提取資料 (記者 & 關鍵詞)...")
    
    df['reporter'] = df['content'].apply(extract_reporter)

    print("🔍 正在從「標題」提取關鍵詞...")
    
    df['keywords'] = df['title'].apply(extract_keywords_from_text)
    
    final_df = df[['title', 'content', 'date_str', 'category', 'reporter', 'link', 'keywords']]
    
    json_data = final_df.to_dict(orient='records')
    
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
        
    print(f"✨ 清洗完成！檔案已存為: {OUTPUT_JSON}")
    # 預覽一下，確認「記者」這種詞有沒有消失
    print("👀 關鍵詞範例:", final_df.iloc[0]['keywords'])

if __name__ == "__main__":
    clean_data()