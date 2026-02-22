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
    # no tags if nothing matches
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
