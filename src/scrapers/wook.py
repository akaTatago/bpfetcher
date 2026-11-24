import urllib.parse
from urllib.parse import urljoin
from .base_scraper import BaseScraper
from src.utils.scraping_helper import (
    get_soup, clean_text, clean_price, normalize_isbn,
    parse_jsonld_product, parse_authors, parse_offer, parse_int
)

class WookScraper(BaseScraper):
    def __init__(self):
        super().__init__("Wook", "https://www.wook.pt")

    def scrape_by_isbn(self, isbn):
        if "https://" in isbn:
            url = isbn
        else:
            isbn = normalize_isbn(isbn)
            url = f"{self.base_url}/pesquisa?keyword={isbn}"

        soup, final_url = get_soup(url)
        if not soup:
            return None

        data = parse_jsonld_product(soup)
        if not data:
            return None

        price, _ = parse_offer(data)
        right_flex = soup.find("div", class_="right d-flex flex-column")

        return {
            "store": self.store_name,
            "title_found": data.get("name", ""),
            "author_found": parse_authors(data.get("author")),
            "price": price,
            "pages": parse_int(data.get("numberOfPages")),
            "on_sale": bool(soup.find("s", class_="text-red text-align-right")),
            "status": "Available" if right_flex and right_flex.find("span", class_="price text-black text-align-right") else "Unavailable",
            "link": final_url
        }
    
    def search_by_text(self, title, author):
        query = urllib.parse.quote(f"{title} {author}".lower())
        url = f"{self.base_url}/pesquisa?keyword={query}"
        soup, response_link = get_soup(url)
        if not soup: return []

        results = []
        unmatches = 0

        products = soup.find_all("li", class_="product d-flex")
        if not products:
            match = self.scrape_by_isbn(response_link)
            if match:
                results.append(match)
            return results

        for prod in products:
            if unmatches >= 10:
                break

            title_area = prod.find("div", class_="title")
            title_tag = title_area.find("span", class_="font-bold") if title_area else None
            link_tag = title_area.find("a", href=True) if title_area else None
            authors_area = prod.find("div", class_="authors")
            author_tag = authors_area.find("a") if authors_area else None

            if not title_tag or not author_tag or not link_tag:
                unmatches += 1
                continue

            f_title, f_author = clean_text(title_tag), clean_text(author_tag)

            if self._validate_match(title, author, f_title, f_author):
                price_tag = prod.find("span", class_="pvp")
                price = clean_price(price_tag.find("span", class_="font-bold")) if price_tag else None

                on_sale = False
                if price_tag:
                    on_sale = bool(price_tag.find("s", class_="text-red"))

                results.append({
                    "store": self.store_name,
                    "title_found": f_title,
                    "author_found": f_author,
                    "price": price,
                    "on_sale": on_sale,
                    "status": "Available" if price else "Unavailable",
                    "link": urljoin(self.base_url, link_tag["href"])
                })
            else:
                unmatches += 1

        return results