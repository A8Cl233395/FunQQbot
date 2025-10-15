from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re

# AI真的太好用了你们知道吗
class BingSpider:
    """Bing搜索引擎爬虫"""
    
    def __init__(self):
        self.results = []
        self.driver = None

    def _create_driver(self):
        """创建并配置浏览器驱动"""
        service = Service(executable_path="./assets/geckodriver.exe")
        options = Options()
        options.add_argument("--headless")
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        return webdriver.Firefox(service=service, options=options)

    def _search_keyword(self, keyword):
        """在Bing首页执行搜索"""
        if not self.driver:
            self.driver = self._create_driver()
            
        self.driver.get("https://cn.bing.com/")
        time.sleep(1)  # 强制等待页面加载
        
        # 等待搜索框加载并输入关键词
        search_box = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, 'sb_form_q'))
        )
        search_box.clear()
        search_box.send_keys(keyword)
        search_box.submit()
        
        # 等待搜索结果加载
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'li.b_algo'))
        )
        time.sleep(1)  # 强制等待JavaScript加载完成

    def _parse_current_page(self, keyword):
        """解析当前页面的搜索结果"""
        page_results = []
        items = self.driver.find_elements(By.CSS_SELECTOR, 'li.b_algo')
        
        for item in items:
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, 'h2 a')
                title = title_elem.text.strip()
                url = title_elem.get_attribute('href')
                
                if title and url:
                    page_results.append({
                        'title': title,
                        'url': url,
                        'keyword': keyword
                    })
            except NoSuchElementException:
                continue
                
        return page_results

    def _click_next_page(self):
        """点击下一页按钮，成功返回True，失败返回False"""
        try:
            next_btn = self.driver.find_element(By.CSS_SELECTOR, 'a.sb_pagN')
            if next_btn.is_enabled():
                next_btn.click()
                # 等待新页面加载
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'li.b_algo'))
                )
                time.sleep(1)  # 强制等待JavaScript加载完成
                return True
        except (NoSuchElementException, TimeoutException):
            pass
        return False

    def search(self, keyword, pages=1, limit=10):
        """执行搜索并获取结果"""
        self.results = []
        
        try:
            self._search_keyword(keyword)
            
            # 持续获取结果直到满足数量要求
            while len(self.results) < limit:
                current_results = self._parse_current_page(keyword)
                self.results.extend(current_results)
                
                # 如果已经达到或超过limit，或者无法翻页，则停止
                if len(self.results) >= limit or not self._click_next_page():
                    break
            
            # 截取所需数量
            self.results = self.results[:limit]
            
        except Exception as e:
            print(f"搜索过程中出现错误: {e}")
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
                
        return self.results

    def formatted(self):
        """格式化输出结果"""
        if not self.results:
            return "搜索暂时不可用"
        
        formatted = ""
        for i, result in enumerate(self.results, 1):
            formatted += f"{i}. 标题: {result['title']}\n"
        
        return formatted.rstrip()

    def get_page_content_with_id(self, result_id):
        """根据结果ID获取网页内容"""
        if 1 <= result_id <= len(self.results):
            url = self.results[result_id - 1]['url']
            return get_page_text(url)  # 使用原有的独立函数
        return None


# 以下是原有的独立函数，保持不变
def _create_driver(executable_path="./assets/geckodriver.exe") -> webdriver.Firefox:
    """
    创建和配置Firefox WebDriver实例
    """
    service = Service(executable_path=executable_path)
    options = Options()
    options.add_argument("--headless")
    return webdriver.Firefox(service=service, options=options)

def get_page_text(url: str, timeout: int = 10) -> str:
    """
    获取指定URL页面的所有可见文本
    """
    driver = None
    try:
        driver = _create_driver()
        driver.set_page_load_timeout(timeout)
        
        try:
            driver.get(url)
            time.sleep(1)  # 强制等待JavaScript加载完成
        except TimeoutException:
            driver.execute_script("window.stop();")
            time.sleep(1)  # 即使超时也等待1秒
            
        try:
            body_text = driver.find_element(By.TAG_NAME, 'body').text
        except NoSuchElementException:
            body_text = ""
            
        return re.sub(r'\n{2,}', '\n', body_text)
        
    except Exception as e:
        print(f"获取页面文本时发生错误: {e}")
        return ""
    finally:
        if driver:
            driver.quit()

def get_page_html(url: str, timeout: int = 10) -> str:
    """
    获取指定URL页面的完整HTML源代码
    """
    driver = None
    try:
        driver = _create_driver()
        driver.set_page_load_timeout(timeout)
        
        try:
            driver.get(url)
            time.sleep(1)  # 强制等待JavaScript加载完成
        except TimeoutException:
            driver.execute_script("window.stop();")
            time.sleep(1)  # 即使超时也等待1秒
            
        return driver.page_source
        
    except Exception as e:
        print(f"获取页面HTML时发生错误: {e}")
        return ""
    finally:
        if driver:
            driver.quit()