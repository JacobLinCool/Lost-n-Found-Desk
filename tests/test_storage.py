import pytest

from lost_found_desk.schemas import Claim, Event, Item, ReturnLog
from lost_found_desk.security import hash_password, verify_password
from lost_found_desk.storage import JsonStore


def _event(store, event_id="ev1", name="Event One"):
    h, s = hash_password("secret")
    return store.create_event(Event(event_id=event_id, name=name, staff_password_hash=h, staff_password_salt=s))


def test_password_hash_roundtrip():
    h, s = hash_password("hunter2")
    assert verify_password("hunter2", h, s)
    assert not verify_password("wrong", h, s)
    assert not verify_password("hunter2", "", "")


def test_event_isolation(tmp_path):
    store = JsonStore(tmp_path / "db.json")
    _event(store, "ev1")
    _event(store, "ev2")
    store.add_item("ev1", Item(item_id="i1", event_id="ev1", caption="black bottle", photo_url="u", photo_path="p"))
    assert len(store.list_items("ev1")) == 1
    assert len(store.list_items("ev2")) == 0
    assert store.get_item("ev2", "i1") is None
    assert store.get_item("ev1", "i1")["caption"] == "black bottle"


def test_duplicate_event_rejected(tmp_path):
    store = JsonStore(tmp_path / "db.json")
    _event(store, "ev1")
    with pytest.raises(ValueError):
        _event(store, "ev1")


def test_return_closes_claim_and_item(tmp_path):
    store = JsonStore(tmp_path / "db.json")
    _event(store, "ev1")
    store.add_item("ev1", Item(item_id="i1", event_id="ev1", caption="c", photo_url="u", photo_path="p"))
    store.add_claim("ev1", Claim(claim_id="c1", event_id="ev1"))
    store.add_return("ev1", ReturnLog(log_id="r1", event_id="ev1", item_id="i1", claim_id="c1"))
    assert store.get_item("ev1", "i1")["status"] == "returned"
    assert store.get_claim("ev1", "c1")["status"] == "closed"
    assert store.report("ev1")["returned_items"] == 1


def test_unknown_event_raises(tmp_path):
    store = JsonStore(tmp_path / "db.json")
    with pytest.raises(KeyError):
        store.list_items("nope")


def test_concurrent_appends_do_not_lose_messages(tmp_path):
    """Regression: atomic append_to_claim must not lose interleaved updates."""
    import threading

    store = JsonStore(tmp_path / "db.json")
    _event(store, "ev1")
    store.add_claim("ev1", Claim(claim_id="c1", event_id="ev1"))

    def worker(n):
        store.append_to_claim("ev1", "c1", messages=[{"role": "user", "content": str(n)}])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    convo = store.get_claim("ev1", "c1")["conversation"]
    assert len(convo) == 50  # no lost writes
    assert {m["content"] for m in convo} == {str(i) for i in range(50)}


def test_append_to_claim_applies_scalar_updates(tmp_path):
    store = JsonStore(tmp_path / "db.json")
    _event(store, "ev1")
    store.add_claim("ev1", Claim(claim_id="c1", event_id="ev1"))
    out = store.append_to_claim(
        "ev1", "c1", messages=[{"role": "staff", "content": "hi"}], has_unread_staff_message=True
    )
    assert out["has_unread_staff_message"] is True
    assert out["conversation"][-1]["content"] == "hi"


def test_item_embedding_roundtrip(tmp_path):
    store = JsonStore(tmp_path / "db.json")
    _event(store, "ev1")
    store.set_item_embedding("ev1", "i1", [0.1, 0.2, 0.3])
    assert store.get_item_embeddings("ev1") == {"i1": [0.1, 0.2, 0.3]}
