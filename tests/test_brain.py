from leond.brain import Message, _delta_text, trim


def test_streamed_delta_is_read() -> None:
    chunk = {"choices": [{"delta": {"content": "Hel"}}]}
    assert _delta_text(chunk) == "Hel"


def test_non_streamed_message_is_read() -> None:
    chunk = {"choices": [{"message": {"content": "Hello"}}]}
    assert _delta_text(chunk) == "Hello"


def test_finish_chunk_has_no_text() -> None:
    assert _delta_text({"choices": [{"delta": {}, "finish_reason": "stop"}]}) == ""


def test_unexpected_shapes_are_ignored() -> None:
    assert _delta_text({}) == ""
    assert _delta_text({"choices": []}) == ""
    assert _delta_text({"choices": [{"delta": {"content": None}}]}) == ""
    assert _delta_text("not a chunk") == ""


def test_trim_keeps_recent_turns_inside_the_budget() -> None:
    messages = [Message("user", "x" * 5000), Message("assistant", "short reply")]
    kept = trim(messages, context=512)
    assert kept == [Message("assistant", "short reply")]


def test_trim_never_starts_on_an_orphan_tool_result() -> None:
    call = {"id": "c1", "type": "function", "function": {"name": "local_time", "arguments": "{}"}}
    messages = [
        Message("assistant", "y" * 3000, tool_calls=(call,)),
        Message("tool", "18:42", tool_call_id="c1"),
    ]
    # The assistant turn that asked for the tool falls outside the budget, so
    # the result goes with it instead of arriving as a bare tool message.
    assert trim(messages, context=512) == []


def test_trim_keeps_everything_that_fits() -> None:
    messages = [Message("user", "hi"), Message("assistant", "hello")]
    assert trim(messages, context=2048) == messages
