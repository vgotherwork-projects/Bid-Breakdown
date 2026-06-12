from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_item_crud_flow():
    created = client.post("/items", json={"name": "Widget", "price": 9.99})
    assert created.status_code == 201
    item = created.json()
    item_id = item["id"]
    assert item["name"] == "Widget"

    fetched = client.get(f"/items/{item_id}")
    assert fetched.status_code == 200

    updated = client.put(f"/items/{item_id}", json={"price": 12.5})
    assert updated.status_code == 200
    assert updated.json()["price"] == 12.5

    deleted = client.delete(f"/items/{item_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/items/{item_id}")
    assert missing.status_code == 404


def test_validation_rejects_negative_price():
    res = client.post("/items", json={"name": "Bad", "price": -1})
    assert res.status_code == 422
