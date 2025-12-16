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
from datetime import datetime, timedelta, timezone
import os
import urllib3

# 1. 關閉 SSL 安全憑證警告 (關鍵修正)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 設定區 ---
# 1. 設定台灣時區 (UTC+8)
# 這樣無論你的程式在美國主機還是在哪裡跑，永遠都是抓台灣的「今天」
tw_timezone = timezone(timedelta(hours=8))
today_in_taiwan = datetime.now(tw_timezone)

# 2. 轉成文字格式 "2025-12-16"
START_DATE = today_in_taiwan.strftime("%Y-%m-%d")

# 3. 每次只抓當天 (因為你每 6 小時就會跑一次來更新)
DAYS_TO_CRAWL = 1 

OUTPUT_FILE = "ettoday_raw_data.csv"

print(f"🤖 自動化啟動：目標日期為 {START_DATE} (台灣時間)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.ettoday.net/",
}

def get_news_links_by_date(date_str):
    url = f"https://www.ettoday.net/news/news-list-{date_str}-0.htm"
    print(f"\n📡 [Selenium] 正在開啟瀏覽器抓取列表: {url}")
    
    target_date_slash = date_str.replace("-", "/") 
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--headless") 

    html_source = "" # 1. 先宣告這個變數

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), 
            options=chrome_options
        )
        
        driver.get(url)
        time.sleep(2)
        
        last_height = driver.execute_script("return document.body.scrollHeight")
        retry_count = 0
        MAX_RETRIES = 3
        
        while True:
            # 捲動邏輯
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            driver.execute_script("window.scrollBy(0, -300);")
            time.sleep(2)
            
            # 日期檢查
            try:
                date_elements = driver.find_elements(By.CSS_SELECTOR, ".part_list_2 .date")
                if date_elements:
                    last_date_text = date_elements[-1].text.strip()
                    current_date_on_page = last_date_text[:10]
                    if current_date_on_page != target_date_slash:
                        print(f"   🛑 偵測到前一日新聞 ({last_date_text})，停止捲動。")
                        break
            except Exception:
                pass

            # 高度檢查
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
        
        # 2.在瀏覽器還活著的時候，把原始碼存進變數
        print("   📥 正在下載網頁原始碼...")
        html_source = driver.page_source 

    except Exception as e:
        print(f"⚠️ Selenium 執行期間發生錯誤: {e}")
        return []
    
    finally:
        if 'driver' in locals():
            driver.quit()
        
    # --- 解析 HTML ---
    
    # 3. 絕對不要再呼叫 driver.page_source，直接用上面存好的 html_source
    if not html_source:
        print("❌ 未取得網頁原始碼，跳過解析。")
        return []

    soup = BeautifulSoup(html_source, "html.parser")
    
    news_list = []
    for item in soup.select(".part_list_2 > h3"):
        try:
            date_time = item.select_one(".date").text.strip()
            
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