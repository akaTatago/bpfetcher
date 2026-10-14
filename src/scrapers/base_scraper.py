from abc import ABC, abstractmethod
from src.utils.scraping_helper import normalize

class BaseScraper(ABC):
    def __init__(self, store_name, base_url):
        self.store_name = store_name
        self.base_url = base_url

    @abstractmethod
    def search_by_text(self, title, author):
        pass

    @abstractmethod
    def scrape_by_isbn(self, isbn):
        pass

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

        if n_title == f_title:
            return True

        n_words = n_title.split()
        f_words = f_title.split()

        if len(f_words) > len(n_words) and f_words[:len(n_words)] == n_words:
            extra_words = f_words[len(n_words):]
            
            sequel_markers = {'2', '3', '4', '5', 'ii', 'iii', 'iv', 'parte', 'pack', 'box', 'conjunto'}
            if any(w in sequel_markers for w in extra_words):
                return False
                
            edition_markers = {'edicao', 'volume', 'vol', 'bolso', 'capa', 'dura', 'ilustrada', 'especial', 'comemorativa', 'definitiva', 'integral', 'unico'}
            if any(w in edition_markers for w in extra_words):
                return True

        return False