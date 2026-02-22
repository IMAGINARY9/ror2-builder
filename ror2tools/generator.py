import csv
import json
import random

import os
from .utils import DATA_DIR, OUTPUT_DIR

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


def generate_pool():
    config = load_config()
    items = load_items()
    rarity_map = build_rarity_map(items)

    print('Configured counts:', config)
    pool = select_pool(rarity_map, config)
    print('\nGenerated pool:')
    for it in pool:
        aspects = categorize_item(it)
        tags = ','.join(it.get('SynergyTags', []))
        plays = ','.join(it.get('Playstyles', []))
        img = it.get('Image', '')
        print(f"- {it['Name']} ({it['Rarity']}) aspects={','.join(aspects)} tags={tags} plays={plays} image={img}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, 'generated_pool.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = ['Name','Rarity','Category','Stats','Desc','Image']
        writer.writerow(header)
        for it in pool:
            writer.writerow([it['Name'], it['Rarity'], it['Category'], it['Stats'], it['Desc'], it.get('Image','')])
    print('\nSaved generated_pool.csv')

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
        f.write('| Name | Rarity | Aspects | Tags | Plays | Image |\n')
        f.write('|------|--------|---------|------|-------|-------|\n')
        for it in pool:
            aspects = ','.join(categorize_item(it))
            tags = ','.join(it.get('SynergyTags', []))
            plays = ','.join(it.get('Playstyles', []))
            img = it.get('Image','')
            img_md = f'<img src="{img}" alt="{it["Name"]}" width="50"/>' if img else ''
            name_colored = color_text(it['Name'], it['Rarity'])
            rarity_colored = color_text(it['Rarity'], it['Rarity'])
            f.write(f'| {name_colored} | {rarity_colored} | {aspects} | {tags} | {plays} | {img_md} |\n')
    print('Saved generated_pool.md (open in editor for visual preview)')


if __name__ == '__main__':
    generate_pool()
