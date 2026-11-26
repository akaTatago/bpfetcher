import urllib.parse
from .base_scraper import BaseScraper
from src.models import BookOffer, Status
from src.utils.scraping_helper import (
    clean_text, clean_price, normalize_isbn, has_text,
    parse_jsonld_product, parse_int
)


class AlmedinaScraper(BaseScraper):
    def __init__(self):
        super().__init__("Almedina", "https://www.almedina.net")

    def scrape_by_isbn(self, isbn):
        # Almedina redirects an ISBN search straight to the product page
        return self.scrape_product_page(f"{self.base_url}/catalogsearch/result/?q={normalize_isbn(isbn)}")

    def _parse_product_page(self, soup, url):
        data = parse_jsonld_product(soup)
        if not data:
            return None

        prod = soup.find("div", class_="product-info-main")
        price_area = prod.find("div", class_="price-box") if prod else None
        availability_tag = prod.find("div", class_="availability") if prod else None

        offer = BookOffer.from_jsonld(self.store_name, data, url)
        offer.on_sale = bool(price_area and price_area.find("span", class_="special-price"))
        offer.status = Status.from_bool(not has_text(availability_tag, "Indisponível"))

        if prod:
            for row in prod.find_all("tr"):
                th, td = row.find("th"), row.find("td")
                if th and td and "páginas" in clean_text(th).lower():
                    offer.pages = parse_int(clean_text(td)) or offer.pages
                    break

        return offer

    def _search_url(self, query):
        return f"{self.base_url}/catalogsearch/result/?q={urllib.parse.quote(query)}"

    def _find_cards(self, soup):
        return soup.find_all("li", class_="product-item")

    def _is_product_page(self, soup):
        # Results pages have a filter sidebar; product pages do not (even though
        # they also contain "product-item" cards for related books).
        return not soup.find("div", class_="sidebar")

    def _parse_card(self, card):
        info = card.find("div", class_="product-item-details")
        if not info:
            return None

        title_tag = info.find("strong", class_="product-item-name")
        author_tag = info.find("div", class_="product-author-name")
        link_tag = info.find("a", href=True)

        if not title_tag or not author_tag or not link_tag:
            return None

        price_area = card.find("div", class_="price-box")

        return BookOffer(
            store=self.store_name,
            title_found=clean_text(title_tag),
            author_found=clean_text(author_tag),
            price=clean_price(price_area.find("span", class_="price")) if price_area else None,
            on_sale=bool(price_area and price_area.find("span", class_="old-price")),
            status=Status.from_bool(not has_text(info.find("p", class_="availability"), "Indisponível")),
            link=self.absolute_url(link_tag["href"])
        )