from lost_found_desk.matching import has_enough_claim_detail, rank_candidates


def test_claim_detail_gate():
    assert not has_enough_claim_detail("I lost a thing")
    assert has_enough_claim_detail("black bottle in room b with sticker")


def test_rank_candidates_black_bottle():
    items = [
        {
            "item_id": "item_1",
            "status": "unclaimed",
            "caption": "Black insulated water bottle with a white conference sticker and silver cap. Found near Workshop Room B.",
            "found_location": "Workshop Room B",
        },
        {
            "item_id": "item_2",
            "status": "unclaimed",
            "caption": "Navy hoodie with a small white logo. Found in lobby.",
            "found_location": "Lobby",
        },
    ]
    state, candidates = rank_candidates("black bottle with white conference sticker in room b", items)
    assert state == "strong_candidate"
    assert candidates[0].item_id == "item_1"
