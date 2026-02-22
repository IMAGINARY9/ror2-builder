import os
import csv
import requests
from bs4 import BeautifulSoup
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# directory layout
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CACHE_DIR = os.path.join(BASE_DIR, 'cache')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

API_URL = 'https://riskofrain2.fandom.com/api.php'
CACHE_FILE = os.path.join(CACHE_DIR, 'thumbnail_cache.json')

# thumbnail cache shared by modules
try:
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        thumbnail_cache = json.load(f)
except FileNotFoundError:
    thumbnail_cache = {}


def save_cache():
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(thumbnail_cache, f, ensure_ascii=False, indent=2)


def fetch_wiki_tips(title):
    """Return the text of the first "Tips" or "Usage" subsection on the item page."""
    params = {'action': 'parse', 'page': title, 'format': 'json', 'prop': 'sections'}
    resp = requests.get(API_URL, params=params)
    resp.raise_for_status()
    sections = resp.json().get('parse', {}).get('sections', [])
    idx = None
    for sec in sections:
        if sec.get('line', '').lower() in ('tips', 'usage'):
            idx = sec.get('index')
            break
    if not idx:
        return ''
    # now request that specific section HTML
    params2 = {'action': 'parse', 'page': title, 'format': 'json',
               'prop': 'text', 'section': idx}
    resp2 = requests.get(API_URL, params=params2)
    resp2.raise_for_status()
    html = resp2.json()['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(separator=' ', strip=True)


def compute_synergy_tags(category_list, desc):
    tags = set()
    # simple heuristics
    if any('OnKill' in c for c in category_list) or 'kill' in desc.lower():
        tags.add('on-kill')
    if 'crit' in desc.lower() or 'critical' in desc.lower():
        tags.add('crit')
    if 'slow' in desc.lower() or 'stun' in desc.lower():
        tags.add('crowd-control')
    if 'speed' in desc.lower() or 'movement' in category_list:
        tags.add('movement')
    # more rules can be added later
    return tags


def compute_playstyles(category_list, synergy_tags):
    styles = set()
    if 'on-kill' in synergy_tags:
        styles.add('frenzy')
    if 'crowd-control' in synergy_tags:
        styles.add('cc')
    if 'movement' in synergy_tags:
        styles.add('mobile')
    return styles


def compute_synergy_graph(items):
    """Build a simple adjacency map based on shared synergy tags.

    `items` should be an iterable of dictionaries each containing at least
    'Name' and 'SynergyTags' (a list).
    The returned graph is a dict mapping item name to another dict of
    neighboring item names with a weight (number of shared tags).
    """
    graph = {}
    for a in items:
        name_a = a.get('Name')
        tags_a = set(a.get('SynergyTags', []))
        graph[name_a] = {}
        for b in items:
            name_b = b.get('Name')
            if name_a == name_b:
                continue
            shared = tags_a.intersection(b.get('SynergyTags', []))
            if shared:
                graph[name_a][name_b] = len(shared)
    return graph


def load_synergy_graph(path=None):
    if path is None:
        path = os.path.join(DATA_DIR, 'synergy.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def is_generic_thumb(url):
    # these patterns indicate non-item icons or placeholders
    return ('AC_Icon' in url
            or '57_Leaf_Clover.png' in url
            or 'Concept_Art' in url)


def lua_parse_items_module(text):
    items = {}
    # iterate through each declaration (items or equipment)
    pattern = re.compile(r'(?:items|equipment)\["(.+?)"\]\s*=\s*\{')
    idx = 0
    while True:
        m = pattern.search(text, idx)
        if not m:
            break
        name = m.group(1)
        # find full block braces
        start = m.end() - 1
        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        block = text[start:end+1]
        data = {}
        rar = re.search(r'Rarity\s*=\s*"([^"]+)"', block)
        if rar:
            data['Rarity'] = rar.group(1)
        desc = re.search(r'Desc\s*=\s*"([^"]+)"', block)
        if desc:
            data['Desc'] = desc.group(1)
        cats = re.findall(r'Category\s*=\s*\{([^\}]+)\}', block)
        if cats:
            entries = re.findall(r'"([^\"]+)"', cats[0])
            data['Category'] = entries
        stats_block = re.search(r'Stats\s*=\s*\{([^\}]*)\}', block, re.DOTALL)
        if stats_block:
            stat_list = []
            for statentry in re.finditer(r'Stat\s*=\s*"([^\"]+)".*?Value\s*=\s*"([^\"]+)"', stats_block.group(1), re.DOTALL):
                stat_list.append({'Stat': statentry.group(1), 'Value': statentry.group(2)})
            data['Stats'] = stat_list
        items[name] = data
        idx = end + 1
    return items


def fetch_item_list():
    params = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': 'Category:Items',
        'cmlimit': 'max',
        'format': 'json'
    }
    resp = requests.get(API_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    return [entry['title'] for entry in data['query']['categorymembers']
            if ':' not in entry['title'] and entry['title'] != 'Items']


def fetch_item_description(name):
    params = {'action': 'parse', 'page': name, 'format': 'json', 'prop': 'text'}
    resp = requests.get(API_URL, params=params)
    resp.raise_for_status()
    html = resp.json()['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')
    div = soup.find('div', {'class': 'mw-parser-output'})
    if not div:
        return ''
    for p in div.find_all('p', recursive=False):
        text = p.get_text(separator=' ', strip=True)
        if text:
            return text
    return ''


def fetch_module(name):
    params = {'action': 'query', 'prop': 'revisions', 'titles': name,
              'rvslots': '*', 'rvprop': 'content', 'format': 'json'}
    resp = requests.get(API_URL, params=params)
    resp.raise_for_status()
    page = list(resp.json()['query']['pages'].values())[0]
    lua_text = page['revisions'][0]['slots']['main']['*']
    return lua_parse_items_module(lua_text)


def fetch_items_module():
    return fetch_module('Module:Items/Data')


def fetch_equipment_module():
    return fetch_module('Module:Equipment/Data')


def fetch_thumbnails_bulk(titles, size=200):
    result = {}
    chunk_size = 50
    for i in range(0, len(titles), chunk_size):
        subset = titles[i:i+chunk_size]
        params = {'action': 'query', 'titles': '|'.join(subset),
                  'prop': 'pageimages', 'pithumbsize': size, 'format': 'json'}
        resp = requests.get(API_URL, params=params)
        resp.raise_for_status()
        pages = resp.json().get('query', {}).get('pages', {})
        for p in pages.values():
            title = p.get('title')
            if 'thumbnail' in p:
                url = p['thumbnail']['source']
                if not is_generic_thumb(url):
                    result[title] = url
    return result


def fetch_thumbnail_parallel(titles):
    def worker(title):
        url = fetch_thumbnail(title)
        thumbnail_cache[title] = url
        return title

    with ThreadPoolExecutor(max_workers=10) as exe:
        futures = {exe.submit(worker, t): t for t in titles}
        for i, fut in enumerate(as_completed(futures), 1):
            t = futures[fut]
            try:
                fut.result()
            except Exception:
                thumbnail_cache[t] = ''
            print(f"thumbnail fetched {i}/{len(titles)}: {t}", end='\r')
    print()
    save_cache()


def fetch_thumbnail(title, size=200):
    # same code from previous script omitted for brevity; copy entire function body
    params = {'action': 'query', 'titles': title, 'prop': 'pageimages',
              'pithumbsize': size, 'format': 'json'}
    resp = requests.get(API_URL, params=params)
    resp.raise_for_status()
    pages = resp.json().get('query', {}).get('pages', {})
    for p in pages.values():
        if 'thumbnail' in p:
            url = p['thumbnail']['source']
            if not is_generic_thumb(url):
                return url
    for ext in ['png', 'jpg']:
        for sep in [' ', '_']:
            fname = f'File:{title.replace(" ", sep)}.{ext}'
            params2 = {'action': 'query', 'titles': fname, 'prop': 'imageinfo',
                       'iiprop': 'url', 'format': 'json'}
            resp2 = requests.get(API_URL, params=params2)
            resp2.raise_for_status()
            for q in resp2.json().get('query', {}).get('pages', {}).values():
                if 'imageinfo' in q:
                    url = q['imageinfo'][0].get('url','')
                    if url and not is_generic_thumb(url):
                        return url
    params2 = {'action': 'query', 'titles': title, 'prop': 'images', 'format': 'json'}
    resp2 = requests.get(API_URL, params=params2)
    resp2.raise_for_status()
    imgs = []
    for p in resp2.json().get('query', {}).get('pages', {}).values():
        for img in p.get('images', []):
            imgs.append(img.get('title'))
    base = title.replace(' ', '_').lower()
    for fname in imgs:
        low = fname.lower()
        if base in low and low.endswith(('.png', '.jpg', '.gif')) and not low.startswith('file:category'):
            params3 = {'action': 'query', 'titles': fname, 'prop': 'imageinfo',
                       'iiprop': 'url', 'format': 'json'}
            resp3 = requests.get(API_URL, params=params3)
            resp3.raise_for_status()
            for q in resp3.json().get('query', {}).get('pages', {}).values():
                if 'imageinfo' in q:
                    url = q['imageinfo'][0].get('url','')
                    return url
    for fname in imgs:
        low = fname.lower()
        if low.endswith(('.png', '.jpg', '.gif')) and not low.startswith('file:category'):
            params3 = {'action': 'query', 'titles': fname, 'prop': 'imageinfo',
                       'iiprop': 'url', 'format': 'json'}
            resp3 = requests.get(API_URL, params=params3)
            resp3.raise_for_status()
            for q in resp3.json().get('query', {}).get('pages', {}).values():
                if 'imageinfo' in q:
                    url = q['imageinfo'][0].get('url','')
                    if '57_Leaf_Clover' not in url:
                        return url
    base = title.replace(' ', '_')
    for ext in ['png', 'jpg']:
        fname = f'File:{base}.{ext}'
        params4 = {'action': 'query', 'titles': fname, 'prop': 'imageinfo',
                   'iiprop': 'url', 'format': 'json'}
        resp4 = requests.get(API_URL, params=params4)
        resp4.raise_for_status()
        for q in resp4.json().get('query', {}).get('pages', {}).values():
            if 'imageinfo' in q:
                return q['imageinfo'][0].get('url','')
    # md5 fallback
    import hashlib
    fn = base
    h = hashlib.md5(fn.encode('utf-8')).hexdigest()
    for ext in ['png', 'jpg']:
        url = f'https://static.wikia.nocookie.net/riskofrain2_gamepedia_en/images/{h[0]}/{h[:2]}/{fn}.{ext}'
        try:
            r = requests.head(url)
            if r.status_code == 200:
                return url
        except Exception:
            pass
    return ''


def is_available_item(name, category_list):
    if any('Scrap' in name for _ in [None]):
        return False
    if 'Key' in name:
        return False
    if any('Scrap' in c for c in category_list):
        return False
    if 'WorldUnique' in category_list:
        return False
    return True
