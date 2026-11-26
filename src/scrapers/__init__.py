from .wook import WookScraper
from .bertrand import BertrandScraper
from .fnac import FnacScraper
from .almedina import AlmedinaScraper

SCRAPERS = {
    "wook": WookScraper,
    "bertrand": BertrandScraper,
    "fnac": FnacScraper,
    "almedina": AlmedinaScraper,
}