from adaptivecua.core.history import History
from adaptivecua.models import Click, Type, ProviderResponse
from tests.fakes import FakeProvider, FakeExecutor


async def test_fake_provider_returns_queued_then_done():
    resp = ProviderResponse([Click(1, 1)], done=False, assistant_text="a", model_flagged_risky=False)
    provider = FakeProvider([resp])
    h = History()
    first = await provider.next_actions("img", h)
    second = await provider.next_actions("img", h)
    assert first is resp
    assert second.done is True
    assert second.actions == []


async def test_fake_provider_records_history_length():
    provider = FakeProvider([
        ProviderResponse([], done=False, assistant_text="", model_flagged_risky=False),
    ])
    h = History()
    h.add_user("hi")
    await provider.next_actions("img", h)
    assert provider.seen_history_lengths == [1]


async def test_fake_executor_records_and_succeeds():
    ex = FakeExecutor()
    result = await ex.do(Click(3, 4))
    assert result.success is True
    assert ex.performed == [Click(3, 4)]


async def test_fake_executor_fails_on_configured_type():
    ex = FakeExecutor(fail_on=Type)
    result = await ex.do(Type(text="x"))
    assert result.success is False
    assert result.error is not None
