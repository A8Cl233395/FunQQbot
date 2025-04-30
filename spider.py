from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
import time
from bs4 import BeautifulSoup
# 基于 https://github.com/tang51678/seCrawler 修改
class WebSpider:
    def __init__(self, keywords=[], se='bing', pages=1):
        self.search_engine = se.lower()
        self.pages = int(pages) if pages else None  # 支持动态模式
        self.keywords = keywords
        self.selector = self.get_selector(self.search_engine)
        self.retry_count = 0
        self.results = []

    def get_selector(self, search_engine):
        """根据搜索引擎选择器"""
        selectors = {
            "bing": {
                "url": "li.b_algo h2 a",
                "title": "li.b_algo h2"
            },
            "baidu": {
                "url": "div.result.c-container h3.t a",
                "title": "div.result.c-container h3.t"
            },
            "google": {
                "url": "div.tF2Cxc h3 a",
                "title": "div.tF2Cxc h3"
            }
        }
        return selectors.get(search_engine, {})

    def get_search_url(self, keyword, page):
        """根据搜索引擎和页码生成搜索URL"""
        if self.search_engine == "bing":
            return f"https://cn.bing.com/search?q={keyword.replace(' ', '+')}&first={page * 10}"
        elif self.search_engine == "baidu":
            return f"https://www.baidu.com/s?wd={keyword.replace(' ', '+')}&pn={page * 10}"
        elif self.search_engine == "google":
            return f"https://www.google.com/search?q={keyword.replace(' ', '+')}&start={page * 10}"
        else:
            raise ValueError(f"不支持的搜索引擎: {self.search_engine}")

    def fetch_page(self, url):
        """获取页面内容"""
        try:
            response = get_page_source(url)
            with open("page.html", "w", encoding="utf-8") as f:
                f.write(response)
            return response
        except:
            return None

    def parse_page(self, html, keyword, page):
        """解析页面内容，提取 URL 和标题"""
        soup = BeautifulSoup(html, 'html.parser')
        self.results = []
        url_elements = soup.select(self.selector['url'])
        title_elements = soup.select(self.selector['title'])
        for url_element, title_element in zip(url_elements, title_elements):
            url = url_element.get('href')
            title = title_element.get_text(strip=True)
            if url and title:
                self.results.append({
                    'url': url,
                    'title': title,
                    'keyword': keyword,
                    'page': page
                })
        return self.results

    def start_crawling(self):
        """开始爬取，并将结果保存到 JSON 文件"""
        self.results = []
        for keyword in self.keywords:
            if self.pages:
                for page in range(self.pages):
                    url = self.get_search_url(keyword, page)
                    html = self.fetch_page(url)
                    if html:
                        self.results.extend(self.parse_page(html, keyword, page + 1))
                    time.sleep(1)
            else:
                page = 0
                while True:
                    url = self.get_search_url(keyword, page)
                    html = self.fetch_page(url)
                    if not html:
                        break
                    page_results = self.parse_page(html, keyword, page + 1)
                    if not page_results:
                        break
                    self.results.extend(page_results)
                    page += 1
                    time.sleep(1)
        if self.results == []:
            if self.retry_count < 1:
                self.retry_count += 1
                self.start_crawling()
        self.results = self.results[:5]
        return self.results

    def formatted(self):
        formatted = ""
        if len(self.results) == 0:
            return "搜索暂时不可用"
        id = 1
        for i in self.results:
            formatted += f"{id}.标题: {i['title']}\n"
            id += 1
        return formatted[:-1]

    def get_page_with_id(self, id):
        url = self.results[id - 1]['url']
        return get_page_text(url)

def get_page_text(url):
    # 使用 GeckoDriverManager 自动管理 GeckoDriver 的安装和路径
    service = Service()
    options = Options()
    
    # 禁用自动化控制的特征
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.add_argument("--headless")
    # 创建 Firefox WebDriver 实例
    driver = webdriver.Firefox(service=service, options=options)

    try:
        driver.get(url)
        time.sleep(5)
        text = driver.find_element(By.TAG_NAME, 'body').text
    finally:
        text = driver.find_element(By.TAG_NAME, 'body').text
        for i in range(3):
            text = text.replace('\n\n', '\n')
        driver.quit()
        return text

def get_page_source(url):
    # 使用 GeckoDriverManager 自动管理 GeckoDriver 的安装和路径
    service = Service()
    options = Options()
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.add_argument("--headless")
    # 创建 Firefox WebDriver 实例
    driver = webdriver.Firefox(service=service, options=options)

    try:
        driver.get(url)
        time.sleep(5)
        # 等待页面加载完成
    finally:
        page_source = driver.page_source
        driver.quit()
        return page_source