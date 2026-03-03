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
IMAGE_CACHE_FILE = os.path.join(CACHE_DIR, 'item_images.json')
TIP_CACHE_FILE = os.path.join(CACHE_DIR, 'tips_cache.json')

# Simple image cache - just load from static file
try:
    with open(IMAGE_CACHE_FILE, 'r', encoding='utf-8') as f:
        image_cache = json.load(f)
except FileNotFoundError:
    image_cache = {}

try:
    with open(TIP_CACHE_FILE, 'r', encoding='utf-8') as f:
        tips_cache = json.load(f)
except FileNotFoundError:
    tips_cache = {}


def get_item_image(item_name):
    """Get the image URL for an item from the cache."""
    return image_cache.get(item_name, '')


def save_tips_cache():
    with open(TIP_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(tips_cache, f, ensure_ascii=False, indent=2)


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
            graph = json.load(f)
    except FileNotFoundError:
        graph = {}
    
    # Boost internal synergies for playstyles with fewer items
    # This ensures styles like CC compete with frenzy/mobile in optimization
    PLAYSTYLE_BOOSTS = {
        'cc': [
            "Frost Relic", "Chronobauble", "Stun Grenade", "Breaching Fin",
            "Sticky Bomb", "Tri-Tip Dagger", "Gasoline", "Ignition Tank",
            "Electric Boomerang", "Royal Capacitor"
        ],
        'tank': [
            'Aegis', "Ben's Raincoat", 'Repulsion Armor Plate', 'Tougher Times',
            'Personal Shield Generator', 'Rose Buckler', 'Oddly-shaped Opal',
            'Jade Elephant', 'Transcendence', 'Titanic Knurl', 'Planula',
            'Safer Spaces', 'Rejuvenation Rack', 'Infusion', 'Kinetic Dampener',
            'Topaz Brooch', 'Prison Matrix', 'Mired Urn'
        ],
        'summon': [
            'Spare Drone Parts', 'Defense Nucleus', 'Empathy Cores',
            "Queen's Gland", 'The Back-up', 'Squid Polyp', 'Ancestral Incubator',
            'Newly Hatched Zoea', 'Goobo Jr.', 'Halcyon Seed', 'Happiest Mask',
            'Gnarled Woodsprite', 'Elusive Antlers', 'Defiant Gouge'
        ],
        'regen': [
            'Bustling Fungus', 'Cautious Slug', "Harvester's Scythe",
            'Leeching Seed', 'Lepton Daisy', 'Medkit', 'Aegis',
            'Rejuvenation Rack', 'Planula', 'Monster Tooth', 'Infusion',
            'Titanic Knurl', 'Super Massive Leech', 'Gnarled Woodsprite',
            'Corpsebloom', 'Weeping Fungus', 'Foreign Fruit', 'Power Elixir',
            'Interstellar Desk Plant', "N'kuhana's Opinion"
        ],
        'proc': [
            'AtG Missile Mk. 1', 'Ukulele', 'Tri-Tip Dagger', 'Sticky Bomb',
            'Charged Perforator', 'Molten Perforator', 'Sentient Meat Hook',
            'Shatterspleen', 'Needletick', 'Polylute', "Lens-Maker's Glasses",
            "Harvester's Scythe", 'Predatory Instincts', 'Brittle Crown',
            'Deus Ex Machina', 'Runic Lens', 'Noxious Thorn',
            'Symbiotic Scorpion', 'Chance Doll'
        ]
    }
    BOOST_WEIGHT = 3
    
    for style, items_list in PLAYSTYLE_BOOSTS.items():
        for i, item1 in enumerate(items_list):
            if item1 not in graph:
                graph[item1] = {}
            for item2 in items_list[i+1:]:
                if item2 not in graph:
                    graph[item2] = {}
                # Add bidirectional synergy if not already present or if weaker
                if item2 not in graph[item1] or graph[item1][item2] < BOOST_WEIGHT:
                    graph[item1][item2] = BOOST_WEIGHT
                if item1 not in graph[item2] or graph[item2][item1] < BOOST_WEIGHT:
                    graph[item2][item1] = BOOST_WEIGHT
    
    return graph



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

