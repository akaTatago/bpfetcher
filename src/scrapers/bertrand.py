import urllib.parse
from .base_scraper import BaseScraper
from src.models import BookOffer, Status
from src.utils.scraping_helper import (
    clean_text, clean_price, normalize_isbn,
    has_text, join_authors, parse_jsonld_product
)


class BertrandScraper(BaseScraper):
    def __init__(self):
        super().__init__("Bertrand", "https://www.bertrand.pt")

    def scrape_by_isbn(self, isbn):
        # The ISBN search is a results list: follow the first result to its product page
        soup, _ = self._fetch(f"{self.base_url}/pesquisa/{normalize_isbn(isbn)}")
        card = soup.find("div", class_="pch") if soup else None
        link_tag = card.find("a", class_="track", href=True) if card else None
        if not link_tag:
            return None

        return self.scrape_product_page(self.absolute_url(link_tag["href"]))

    def _parse_product_page(self, soup, url):
        data = parse_jsonld_product(soup)
        if not data:
            return None

        offer = BookOffer.from_jsonld(self.store_name, data, url)
        offer.on_sale = bool(soup.find("span", class_="old"))
        offer.status = Status.from_bool(
            not has_text(soup.find("span", class_="availability"), "Esgotado")
        )
        return offer

    def _text_queries(self, title, author):
        return self.normalized_queries(title, author)

    def _search_url(self, query):
        # Bertrand answers 403 to %20 in the path, so spaces must be '+'
        return f"{self.base_url}/pesquisa/{urllib.parse.quote_plus(query)}"

    def _find_cards(self, soup):
        return soup.find_all("div", class_="pch")

    def _parse_card(self, card):
        title_tag = card.find("p", class_="pch__title")
        author_tag = card.find("p", class_="pch__author")
        link_tag = title_tag.find("a", href=True) if title_tag else None

        if not title_tag or not author_tag or not link_tag:
            return None

        return BookOffer(
            store=self.store_name,
            title_found=clean_text(title_tag),
            author_found=join_authors(a.get_text(strip=True) for a in author_tag.find_all("a")),
            price=clean_price(card.find("span", class_="pch__price-current")),
            on_sale=bool(card.find("span", class_="pch__price-old")),
            status=Status.from_bool(not card.find("p", class_="pch__unavailable")),
            link=self.absolute_url(link_tag["href"])
        )