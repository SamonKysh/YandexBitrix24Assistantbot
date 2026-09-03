import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Папка для сохранения собранных документов
DATA_DIR = "data/docs"
os.makedirs(DATA_DIR, exist_ok=True)

# Список страниц для парсинга (для примера возьмем 3 ключевых метода CRM)
# В реальном проекте здесь можно собрать все ссылки с главной страницы
URLS_TO_PARSE = [
    "https://apidocs.bitrix24.ru/api-reference/crm/deals/crm-deal-add.html",
    "https://apidocs.bitrix24.ru/api-reference/crm/leads/crm-lead-add.html",
    "https://apidocs.bitrix24.ru/api-reference/crm/contacts/crm-contact-add.html"
]

def setup_driver():
    """Настройка headless-браузера Chrome (работает в фоне)"""
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Фоновый режим
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Автоматически скачивает нужный ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def parse_and_save():
    """Парсит страницы и сохраняет их в текстовые файлы"""
    driver = setup_driver()
    parsed_count = 0
    
    try:
        for url in URLS_TO_PARSE:
            print(f"🔍 Парсинг: {url}")
            driver.get(url)
            
            # Ждем 4 секунды, чтобы прогрузился JavaScript на сайте Bitrix24
            time.sleep(4) 
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Удаляем теги скриптов, стилей и навигации, чтобы остался только полезный текст
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.extract()
                
            # Извлекаем чистый текст
            text = soup.get_text(separator='\n', strip=True)
            
            # Формируем имя файла из URL
            filename = url.split('/')[-1].replace('.html', '.txt')
            if not filename:
                filename = f"page_{parsed_count}.txt"
                
            filepath = os.path.join(DATA_DIR, filename)
            
            # Сохраняем в файл
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Источник: {url}\n\n")
                f.write(text)
                
            print(f"✅ Успешно сохранено: {filepath}")
            parsed_count += 1
            
    finally:
        driver.quit()
        
    print(f"\n🎉 Парсинг завершен! Успешно обработано {parsed_count} страниц.")

if __name__ == "__main__":
    parse_and_save()