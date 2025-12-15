from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
from datetime import datetime, timedelta
import os
import urllib3

# 1. 關閉 SSL 安全憑證警告 (關鍵修正)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定區 ---
START_DATE = "2025-12-15" 
DAYS_TO_CRAWL = 1  # 先設 2 天試跑，確認 OK 後再改成 20
OUTPUT_FILE = "ettoday_raw_data.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.ettoday.net/",
}

def get_news_links_by_date(date_str):
    url = f"https://www.ettoday.net/news/news-list-{date_str}-0.htm"
    print(f"\n📡 [Selenium] 正在開啟瀏覽器抓取列表: {url}")
    
    # 格式化日期以便比對 (ETtoday 網頁顯示的是 2024/03/20，而我們輸入的是 2024-03-20)
    target_date_slash = date_str.replace("-", "/") 
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    # chrome_options.add_argument("--headless") # 建議除錯時先關掉 headless

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), 
            options=chrome_options
        )
    except Exception as e:
        print(f"❌ 瀏覽器啟動失敗: {e}")
        return []
    
    try:
        driver.get(url)
        time.sleep(2)
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        retry_count = 0
        MAX_RETRIES = 3
        
        while True:
            # 1. 執行捲動
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # --- 新增邏輯：檢查最後一則新聞的日期 ---
            try:
                # 抓取畫面上所有的日期標籤 (.date)
                date_elements = driver.find_elements(By.CSS_SELECTOR, ".part_list_2 .date")
                
                if date_elements:
                    # 抓最後一個元素的文字 (例如: "2024/03/20 12:30")
                    last_date_text = date_elements[-1].text.strip()
                    
                    # 取出日期部分 (前面 10 個字: "2024/03/20")
                    current_date_on_page = last_date_text[:10]
                    
                    # 比對：如果頁面上的最後日期 不等於 目標日期 (代表已經滑過頭，滑到前一天了)
                    if current_date_on_page != target_date_slash:
                        print(f"   🛑 偵測到前一日新聞 ({last_date_text})，停止捲動。")
                        break
            except Exception as e:
                # 偶爾抓不到元素不影響大局，繼續滑
                pass
            # -------------------------------------

            # 2. 檢查高度是否變化 (原本的重試邏輯)
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                retry_count += 1
                print(f"   ⚠️ 高度未變化，第 {retry_count}/{MAX_RETRIES} 次重試...")
                if retry_count >= MAX_RETRIES:
                    print("   🛑 已達重試上限，停止捲動。")
                    break
                else:
                    time.sleep(2)
                    continue
            else:
                retry_count = 0
                last_height = new_height
                
    except Exception as e:
        print(f"⚠️ Selenium 執行期間發生錯誤: {e}")
        return []
    finally:
        if 'driver' in locals():
            driver.quit()
        
    # --- 解析 HTML ---
    html_source = driver.page_source if 'driver' in locals() else ""
    soup = BeautifulSoup(html_source, "html.parser")
    
    news_list = []
    # 這裡也要做過濾，確保最後存進去的真的只有當天的
    for item in soup.select(".part_list_2 > h3"):
        try:
            date_time = item.select_one(".date").text.strip() # "2024/03/20 12:30"
            
            # 二次確認：只收錄當天日期
            if target_date_slash not in date_time:
                continue

            category = item.select_one("em").text.strip()
            a_tag = item.select_one("a")
            title = a_tag.text.strip()
            href = a_tag["href"]
            
            if href.startswith("http"):
                link = href
            else:
                link = "https://www.ettoday.net" + href
            
            news_list.append({
                "date_str": date_time,
                "category": category,
                "title": title,
                "link": link
            })
        except AttributeError:
            continue
    
    print(f"✅ {date_str} 最終整理出 {len(news_list)} 則新聞")
    return news_list

def get_news_content(url):
    """抓取內文 (開啟除錯模式)"""
    try:
        # print(f"DEBUG: 嘗試抓取 {url}") # 如果還是失敗，把這行註解打開看網址對不對
        
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        
        if resp.status_code != 200:
            print(f"⚠️ 請求失敗 ({resp.status_code}): {url}")
            return None
        
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, "html.parser")
        
        story_div = soup.select_one("div.story")
        if not story_div:
            story_div = soup.select_one("div.subject_article")
            
        if story_div:
            paragraphs = [p.text.strip() for p in story_div.select("p") if p.text.strip()]
            content = "\n".join(paragraphs)
            return content
        else:
            # 印出失敗原因
            print(f"⚠️ 找不到內文區塊 (div.story): {url}")
            return None 

    except Exception as e:
        print(f"❌ 發生錯誤 {url}: {e}")
        return None

# --- 主程式 ---
if __name__ == "__main__":
    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    date_list = [(start - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(DAYS_TO_CRAWL)]

    total_count = 0

    for date in date_list:
        print(f"🚀 日期: {date}")
        
        news_items = get_news_links_by_date(date)
        
        if not news_items:
            continue

        data_for_csv = []
        
        # 使用 enumerate 方便看進度
        for i, news in enumerate(news_items):
            content = get_news_content(news["link"])
            
            if content:
                news["content"] = content
                data_for_csv.append(news)
                
                # 每 50 篇印一次進度，讓你知道它還活著
                if i % 50 == 0:
                    print(f"  - ({i}/{len(news_items)}) 成功抓取: {news['title'][:15]}...")
            else:
                # 抓不到內文就跳過，不存
                pass
            
            # 隨機休息 0.5 ~ 1 秒
            time.sleep(random.uniform(0.5, 1.0))

        # 該日期跑完，存入 CSV
        if data_for_csv:
            df = pd.DataFrame(data_for_csv)
            file_exists = os.path.isfile(OUTPUT_FILE)
            # 追加模式 'a'
            df.to_csv(OUTPUT_FILE, mode='a', header=not file_exists, index=False, encoding='utf-8-sig')
            print(f"💾 {date} 存檔完成！新增 {len(df)} 筆資料")
            total_count += len(df)
        
    print(f"\n🎉 全部完成！總共累積 {total_count} 筆資料在 {OUTPUT_FILE}")