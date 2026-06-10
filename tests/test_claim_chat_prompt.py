"""Prompt assembly for the model-driven claim conversation (no model load)."""

from lost_found_desk.conversation import is_inventory_probe
from lost_found_desk.models.minicpm5 import _is_echo, build_claim_chat_messages
from lost_found_desk.prompts import CLAIM_ASSISTANT_SYSTEM


def test_echo_detection_catches_near_repeats():
    first = "Hi! I'm sorry you lost something. Could you please tell me what item you lost?"
    # Observed live: the model replayed its previous reply minus the greeting.
    near_repeat = "I'm sorry you lost something. Could you please tell me what item you lost?"
    assert _is_echo(near_repeat, first)
    assert _is_echo(first, first)
    # A genuinely new reply must pass, even when it shares a few words.
    fresh = "Thanks — a water bottle. What color is it?"
    assert not _is_echo(fresh, first)
    assert not _is_echo("", first)


def test_inventory_probe_detection():
    probes = [
        "what do you have at the desk?",
        "what items do you have?",
        "What things did you have there",
        "show me the items",
        "did anyone find a bottle?",
        "have you seen a black wallet",
        "anything been found?",
        "你們有撿到什麼嗎",
        "有沒有人撿到水壺",
        "找到了嗎",
    ]
    for text in probes:
        assert is_inventory_probe(text), text
    not_probes = [
        "I lost a bottle",
        "it's blue with a dinosaur sticker",
        "I have a sticker on it",  # claimant describing their own item
        "我掉了一個黑色的水壺",
    ]
    for text in not_probes:
        assert not is_inventory_probe(text), text


def _msgs(*pairs):
    return [{"role": role, "content": content} for role, content in pairs]


def test_system_prompt_and_turn_order():
    conversation = _msgs(("assistant", "Hi! Describe the item you lost."), ("user", "I lost a bottle"))
    messages = build_claim_chat_messages(conversation, "it is black", language="en", missing=["color"])
    assert messages[0] == {"role": "system", "content": CLAIM_ASSISTANT_SYSTEM}
    assert [m["role"] for m in messages] == ["system", "assistant", "user"]
    # The new user message lands in the final user turn with the instructions.
    final = messages[-1]["content"]
    assert "it is black" in final
    assert "Reply in English." in final
    assert "ask ONE short question about exactly this and nothing else: color" in final


def test_zh_language_and_translated_category_hint():
    conversation = _msgs(("assistant", "Hi!"), ("user", "我掉了一個黑色的水壺"))
    messages = build_claim_chat_messages(conversation, "上面有貼紙", language="zh", missing=["distinctive mark"])
    final = messages[-1]["content"]
    assert "使用繁體中文" in final  # instructions written in the conversation's language
    assert "獨特特徵" in final  # category hint translated for the zh conversation


def test_consecutive_same_role_messages_are_merged():
    conversation = _msgs(
        ("assistant", "Hi!"),
        ("staff", "Please visit the desk before 5pm."),  # staff folds into assistant side
        ("user", "ok"),
        ("user", "I lost a black bottle"),
    )
    messages = build_claim_chat_messages(conversation, "with a sticker")
    roles = [m["role"] for m in messages]
    # Strict alternation after the system turn: no consecutive duplicates.
    assert all(a != b for a, b in zip(roles[1:], roles[2:]))
    staff_turn = messages[1]
    assert staff_turn["role"] == "assistant"
    assert "(Message from the desk team) Please visit the desk before 5pm." in staff_turn["content"]
    # Both user lines merged with the new message appended.
    assert messages[-1]["role"] == "user"
    assert "ok" in messages[-1]["content"] and "with a sticker" in messages[-1]["content"]


def test_history_is_capped_and_inventory_never_present():
    conversation = []
    for i in range(40):
        conversation.append({"role": "user", "content": f"detail {i}"})
        conversation.append({"role": "assistant", "content": f"question {i}"})
    messages = build_claim_chat_messages(conversation, "latest answer")
    # 12 history messages merge into at most 13 turns + system.
    assert len(messages) <= 14
    assert "detail 0" not in str(messages)  # old turns dropped
    assert "latest answer" in messages[-1]["content"]
    # The system prompt never mentions inventory contents — only the rule that
    # the assistant must not reveal them.
    assert "item_" not in CLAIM_ASSISTANT_SYSTEM
