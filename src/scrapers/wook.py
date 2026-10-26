import json
import urllib.parse
from .base_scraper import BaseScraper
from src.utils.scraping_helper import get_soup, clean_text, clean_price, normalize_isbn

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
        if not soup or not soup.find("script", type="application/ld+json"):
            return None

        data = json.loads(soup.find("script", type="application/ld+json").string)
        
        authors_data = data.get("author", {})
        if isinstance(authors_data, list):
            author_found = " e ".join([a.get("name", "") for a in authors_data])
        elif isinstance(authors_data, dict):
            author_found = authors_data.get("name", "")
        else:
            author_found = str(authors_data)
            
        right_flex = soup.find("div", class_="right d-flex flex-column")
        
        return {
            "store": self.store_name,
            "title_found": data.get("name", ""),
            "author_found": author_found.replace(" e ", " and "),
            "price": data.get("offers", {}).get("price", 0.0),
            "pages": data.get("numberOfPages", 0),
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
            author_tag = prod.find("div", class_="authors").find("a") if prod.find("div", class_="authors") else None
            
            if not title_tag or not author_tag: 
                unmatches += 1
                continue
            
            f_title, f_author = clean_text(title_tag), clean_text(author_tag)
            
            if self._validate_match(title, author, f_title, f_author):
                price_tag = prod.find("span", class_="pvp")
                price = clean_price(price_tag.find("span", class_="font-bold")) if price_tag else 0.0

                on_sale = False
                if price_tag:
                    on_sale = bool(price_tag.find("s", class_="text-red"))
                
                results.append({
                    "store": self.store_name,
                    "title_found": f_title,
                    "author_found": f_author,
                    "price": price,
                    "on_sale": on_sale,
                    "status": "Available" if price > 0 else "Unavailable",
                    "link": self.base_url + title_area.find("a")['href']
                })
            else:
                unmatches += 1

        return results