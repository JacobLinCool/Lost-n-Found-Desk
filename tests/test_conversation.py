from lost_found_desk.conversation import build_summary, detect_language, plan_turn


def test_detect_language():
    assert detect_language("我掉了一個黑色水壺") == "zh"
    assert detect_language("I lost a black bottle") == "en"
    assert detect_language("カバンをなくしました") == "zh"  # CJK family


def _user(content):
    return {"role": "user", "content": content}


def _assistant(content):
    return {"role": "assistant", "content": content}


def test_unparseable_answers_progress_without_repeat():
    """Regression: even answers we cannot machine-parse must advance the flow.

    The old English-keyword gate left such claims stuck on the same question
    forever. The brain tracks which attributes it already asked about, so it
    asks each at most once and then becomes ready — never repeating a question.
    """
    conversation = [_assistant("seed")]
    collecting = []
    final = None
    for msg in ["aaa", "bbb", "ccc", "ddd"]:
        plan = plan_turn(conversation, msg)  # no inventory -> generic collection
        assert plan["assistant_message"]
        assert msg in plan["summary"]
        if plan["readiness_state"] == "collecting":
            collecting.append(plan["assistant_message"])
        conversation += [_user(msg), _assistant(plan["assistant_message"])]
        final = plan
    assert len(collecting) == len(set(collecting)), "a question was repeated"
    assert final["readiness_state"] == "ready_for_staff_review"


def test_chinese_attributes_are_understood():
    """A Chinese description that already gives type+color shouldn't be re-asked
    for them — only the remaining distinguishing detail."""
    plan = plan_turn([_assistant("seed")], "我掉了一個黑色的水壺", _TWO_BOTTLES)
    assert plan["readiness_state"] == "collecting"
    assert plan["target"] == "distinctive"


def test_summary_accumulates_user_words():
    conversation = [_assistant("seed"), _user("a navy hoodie"), _assistant("q")]
    assert build_summary(conversation, "with a small logo") == "a navy hoodie with a small logo"


_TWO_BOTTLES = [
    {"item_id": "b1", "status": "unclaimed", "caption": "black water bottle with a silver cap", "found_location": ""},
    {"item_id": "b2", "status": "unclaimed", "caption": "blue water bottle with a dinosaur sticker", "found_location": ""},
]


def test_inventory_driven_disambiguation_asks_a_distinguishing_attribute():
    # Two bottles that differ in color; the claimant only gave the type, so the
    # follow-up should target a distinguishing attribute, not a fixed script.
    plan = plan_turn([_assistant("seed")], "I lost a bottle", _TWO_BOTTLES)
    assert plan["readiness_state"] == "collecting"
    assert plan["target"] in {"color", "distinctive"}


def test_specific_description_is_ready_immediately():
    plan = plan_turn([_assistant("seed")], "a black water bottle with a silver cap and a sticker", _TWO_BOTTLES)
    assert plan["readiness_state"] == "ready_for_staff_review"


def test_chinese_with_inventory_progresses_without_repeat():
    conversation = [_assistant("seed")]
    seen = set()
    final = None
    for msg in ["我掉了一個水壺", "黑色的", "上面有貼紙"]:
        plan = plan_turn(conversation, msg, _TWO_BOTTLES)
        assert plan["assistant_message"] not in seen
        seen.add(plan["assistant_message"])
        conversation += [_user(msg), _assistant(plan["assistant_message"])]
        final = plan
    assert final["readiness_state"] == "ready_for_staff_review"
