"""Tests for chat announcements and the fan-out sink."""

from __future__ import annotations

import asyncio

from server import events
from server.announce import ChatAnnouncer


class _Boom:
    async def emit(self, event):
        raise RuntimeError("sink is down")


def test_fanout_delivers_to_all_and_isolates_failures():
    a, b = events.RecordingSink(), events.RecordingSink()
    fan = events.FanoutSink(a, _Boom(), b)  # bad sink in the middle
    asyncio.run(fan.emit({"type": "attack"}))
    assert a.events == b.events == [{"type": "attack"}]  # both still got it


def _collect(evts):
    sent: list[str] = []

    async def send(msg: str) -> None:
        sent.append(msg)

    ann = ChatAnnouncer(send)

    async def run():
        for e in evts:
            await ann.emit(e)

    asyncio.run(run())
    return sent


def test_round_start_names_players_not_npcs():
    evt = {
        "type": "round_start",
        "round_id": 7,
        "fighters": [
            {"name": "Thorak", "is_npc": False},
            {"name": "[NPC] Rusty", "is_npc": True},
            {"name": "Pip", "is_npc": False},
        ],
    }
    (line,) = _collect([evt])
    assert "Round 7 begins!" in line
    assert "Thorak" in line and "Pip" in line
    assert "Rusty" not in line


def test_round_end_announces_winner_and_top3():
    evt = {
        "type": "round_end",
        "standings": [
            {"name": "Pip", "total": 1873, "placement": 1},
            {"name": "Thorak", "total": 1720, "placement": 2},
            {"name": "Nyx", "total": 1500, "placement": 3},
            {"name": "Zed", "total": 900, "placement": 4},
        ],
    }
    (line,) = _collect([evt])
    assert line.startswith("Winner: Pip with 1,873 damage!")
    assert "Zed" not in line  # only top 3 on the podium


def test_intermission_open_announced_once_at_second_1():
    lines = _collect(
        [
            {"type": "countdown", "phase": "intermission", "seconds_left": 90},
            {"type": "countdown", "phase": "intermission", "seconds_left": 1},
            {"type": "countdown", "phase": "results", "seconds_left": 1},
        ]
    )
    assert len(lines) == 1
    assert "Arena is open" in lines[0]
