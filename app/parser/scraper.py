import os
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from app.config import PARSE_MAX_PAGES, PARSE_DELAY_SECONDS
from app.logger import logger

DATA_DIR = "data/docs"
BASE_URL = "https://apidocs.bitrix24.ru/"
START_URL = "https://apidocs.bitrix24.ru/api-reference/"


def setup_driver() -> webdriver.Chrome:
    """Headless Chrome для рендеринга JS-страниц документации."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def _normalize(url: str) -> str:
    """Канонический вид URL: без query-параметров и якорей."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _is_doc_url(url: str) -> bool:
    """Страница с описанием API-метода, а не навигация."""
    return url.startswith(BASE_URL) and "/api-reference/" in url and url.endswith(".html")


def _save_soup(soup: BeautifulSoup, url: str):
    """Сохраняет очищенный текст страницы в .txt файл. Возвращает имя файла."""
    try:
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.extract()
        text = soup.get_text(separator="\n", strip=True)
        filename = url.rstrip("/").split("/")[-1].replace(".html", ".txt")
        with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
            f.write(f"Source: {url}\n\n{text}")
        return filename
    except Exception as exc:
        logger.error("Ошибка сохранения %s: %s", url, exc)
        return None


def parse_and_save() -> int:
    """
    Обходит ВСЮ документацию Bitrix24 (BFS по внутренним ссылкам),
    сохраняет страницы и удаляет устаревшие файлы (замечания №2 и №5).
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    driver = setup_driver()
    visited = set()
    queue = [_normalize(START_URL)]
    written = set()

    try:
        while queue and len(visited) < PARSE_MAX_PAGES:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                driver.get(url)
                time.sleep(PARSE_DELAY_SECONDS)
                soup = BeautifulSoup(driver.page_source, "html.parser")
            except Exception as exc:
                logger.warning("Не удалось открыть %s: %s", url, exc)
                continue

            if _is_doc_url(url):
                filename = _save_soup(soup, url)
                if filename:
                    written.add(filename)

            # Добавляем в очередь все внутренние ссылки страницы
            for a in soup.find_all("a", href=True):
                link = _normalize(urljoin(url, a["href"]))
                if link.startswith(BASE_URL) and link not in visited:
                    queue.append(link)

            if len(visited) % 10 == 0:
                logger.info("Просмотрено страниц: %d | сохранено документов: %d",
                            len(visited), len(written))
    finally:
        driver.quit()

    # Замечание №5: удаляем файлы страниц, которых больше нет в документации
    removed = 0
    for name in os.listdir(DATA_DIR):
        if name.endswith(".txt") and name not in written:
            os.remove(os.path.join(DATA_DIR, name))
            removed += 1

    logger.info("Устаревших файлов удалено: %d", removed)
    logger.info("Парсинг завершён: сохранено документов: %d", len(written))
    return len(written)


if __name__ == "__main__":
    logger.info("Запуск полного парсинга документации Bitrix24...")
    count = parse_and_save()
    logger.info("Готово. Страниц в базе знаний: %d", count)
