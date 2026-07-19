"""Console adapter tests — proves a second (non-twitchio) source drives the game
through the same normalized boundary."""

from __future__ import annotations

import asyncio

from server.adapters import InboundMessage
from server.console_adapter import ConsoleAdapter


def test_dispatch_line_normalizes_to_inbound_message():
    seen: list[InboundMessage] = []

    async def dispatch(msg: InboundMessage) -> list[str]:
        seen.append(msg)
        return [f"echo:{msg.text}"]

    out: list[str] = []
    adapter = ConsoleAdapter(dispatch, out=out.append)

    asyncio.run(adapter.dispatch_line("  !create barbarian orc Thorak \n"))

    assert len(seen) == 1
    msg = seen[0]
    assert msg.platform == "console"
    assert msg.text == "!create barbarian orc Thorak"  # trimmed
    assert msg.is_mod is True  # dev user is a mod so mod commands are testable
    assert msg.login == "dev"
    # can_send is True -> the chat mirror is echoed to the console
    assert out == ["[chat] echo:!create barbarian orc Thorak"]


def test_blank_lines_are_ignored():
    calls = 0

    async def dispatch(_msg: InboundMessage) -> list[str]:
        nonlocal calls
        calls += 1
        return []

    adapter = ConsoleAdapter(dispatch, out=lambda _line: None)
    asyncio.run(adapter.dispatch_line("   \n"))
    asyncio.run(adapter.dispatch_line(""))
    assert calls == 0


def test_dispatch_error_is_contained():
    async def dispatch(_msg: InboundMessage) -> list[str]:
        raise RuntimeError("boom")

    adapter = ConsoleAdapter(dispatch, out=lambda _line: None)
    # A failing dispatch must not raise out of the adapter (round loop safety).
    asyncio.run(adapter.dispatch_line("!help"))


def test_implements_chat_adapter_shape():
    from server.adapters import ChatAdapter

    async def dispatch(_msg: InboundMessage) -> list[str]:
        return []

    adapter = ConsoleAdapter(dispatch, out=lambda _line: None)
    assert isinstance(adapter, ChatAdapter)  # runtime_checkable protocol
    assert adapter.platform == "console" and adapter.can_send is True
