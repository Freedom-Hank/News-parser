import pandas as pd
import re
import json
import os
import jieba
import jieba.analyse

INPUT_FILE = "ettoday_raw_data.csv"
OUTPUT_JSON = "cleaned_news.json"

# --- 關鍵修正：定義「垃圾詞」黑名單 ---
# 這些詞雖然出現頻率高，但對分析沒幫助，我們要把它們過濾掉
STOP_WORDS = {
    "記者", "報導", "翻攝", "圖文", "採訪", "綜合", "中心", "編輯", 
    "來源", "畫面", "曝光", "指出", "表示", "認為", "今日", "昨日",
    "台灣", "台北", "ETtoday", "新聞雲", "可以", "我們", "應該"
}

def extract_keywords_from_text(text):
    if not text or pd.isna(text):
        return []
    
    # 擴大候選範圍到 20 個，因為我們會過濾掉很多東西
    raw_keywords = jieba.analyse.extract_tags(text, topK=20)
    
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
            if len(name) > 5 or any(x in name for x in ["中心", "報導", "綜合"]): 
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