import urllib.parse
from urllib.parse import urljoin
from .base_scraper import BaseScraper
from src.utils.scraping_helper import (
    get_soup, clean_text, clean_price, normalize_isbn, normalize,
    parse_jsonld_product, parse_authors, parse_offer, parse_int
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

        prod_url = urljoin(self.base_url, link_tag["href"])

        soup, final_url = get_soup(prod_url)
        if not soup: return None

        data = parse_jsonld_product(soup)
        if not data:
            return None

        price, _ = parse_offer(data)
        availability_tag = soup.find("span", class_="availability")

        return {
            "store": self.store_name,
            "title_found": data.get("name", ""),
            "author_found": parse_authors(data.get("author")),
            "price": price,
            "pages": parse_int(data.get("numberOfPages")),
            "on_sale": bool(soup.find("span", class_="old")),
            "status": "Unavailable" if availability_tag and "Esgotado" in clean_text(availability_tag) else "Available",
            "link": final_url
        }

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
            f_author = " e ".join([a.get_text(strip=True) for a in author_tag.find_all("a")])

            if self._validate_match(title, author, f_title, f_author):
                price = clean_price(prod.find("span", class_="pch__price-current"))

                results.append({
                    "store": self.store_name,
                    "title_found": f_title,
                    "author_found": f_author.strip(),
                    "price": price,
                    "on_sale": bool(prod.find("span", class_="pch__price-old")),
                    "status": "Unavailable" if prod.find("p", class_="pch__unavailable") else "Available",
                    "link": urljoin(self.base_url, link_tag["href"])
                })
            else:
                unmatches += 1

        return results