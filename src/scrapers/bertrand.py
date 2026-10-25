import re, urllib.parse
from .base_scraper import BaseScraper
from src.utils.scraping_helper import get_soup, clean_text, clean_price, normalize_isbn, normalize

class BertrandScraper(BaseScraper):
    def __init__(self):
        super().__init__("Bertrand", "https://www.bertrand.pt")

    def scrape_by_isbn(self, isbn):
        isbn=normalize_isbn(isbn)
        url = f"{self.base_url}/pesquisa/{isbn}"
        soup, final_url = get_soup(url)
        if not soup: return None
        prod = soup.find("div", class_="pch")
        if not prod: return None
        
        #TITLE
        title_tag = prod.find("p", class_="pch__title")

        #AUTHOR
        author_tag = prod.find("p", class_="pch__author")

        #PRICE
        price = clean_price(prod.find("span", class_="pch__price-current"))

        return {
            "store": self.store_name,
            "title_found": clean_text(title_tag),
            "author_found": " e ".join([a.get_text(strip=True) for a in author_tag.find_all("a")]),
            "price": price,
            "on_sale": bool(prod.find("span", class_="pch__price-old")),
            "status": "Unavailable" if soup.find("div", class_="pch--unavailable") else "Available",
            "link": self.base_url + title_tag.find("a")["href"]
        }

    def search_by_text(self, title, author):
        safe_title = normalize(title) or title
        safe_author = normalize(author) or author

        query = urllib.parse.quote(f"{safe_title} {safe_author}".lower())
        url = f"{self.base_url}/pesquisa/{query}"
        soup, _ = get_soup(url)
        products = soup.find_all("div", class_="pch") if soup else []
        
        if not products:
            query = urllib.parse.quote(safe_title.lower())
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

            if not title_tag or not author_tag: 
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
                    "link": self.base_url + title_tag.find("a")["href"]
                })
            else:
                unmatches += 1

        return results