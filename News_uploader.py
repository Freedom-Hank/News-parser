import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
import json
import os
import hashlib

# --- 設定區 ---
JSON_FILE = "cleaned_news.json"
KEY_FILE = "serviceAccountKey.json" 
COLLECTION_NAME = "news"

def upload_to_firebase():
    # 1. 檢查金鑰是否存在
    if not os.path.exists(KEY_FILE):
        print(f"❌ 找不到金鑰檔案: {KEY_FILE}")
        print("請到 Firebase Console -> Project Settings -> Service accounts 下載！")
        return

    # 2. 初始化 Firebase (防止重複初始化報錯)
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
    
    # 3. 讀取清洗好的 JSON
    if not os.path.exists(JSON_FILE):
        print(f"❌ 找不到資料檔: {JSON_FILE}")
        return
        
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        news_list = json.load(f)
        
    print(f"📦 準備上傳 {len(news_list)} 筆資料到 Firestore...")
    
    # 4. 批次寫入 (Batch Write)
    # Firestore 一個 Batch 最多只能有 500 個操作，所以我們要分批切塊
    batch_size = 400 
    total_batches = (len(news_list) // batch_size) + 1
    
    for i in range(0, len(news_list), batch_size):
        batch = db.batch()
        chunk = news_list[i : i + batch_size]
        
        for news in chunk:
            # 1. 拿出這篇新聞的連結
            link = news.get('link')
            
            if link:
                # 2. 把網址轉成 MD5 編碼 (例如: 'https://...' -> 'a1b2c3d4...')
                # 因為網址太長且含特殊符號，不適合直接當 Document ID
                doc_id = hashlib.md5(link.encode('utf-8')).hexdigest()
                
                # 3. 指定 ID 寫入 (如果有重複的 ID，就會變成更新，不會新增)
                doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
                batch.set(doc_ref, news)
            
        # 提交這一個批次
        batch.commit()
        print(f"   ✅ 已寫入第 {i//batch_size + 1}/{total_batches} 批 (本批 {len(chunk)} 筆)")

    print(f"🎉 上傳完畢！請去 Firebase Console 檢查資料。")

if __name__ == "__main__":
    upload_to_firebase()