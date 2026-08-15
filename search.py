import requests
import random
import re
import urllib.parse
import threading
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, wait
from requests.adapters import HTTPAdapter
import warnings

warnings.filterwarnings("ignore")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Mozilla/5.0 (X11; Linux i686; rv:137.0) Gecko/20100101 Firefox/137.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.3179.54",
]

# Prioritized dark web search engines (most reliable top-tier engines first)
SEARCH_ENGINES = [
    {"name": "Ahmia Web", "url": "https://ahmia.fi/search/?q={query}"},
    {"name": "Ahmia Onion", "url": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={query}"},
    {"name": "Tor66", "url": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q={query}"},
    {"name": "TorNet", "url": "http://tornetupfu7gcgidt33ftnungxzyfq2pygui5qdoyss34xbgx2qruzid.onion/search?q={query}"},
    {"name": "Onionway", "url": "http://oniwayzz74cv2puhsgx4dpjwieww4wdphsydqvf5q7eyz4myjvyw26ad.onion/search.php?s={query}"},
    {"name": "Amnesia", "url": "http://amnesia7u5odx5xbwtpnqk3edybgud5bmiagu75bnqx2crntw5kry7ad.onion/search?query={query}"},
    {"name": "Excavator", "url": "http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search?query={query}"},
    {"name": "The Deep Searches", "url": "http://searchgf7gdtauh7bhnbyed4ivxqmuoat3nm6zfrg3ymkq6mtnpye3ad.onion/search?q={query}"},
    {"name": "Torland", "url": "http://torlbmqwtudkorme6prgfpmsnile7ug2zm4u3ejpcncxuhpu4k2j4kyd.onion/index.php?a=search&q={query}"},
    {"name": "OnionLand", "url": "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={query}"},
]

DEFAULT_SEARCH_ENGINES = [e["url"] for e in SEARCH_ENGINES]

ENGINE_DOMAINS = {
    "ahmia.fi",
    "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
    "tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion",
    "tornetupfu7gcgidt33ftnungxzyfq2pygui5qdoyss34xbgx2qruzid.onion",
    "oniwayzz74cv2puhsgx4dpjwieww4wdphsydqvf5q7eyz4myjvyw26ad.onion",
    "amnesia7u5odx5xbwtpnqk3edybgud5bmiagu75bnqx2crntw5kry7ad.onion",
    "2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion",
    "searchgf7gdtauh7bhnbyed4ivxqmuoat3nm6zfrg3ymkq6mtnpye3ad.onion",
    "torlbmqwtudkorme6prgfpmsnile7ug2zm4u3ejpcncxuhpu4k2j4kyd.onion",
    "3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion",
}

_thread_local = threading.local()

def get_tor_session():
    if not hasattr(_thread_local, "tor_session"):
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.proxies = {
            "http": "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050"
        }
        _thread_local.tor_session = session
    return _thread_local.tor_session

def _extract_onion_url(raw_str):
    """Extract and unquote a clean .onion URL from any raw href or text."""
    if not raw_str:
        return None
    decoded = urllib.parse.unquote(raw_str)
    matches = re.findall(r'https?:\/\/[a-z0-9\.\-]+\.onion[^\s"\'<>]*', decoded)
    if matches:
        clean = matches[0].strip(").,;\"'")
        for eng in ENGINE_DOMAINS:
            if eng in clean and ("/search" in clean or clean.endswith(eng) or clean.endswith(eng + "/")):
                return None
        return clean
    standalone = re.findall(r'[a-z2-7]{16,56}\.onion(?:[^\s"\'<>]*)?', decoded)
    if standalone:
        clean = "http://" + standalone[0].strip(").,;\"'")
        for eng in ENGINE_DOMAINS:
            if eng in clean:
                return None
        return clean
    return None

def fetch_search_results(endpoint, query):
    url = endpoint.format(query=urllib.parse.quote_plus(query))
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
    }
    session = get_tor_session()
    
    try:
        response = session.get(url, headers=headers, timeout=(5, 10))
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            links = []
            seen_in_page = set()

            for a in soup.find_all('a'):
                try:
                    href = a.get('href', '')
                    title = a.get_text(strip=True)
                    clean_url = _extract_onion_url(href)
                    if not clean_url:
                        clean_url = _extract_onion_url(title)
                    
                    if clean_url and clean_url not in seen_in_page:
                        seen_in_page.add(clean_url)
                        if not title or len(title) < 2:
                            title = clean_url
                        links.append({"title": title, "link": clean_url})
                except Exception:
                    continue

            if not links:
                for cite in soup.find_all(['cite', 'span', 'p', 'div', 'h4']):
                    text = cite.get_text(strip=True)
                    clean_url = _extract_onion_url(text)
                    if clean_url and clean_url not in seen_in_page:
                        seen_in_page.add(clean_url)
                        links.append({"title": text[:60], "link": clean_url})

            return links
        return []
    except Exception:
        return []

def get_search_results(refined_query, max_workers=16, global_timeout=12):
    results = []
    workers = max(1, min(len(DEFAULT_SEARCH_ENGINES), int(max_workers)))
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(fetch_search_results, endpoint, refined_query)
                   for endpoint in DEFAULT_SEARCH_ENGINES]
        done, not_done = wait(futures, timeout=global_timeout)
        for f in not_done:
            f.cancel()
        for future in done:
            try:
                result_urls = future.result()
                if result_urls:
                    results.extend(result_urls)
            except Exception:
                continue
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            executor.shutdown(wait=False)

    # Deduplicate results
    seen_links = set()
    unique_results = []
    for res in results:
        link = res.get("link", "").rstrip('/')
        if link and link not in seen_links:
            seen_links.add(link)
            unique_results.append(res)
            
    return unique_results
