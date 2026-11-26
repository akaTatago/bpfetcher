from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.utils.scraping_helper import parse_authors, parse_offer, parse_int


class Status(str, Enum):
    AVAILABLE = "Available"
    UNAVAILABLE = "Unavailable"
    NOT_FOUND = "Not found"
    BLOCKED = "Blocked"      # the store refused us (403, 429, CAPTCHA...)
    ERROR = "Error"          # the store failed or could not be read
    SKIPPED = "Skipped"      # store disabled after repeated failures

    @classmethod
    def from_bool(cls, available):
        return cls.AVAILABLE if available else cls.UNAVAILABLE


@dataclass
class BookOffer:
    store: str
    title_found: str = ""
    author_found: str = ""
    price: Optional[float] = None
    pages: Optional[int] = None
    on_sale: bool = False
    status: Status = Status.UNAVAILABLE
    link: str = ""

    #placeholder row for not returned books
    @classmethod
    def not_found(cls):
        return cls(store="N/A", status=Status.NOT_FOUND)

    #json-ld clock common fields
    @classmethod
    def from_jsonld(cls, store, data, link):
        price, _ = parse_offer(data)
        return cls(
            store=store,
            title_found=data.get("name", ""),
            author_found=parse_authors(data.get("author")),
            price=price,
            pages=parse_int(data.get("numberOfPages")),
            link=link,
        )

    @classmethod
    def missing(cls, store, status=Status.NOT_FOUND):
        return cls(store=store, status=status)

    #csv columns in output order
    def to_row(self):
        return {
            "Store": self.store,
            "Title Found": self.title_found,
            "Author Found": self.author_found,
            "Status": self.status.value,
            "Price": self.price,
            "Pages": self.pages,
            "On Sale": "Yes" if self.on_sale else "No",
            "Link": self.link,
        }