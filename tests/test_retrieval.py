from lost_found_desk.embeddings import MockEmbedder
from lost_found_desk.retrieval import cosine, rank_items_by_embedding


def test_cosine_basic():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9
    assert cosine([], [1.0]) == 0.0
    assert cosine([1.0, 2.0], [1.0]) == 0.0  # dimension mismatch -> 0


def test_mock_embedder_is_deterministic_and_normalized():
    e = MockEmbedder(dim=64)
    a = e.embed_query("black bottle with sticker")
    b = e.embed_query("black bottle with sticker")
    assert a == b
    assert abs(sum(x * x for x in a) ** 0.5 - 1.0) < 1e-6
    # similar text is closer than unrelated text
    related = e.embed_item("x.png", "a black water bottle")
    unrelated = e.embed_item("y.png", "navy hoodie with logo")
    assert cosine(a, related) > cosine(a, unrelated)


def test_rank_items_by_embedding_picks_topk():
    e = MockEmbedder(dim=128)
    items = [
        {"item_id": "bottle", "caption": "black water bottle silver cap sticker"},
        {"item_id": "hoodie", "caption": "navy hoodie white logo"},
        {"item_id": "charger", "caption": "white usb-c charger cable"},
    ]
    embeddings = {it["item_id"]: e.embed_item("p", it["caption"]) for it in items}
    query = e.embed_query("i lost a black bottle with a sticker")
    top = rank_items_by_embedding(query, items, embeddings, topk=1)
    assert len(top) == 1
    assert top[0]["item_id"] == "bottle"


def test_rank_items_without_embeddings_are_not_dropped():
    e = MockEmbedder(dim=64)
    items = [{"item_id": "a", "caption": "x"}, {"item_id": "b", "caption": "y"}]
    # only "a" has an embedding; "b" must still be returned (sorted last), not hidden
    embeddings = {"a": e.embed_item("p", "x")}
    top = rank_items_by_embedding(e.embed_query("z"), items, embeddings, topk=2)
    assert {i["item_id"] for i in top} == {"a", "b"}
