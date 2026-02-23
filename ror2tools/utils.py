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
TIP_CACHE_FILE = os.path.join(CACHE_DIR, 'tips_cache.json')

# thumbnail cache shared by modules
try:
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        thumbnail_cache = json.load(f)
except FileNotFoundError:
    thumbnail_cache = {}

try:
    with open(TIP_CACHE_FILE, 'r', encoding='utf-8') as f:
        tips_cache = json.load(f)
except FileNotFoundError:
    tips_cache = {}


def save_cache():
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(thumbnail_cache, f, ensure_ascii=False, indent=2)

def save_tips_cache():
    with open(TIP_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(tips_cache, f, ensure_ascii=False, indent=2)


def normalize_image_url(raw_url: str) -> str:
    """Return a cleaned, https image URL or placeholder.

    Strips resizing segments (`/scale-to-width-down/...`), ensures the
    protocol is HTTPS, and rejects clearly incorrect pictures by
    falling back to the Squid‑Polyp placeholder. Maintains any
    timestamp present (`?cb=...`).
    """
    placeholder = (
        "https://static.wikia.nocookie.net/riskofrain2_gamepedia_en/images/d/de/"
        "Squid_Polyp.png/revision/latest?cb=20210329071113"
    )
    if not raw_url:
        return placeholder
    url = raw_url.strip()
    # enforce https
    if url.startswith('http://'):
        url = 'https://' + url.split('://', 1)[1]
    # remove any scale-to-width-down fragments
    url = re.sub(r'/revision/latest/scale-to-width-down/[^?]+', '/revision/latest', url)
    # verify filename extension
    m = re.search(r'/([^/]+\.(png|jpg))', url, flags=re.IGNORECASE)
    if not m:
        return placeholder
    fname = m.group(1)
    # if the file name looks like a squiddy placeholder or weird personal photo
    if 'jaime' in fname.lower() or 'garcia' in fname.lower() or 'squid.jpg' in fname.lower():
        return placeholder
    return url


def fetch_wiki_tips(title):
    """Return the text of the first "Tips" or "Usage" subsection on the item page."""
    if title in tips_cache:
        return tips_cache[title]
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
    text = soup.get_text(separator=' ', strip=True)
    tips_cache[title] = text
    save_tips_cache()
    return text


def compute_synergy_tags(category_list, desc, stats_list=None):
    """Return a set of low‑level keywords for the item.

    We derive tags from multiple sources:
    * category entries (lowercased)
    * keywords found in the description text
    * stat names from the Lua module (if provided)

    Tags should be fairly specific so that the synergy graph doesn't
    collapse into a giant clique.
    """
    tags = set()
    # include categories themselves as tags (normalize lower)
    for c in category_list:
        tags.add(c.lower())
    # remove undesirable tokens
    cleaned = set()
    for t in tags:
        tnorm = t.strip().lower()
        # ignore technical garbage and blacklist/shrine markers, and generic "effect"
        if any(x in tnorm for x in ('blacklist', 'shrine', 'worldunique', 'ai', 'effect')):
            continue
        # drop generic categories that are too broad
        if tnorm in ('utility','damage','healing'):
            continue
        # drop empty or numeric-only tags
        if not tnorm or tnorm.isdigit():
            continue
        cleaned.add(tnorm)
    tags = cleaned

    # description-based heuristics
    d = desc.lower()
    if any('onkill' in c.lower() for c in category_list) or 'kill' in d:
        tags.add('on-kill')
    if 'crit' in d or 'critical' in d:
        tags.add('crit')
    if 'slow' in d or 'stun' in d or 'freeze' in d:
        tags.add('crowd-control')
    if 'speed' in d or 'movement' in category_list:
        tags.add('movement')
    if 'heal' in d or 'health' in d or 'barrier' in d:
        tags.add('healing')
    if 'armor' in d or 'protection' in d:
        tags.add('armor')
    if 'cooldown' in d or 'delay' in d:
        tags.add('cooldown')
    if 'area' in d or 'aoe' in d or 'radius' in d:
        tags.add('area')
    # stats-based tags
    if stats_list:
        for st in stats_list:
            statname = st.get('Stat','').lower()
            if statname:
                tags.add(statname.replace(' ','-'))
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


def compute_tag_frequencies(items):
    """Return Counter of how often each synergy tag appears in the item list."""
    from collections import Counter
    freq = Counter()
    for a in items:
        for t in a.get('SynergyTags', []):
            freq[t] += 1
    return freq


def compute_synergy_graph(items, min_freq=1, max_freq_ratio=0.25, ignore_tags=None):
    """Build an adjacency map but ignore tags that are too rare/common.

    *Tags* with frequency < *min_freq* or > *max_freq_ratio* × len(items) are
    dropped before computing shared-tag weights.  A list of additional
    `ignore_tags` may also be provided (these are removed regardless of
    frequency).  By default we also ignore the most generic combat tags
    (`utility`, `damage`, `healing`).
    """
    freq = compute_tag_frequencies(items)
    n = len(items)
    # when dataset is very small the ratio filter becomes too strict
    # (e.g. 0.25*3 = 0.75), so we only apply it if the threshold >= 1.
    if max_freq_ratio * n < 1:
        allowed = {t for t,c in freq.items() if c >= min_freq}
    else:
        allowed = {t for t,c in freq.items() if c >= min_freq and c <= max_freq_ratio * n}
    # always exclude extremely generic tags
    allowed -= {'utility', 'damage', 'healing'}
    if ignore_tags:
        allowed -= set(ignore_tags)
    graph = {}
    for a in items:
        name_a = a.get('Name')
        tags_a = set(a.get('SynergyTags', [])) & allowed
        graph[name_a] = {}
        for b in items:
            name_b = b.get('Name')
            if name_a == name_b:
                continue
            shared = tags_a & (set(b.get('SynergyTags', [])) & allowed)
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
    # these patterns indicate non-item icons, placeholders, or unrelated graphics
    if not url:
        return True
    low = url.lower()
    # common placeholders or irrelevant assets
    generic_tokens = [
        'ac_icon',
        '57_leaf_clover.png',
        'concept_art',
        '_graph_',       # many items have a graph image instead of their icon
        'railgunner_issue',
        'plot_',
        'stats',
        'issue',
        'survivors.png', # stage/character artwork
        'logbook',       # informational images
        # additional tokens discovered during export debugging
        'moment',        # generic "A Moment, Fractured" placeholder
        'fractured',     # part of the bad filename
        'boost',         # boosthp/boostdamage debug entries
        'drizzleplayer', # non-item placeholder names
        'healthdecay',   # placeholder entry
        'ghost',         # placeholder entry
        'abandoned_aqueduct', # wiki often returns a random stage image
        'abyssal_',      # stage backgrounds like Abyssal_Depths
        'siren',         # Siren's Call screenshot
        'graveyard',     # Ship Graveyard etc
        'sundered',      # Sundered Grove
        'sky_meadow',    # Sky Meadow background
        'acrid.png',      # API returns Acrid icon when no thumbnail exists
    ]
    return any(tok in low for tok in generic_tokens)


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



# a couple of helper routines to avoid hitting the API when a URL can be
# constructed deterministically.  the wiki stores images under a pair of
# directory names derived from the file name; historically this was the first
# letter and the first two letters, but the canonical scheme today is the
# md5 hash of the filename.  we try the simpler letter-based location first
# (what the user described) and fall back to the md5 path if necessary.

def _build_simple_image_urls(title):
    """Yield candidate URLs for the given wiki title.

    The caller is responsible for checking the URL via a HEAD request.  We
    return both the naive letter-based path (which often works) and the
    md5-hash path used by the fandom CDN.
    """
    fn = title.replace(' ', '_')
    # first try plain directories based on the name characters
    first = fn[0].lower() if fn else ''
    first2 = fn[:2].lower() if len(fn) >= 2 else first
    for ext in ('png', 'jpg'):
        yield f'https://static.wikia.nocookie.net/riskofrain2_gamepedia_en/images/{first}/{first2}/{fn}.{ext}'
    # now the md5-based path
    import hashlib
    h = hashlib.md5(fn.encode('utf-8')).hexdigest()
    for ext in ('png', 'jpg'):
        yield f'https://static.wikia.nocookie.net/riskofrain2_gamepedia_en/images/{h[0]}/{h[:2]}/{fn}.{ext}'


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
            # try to construct a URL before trusting the API result; this is not
            # faster than the bulk query itself but avoids returning placeholders
            # on missing pages and keeps subsequent runs deterministic.
            for candidate in _build_simple_image_urls(title):
                try:
                    r = requests.head(candidate)
                    if r.status_code == 200 and not is_generic_thumb(candidate):
                        result[title] = candidate
                        break
                except Exception:
                    pass
            else:
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
    # First try deterministic paths that don't require an API call.  This
    # covers the pattern the user mentioned (first-letter/first-two-letters)
    # as well as the md5-hash based layout used by the CDN.
    for candidate in _build_simple_image_urls(title):
        try:
            r = requests.head(candidate)
            if r.status_code == 200 and not is_generic_thumb(candidate):
                return candidate
        except Exception:
            pass
    # fall back to API queries for anything more complicated
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
                    if '57_Leaf_Clover' not in url and not is_generic_thumb(url):
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
                url = q['imageinfo'][0].get('url','')
                if not is_generic_thumb(url):
                    return url
    # attempt to scrape wiki page for an appropriate icon
    try:
        pageurl = f"https://riskofrain2.fandom.com/wiki/{title.replace(' ', '_')}"
        resp_page = requests.get(pageurl)
        resp_page.raise_for_status()
        soup = BeautifulSoup(resp_page.text, 'html.parser')
        for img in soup.find_all('img'):
            src = img.get('src','')
            if title.replace(' ','_').lower() in src.lower() and not is_generic_thumb(src):
                return src
    except Exception:
        pass
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
    # filter out developer/debug or otherwise unusable items
    # - the API often lists hidden/test entries which are not relevant to players
    # - stages, keys, scraps, or worldunique items are also excluded
    if any('Scrap' in name for _ in [None]):
        return False
    if 'Key' in name:
        return False
    if any('Scrap' in c for c in category_list):
        return False
    # hide any items explicitly marked hidden or debug in the category list
    if any('Hidden' in c or 'Debug' in c for c in category_list):
        return False
    if 'WorldUnique' in category_list:
        return False
    return True
