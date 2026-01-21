import os
import json
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. 智慧型連線 (本地/雲端通用) ---
# 優先讀取環境變數 (GitHub Action 用)，如果沒有就讀本地 Key (你測試用)
firebase_key_env = os.environ.get("FIREBASE_CREDENTIALS")

if not firebase_admin._apps:
    if firebase_key_env:
        print("🔐 使用環境變數金鑰連線")
        cred = credentials.Certificate(json.loads(firebase_key_env))
    elif os.path.exists("serviceAccountKey.json"):
        print("🔑 使用本地 JSON 檔案連線")
        cred = credentials.Certificate("serviceAccountKey.json")
    else:
        raise FileNotFoundError("❌ 找不到 Firebase 金鑰！無法連線。")
    
    firebase_admin.initialize_app(cred)

db = firestore.client()
CSV_FILE = "news_history.csv"

def main():
    # --- 2. 判斷起點 ---
    if os.path.exists(CSV_FILE):
        df_old = pd.read_csv(CSV_FILE)
        last_date = df_old['date_str'].max()
        print(f"📂 讀取現有 CSV，最後資料日期: {last_date}")
    else:
        df_old = pd.DataFrame()
        last_date = "2025-11-01" # 設定你的資料起始日
        print(f"📂 找不到 CSV，將抓取 {last_date} 之後的所有資料...")

    # --- 3. 抓取新資料 ---
    print(f"📡 正在向 Firebase 請求 {last_date} 之後的資料...")
    docs = db.collection("news").where("date_str", ">", last_date).stream()
    
    new_data = [doc.to_dict() for doc in docs]
    print(f"✅ 抓到 {len(new_data)} 筆新資料")

    if not new_data:
        print("😴 目前是最新的，無需更新")
        return

    # --- 4. 合併與存檔 ---
    df_new = pd.DataFrame(new_data)
    
    if not df_old.empty:
        df_final = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_final = df_new

    # 去重複 (以連結 link 為準)
    df_final = df_final.drop_duplicates(subset=['link'])
    
    # 存檔
    df_final.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    print(f"💾 已儲存至 {CSV_FILE}，目前總筆數: {len(df_final)}")

if __name__ == "__main__":
    main()