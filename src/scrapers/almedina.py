import json
import urllib.parse
from .base_scraper import BaseScraper
from src.utils.scraping_helper import get_soup, clean_text, clean_price, normalize_isbn

class AlmedinaScraper(BaseScraper):
    def __init__(self):
        super().__init__("Almedina", "https://www.almedina.net")

    def scrape_by_isbn(self, isbn):
        if "https://" in isbn:
            url = isbn
        else:
            isbn = normalize_isbn(isbn)
            url = f"{self.base_url}/catalogsearch/result/?q={isbn}"

        soup, response_link = get_soup(url)
        if not soup or not soup.find("script", type="application/ld+json"): 
            return None

        data = json.loads(soup.find("script", type="application/ld+json").string)

        prod = soup.find("div", class_="product-info-main")
        price_area = prod.find("div", class_="price-box") if prod else None
        availability_tag = prod.find("div", class_="availability") if prod else None

        pages = 0
        if prod:
            for row in prod.find_all("tr"):
                th, td = row.find("th"), row.find("td")
                if th and td and "páginas" in clean_text(th).lower():
                    value = clean_text(td)
                    pages = int(value) if value.isdigit() else 0
                    break

        authors_data = data.get("author", {})
        if isinstance(authors_data, list):
            author_found = " e ".join([a.get("name", "") for a in authors_data])
        elif isinstance(authors_data, dict):
            author_found = authors_data.get("name", "")
        else:
            author_found = str(authors_data)

        return {
            "store": self.store_name,
            "title_found": data.get("name", ""),
            "author_found": author_found.replace(" e ", " and "),
            "price": data.get("offers", {}).get("price", 0.0),
            "pages": pages,
            "on_sale": bool(price_area.find("span", class_="special-price")) if price_area else False,
            "status": "Unavailable" if availability_tag and "Indisponível" in availability_tag.text else "Available",
            "link": response_link
        }
    
    def search_by_text(self, title, author):
        query = urllib.parse.quote(f"{title} {author}".lower())
        url = f"{self.base_url}/catalogsearch/result/?q={query}"
        soup, response_url = get_soup(url)

        if not soup: return []

        results = []
        unmatches = 0
        products = soup.find_all("li", class_="product-item")

        if not soup.find("div", class_="sidebar"):
            match = self.scrape_by_isbn(response_url)
            if match:
                results.append(match)
            return results

        for prod in products:
            if unmatches >= 10:
                break
            
            info = prod.find("div", class_="product-item-details")
            title_tag = info.find("strong", class_="product-item-name")
            author_tag = info.find("div", class_= "product-author-name")

            if not title_tag or not author_tag:
                unmatches += 1
                continue

            f_title = clean_text(title_tag)
            f_author = clean_text(author_tag)

            if self._validate_match(title, author, f_title, f_author):
                price_area = prod.find("div", class_="price-box")
                price = clean_price(price_area.find("span", class_="price"))

                results.append({
                    "store": self.store_name,
                    "title_found": f_title,
                    "author_found": f_author,
                    "price": price,
                    "on_sale": bool(price_area.find("span", class_="old-price")),
                    "status": "Unavailable" if info.find("p", class_="availability") and "Indisponível" in info.find("p", class_="availability") else "Available",
                    "link": info.find("a")['href']
                })
            else:
                unmatches += 1

    
        return results