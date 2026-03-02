import csv
import json
import random
import os
import re
import time
from collections import Counter
from datetime import datetime
from html import escape
from typing import Dict, List, Optional, Set

from .utils import DATA_DIR, OUTPUT_DIR, load_synergy_graph
from .scoring import score_pool, score_breakdown

CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
ITEMS_CSV = os.path.join(DATA_DIR, 'items.csv')

REQUIRED_ASPECTS = {'damage', 'movement', 'defense'}


def load_config(path=CONFIG_PATH):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_items(path=ITEMS_CSV, enabled_dlcs=None):
    """Load items from CSV, optionally filtering by enabled DLCs.
    
    Args:
        path: Path to items CSV file
        enabled_dlcs: Set of enabled DLC names (e.g., {'Base', 'SOTV', 'SOTS', 'AC'})
                     If None, all DLCs are enabled
    
    Returns:
        List of item dictionaries
    """
    items = []
    seen = set()  # track names we've already loaded to avoid duplicates
    with open(path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = r.get('Name')
            # skip duplicate names that sometimes appear in the CSV
            if name in seen:
                continue
            seen.add(name)

            if not r.get('Rarity'):
                continue
            avail = r.get('Available', 'true').strip().lower()
            if avail not in ('', 'true', '1', 'yes'):
                continue
            
            # Filter by DLC if specified
            item_dlc = r.get('DLC', 'Base')
            if item_dlc == 'Hidden':
                continue  # Always skip hidden/system items
            if enabled_dlcs is not None and item_dlc not in enabled_dlcs:
                continue
            
            # Images are already correct in the cache - no need to normalize
            # comma-separated lists may be empty strings
            r['SynergyTags'] = [t for t in r.get('SynergyTags', '').split(',') if t]
            r['Playstyles'] = [p for p in r.get('Playstyles', '').split(',') if p]
            # pre-compute cleaned description so callers don't need to repeat logic
            r['clean_desc'] = clean_wiki_markup(r.get('Desc', ''))
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

    # compute score once for possible use in outputs
    score = 0
    graph = load_synergy_graph()
    if config.get('style') or config.get('synergy_weight', 0) or config.get('size'):
        score = score_pool(pool, graph, config.get('style'), config.get('synergy_weight', 0))

    export_pool_files(pool, score=score, config=config, synergy_graph=graph)
    print('\nSaved generated_pool.csv')
    print('Saved generated_pool.md (open in editor for visual preview)')
    return pool


def clean_wiki_markup(text: str) -> str:
    """Strip RoR2 wiki template markup from a description string.

    Handles patterns like ``{{Color|u|text}}``, ``{{Stack|text}}``,
    ``{{Color|#hex|text}}``, and escaped newlines.

    Args:
        text: Raw description string from items.csv.

    Returns:
        Plain-text description with markup removed.
    """
    if not text:
        return ''
    # {{Color|<code>|<content>}} → content
    text = re.sub(r'\{\{Color\|[^|]+\|([^}]+)\}\}', r'\1', text)
    # {{Stack|<content>}} → content
    text = re.sub(r'\{\{Stack\|([^}]+)\}\}', r'\1', text)
    # Catch any remaining {{...}} templates
    text = re.sub(r'\{\{[^}]*\}\}', '', text)
    # Normalise escaped newlines
    text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
    # Collapse multiple spaces
    text = re.sub(r' {2,}', ' ', text).strip()
    return text


# Rarity → colour mapping shared by all Markdown writers
_RARITY_COLORS: Dict[str, str] = {
    'Common': '#FFFFFF',
    'Uncommon': '#50C878',
    'Legendary': '#FF4500',
    'Boss': '#FFD700',
    'Lunar': '#6699FF',
    'Void': '#800080',
    'Equipment': '#FFA500',
    'Elite Equipment': '#FF8C00',
    'Lunar Equipment': '#00CED1',
}


def _color_text(text: str, rarity: str) -> str:
    """Wrap *text* in an HTML span coloured by *rarity*."""
    col = _RARITY_COLORS.get(rarity, '')
    return f'<span style="color:{col}">{text}</span>' if col else text


def export_pool_files(
    pool: List[Dict],
    score: float = 0,
    config: Optional[Dict] = None,
    synergy_graph: Optional[Dict] = None,
    enabled_dlcs: Optional[Set[str]] = None,
) -> None:
    """Export a pool to CSV and a detailed Markdown report.

    The Markdown report includes:
    * Generation timestamp
    * Enabled DLCs
    * Scoring parameters and full score breakdown
    * Pool composition statistics (rarity & category counts)
    * Item table with cleaned descriptions

    Args:
        pool: List of item dictionaries.
        score: Overall pool score.
        config: Configuration dict (weights, style, optimization params).
        synergy_graph: Synergy adjacency map (for breakdown calculation).
        enabled_dlcs: Set of enabled DLC identifiers.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # CSV export (unchanged schema for backward compatibility)
    # ------------------------------------------------------------------
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
                it.get('Image', ''),
            ])

    # ------------------------------------------------------------------
    # Compute score breakdown when enough context is available
    # ------------------------------------------------------------------
    breakdown: Optional[Dict[str, float]] = None
    if config and synergy_graph is not None:
        scoring_params = {
            'style': config.get('style'),
            'synergy_weight': config.get('synergy_weight', 0.5),
            'style_weight': config.get('style_weight', 8.0),
            'diversity_weight': config.get('diversity_weight', 1.0),
            'coverage_weight': config.get('coverage_weight', 1.0),
            'balance_weight': config.get('balance_weight', 5.0),
            'pinned_items': config.get('pinned_items', []),
        }
        breakdown = score_breakdown(pool, synergy_graph, **scoring_params)

    # ------------------------------------------------------------------
    # Pool statistics
    # ------------------------------------------------------------------
    rarity_counts: Dict[str, int] = Counter(
        it.get('Rarity', 'Unknown') for it in pool
    )
    category_counts: Dict[str, int] = Counter()
    for it in pool:
        cats = it.get('Category', '')
        if isinstance(cats, str):
            for c in cats.split(','):
                c = c.strip()
                if c:
                    category_counts[c] += 1

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------
    md_path = os.path.join(OUTPUT_DIR, 'generated_pool.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('# Generated Item Pool\n\n')

        # Timestamp
        f.write(f'*Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*\n\n')

        # --- Configuration Parameters ---
        if config:
            f.write('## Configuration\n\n')
            f.write('| Parameter | Value |\n')
            f.write('|-----------|-------|\n')
            style = config.get('style') or 'None'
            f.write(f'| Play Style | {style} |\n')
            f.write(f'| Synergy Weight | {config.get("synergy_weight", 0.5)} |\n')
            f.write(f'| Style Weight | {config.get("style_weight", 8.0)} |\n')
            f.write(f'| Diversity Weight | {config.get("diversity_weight", 1.0)} |\n')
            f.write(f'| Coverage Weight | {config.get("coverage_weight", 1.0)} |\n')
            f.write(f'| Balance Weight | {config.get("balance_weight", 5.0)} |\n')
            opt = config.get('optimization', {})
            if isinstance(opt, dict) and opt:
                f.write(f'| K-opt | {opt.get("k_opt", 1)} |\n')
                f.write(f'| Max Iterations | {opt.get("max_iterations", 50)} |\n')
            pinned = config.get('pinned_items', [])
            if pinned:
                f.write(f'| Pinned Items | {", ".join(pinned)} |\n')
            if enabled_dlcs:
                f.write(f'| Enabled DLCs | {", ".join(sorted(enabled_dlcs))} |\n')
            f.write('\n')

        # --- Score Breakdown ---
        f.write('## Score\n\n')
        if breakdown:
            f.write(f'**Total Score: {breakdown["total"]:.2f}**\n\n')
            f.write('| Component | Raw | Weight | Weighted |\n')
            f.write('|-----------|-----|--------|----------|\n')
            rows = [
                ('Style Match', 'style_score', 'weighted_style',
                 config.get('style_weight', 8.0) if config else 8.0),
                ('Synergy', 'synergy_score', 'weighted_synergy',
                 config.get('synergy_weight', 0.5) if config else 0.5),
                ('Rarity Diversity', 'diversity_score', 'weighted_diversity',
                 config.get('diversity_weight', 1.0) if config else 1.0),
                ('Tag Coverage', 'coverage_score', 'weighted_coverage',
                 config.get('coverage_weight', 1.0) if config else 1.0),
                ('Category Balance', 'balance_score', 'weighted_balance',
                 config.get('balance_weight', 5.0) if config else 5.0),
                ('Pinned Items', 'pin_score', 'weighted_pin', 2.0),
            ]
            for label, raw_key, weighted_key, weight in rows:
                raw = breakdown.get(raw_key, 0)
                weighted = breakdown.get(weighted_key, 0)
                f.write(f'| {label} | {raw:.2f} | ×{weight} | {weighted:.2f} |\n')
            f.write('\n')
        elif score:
            f.write(f'**Total Score: {score:.2f}**\n\n')

        # --- Pool Statistics ---
        f.write('## Pool Statistics\n\n')
        f.write(f'**Total items:** {len(pool)}\n\n')

        if rarity_counts:
            f.write('**By Rarity:**\n\n')
            # Sort by count descending
            for rarity, count in sorted(rarity_counts.items(), key=lambda x: -x[1]):
                color = _RARITY_COLORS.get(rarity, '#FFFFFF')
                f.write(f'- <span style="color:{color}">{rarity}</span>: {count}\n')
            f.write('\n')

        core_cats = ['Damage', 'Utility', 'Healing']
        core_counts = {c: category_counts.get(c, 0) for c in core_cats}
        if any(core_counts.values()):
            f.write('**By Core Category:**\n\n')
            for cat, count in core_counts.items():
                f.write(f'- {cat}: {count}\n')
            f.write('\n')

        # --- Item Table ---
        f.write('## Items\n\n')
        f.write('| | Name | Rarity | Description | Tags |\n')
        f.write('|---|------|--------|-------------|------|\n')
        for it in pool:
            tag_list = list(it.get('SynergyTags', []) or [])
            plays_list = it.get('Playstyles', []) or []
            if plays_list:
                tag_list.append('(' + ', '.join(plays_list) + ')')
            display_blacklist = {'damage', 'utility', 'healing'}
            tag_list = [t for t in tag_list if t not in display_blacklist]
            tags = ', '.join(f'`{t}`' for t in tag_list if t)
            img = it.get('Image', '') or ''
            img_md = f'<img src="{img}" alt="{it["Name"]}" width="48"/>' if img else ''
            name_colored = _color_text(it['Name'], it['Rarity'])
            desc = clean_wiki_markup(it.get('Desc', ''))
            # Truncate very long descriptions for readability
            if len(desc) > 120:
                desc = desc[:117] + '...'
            f.write(f'| {img_md} | {name_colored} | {it.get("Rarity", "")} | {desc} | {tags} |\n')

        f.write('\n---\n*Report generated by RoR2 Pool Optimizer*\n')
