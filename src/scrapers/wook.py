import urllib.parse
from .base_scraper import BaseScraper
from src.models import BookOffer, Status
from src.utils.scraping_helper import clean_text, clean_price, normalize_isbn, parse_jsonld_product


class WookScraper(BaseScraper):
    def __init__(self):
        super().__init__("Wook", "https://www.wook.pt")

    def scrape_by_isbn(self, isbn):
        # Wook redirects an ISBN search straight to the product page
        return self.scrape_product_page(f"{self.base_url}/pesquisa?keyword={normalize_isbn(isbn)}")

    def _parse_product_page(self, soup, url):
        data = parse_jsonld_product(soup)
        if not data:
            return None

        right_flex = soup.find("div", class_="right d-flex flex-column")

        offer = BookOffer.from_jsonld(self.store_name, data, url)
        offer.on_sale = bool(soup.find("s", class_="text-red text-align-right"))
        offer.status = Status.from_bool(
            right_flex and right_flex.find("span", class_="price text-black text-align-right")
        )
        return offer

    def _search_url(self, query):
        return f"{self.base_url}/pesquisa?keyword={urllib.parse.quote(query)}"

    def _find_cards(self, soup):
        return soup.find_all("li", class_="product d-flex")

    def _is_product_page(self, soup):
        # With a single result Wook goes straight to the product page
        return not self._find_cards(soup)

    def _parse_card(self, card):
        title_area = card.find("div", class_="title")
        title_tag = title_area.find("span", class_="font-bold") if title_area else None
        link_tag = title_area.find("a", href=True) if title_area else None
        authors_area = card.find("div", class_="authors")
        author_tag = authors_area.find("a") if authors_area else None

        if not title_tag or not author_tag or not link_tag:
            return None

        price_tag = card.find("span", class_="pvp")
        price = clean_price(price_tag.find("span", class_="font-bold")) if price_tag else None

        return BookOffer(
            store=self.store_name,
            title_found=clean_text(title_tag),
            author_found=clean_text(author_tag),
            price=price,
            on_sale=bool(price_tag and price_tag.find("s", class_="text-red")),
            status=Status.from_bool(price),
            link=self.absolute_url(link_tag["href"])
        )