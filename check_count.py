import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 🔥 使用 count() 查詢，叫 Firebase 算總數
collection_ref = db.collection("news")
count_query = collection_ref.count()

# 取得結果
aggregates = count_query.get()
total_count = aggregates[0][0].value

print(f"📊 目前資料庫裡的總新聞數：{total_count} 筆")