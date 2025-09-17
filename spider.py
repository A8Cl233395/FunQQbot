from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
import time
from bs4 import BeautifulSoup
import re
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 感谢 https://github.com/tang51678/seCrawler
class BingSpider:
    """
    Bing搜索引擎爬虫类
    
    属性:
        results: 存储爬取结果的列表
        retry_count: 重试次数计数器
    """
    
    def __init__(self):
        """
        初始化BingSpider实例
        """
        self.results = []  # 存储爬取结果
        self.retry_count = 0  # 重试计数器

    def get_search_url(self, keyword, page=0):
        """
        根据关键词和页码生成Bing搜索URL
        
        参数:
            keyword: 搜索关键词
            page: 页码(从0开始)
            
        返回:
            完整的Bing搜索URL
        """
        return f"https://cn.bing.com/search?q={keyword.replace(' ', '+')}&first={page * 10}"

    def fetch_page(self, url):
        """
        获取指定URL的页面内容
        
        参数:
            url: 要获取的网页URL
            
        返回:
            页面HTML内容，获取失败时返回None
        """
        try:
            response = get_page_html(url)
            return response
        except:
            return None

    def parse_page(self, html, keyword, page):
        """
        解析页面HTML内容，提取URL和标题
        
        参数:
            html: 页面HTML内容
            keyword: 搜索关键词(用于结果记录)
            page: 当前页码(用于结果记录)
            
        返回:
            提取的结果列表
        """
        soup = BeautifulSoup(html, 'html.parser')
        page_results = []
        
        # Bing搜索结果的选择器
        url_elements = soup.select("li.b_algo h2 a")
        title_elements = soup.select("li.b_algo h2")
        
        # 配对URL和标题元素，提取文本信息
        for url_element, title_element in zip(url_elements, title_elements):
            url = url_element.get('href')
            title = title_element.get_text(strip=True)
            
            if url and title:
                page_results.append({
                    'url': url,
                    'title': title,
                    'keyword': keyword,
                    'page': page
                })
        return page_results

    def search(self, keyword, pages=1, limit=10):
        """
        执行Bing搜索
        
        参数:
            keyword: 搜索关键词
            pages: 爬取页数，默认为1
            limit: 结果数量限制，默认为10
            
        返回:
            爬取的结果列表
        """
        self.results = []  # 重置结果列表
        
        for page in range(pages):
            url = self.get_search_url(keyword, page)
            html = self.fetch_page(url)
            
            if html:
                page_results = self.parse_page(html, keyword, page + 1)
                self.results.extend(page_results)
                time.sleep(1)  # 延迟1秒，避免请求过于频繁
        
        # 如果未获取到结果且重试次数未超限，则重试一次
        if not self.results and self.retry_count < 1:
            self.retry_count += 1
            return self.search(keyword, pages, limit)
        self.retry_count = 0  # 重置重试计数器
        
        # 限制结果数量并返回
        self.results = self.results[:limit]
        return self.results

    def formatted(self):
        """
        将结果格式化为易读的字符串
        
        返回:
            格式化后的结果字符串
        """
        if not self.results:
            return "搜索暂时不可用"
        
        formatted = ""
        for i, result in enumerate(self.results, 1):
            formatted += f"{i}. 标题: {result['title']}\n"
        
        return formatted.rstrip()  # 去除末尾的换行符

    def get_page_content(self, result_id):
        """
        根据结果ID获取对应网页的文本内容
        
        参数:
            result_id: 结果编号(从1开始)
            
        返回:
            对应网页的文本内容
        """
        if 1 <= result_id <= len(self.results):
            url = self.results[result_id - 1]['url']
            return get_page_text(url)
        return None

def _create_driver(executable_path="./assets/geckodriver.exe") -> webdriver.Firefox:
    """
    一个辅助函数，用于创建和配置Firefox WebDriver实例。
    """
    service = Service(executable_path=executable_path)
    options = Options()
    options.add_argument("--headless")
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    
    return webdriver.Firefox(service=service, options=options)

def get_page_text(url: str, timeout: int = 10) -> str:
    """
    获取并返回指定URL页面的所有可见文本。
    如果页面加载超时，则返回已加载部分的文本内容。

    Args:
        url (str): 目标网页的URL。
        timeout (int): 等待页面加载的最长时间（秒）。

    Returns:
        str: 页面的文本内容（可能是部分的）。
    """
    driver = None
    try:
        driver = _create_driver()
        # 设置页面加载的超时时间
        driver.set_page_load_timeout(timeout)
        
        try:
            # 尝试加载页面，如果超过`timeout`秒，会抛出TimeoutException
            driver.get(url)
        except TimeoutException:
            # 当超时发生时，打印一条警告，然后继续执行
            print(f"警告: 页面 {url} 加载超时。将尝试返回已加载的部分内容。")
            # (推荐) 发送JS命令停止浏览器进一步加载
            driver.execute_script("window.stop();")
            
        # 无论是否超时，都尝试提取内容
        try:
            body_text = driver.find_element(By.TAG_NAME, 'body').text
        except NoSuchElementException:
            # 如果连body标签都还没加载出来，就返回空字符串
            body_text = ""
            
        return re.sub(r'\n{2,}', '\n', body_text)
        
    except Exception as e:
        print(f"获取页面文本时发生未知错误: {e}")
        return ""
    finally:
        if driver:
            driver.quit()

def get_page_html(url: str, timeout: int = 10) -> str:
    """
    获取并返回指定URL页面的完整HTML源代码。
    如果页面加载超时，则返回已加载部分的HTML。

    Args:
        url (str): 目标网页的URL。
        timeout (int): 等待页面加载的最长时间（秒）。

    Returns:
        str: 页面的HTML源代码（可能是部分的）。
    """
    driver = None
    try:
        driver = _create_driver()
        driver.set_page_load_timeout(timeout)
        
        try:
            driver.get(url)
        except TimeoutException:
            print(f"警告: 页面 {url} 加载超时。将尝试返回已加载的部分内容。")
            driver.execute_script("window.stop();")
            
        # 无论是否超时，都直接返回当前浏览器的page_source
        return driver.page_source
        
    except Exception as e:
        print(f"获取页面HTML时发生未知错误: {e}")
        return ""
    finally:
        if driver:
            driver.quit()