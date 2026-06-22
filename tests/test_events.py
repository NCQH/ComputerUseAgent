from cua.core.events import EventBus, LogMessage, ErrorOccurred


def test_subscriber_receives_published_event():
    # Arrange
    bus = EventBus()
    received = []
    bus.subscribe(received.append)
    # Act
    bus.publish(LogMessage(text="hello"))
    # Assert
    assert received == [LogMessage(text="hello")]


def test_multiple_subscribers_all_receive():
    bus = EventBus()
    a, b = [], []
    bus.subscribe(a.append)
    bus.subscribe(b.append)
    event = ErrorOccurred(message="boom")
    bus.publish(event)
    assert a == [event]
    assert b == [event]


def test_one_subscriber_raising_does_not_block_others():
    bus = EventBus()
    delivered = []

    def bad(_event):
        raise RuntimeError("subscriber failed")

    bus.subscribe(bad)
    bus.subscribe(delivered.append)
    bus.publish(LogMessage(text="x"))
    assert delivered == [LogMessage(text="x")]
