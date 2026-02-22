import pytest

from ror2tools.utils import compute_synergy_tags, compute_playstyles, fetch_wiki_tips


def test_compute_synergy_tags_basic():
    # on kill tag should detect from category or description
    tags = compute_synergy_tags(['OnKill', 'Damage'], 'The next kill grants speed')
    assert 'on-kill' in tags
    # critical detection
    tags = compute_synergy_tags([], 'Enhances critical strike chance')
    assert 'crit' in tags
    # crowd control detection
    tags = compute_synergy_tags([], 'Slows enemies on hit')
    assert 'crowd-control' in tags
    # generic utility category should be ignored
    tags = compute_synergy_tags(['Utility'], 'Just a utility item')
    assert tags == set()


def test_compute_playstyles_simple():
    assert compute_playstyles(['Damage'], {'on-kill'}) == {'frenzy'}
    assert compute_playstyles([], {'crowd-control'}) == {'cc'}
    assert compute_playstyles([], {'movement'}) == {'mobile'}
    assert compute_playstyles([], set()) == set()


def test_fetch_wiki_tips_returns_string():
    # should not raise and should return a string (possibly empty)
    tips = fetch_wiki_tips('Crowbar')
    assert isinstance(tips, str)
    # At least one or zero is acceptable; the function may return empty if not found


def test_compute_synergy_graph_empty():
    # graph should be empty when items have no shared tags
    items = [{'Name': 'A','SynergyTags': []}, {'Name':'B','SynergyTags': []}]
    from ror2tools.utils import compute_synergy_graph
    g = compute_synergy_graph(items)
    assert g == {'A': {}, 'B': {}}


def test_tag_frequencies_and_filter():
    from ror2tools.utils import compute_tag_frequencies, compute_synergy_graph
    items = [
        {'Name':'X','SynergyTags':['foo','common']},
        {'Name':'Y','SynergyTags':['foo','common']},
        {'Name':'Z','SynergyTags':['bar','common']},
    ]
    freq = compute_tag_frequencies(items)
    assert freq['common'] == 3
    # small dataset: ratio threshold < 1, so filtering should be skipped and
    # weights computed from shared tags
    g = compute_synergy_graph(items)
    assert g['X'] == {'Y': 2, 'Z': 1}
    assert g['Z'] == {'X': 1, 'Y': 1}
    # ignoring tags still works
    g_ignore = compute_synergy_graph(items, ignore_tags=['foo'])
    # 'foo' removed, only common remains; each pair connected by 1
    assert g_ignore['X'] == {'Y': 1, 'Z': 1}


def test_blacklist_removal():
    from ror2tools.utils import compute_synergy_tags
    tags = compute_synergy_tags(['Utility','AIBlacklist','OnKillEffect'], 'Shiny shrine effect', [])
    assert 'aiblacklist' not in tags
    assert 'halcyoniteshrine' not in tags
    assert 'onkilleffect' not in tags
    # normal tags remain
    tags2 = compute_synergy_tags([], 'Deals damage on kill', [])
    assert 'on-kill' in tags2


def test_graph_config_params():
    from ror2tools.utils import compute_synergy_graph
    items = [
        {'Name':'A','SynergyTags':['foo','common']},
        {'Name':'B','SynergyTags':['foo','common']},
        {'Name':'C','SynergyTags':['bar','common']},
    ]
    # small dataset: default ratio threshold <1, so no tags are filtered
    g1 = compute_synergy_graph(items)
    # A and B share two tags (foo and common), C shares common with each
    assert g1['A']['B'] == 2
    assert g1['A']['C'] == 1

    # if we artificially force a very low ratio, the small-n override keeps the
    # graph unchanged (max_freq_ratio * n < 1)
    g_low = compute_synergy_graph(items, max_freq_ratio=0.0)
    assert g_low == g1

    # high ratio keeps everything too
    g2 = compute_synergy_graph(items, max_freq_ratio=1.0)
    assert g2['A']['B'] >= 1

    # ignore_tags should drop foo even though frequency low
    g3 = compute_synergy_graph(items, ignore_tags=['foo'])
    # now only 'common' contributes a weight of 1
    assert g3['A']['B'] == 1

