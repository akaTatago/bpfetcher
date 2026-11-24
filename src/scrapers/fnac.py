import os
import re
import time
import urllib.parse
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright
from .base_scraper import BaseScraper
from src.utils.scraping_helper import (
    clean_text, clean_price, normalize_isbn, normalize,
    parse_jsonld_product, parse_authors, parse_offer, parse_int
)


class FnacScraper(BaseScraper):
    def __init__(self):
        super().__init__("Fnac", "https://www.fnac.pt")
        self.playwright = None
        self.context = None
        self.page = None
        self._init_browser()

    def _init_browser(self):
        print("\n[Fnac] Starting browser session...")
        profile_dir = os.path.join(os.getcwd(), ".fnac_browser_profile")
        os.makedirs(profile_dir, exist_ok=True)

        self.playwright = sync_playwright().start()

        launch_kwargs = {
            "user_data_dir": profile_dir,
            "headless": False,
            "locale": "pt-PT",
            "viewport": {"width": 1280, "height": 800},
        }

        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                channel="chrome",
                **launch_kwargs
            )
        except Exception:
            self.context = self.playwright.chromium.launch_persistent_context(
                **launch_kwargs
            )

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

        def _block_heavy_assets(route):
            if route.request.resource_type in ("image", "media", "font"):
                route.abort()
            else:
                route.continue_()

        self.page.route("**/*", _block_heavy_assets)

    def _get_fnac_soup(self, url):
        try:
            time.sleep(1.5)
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)

            html = self.page.content()

            if "O acesso está temporariamente restrito" in html or "Access is temporarily restricted" in html:
                print("\n[Fnac] Blocked by DataDome (IP temporarily restricted).")
                print("[Fnac] Please switch network/IP (e.g., router restart or hotspot) and press ENTER to retry...")
                input()
                self.page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                html = self.page.content()

            if "captcha-delivery.com" in html:
                print("\n[Fnac] CAPTCHA detected! Please solve it in the browser window...")
                self.page.wait_for_selector("article.Article-itemGroup, .f-productHeader, header", timeout=120000)
                time.sleep(2)
                html = self.page.content()

            return BeautifulSoup(html, "lxml"), self.page.url

        except Exception as e:
            print(f"[Fnac] Navigation error ({url}): {e}")
            return None, None

    def _is_marketplace(self, url):
        return bool(url and re.search(r"/mp\d+", url))

    def scrape_by_isbn(self, isbn):
        isbn = normalize_isbn(isbn)
        url = f"{self.base_url}/SearchResult/ResultList.aspx?Search={isbn}&sft=1&sa=0"

        soup, response_url = self._get_fnac_soup(url)
        if not soup:
            return None

        data = parse_jsonld_product(soup)
        final_url = response_url

        if not data:
            prod = soup.find("article", class_="Article-itemGroup")
            if not prod:
                return None
            title_link = prod.find("a", class_="Article-title")
            if not title_link or not title_link.get("href"):
                return None

            prod_url = title_link["href"]
            if not prod_url.startswith("http"):
                prod_url = self.base_url + prod_url

            soup, final_url = self._get_fnac_soup(prod_url)
            if not soup or self._is_marketplace(final_url):
                return None
            data = parse_jsonld_product(soup)

        if not data:
            return None

        author_found = parse_authors(data.get("author"))

        price, availability_url = parse_offer(data)
        is_available = "InStock" in availability_url and bool(price)

        on_sale = False
        active_offer = None

        for wrapper in soup.find_all("div", class_="f-faPriceBox__radioWrapper"):
            if wrapper.find("input", {"name": "fnacoffer", "checked": True}) or wrapper.find(class_="checked"):
                active_offer = wrapper
                break

        if active_offer:
            on_sale = bool(
                active_offer.find("strong", class_="f-faPriceBox__price--striked")
                or active_offer.find(class_="f-faPriceBox__stimuliOpcLabel")
            )
        else:
            on_sale = bool(soup.find("strong", class_="f-faPriceBox__price--striked"))

        pages = parse_int(data.get("numberOfPages"))
        if not pages:
            for item in soup.find_all("dl", class_="f-productProperties__item"):
                term = item.find("dt", class_="f-productProperties__term")
                definition = item.find("dd", class_="f-productProperties__definition")
                if term and definition and "páginas" in clean_text(term).lower():
                    pages = parse_int(clean_text(definition))
                    if pages:
                        break


        return {
            "store": self.store_name,
            "title_found": data.get("name", ""),
            "author_found": author_found,
            "price": price,
            "pages": pages,
            "on_sale": on_sale,
            "status": "Available" if is_available else "Unavailable",
            "link": final_url
        }

    def search_by_text(self, title, author):
        safe_title = normalize(title) or title
        safe_author = normalize(author) or author
        query = urllib.parse.quote(f"{safe_title} {safe_author}".lower())
        url = f"{self.base_url}/SearchResult/ResultList.aspx?Search={query}&sft=1&sa=0"

        soup, _ = self._get_fnac_soup(url)
        products = soup.find_all("article", class_="Article-itemGroup") if soup else []

        if not products:
            query = urllib.parse.quote(safe_title.lower())
            url = f"{self.base_url}/SearchResult/ResultList.aspx?Search={query}&sft=1&sa=0"
            soup, _ = self._get_fnac_soup(url)
            products = soup.find_all("article", class_="Article-itemGroup") if soup else []

        if not products:
            return []

        results = []
        unmatches = 0

        for prod in products:
            if unmatches >= 10:
                break

            title_tag = prod.find("a", class_="Article-title")
            author_tag = prod.find(class_="Article-descSub")

            if not title_tag or not author_tag:
                unmatches += 1
                continue

            link = title_tag.get("href", "")
            if self._is_marketplace(link):
                continue

            f_title = clean_text(title_tag)
            author_links = author_tag.find_all("a")
            if author_links:
                f_author = " e ".join([a.get_text(strip=True) for a in author_links])
            else:
                f_author = clean_text(author_tag)

            if self._validate_match(title, author, f_title, f_author):
                price_tag = prod.find(class_="userPrice")
                price = clean_price(price_tag)
                link = title_tag.get("href", "")
                if link and not link.startswith("http"):
                    link = self.base_url + link

                results.append({
                    "store": self.store_name,
                    "title_found": f_title,
                    "author_found": f_author.strip(),
                    "price": price,
                    "on_sale": bool(prod.find(class_="oldPrice")),
                    "status": "Available" if price else "Unavailable",
                    "link": link
                })
            else:
                unmatches += 1

        return results

    def close(self):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()