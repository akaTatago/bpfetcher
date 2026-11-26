import os
import re
import time
import urllib.parse
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright
from .base_scraper import BaseScraper
from src.models import BookOffer, Status
from src.utils.scraping_helper import (
    clean_text, clean_price, normalize_isbn,
    is_available, join_authors, parse_jsonld_product, parse_offer, parse_int
)


class FnacScraper(BaseScraper):
    requires_browser = True

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

    def _fetch(self, url):
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

    def _search_url(self, query):
        return f"{self.base_url}/SearchResult/ResultList.aspx?Search={urllib.parse.quote(query)}&sft=1&sa=0"

    def scrape_by_isbn(self, isbn):
        soup, final_url = self._fetch(self._search_url(normalize_isbn(isbn)))
        if not soup:
            return None

        # The search may land directly on the product page...
        offer = self._parse_product_page(soup, final_url)
        if offer:
            return offer

        # ...otherwise follow the first result
        card = soup.find("article", class_="Article-itemGroup")
        title_link = card.find("a", class_="Article-title") if card else None
        if not title_link or not title_link.get("href"):
            return None

        soup, final_url = self._fetch(self.absolute_url(title_link["href"]))
        if not soup or self._is_marketplace(final_url):
            return None
        return self._parse_product_page(soup, final_url)

    def _parse_product_page(self, soup, url):
        data = parse_jsonld_product(soup)
        if not data:
            return None

        offer = BookOffer.from_jsonld(self.store_name, data, url)

        _, availability_url = parse_offer(data)
        offer.status = Status.from_bool(is_available(availability_url) and bool(offer.price))

        active_offer = None
        for wrapper in soup.find_all("div", class_="f-faPriceBox__radioWrapper"):
            if wrapper.find("input", {"name": "fnacoffer", "checked": True}) or wrapper.find(class_="checked"):
                active_offer = wrapper
                break

        if active_offer:
            offer.on_sale = bool(
                active_offer.find("strong", class_="f-faPriceBox__price--striked")
                or active_offer.find(class_="f-faPriceBox__stimuliOpcLabel")
            )
        else:
            offer.on_sale = bool(soup.find("strong", class_="f-faPriceBox__price--striked"))

        if not offer.pages:
            for item in soup.find_all("dl", class_="f-productProperties__item"):
                term = item.find("dt", class_="f-productProperties__term")
                definition = item.find("dd", class_="f-productProperties__definition")
                if term and definition and "páginas" in clean_text(term).lower():
                    offer.pages = parse_int(clean_text(definition))
                    if offer.pages:
                        break

        return offer

    def _text_queries(self, title, author):
        return self.normalized_queries(title, author)

    @staticmethod
    def _card_link(card):
        title_tag = card.find("a", class_="Article-title")
        return title_tag.get("href", "") if title_tag else ""

    def _find_cards(self, soup):
        cards = soup.find_all("article", class_="Article-itemGroup")
        # Skip ebook sub-cards ("Versão ebook em ...") and marketplace (third-party seller) listings
        return [
            c for c in cards
            if "Article-itemGroup--subPE" not in c.get("class", [])
            and not self._is_marketplace(self._card_link(c))
        ]

    @staticmethod
    def _card_price(card):
        for block in card.find_all("div", class_="blocPriceBorder"):
            if "base" in block.get_text().lower():
                return clean_price(block.find("span", class_="price"))
        return clean_price(card.find(class_="userPrice"))

    def _parse_card(self, card):
        title_tag = card.find("a", class_="Article-title")
        author_tag = card.find(class_="Article-descSub")

        if not title_tag or not author_tag:
            return None

        author_links = author_tag.find_all("a")
        if author_links:
            author_found = join_authors(a.get_text(strip=True) for a in author_links)
        else:
            author_found = clean_text(author_tag)

        price = self._card_price(card)

        return BookOffer(
            store=self.store_name,
            title_found=clean_text(title_tag),
            author_found=author_found,
            price=price,
            on_sale=bool(card.find(class_="oldPrice")),
            status=Status.from_bool(price and card.find("button", class_="js-ProductBuy-add")),
            link=self.absolute_url(self._card_link(card))
        )

    def close(self):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()