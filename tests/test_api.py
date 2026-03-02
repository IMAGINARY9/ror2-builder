import pytest

from app import app, initialize_data


@pytest.fixture
def client():
    # configure flask test client and ensure data is loaded
    app.config['TESTING'] = True
    # load items/synergy/config before running requests
    initialize_data()
    with app.test_client() as client:
        yield client


def test_items_endpoint_includes_clean_desc(client):
    resp = client.get('/api/items')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'items' in data
    # every item should have the cleaned description field
    assert all('clean_desc' in item for item in data['items'])
    # formatted stats/category should also be provided (may be empty)
    assert all('formatted_stats' in item for item in data['items'])
    assert all('formatted_category' in item for item in data['items'])
    # basic sanity: clean_desc should not contain any template braces
    for item in data['items'][:5]:
        assert '{{' not in item['clean_desc']
        assert '}}' not in item['clean_desc']


def test_pool_responses_always_include_clean_desc(client):
    # start with an empty pool
    # pick two different items from the items list
    items = client.get('/api/items').get_json()['items']
    assert len(items) >= 2
    first = items[0]
    second = items[1]

    # update pool explicitly with the first item
    resp = client.post('/api/pool', json={'items': [first['name']]})
    assert resp.status_code == 200
    payload = resp.get_json()
    pool = payload['pool']
    assert len(pool) == 1
    assert 'clean_desc' in pool[0]
    assert pool[0]['clean_desc'] == first['clean_desc']

    # GET /api/pool should reflect the same
    resp2 = client.get('/api/pool')
    assert resp2.status_code == 200
    pool2 = resp2.get_json()['pool']
    assert pool2 and pool2[0].get('clean_desc') == first['clean_desc']

    # add a second item using /api/pool/add
    resp3 = client.post('/api/pool/add', json={'item': second['name']})
    pool3 = resp3.get_json()['pool']
    assert len(pool3) == 2
    assert all('clean_desc' in it for it in pool3)

    # generate random pool and confirm clean_desc persists
    resp4 = client.post('/api/pool/random', json={'config': {}})
    pool4 = resp4.get_json()['pool']
    assert pool4
    assert all('clean_desc' in it for it in pool4)
