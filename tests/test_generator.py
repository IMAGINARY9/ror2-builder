import pytest

from ror2tools.generator import (
    satisfies_config, build_rarity_map, select_pool
)


def make_item(name, rarity, tags=None, plays=None):
    return {
        'Name': name,
        'Rarity': rarity,
        'SynergyTags': tags or [],
        'Playstyles': plays or []
    }


def test_satisfies_config_tags():
    item = make_item('Foo', 'Common', tags=['on-kill', 'crit'])
    cfg = {'require_tags': ['crit']}
    assert satisfies_config(item, cfg)
    cfg = {'require_tags': ['movement']}
    assert not satisfies_config(item, cfg)


def test_select_pool_honors_require_tags():
    # build a simple rarity map with one common item with tag 'crit'
    item = make_item('Bar', 'Common', tags=['crit'])
    rarity_map = {'Common': [item]}
    cfg = {'Common': 1, 'require_tags': ['crit']}
    pool = select_pool(rarity_map, cfg, max_attempts=10)
    assert pool and pool[0]['Name'] == 'Bar'

    # if requirement not met, pool may be empty or not include the item
    cfg2 = {'Common': 1, 'require_tags': ['movement']}
    pool2 = select_pool(rarity_map, cfg2, max_attempts=10)
    # when no candidates exist after filtering, select_pool returns empty list
    assert pool2 == []


def test_build_rarity_map():
    items = [make_item('A', 'Common'), make_item('B', 'Legendary'), make_item('C', 'Common')]
    rm = build_rarity_map(items)
    assert set(rm.keys()) == {'Common', 'Legendary'}
    assert len(rm['Common']) == 2
