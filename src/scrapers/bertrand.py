import urllib.parse
from .base_scraper import BaseScraper
from src.models import BookOffer, Status
from src.utils.scraping_helper import (
    get_soup, clean_text, clean_price, normalize_isbn, normalize,
    has_text, join_authors, parse_jsonld_product
)

class BertrandScraper(BaseScraper):
    def __init__(self):
        super().__init__("Bertrand", "https://www.bertrand.pt")

    def scrape_by_isbn(self, isbn):
        isbn=normalize_isbn(isbn)
        url = f"{self.base_url}/pesquisa/{isbn}"
        soup, _ = get_soup(url)
        if not soup: return None
        prod = soup.find("div", class_="pch")
        if not prod: return None

        link_tag = prod.find("a", class_="track", href=True)
        if not link_tag: return None

        soup, final_url = get_soup(self.absolute_url(link_tag["href"]))
        if not soup: return None

        data = parse_jsonld_product(soup)
        if not data:
            return None

        offer = BookOffer.from_jsonld(self.store_name, data, final_url)
        offer.on_sale = bool(soup.find("span", class_="old"))
        offer.status = Status.from_bool(
            not has_text(soup.find("span", class_="availability"), "Esgotado")
        )
        return offer

    def search_by_text(self, title, author):
        safe_title = normalize(title) or title
        safe_author = normalize(author) or author

        query = urllib.parse.quote_plus(f"{safe_title} {safe_author}".lower())
        url = f"{self.base_url}/pesquisa/{query}"
        soup, _ = get_soup(url)
        products = soup.find_all("div", class_="pch") if soup else []
        
        if not products:
            query = urllib.parse.quote_plus(safe_title.lower())
            url = f"{self.base_url}/pesquisa/{query}"
            soup, _ = get_soup(url)
            products = soup.find_all("div", class_="pch") if soup else []

        if not products: 
            return []

        results = []
        unmatches = 0
        
        for prod in products:
            if unmatches>=10:
                break

            title_tag = prod.find("p", class_="pch__title")
            author_tag = prod.find("p", class_="pch__author")
            link_tag = title_tag.find("a", href=True) if title_tag else None

            if not title_tag or not author_tag or not link_tag:
                unmatches += 1
                continue

            f_title = clean_text(title_tag)
            f_author = join_authors(a.get_text(strip=True) for a in author_tag.find_all("a"))

            if self._validate_match(title, author, f_title, f_author):
                results.append(BookOffer(
                    store=self.store_name,
                    title_found=f_title,
                    author_found=f_author,
                    price=clean_price(prod.find("span", class_="pch__price-current")),
                    on_sale=bool(prod.find("span", class_="pch__price-old")),
                    status=Status.from_bool(not prod.find("p", class_="pch__unavailable")),
                    link=self.absolute_url(link_tag["href"])
                ))
            else:
                unmatches += 1

        return results