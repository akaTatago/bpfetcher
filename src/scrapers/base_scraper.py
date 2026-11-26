import re
from abc import ABC, abstractmethod
from urllib.parse import urljoin
from unidecode import unidecode
from src.utils.scraping_helper import get_soup, normalize


class BaseScraper(ABC):
    """Common flow for every store.

    A store only describes WHERE things are (URLs and HTML selectors) by implementing
    the hooks below. The search flow itself lives here, once:

        search_by_text -> _text_queries -> _fetch(_search_url) -> _find_cards
                       -> _parse_card -> _validate_match

    Public API (what main.py calls):
        search_by_text(title, author) -> list[BookOffer]
        scrape_by_isbn(isbn)          -> BookOffer | None
    """

    requires_browser = False   # True for scrapers that drive a real browser (not thread-safe)
    MAX_UNMATCHES = 10         # stop reading a results page after this many non-matching cards

    def __init__(self, store_name, base_url):
        self.store_name = store_name
        self.base_url = base_url


    @abstractmethod
    def scrape_by_isbn(self, isbn):
        """Return a BookOffer, or None if the book is not found."""

    @abstractmethod
    def _parse_product_page(self, soup, url):
        """Build a BookOffer from an already fetched product page, or None."""

    @abstractmethod
    def _search_url(self, query):
        """URL of the results page for a text query."""

    @abstractmethod
    def _find_cards(self, soup):
        """The result cards (one per book) of a results page."""

    @abstractmethod
    def _parse_card(self, card):
        """Build a BookOffer from one result card, or None if it is incomplete."""

    def _text_queries(self, title, author):
        return [f"{title} {author}".lower()]

    def _is_product_page(self, soup):
        return False

    def _fetch(self, url):
        return get_soup(url)


    def scrape_product_page(self, url):
        soup, final_url = self._fetch(url)
        return self._parse_product_page(soup, final_url) if soup else None

    def search_by_text(self, title, author):
        cards = []
        for query in self._text_queries(title, author):
            soup, url = self._fetch(self._search_url(query))
            if not soup:
                continue

            if self._is_product_page(soup):
                offer = self._parse_product_page(soup, url)
                return [offer] if offer else []

            cards = self._find_cards(soup)
            if cards:
                break

        results = []
        unmatches = 0
        for card in cards:
            if unmatches >= self.MAX_UNMATCHES:
                break

            offer = self._parse_card(card)
            if offer and self._validate_match(title, author, offer.title_found, offer.author_found):
                results.append(offer)
            else:
                unmatches += 1

        return results

    # ----------------------------------------------------------------- helpers

    def absolute_url(self, href):
        return urljoin(self.base_url, href) if href else ""

    def normalized_queries(self, title, author):
        safe_title = normalize(title) or title
        safe_author = normalize(author) or author
        return [f"{safe_title} {safe_author}".lower(), safe_title.lower()]

    def close(self):
        pass

    def _validate_match(self, search_title, search_author, found_title, found_author):
        n_title, n_author = normalize(search_title), normalize(search_author)
        f_title, f_author = normalize(found_title), normalize(found_author)

        if not f_title or not f_author:
            return False

        n_author_words = n_author.split()
        f_author_words = f_author.split()
        author_match = (
            all(w in f_author_words for w in n_author_words) or
            all(w in n_author_words for w in f_author_words)
        )
        if not author_match:
            return False

        raw_n_words = set(re.sub(r'[^\w\s]', ' ', unidecode(search_title.lower())).split())
        raw_f_words = set(re.sub(r'[^\w\s]', ' ', unidecode(found_title.lower())).split())
        sequel_markers = {'2', '3', '4', '5', 'ii', 'iii', 'iv', 'parte', 'pack', 'box', 'conjunto'}

        if any(w in sequel_markers and w not in raw_n_words for w in raw_f_words):
            return False

        if n_title == f_title:
            return True

        n_words = n_title.split()
        f_words = f_title.split()
        if len(f_words) > len(n_words) and f_words[:len(n_words)] == n_words:
            extra_words = f_words[len(n_words):]
            edition_markers = {
                'edicao', 'volume', 'vol', 'bolso', 'capa', 'dura',
                'ilustrada', 'especial', 'comemorativa', 'definitiva', 'integral', 'unico'
            }
            if any(w in edition_markers for w in extra_words):
                return True

        return False