from adaptivecua.core.queue import InputQueue


async def test_drain_returns_all_pending_in_fifo_order():
    # Arrange
    q = InputQueue()
    await q.submit("first")
    await q.submit("second")
    # Act
    drained = q.drain()
    # Assert
    assert drained == ["first", "second"]
    assert q.is_empty() is True


async def test_drain_on_empty_queue_returns_empty_list():
    q = InputQueue()
    assert q.drain() == []
    assert q.is_empty() is True


async def test_is_empty_false_when_item_pending():
    q = InputQueue()
    await q.submit("x")
    assert q.is_empty() is False
