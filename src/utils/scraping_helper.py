from curl_cffi import requests
from bs4 import BeautifulSoup
from unidecode import unidecode
import time
import random
import re

def get_soup(url):
    try:
        time.sleep(random.uniform(2, 4))
        response = requests.get(url, impersonate="chrome", timeout=15)
        return BeautifulSoup(response.text, "lxml"), response.url
    except Exception as e:
        print(f"Connection error ({url}): {e}")
        return None, None

def clean_text(element):
    if element:
        return element.get_text(separator=" ", strip=True)
    return None

def normalize_isbn(isbn):
    return isbn.replace('-', '').strip()

def normalize(text):
    if not text:
        return None
    
    text = re.sub(r'[\(\[].*?[\)\]]', '', text)
    
    for sep in (' -', ':'):
        if sep in text:
            text = text[:text.find(sep)]
            
    text = unidecode(text.strip().lower())
    return re.sub(r'[^\w\s]', '', text).strip()

def clean_price(element_or_text):
    if not element_or_text:
        return 0.0
    
    text = element_or_text if isinstance(element_or_text, str) else element_or_text.text
    
    clean = text.replace("€", "").replace(",", ".").strip()
    try:
        return float(clean)
    except ValueError:
        return 0.0