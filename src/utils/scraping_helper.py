import json
import random
import re
import threading
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests
from unidecode import unidecode

AUTHOR_SEPARATOR = " e "
MIN_DELAY, MAX_DELAY = 2, 4

_last_request = {}
_throttle_lock = threading.Lock()


def _throttle(url):
    domain = urlparse(url).netloc
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    with _throttle_lock:
        now = time.monotonic()
        start = max(now, _last_request.get(domain, 0) + delay)
        _last_request[domain] = start
    if start > now:
        time.sleep(start - now)


def get_soup(url, cookies=None, headers=None):
    try:
        _throttle(url)
        response = requests.get(
            url,
            impersonate="chrome",
            cookies=cookies,
            headers=headers,
            timeout=15
        )
        if response.status_code >= 400:
            if response.status_code != 404:
                print(f"HTTP {response.status_code} ({url})")
            return None, None
        return BeautifulSoup(response.text, "lxml"), response.url
    except Exception as e:
        print(f"Connection error ({url}): {e}")
        return None, None

def clean_text(element):
    if element:
        return " ".join(element.get_text(separator=" ").split())
    return None

def has_text(element, needle):
    return needle.casefold() in (clean_text(element) or "").casefold()

def normalize_isbn(isbn):
    return isbn.replace('-', '').strip()

def normalize(text):
    if not text:
        return None
    
    text = re.sub(r'[\(\[].*?[\)\]]', '', text)
    
    for sep in (' -', ':', ' ou '):
        if sep in text:
            text = text[:text.find(sep)]
            
    text = unidecode(text.strip().lower())
    return re.sub(r'[^\w\s]', '', text).strip()

def clean_price(element_or_text):
    if not element_or_text:
        return None

    text = element_or_text if isinstance(element_or_text, str) else element_or_text.text

    clean = text.replace("€", "").replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def parse_int(value):
    try:
        return int(value) or None
    except (TypeError, ValueError):
        return None


def parse_jsonld_product(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            parsed = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict) and isinstance(parsed.get("@graph"), list):
            items = parsed["@graph"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = [parsed]

        for item in items:
            if not isinstance(item, dict):
                continue
            types = item.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if "Product" in types or "Book" in types or "offers" in item:
                return item
    return None

#join author names
def join_authors(names):
    return AUTHOR_SEPARATOR.join(n.strip() for n in names if n and n.strip())

#join authors of a json-ld block
def parse_authors(author_data):
    if not author_data:
        return ""
    if isinstance(author_data, (dict, str)):
        author_data = [author_data]

    return join_authors(
        a.get("name", "") if isinstance(a, dict) else str(a)
        for a in author_data
    )


AVAILABLE_SCHEMA_VALUES = {"InStock", "LimitedAvailability", "OnlineOnly"}


def is_available(availability_url):
    return (availability_url or "").rsplit("/", 1)[-1] in AVAILABLE_SCHEMA_VALUES

def parse_offer(data):
    offers = data.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None, ""

    price = clean_price(str(offers.get("price", "")))
    return price, offers.get("availability", "") or ""