import csv
import time

from .utils import (
    fetch_item_list,
    fetch_items_module,
    fetch_equipment_module,
    fetch_thumbnails_bulk,
    fetch_thumbnail_parallel,
    thumbnail_cache,
    save_cache,
    is_available_item,
)


import os
from .utils import DATA_DIR, OUTPUT_DIR

def export_items(output_csv=None):
    if output_csv is None:
        output_csv = os.path.join(DATA_DIR, 'items.csv')
    print('Fetching item list...')
    items = fetch_item_list()
    print(f'Found {len(items)} items')

    print('Downloading full module data...')
    module_items = fetch_items_module()
    equip_items = fetch_equipment_module()
    module_items.update(equip_items)
    print('parsed items count', len(module_items))

    all_titles = sorted(items + list(equip_items.keys()))
    # purge generic urls from cache so they can be refetched
    for k, v in list(thumbnail_cache.items()):
        if v and 'AC_Icon' in v:
            del thumbnail_cache[k]
    missing = [t for t in all_titles if t not in thumbnail_cache]
    if missing:
        print(f'Fetching thumbnails for {len(missing)} entries in bulk...')
        bulk = fetch_thumbnails_bulk(missing)
        thumbnail_cache.update(bulk)
        remaining = [t for t in missing if not thumbnail_cache.get(t)]
        if remaining:
            print(f'Fetching {len(remaining)} remaining thumbnails in parallel...')
            fetch_thumbnail_parallel(remaining)
        save_cache()

    # write into specified output location
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Name', 'Rarity', 'Category', 'Stats', 'Desc', 'Image', 'Available'])
        total = len(all_titles)
        for idx, name in enumerate(all_titles, 1):
            print(f'Processing {idx}/{total} {name}')
            data = module_items.get(name, {})
            rarity = data.get('Rarity', '')
            category_list = data.get('Category', [])
            category = ','.join(category_list)
            desc = data.get('Desc', '')
            stats = ''
            if 'Stats' in data:
                stats_list = []
                for st in data['Stats']:
                    stats_list.append(f"{st.get('Stat')}={st.get('Value')}")
                stats = ';'.join(stats_list)
            img = thumbnail_cache.get(name, '')
            available = is_available_item(name, category_list)
            writer.writerow([name, rarity, category, stats, desc, img, 'true' if available else 'false'])

    print(f'Export complete: {output_csv}')


if __name__ == '__main__':
    export_items()
