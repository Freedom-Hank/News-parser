# 📰 ETtoday 新聞輿情分析系統 (News Sentiment & Analysis Dashboard)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-red)](https://streamlit.io/)
[![Firebase](https://img.shields.io/badge/Database-Firestore-orange)](https://firebase.google.com/)
![GitHub Actions](https://img.shields.io/badge/Automation-Daily%20Scrape-green)

這是一個全自動化的新聞輿情分析系統，專門針對 **ETtoday 新聞雲** 進行資料蒐集與分析。
透過 GitHub Actions 實現每日自動爬蟲，並結合 Firebase Firestore 與 Streamlit 打造即時互動儀表板，提供記者戰力分析、熱門關鍵詞雲與發文趨勢觀察。

## 🚀 功能特色

* **自動化爬蟲 (Web Crawler)**：
    * 使用 Selenium 模擬真人瀏覽行為，具備自動捲動 (Infinite Scroll) 與防偵測機制。
    * 支援 Headless 模式，可於伺服器端背景執行。
    * 自動偵測日期邊界，精準抓取特定日期區間的新聞。
* **資料清洗與 NLP (Data Cleaning)**：
    * 自動過濾非記者署名（如「翻攝」、「網友提供」）。
    * 整合 Jieba 斷詞系統，提取新聞標題中的熱門關鍵詞。
    * 使用 MD5 雜湊網址作為唯一 ID，防止資料重複儲存。
* **雲端資料庫 (Cloud Database)**：
    * 整合 Google Firebase (Firestore)，支援高併發讀寫與即時同步。
* **互動式儀表板 (Dashboard)**：
    * **關鍵詞文字雲**：視覺化當日最熱門議題。
    * **記者戰力分析**：統計記者發稿量排名。
    * **多維度篩選**：支援依日期、類別進行資料過濾。
* **CI/CD 自動化**：
    * 整合 GitHub Actions，每日定時自動執行爬蟲與資料更新。
    * 自動執行「爬取 -> 清洗 -> 去重 -> 上傳」流程，無需人工介入。
    * 實作 Secrets 管理，確保雲端金鑰安全。
* **成本效益最佳化架構 (Cost-Efficient Architecture)**：
    * 冷熱資料分離：採用混合讀取模式 (Hybrid Loading)，將歷史資料封存為 CSV (Cold Data)，僅即時資料讀取 Firebase (Hot Data)。
    * 流量節省：大幅降低 Firestore 讀取頻率，解決 NoSQL 資料庫隨著資料量增長而產生的讀取成本問題。
    * 自動歸檔機制：每週自動將 Firebase 舊資料備份回 GitHub Repo，實現永久免費的歷史資料儲存。

## 🛠️ 系統架構

```mermaid
graph TD
    subgraph "Daily Routine (Hot Data)"
    A[GitHub Actions<br>每6小時] -->|"執行爬蟲"| B(News_crawler / Pipeline)
    B -->|"寫入新資料"| C[(Firebase Firestore)]
    end

    subgraph "Weekly Archive (Cold Data)"
    C -->|"讀取舊資料"| D(update_csv.py)
    D -->|"產生/更新"| E(news_history.csv)
    D -->|"Git Commit & Push"| F[GitHub Repo]
    end

    subgraph "Dashboard (Hybrid Loading)"
    G[User] -->|"訪問"| H[Streamlit App]
    H <-->|"讀取歷史"| E
    H <-->|"讀取即時"| C
    end
```
## 📂 檔案結構說明

| 檔名 | 類別 | 說明 |
| :--- | :--- | :--- |
| `app.py` | 應用程式 | Streamlit 戰情室主程式，負責前端介面與資料視覺化 |
|`update_csv.py`|	自動化工具|資料歸檔核心，負責將 Firebase 資料增量備份至 CSV 並推送到 GitHub|
|`news_history.csv`|資料庫|冷資料儲存區，存放歷史新聞數據 (由 Action 自動更新)|
| `News_crawler.py` | 資料管線 | 爬蟲核心，負責從新聞網站抓取原始 HTML 資料 |
| `news_cleaner.py` | 資料管線 | 負責資料清洗、欄位標準化 (ETL Process) |
| `news_uploader.py` | 資料管線 | 負責產生去重 ID 並將資料上傳至 Firestore |
| `check_count.py` | 維運工具 | **成本優化工具**，利用 Aggregation Query 快速查詢資料庫總筆數 (不消耗大量讀取額度) |
| `.github/workflows/` | 自動化 | GitHub Actions CI/CD 自動化腳本設定檔 |
| `requirements.txt` | 設定檔 | 專案相依套件列表 |

## 💻 安裝與執行 (Local Development)
1. 複製專案
```
git clone [https://github.com/你的帳號/你的專案名稱.git](https://github.com/你的帳號/你的專案名稱.git)
cd 你的專案名稱
```
2. 安裝依賴套件
```
pip install -r requirements.txt
```
3.  設定 Firebase 金鑰
本專案需要 Firebase Admin SDK 的金鑰 (serviceAccountKey.json)。
請將金鑰檔案放入專案根目錄。
注意：請勿將此金鑰上傳至 GitHub (已加入 .gitignore)
4.  執行流程
```
1. 抓取新聞 (預設抓取 1 天)
python News_crawler.py

2. 清洗資料
python news_cleaner.py

3. 上傳至 Firebase
python news_uploader.py
```
5.  啟動儀表板
```
streamlit run app.py
```

## ☁️ 部署 (Deployment)

本專案採用 **前後端分離** 的部署策略，確保資料流與介面運作的獨立性與穩定性。

### ⚙️ 後端自動化 (GitHub Actions)
本專案設計了 **雙軌並行 (Dual-Track)** 的自動化策略，由 GitHub Actions 全權託管：

1.  **🔥 資料蒐集 (Data Collection)**
    * **設定檔**：`news_scraper.yml`
    * **頻率**：每 6 小時執行一次
    * **任務**：執行爬蟲腳本，並將最新資料即時寫入 **Firebase (熱區)**。

2.  **❄️ 資料歸檔 (Data Archiving)**
    * **設定檔**：`weekly_archive.yml`
    * **頻率**：每週一 08:00 (UTC+8) 執行
    * **任務**：將 Firebase 中的資料增量備份至 `news_history.csv` **(冷區)** 並 Commit 回 GitHub，實現 **長期儲存零成本**。

> 🔑 **Secrets 設定**：
> 請至 GitHub Repo 的 `Settings` > `Secrets and variables` > `Actions`，新增 Secret：
> * Key: `FIREBASE_CREDENTIALS`
> * Value: (貼上 `serviceAccountKey.json` 的完整內容)

---

### 🖥️ 前端網頁 (Streamlit Cloud)
本專案支援一鍵部署至 **Streamlit Community Cloud**，且具備自動同步 GitHub 更新的功能。

> 🔑 **Secrets 設定**：
> 請至 Streamlit App 的 `Settings` > `Secrets`，貼上以下格式的 TOML 設定：
>
> ```toml
> [firebase]
> type = "service_account"
> project_id = "..."
> # ... (其他欄位)
> ```
