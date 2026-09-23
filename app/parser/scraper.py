import os
import time
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from app.config import PARSE_MAX_PAGES, PARSE_DELAY_SECONDS
from app.logger import logger

DATA_DIR = "data/docs"
SITEMAP_URL = "https://apidocs.bitrix24.ru/sitemap.xml"
BASE_URL = "https://apidocs.bitrix24.ru/"


def setup_driver() -> webdriver.Chrome:
    """Headless Chrome с оптимизациями для быстрого рендеринга."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    # Оптимизации: отключаем картинки и CSS для ускорения
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def fetch_sitemap_urls() -> list[str]:
    """Скачивает sitemap.xml и извлекает все URL."""
    logger.info("Скачиваю sitemap.xml...")
    try:
        response = requests.get(SITEMAP_URL, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        logger.error("Не удалось скачать sitemap: %s", exc)
        return []

    # Парсим XML
    root = ET.fromstring(response.content)
    # Namespace в sitemap: http://www.sitemaps.org/schemas/sitemap/0.9
    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    
    urls = []
    for loc in root.findall(".//ns:loc", namespace):
        url = loc.text.strip()
        # Фильтруем только страницы API-методов
        if url.startswith(BASE_URL) and "/api-reference/" in url and url.endswith(".html"):
            urls.append(url)
    
    logger.info("Найдено %d URL в sitemap (после фильтрации)", len(urls))
    return urls


def save_page(soup: BeautifulSoup, url: str) -> str | None:
    """Сохраняет очищенный текст страницы в .txt файл."""
    try:
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.extract()
        text = soup.get_text(separator="\n", strip=True)
        filename = url.rstrip("/").split("/")[-1].replace(".html", ".txt")
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Source: {url}\n\n{text}")
        return filename
    except Exception as exc:
        logger.error("Ошибка сохранения %s: %s", url, exc)
        return None


def parse_and_save() -> int:
    """
    Парсит ВСЮ документацию через sitemap.xml (замечание №2),
    удаляет устаревшие файлы (замечание №5).
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Получаем список всех URL из sitemap
    all_urls = fetch_sitemap_urls()
    if not all_urls:
        logger.error("Не удалось получить URL из sitemap")
        return 0
    
    # Ограничиваем количество страниц (для тестирования)
    urls_to_parse = all_urls[:PARSE_MAX_PAGES]
    logger.info("Будет обработано %d из %d страниц", len(urls_to_parse), len(all_urls))
    
    driver = setup_driver()
    written = set()
    
    try:
        for i, url in enumerate(urls_to_parse, 1):
            logger.info("[%d/%d] Парсинг: %s", i, len(urls_to_parse), url)
            try:
                driver.get(url)
                time.sleep(PARSE_DELAY_SECONDS)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                filename = save_page(soup, url)
                if filename:
                    written.add(filename)
            except Exception as exc:
                logger.warning("Не удалось обработать %s: %s", url, exc)
    finally:
        driver.quit()
    
    # Замечание №5: удаляем устаревшие файлы
    removed = 0
    for name in os.listdir(DATA_DIR):
        if name.endswith(".txt") and name not in written:
            os.remove(os.path.join(DATA_DIR, name))
            removed += 1
    
    logger.info("Устаревших файлов удалено: %d", removed)
    logger.info("Парсинг завершён: сохранено документов: %d", len(written))
    return len(written)


if __name__ == "__main__":
    logger.info("Запуск парсинга документации Bitrix24 через sitemap...")
    count = parse_and_save()
    logger.info("Готово. Страниц в базе знаний: %d", count)