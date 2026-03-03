import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .utils import (
    fetch_item_list,
    fetch_items_module,
    fetch_equipment_module,
    get_item_image,
    is_available_item,
)


import os
import json
from .utils import DATA_DIR, OUTPUT_DIR, fetch_wiki_tips, compute_synergy_tags, compute_playstyles
from .generator import load_config

# Equipment items do not carry Category data in the Lua module, so we maintain
# a curated fallback mapping.  Keys are the canonical wiki item names; values
# are comma-separated Damage/Utility/Healing category strings (same format as
# regular items).
_EQUIPMENT_CATEGORY_FALLBACK: dict = {
    'Blast Shower':                         'Utility',
    'Deus Ex Machina':                      'Damage',
    'Eccentric Vase':                       'Utility',
    'Executive Card':                       'Utility',
    'Foreign Fruit':                        'Healing',
    'Fuel Array':                           'Damage',
    'Disposable Missile Launcher':          'Damage',
    'Gnarled Woodsprite':                   'Healing',
    'Goobo Jr.':                            'Utility',
    "Gorag's Opus":                         'Damage',
    'Forgive Me Please':                    'Utility',
    'Milky Chrysalis':                      'Utility',
    'Molotov (6-Pack)':                     'Damage',
    'Jade Elephant':                        'Utility',
    'Ocular HUD':                           'Damage',
    'Preon Accumulator':                    'Damage',
    'Primordial Cube':                      'Utility',
    'Radar Scanner':                        'Utility',
    'Recycler':                             'Utility',
    'Remote Caffeinator':                   'Healing',
    'Royal Capacitor':                      'Damage',
    'Sawmerang':                            'Damage',
    'Seed of Life':                         'Healing',
    'Seed of Life (Consumed)':              'Healing',
    'Super Massive Leech':                  'Healing',
    'The Back-up':                          'Damage',
    'The Crowdfunder':                      'Damage',
    "Trophy Hunter's Tricorn":              'Damage',
    "Trophy Hunter's Tricorn (Consumed)":   'Damage',
    'Volcanic Egg':                         'Damage,Utility',
}


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

    # ensure each title appears only once in the final list; the API occasionally duplicates
    all_titles = sorted(dict.fromkeys(items + list(equip_items.keys())))

    # write into specified output location (parallelize heavy work)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    exported_rows = []
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Name','Rarity','Category','Stats','Desc','Image','Available',
                         'SynergyTags','Playstyles','WikiTips','StatsJson'])
        total = len(all_titles)

        def process(name):
            data = module_items.get(name, {})
            rarity = data.get('Rarity', '')
            category_list = data.get('Category', [])
            # Equipment items rarely carry Category data in the Lua module.
            # Apply curated fallback when none was parsed.
            if not category_list and name in _EQUIPMENT_CATEGORY_FALLBACK:
                category_list = [c.strip() for c in _EQUIPMENT_CATEGORY_FALLBACK[name].split(',')]
            category = ','.join(category_list)
            desc = data.get('Desc', '')
            stats_list = data.get('Stats', [])
            stats = ''
            if stats_list:
                stats = ';'.join(f"{st.get('Stat')}={st.get('Value')}" for st in stats_list)
            
            # Use the simple image cache
            img = get_item_image(name)
            
            # Mark items without images as unavailable (debug items, consumed items, etc.)
            has_image = bool(img and img.strip())
            available = has_image and is_available_item(name, category_list)
            synergy = compute_synergy_tags(category_list, desc, stats_list)
            playstyles = compute_playstyles(category_list, synergy)
            try:
                tips = fetch_wiki_tips(name)
            except Exception:
                tips = ''
            row = [name, rarity, category, stats, desc, img,
                   'true' if available else 'false',
                   ','.join(synergy), ','.join(playstyles), tips,
                   json.dumps(stats_list)]
            return name, row, {'Name': name, 'SynergyTags': list(synergy)}

        with ThreadPoolExecutor(max_workers=8) as exe:
            futures = {exe.submit(process, n): n for n in all_titles}
            for idx, fut in enumerate(as_completed(futures), 1):
                name = futures[fut]
                try:
                    name, row, meta = fut.result()
                except Exception as e:
                    print(f'Error processing {name}: {e}')
                    row = [name] + [''] * 10
                    meta = {'Name': name, 'SynergyTags': []}
                print(f'Processed {idx}/{total} {name}')
                writer.writerow(row)
                exported_rows.append(meta)

    # after exporting CSV, compute synergy graph and save to file
    try:
        from .utils import compute_synergy_graph
        # load config for graph options
        cfg = load_config()
        g_max = cfg.get('graph_max_ratio', 0.25)
        g_ignore = cfg.get('graph_ignore_tags', ['utility','damage','healing'])
        graph = compute_synergy_graph(exported_rows,
                                      max_freq_ratio=g_max,
                                      ignore_tags=g_ignore)
        graph_path = os.path.join(DATA_DIR, 'synergy.json')
        with open(graph_path, 'w', encoding='utf-8') as gf:
            json.dump(graph, gf, ensure_ascii=False, indent=2)
        print(f'Saved synergy graph: {graph_path}')
    except Exception as e:
        print('Warning: failed to compute/save synergy graph', e)

    print(f'Export complete: {output_csv}')


if __name__ == '__main__':
    export_items()
