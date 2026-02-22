import csv
import json
import random
import os
import time
from html import escape

from .utils import DATA_DIR, OUTPUT_DIR, load_synergy_graph
from .scoring import score_pool, score_breakdown

CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
ITEMS_CSV = os.path.join(DATA_DIR, 'items.csv')

REQUIRED_ASPECTS = {'damage', 'movement', 'defense'}


def load_config(path=CONFIG_PATH):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_items(path=ITEMS_CSV):
    items = []
    with open(path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r.get('Rarity'):
                continue
            avail = r.get('Available', 'true').strip().lower()
            if avail not in ('', 'true', '1', 'yes'):
                continue
            # parse new metadata columns into Python structures
            r['Image'] = r.get('Image', '')
            # comma-separated lists may be empty strings
            r['SynergyTags'] = [t for t in r.get('SynergyTags', '').split(',') if t]
            r['Playstyles'] = [p for p in r.get('Playstyles', '').split(',') if p]
            items.append(r)
    return items


def build_pool(items, config, max_attempts=5000):
    """Attempt to build a pool respecting style/size/synergy preferences.

    Falls back to simple rarity-based selection if no advanced keys are present.
    """
    # detect if advanced generation requested
    style = config.get('style')
    size = config.get('size')
    synergy_weight = config.get('synergy_weight', 0)
    if style is None and size is None and not synergy_weight:
        # use legacy selection path
        rarity_map = build_rarity_map(items)
        return select_pool(rarity_map, config, max_attempts)

    # determine desired cardinality
    if size is None:
        # if no explicit size, use sum of rarity counts if present
        size = sum(v for k,v in config.items() if isinstance(v, int) and k not in ('require_tags','require_playstyles'))
    # load graph for scoring
    graph = load_synergy_graph()
    # if the graph does not contain our test items, recompute from the provided list
    if not graph or not set(it['Name'] for it in items).issubset(graph.keys()):
        try:
            from .utils import compute_synergy_graph
            graph = compute_synergy_graph(items)
        except ImportError:
            graph = {}
    best = None
    best_score = -1
    for _ in range(max_attempts):
        if size > len(items):
            break
        candidate = random.sample(items, size)
        sc = score_pool(candidate, graph, style, synergy_weight)
        if sc > best_score:
            best_score = sc
            best = candidate
    return best if best is not None else []


def categorize_item(row):
    aspects = set()
    cat = row.get('Category', '')
    stats = row.get('Stats', '')
    if 'Damage' in cat or 'Damage' in stats or 'damage' in stats.lower():
        aspects.add('damage')
    if 'Speed' in stats or 'speed' in stats.lower() or 'Quail' in row['Name']:
        aspects.add('movement')
    if 'Health' in stats or 'Heal' in stats or 'Healing' in cat:
        aspects.add('defense')
    if 'Utility' in cat:
        aspects.add('utility')
    return aspects


def build_rarity_map(items):
    mapping = {}
    for it in items:
        mapping.setdefault(it['Rarity'], []).append(it)
    return mapping


def satisfies_config(item, config):
    """Return True if the given item meets tag/playstyle constraints in config."""
    # config may include optional lists 'require_tags' and 'require_playstyles'
    req_tags = set(config.get('require_tags', []))
    req_play = set(config.get('require_playstyles', []))
    if req_tags:
        # item must have at least one of the required tags
        if not req_tags.intersection(item.get('SynergyTags', [])):
            return False
    if req_play:
        if not req_play.intersection(item.get('Playstyles', [])):
            return False
    return True


def select_pool(rarity_map, config, max_attempts=1000):
    pool = []
    # build a filtered map to avoid repeating the same check every attempt
    filtered_map = {}
    for rarity, items in rarity_map.items():
        filtered_map[rarity] = [it for it in items if satisfies_config(it, config)]

    for attempt in range(max_attempts):
        pool = []
        for rarity, count in config.items():
            # skip our special config keys
            if rarity in ('require_tags', 'require_playstyles', 'exclude_tags', 'exclude_playstyles'):
                continue
            candidates = filtered_map.get(rarity, [])
            if not candidates or count <= 0:
                continue
            pool.extend(random.sample(candidates, min(count, len(candidates))))
        aspects = set()
        for it in pool:
            aspects |= categorize_item(it)
        if REQUIRED_ASPECTS.issubset(aspects):
            return pool
    return pool


def generate_pool(config=None):
    """Generate a pool and write output in Markdown format.

    The resulting CSV/Markdown includes columns for Name, Rarity, Aspects,
    Tags, Plays, and Image.  "Plays" refers to playstyle keywords derived
    from the item's synergies (e.g. 'frenzy', 'cc', or 'mobile').

    ``generate_pool`` uses whatever keys are present in the provided
    configuration.  If only rarity counts are given it falls back to the
    legacy simple generator (same as `main.py generate`).  Advanced options
    such as `style`, `size`, and `synergy_weight` are used only when present.

    For richer styling users can convert the resulting `.md` file to HTML
    using external tools such as pandoc.  No web technologies are required.
    """
    if config is None:
        config = load_config()
    items = load_items()

    print('Configuration:', config)
    pool = build_pool(items, config)
    # if any advanced parameters exist, compute and show score
    if config.get('style') or config.get('synergy_weight', 0) or config.get('size'):
        total_score = score_pool(pool, load_synergy_graph(), config.get('style'), config.get('synergy_weight',0))
        print(f'Pool score: {total_score}')
    print('\nGenerated pool:')
    for it in pool:
        tag_list = it.get('SynergyTags', [])[:]
        plays_list = it.get('Playstyles', [])
        if plays_list:
            tag_list.append('(' + ','.join(plays_list) + ')')
        tags = ','.join(tag_list)
        img = it.get('Image', '')
        print(f"- {it['Name']} ({it['Rarity']}) tags={tags} image={img}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, 'generated_pool.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['Name','Rarity','Category','Stats','Desc','Image']
        writer.writerow(header)
        for it in pool:
            writer.writerow([
                it.get('Name',''),
                it.get('Rarity',''),
                it.get('Category',''),
                it.get('Stats',''),
                it.get('Desc',''),
                it.get('Image','')
            ])
    print('\nSaved generated_pool.csv')

    # compute score once for possible use in outputs
    score = 0
    if config.get('style') or config.get('synergy_weight', 0) or config.get('size'):
        score = score_pool(pool, load_synergy_graph(), config.get('style'), config.get('synergy_weight',0))

    def color_text(text, rarity):
        colors = {
            'Common': '#FFFFFF',
            'Uncommon': '#50C878',
            'Legendary': '#FF4500',
            'Boss': '#FFD700',
            'Lunar': '#6699FF',
            'Void': '#800080',
            'Equipment': '#FFA500',
            'Elite Equipment': '#FF8C00',
            'Lunar Equipment': '#00CED1'
        }
        col = colors.get(rarity, '')
        return f'<span style="color:{col}">{text}</span>' if col else text

    md_path = os.path.join(OUTPUT_DIR, 'generated_pool.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('# Generated Item Pool\n\n')
        f.write(f'Pool score: {score}\n\n' if score else '')
        f.write('| Name | Rarity | Tags | Image |\n')
        f.write('|------|--------|------|-------|\n')
        for it in pool:
            aspects = ','.join(categorize_item(it))
            tag_list = it.get('SynergyTags', [])[:]
            plays_list = it.get('Playstyles', [])
            if plays_list:
                # include playstyles in tags parenthetically
                tag_list.append('(' + ','.join(plays_list) + ')')
            # omit overly generic tags from display
            display_blacklist = {'damage', 'utility', 'healing'}
            tag_list = [t for t in tag_list if t not in display_blacklist]
            # wrap each tag/entry in backticks to highlight
            tags = ', '.join(f'`{t}`' for t in tag_list if t)
            img = it.get('Image','')
            img_md = f'<img src="{img}" alt="{it["Name"]}" width="50"/>' if img else ''
            name_colored = color_text(it['Name'], it['Rarity'])
            rarity_colored = color_text(it['Rarity'], it['Rarity'])
            f.write(f'| {name_colored} | {rarity_colored} | {tags} | {img_md} |\n')
    print('Saved generated_pool.md (open in editor for visual preview)')
    return pool


def export_pool_files(pool, score=0):
    """
    Export a pool to CSV and Markdown files.
    
    Args:
        pool: List of item dictionaries
        score: Optional pool score to include in output
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Export CSV
    csv_path = os.path.join(OUTPUT_DIR, 'generated_pool.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['Name', 'Rarity', 'Category', 'Stats', 'Desc', 'Image']
        writer.writerow(header)
        for it in pool:
            writer.writerow([
                it.get('Name', ''),
                it.get('Rarity', ''),
                it.get('Category', ''),
                it.get('Stats', ''),
                it.get('Desc', ''),
                it.get('Image', '')
            ])
    
    # Export Markdown
    def color_text(text, rarity):
        colors = {
            'Common': '#FFFFFF',
            'Uncommon': '#50C878',
            'Legendary': '#FF4500',
            'Boss': '#FFD700',
            'Lunar': '#6699FF',
            'Void': '#800080',
            'Equipment': '#FFA500',
            'Elite Equipment': '#FF8C00',
            'Lunar Equipment': '#00CED1'
        }
        col = colors.get(rarity, '')
        return f'<span style="color:{col}">{text}</span>' if col else text
    
    md_path = os.path.join(OUTPUT_DIR, 'generated_pool.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('# Generated Item Pool\n\n')
        if score:
            f.write(f'Pool score: {score:.2f}\n\n')
        f.write('| Name | Rarity | Tags | Image |\n')
        f.write('|------|--------|------|-------|\n')
        for it in pool:
            tag_list = it.get('SynergyTags', [])[:]
            plays_list = it.get('Playstyles', [])
            if plays_list:
                tag_list.append('(' + ','.join(plays_list) + ')')
            # omit overly generic tags from display
            display_blacklist = {'damage', 'utility', 'healing'}
            tag_list = [t for t in tag_list if t not in display_blacklist]
            tags = ', '.join(f'`{t}`' for t in tag_list if t)
            img = it.get('Image', '')
            img_md = f'<img src="{img}" alt="{it["Name"]}" width="50"/>' if img else ''
            name_colored = color_text(it['Name'], it['Rarity'])
            rarity_colored = color_text(it['Rarity'], it['Rarity'])
            f.write(f'| {name_colored} | {rarity_colored} | {tags} | {img_md} |\n')
