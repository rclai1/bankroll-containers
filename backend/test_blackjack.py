"""Tests for the blackjack API. Run from the project root: ``python -m unittest backend.test_blackjack``
(or from backend/: ``python -m unittest test_blackjack``).

Route functions are called directly (no HTTP client needed) and the deck is
rigged: ``rig(...)`` lists cards in draw order. Deal order is each seated
player in seat order (2 cards each), then the dealer (2 cards), then hits.
"""

import asyncio
import logging
import os
import sys
import time
import types
import unittest
from unittest import mock

# The app lives in the ``backend.app`` package, so the project root (the folder above backend/) must be importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.app.routers.blackjack_api as bj  # noqa: E402
import backend.app.routers.cpu_agents as cpu_agents  # noqa: E402
from backend.app.routers.cpu_agents import Action, BetChoice, DefaultCpuAgent, bet_for_choice  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def rig(*cards):
    """A deck that deals ``cards`` in order (then harmless filler)."""
    return ["2 of clubs"] * 30 + list(reversed(cards))


class ScriptedAgent:
    """Test agent: returns canned answers, records what it was shown."""

    def __init__(self, actions=(), bet=BetChoice.MIN, delay=0.0, raises=False):
        self.actions = list(actions)
        self.bet = bet
        self.delay = delay
        self.raises = raises
        self.contexts = []

    async def choose_bet(self, ctx):
        self.contexts.append(ctx)
        await asyncio.sleep(self.delay)
        return self.bet

    async def choose_action(self, ctx):
        self.contexts.append(ctx)
        if self.raises:
            raise RuntimeError("boom")
        await asyncio.sleep(self.delay)
        return self.actions.pop(0) if self.actions else Action.STAND


class BlackjackTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Never touch the real Gemini API from tests: force the default agent
        # and make creating the real client an error.
        def no_real_client():
            raise AssertionError("tests must not create the real Gemini client")

        patches = [
            mock.patch.object(cpu_agents, "CPU_MIN_ACTION_SECONDS", 0.05),  # keep CPU timing tests fast
            mock.patch.object(cpu_agents, "CPU_MAX_ACTION_SECONDS", 0.3),
            mock.patch.dict(os.environ, {"CPU_AGENT": "default"}),
            mock.patch.object(cpu_agents, "_get_client", no_real_client),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        bj.games.clear()  # games are module-global; keep tests independent

    def new_game(self, bankroll=100.0, cpus=0):
        view = bj.create_game(bj.NewGameRequest(bankroll=bankroll, cpu_count=cpus))
        return bj.games[view["game_id"]]

    async def deal(self, game, deck, amount=10.0):
        with mock.patch.object(bj, "_new_deck", return_value=rig(*deck)):
            return await bj.bet(game.game_id, bj.BetRequest(amount=amount))

    def human(self, game):
        return game.players[0]


class SinglePlayerTests(BlackjackTestCase):
    async def test_min_bet_enforced(self):
        game = self.new_game()
        with self.assertRaises(HTTPException) as ctx:
            await bj.bet(game.game_id, bj.BetRequest(amount=5))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_all_in_below_min_allowed(self):
        game = self.new_game(bankroll=5)
        view = await self.deal(game, ["10 of hearts", "9 of hearts", "10 of clubs", "7 of clubs"], amount=5)
        self.assertEqual(view["players"][0]["bet_amount"], 5)

    async def test_bet_over_bankroll_rejected(self):
        game = self.new_game(bankroll=50)
        with self.assertRaises(HTTPException) as ctx:
            await bj.bet(game.game_id, bj.BetRequest(amount=60))
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_player_natural_pays_3_to_2(self):
        game = self.new_game()
        view = await self.deal(game, ["A of spades", "K of spades", "9 of clubs", "8 of clubs"])
        self.assertEqual(view["status"], "finished")
        self.assertEqual(view["players"][0]["result"], "blackjack")
        self.assertEqual(view["players"][0]["bankroll"], 115.0)
        self.assertEqual(view["pot_amount"], 10.0)

    async def test_dealer_natural_beats_player(self):
        game = self.new_game()
        view = await self.deal(game, ["10 of hearts", "K of hearts", "A of clubs", "K of clubs"])
        self.assertEqual(view["players"][0]["result"], "loss")
        self.assertEqual(view["players"][0]["bankroll"], 90.0)

    async def test_both_natural_push(self):
        game = self.new_game()
        view = await self.deal(game, ["A of hearts", "K of hearts", "A of clubs", "K of clubs"])
        self.assertEqual(view["players"][0]["result"], "push")
        self.assertEqual(view["players"][0]["bankroll"], 100.0)

    async def test_stand_win(self):
        game = self.new_game()
        await self.deal(game, ["10 of hearts", "9 of hearts", "10 of clubs", "7 of clubs"])
        view = bj.stand(game.game_id)
        self.assertEqual(view["status"], "finished")
        self.assertEqual(view["players"][0]["result"], "win")
        self.assertEqual(view["players"][0]["bankroll"], 110.0)
        self.assertEqual([e["action"] for e in view["events"]], ["stand", "flip"])

    async def test_hit_bust_loses_and_dealer_does_not_draw(self):
        game = self.new_game()
        await self.deal(game, ["10 of hearts", "6 of hearts", "5 of clubs", "6 of clubs", "10 of spades"])
        view = bj.hit(game.game_id)
        self.assertEqual(view["players"][0]["player_status"], "bust")
        self.assertEqual(view["players"][0]["result"], "loss")
        self.assertEqual(view["status"], "finished")
        self.assertEqual(len(view["dealer_hand"]), 2)

    async def test_hit_to_21_auto_stands(self):
        game = self.new_game()
        await self.deal(game, ["10 of hearts", "5 of hearts", "10 of clubs", "7 of clubs", "6 of spades"])
        view = bj.hit(game.game_id)
        self.assertEqual(view["status"], "finished")
        self.assertEqual(view["players"][0]["result"], "win")

    async def test_double_down(self):
        game = self.new_game()
        await self.deal(game, ["5 of hearts", "6 of hearts", "10 of clubs", "7 of clubs", "10 of spades"])
        view = bj.double_down(game.game_id)
        player = view["players"][0]
        self.assertEqual(len(player["hand"]), 3)
        self.assertEqual(player["bet_amount"], 20.0)
        self.assertEqual(player["player_status"], "double_down")
        self.assertEqual(player["result"], "win")
        self.assertEqual(player["bankroll"], 120.0)
        self.assertEqual(view["pot_amount"], 20.0)
        self.assertEqual(view["status"], "finished")

    async def test_double_down_bust_loses_both_bets(self):
        game = self.new_game()
        await self.deal(game, ["10 of hearts", "6 of hearts", "10 of clubs", "7 of clubs", "10 of spades"])
        view = bj.double_down(game.game_id)
        self.assertEqual(view["players"][0]["result"], "loss")
        self.assertEqual(view["players"][0]["bankroll"], 80.0)

    async def test_double_down_needs_bankroll(self):
        game = self.new_game(bankroll=15)
        await self.deal(game, ["5 of hearts", "6 of hearts", "10 of clubs", "7 of clubs"])
        self.assertNotIn("double_down", bj._view(game)["players"][0]["legal_actions"])
        with self.assertRaises(HTTPException) as ctx:
            bj.double_down(game.game_id)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_double_and_surrender_only_as_first_action(self):
        game = self.new_game()
        await self.deal(game, ["2 of hearts", "3 of hearts", "10 of clubs", "7 of clubs", "2 of spades"])
        self.assertEqual(
            bj._view(game)["players"][0]["legal_actions"], ["hit", "stand", "double_down", "surrender"]
        )
        bj.hit(game.game_id)
        self.assertEqual(bj._view(game)["players"][0]["legal_actions"], ["hit", "stand"])
        for route in (bj.double_down, bj.surrender):
            with self.assertRaises(HTTPException) as ctx:
                route(game.game_id)
            self.assertEqual(ctx.exception.status_code, 409)

    async def test_surrender_returns_half(self):
        game = self.new_game()
        await self.deal(game, ["10 of hearts", "6 of hearts", "10 of clubs", "7 of clubs"])
        view = bj.surrender(game.game_id)
        self.assertEqual(view["players"][0]["result"], "surrender")
        self.assertEqual(view["players"][0]["player_status"], "surrender")
        self.assertEqual(view["players"][0]["bankroll"], 95.0)
        self.assertEqual(view["status"], "finished")
        self.assertEqual(len(view["dealer_hand"]), 2)

    async def test_hole_card_hidden_while_playing(self):
        game = self.new_game()
        view = await self.deal(game, ["10 of hearts", "9 of hearts", "10 of clubs", "7 of clubs"])
        self.assertEqual(view["dealer_hand"], ["10 of clubs"])
        self.assertIsNone(view["dealer_score"])

    async def test_actions_rejected_without_round(self):
        game = self.new_game()
        with self.assertRaises(HTTPException) as ctx:
            bj.hit(game.game_id)
        self.assertEqual(ctx.exception.status_code, 409)


class DailyAndAdviceTests(BlackjackTestCase):
    """Daily mode (seeded, saved to the database) and Learning-mode advice on the multi-player game."""

    def daily_row(self, seed=1234, money=100.0):
        return {"id": 7, "seed": seed, "curr_money": money, "cash_out": False}

    def open_daily(self, **row):
        with mock.patch.object(bj, "get_daily_game", return_value=self.daily_row(**row)):
            return bj.create_daily_game(user_id=1)

    async def test_daily_game_has_one_human_and_the_saved_balance(self):
        view = self.open_daily(money=250.0)
        self.assertEqual(view["cash_out"], False)
        self.assertEqual(view["seed"], 1234)
        self.assertEqual(len(view["players"]), 1)
        self.assertEqual(view["players"][0]["bankroll"], 250.0)

    async def test_cashed_out_daily_returns_the_score(self):
        with mock.patch.object(bj, "get_daily_game", return_value={**self.daily_row(), "cash_out": True, "curr_money": 321.0}):
            self.assertEqual(bj.create_daily_game(user_id=1), {"cash_out": True, "score": 321.0, "seed": 1234})

    async def test_same_seed_deals_the_same_cards(self):
        hands = []
        for _ in range(2):
            bj.games.clear()
            view = self.open_daily(seed=99)
            game = bj.games[view["game_id"]]
            with mock.patch.object(bj, "_ensure_daily_open"), mock.patch.object(bj, "save_daily_score"):
                result = await bj.bet(game.game_id, bj.BetRequest(amount=10))
            hands.append((result["players"][0]["hand"], result["dealer_hand"][:1]))
        self.assertEqual(hands[0], hands[1])

    async def test_finished_round_saves_the_humans_bankroll(self):
        view = self.open_daily()
        game = bj.games[view["game_id"]]
        with mock.patch.object(bj, "_ensure_daily_open"), mock.patch.object(bj, "save_daily_score") as save:
            with mock.patch.object(bj, "_new_deck", return_value=rig("10 of hearts", "9 of hearts", "10 of clubs", "7 of clubs")):
                await bj.bet(game.game_id, bj.BetRequest(amount=10))
            save.assert_not_called()  # round still in progress
            bj.stand(game.game_id)
            save.assert_called_once_with(7, 110.0)

    async def test_daily_actions_are_blocked_once_cashed_out(self):
        view = self.open_daily()
        game = bj.games[view["game_id"]]
        with mock.patch.object(bj, "_ensure_daily_open", side_effect=HTTPException(status_code=409, detail="cashed out")):
            with self.assertRaises(HTTPException):
                await bj.bet(game.game_id, bj.BetRequest(amount=10))

    async def test_advice_uses_the_humans_hand(self):
        game = self.new_game()
        await self.deal(game, ["10 of hearts", "6 of hearts", "10 of clubs", "7 of clubs"])
        advice = bj.get_game_advice(game.game_id)
        self.assertIn(advice["best_move"], ("hit", "stand"))
        self.assertEqual(advice["bet_amount"], 10.0)

    async def test_advice_needs_the_players_turn_and_no_cpus(self):
        game = self.new_game()
        with self.assertRaises(HTTPException):  # no round yet
            bj.get_game_advice(game.game_id)
        cpu_game = self.new_game(cpus=1)
        await self.deal(cpu_game, HUMAN_19 + CPU1_16 + DEALER_17)
        with self.assertRaises(HTTPException) as ctx:
            bj.get_game_advice(cpu_game.game_id)
        self.assertEqual(ctx.exception.status_code, 409)


class BetChoiceTests(unittest.TestCase):
    def test_bet_for_choice(self):
        self.assertEqual(bet_for_choice(BetChoice.MIN, 100), 10)
        self.assertEqual(bet_for_choice(BetChoice.PCT_25, 100), 25)
        self.assertEqual(bet_for_choice(BetChoice.PCT_50, 100), 50)
        self.assertEqual(bet_for_choice(BetChoice.PCT_75, 100), 75)
        self.assertEqual(bet_for_choice(BetChoice.ALL_IN, 100), 100)
        # Percentages never go below the minimum bet, and never above the bankroll.
        self.assertEqual(bet_for_choice(BetChoice.PCT_25, 20), 10)
        self.assertEqual(bet_for_choice(BetChoice.MIN, 8), 8)
        self.assertEqual(bet_for_choice(BetChoice.PCT_75, 8), 8)


# Deal order for 2 CPUs: human, cpu1, cpu2, dealer.
HUMAN_19 = ["10 of hearts", "9 of hearts"]
CPU1_16 = ["10 of diamonds", "6 of diamonds"]
CPU2_18 = ["10 of spades", "8 of spades"]
DEALER_17 = ["10 of clubs", "7 of clubs"]


class CpuTests(BlackjackTestCase):
    async def test_cpu_turns_play_one_action_per_call(self):
        game = self.new_game(cpus=2)
        view = await self.deal(game, HUMAN_19 + CPU1_16 + CPU2_18 + DEALER_17 + ["5 of hearts"])
        self.assertEqual(view["pot_amount"], 30.0)
        self.assertEqual(view["current_player"], 0)

        view = bj.stand(game.game_id)  # human done; round is NOT finished yet
        self.assertEqual(view["status"], "playing")
        self.assertEqual(view["current_player"], 1)

        view = await bj.cpu_turn(game.game_id)  # CPU1 has 16 -> default agent hits, draws 5 -> 21
        self.assertEqual([e["action"] for e in view["events"]], ["hit", "stand"])
        self.assertEqual(view["current_player"], 2)

        view = await bj.cpu_turn(game.game_id)  # CPU2 has 18 -> stands; dealer then plays
        self.assertEqual(view["status"], "finished")
        self.assertEqual([e["action"] for e in view["events"]], ["stand", "flip"])
        self.assertEqual([p["result"] for p in view["players"]], ["win", "win", "win"])

    async def test_human_cannot_act_during_cpu_turn(self):
        game = self.new_game(cpus=1)
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
        bj.stand(game.game_id)
        for route in (bj.hit, bj.stand, bj.double_down, bj.surrender):
            with self.assertRaises(HTTPException) as ctx:
                route(game.game_id)
            self.assertEqual(ctx.exception.status_code, 409)

    async def test_cpu_turn_rejected_on_human_turn(self):
        game = self.new_game(cpus=1)
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
        with self.assertRaises(HTTPException) as ctx:
            await bj.cpu_turn(game.game_id)
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_concurrent_cpu_turn_rejected(self):
        game = self.new_game(cpus=1)
        game.players[1].agent = ScriptedAgent(delay=0.2)
        with mock.patch.object(cpu_agents, "CPU_MAX_ACTION_SECONDS", 1.0):
            await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
            bj.stand(game.game_id)
            first = asyncio.create_task(bj.cpu_turn(game.game_id))
            await asyncio.sleep(0.05)
            with self.assertRaises(HTTPException) as ctx:
                await bj.cpu_turn(game.game_id)
            self.assertEqual(ctx.exception.status_code, 409)
            await first

    async def test_cpu_never_acts_faster_than_minimum(self):
        game = self.new_game(cpus=1)
        game.players[1].agent = ScriptedAgent([Action.STAND])
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
        bj.stand(game.game_id)
        with mock.patch.object(cpu_agents, "CPU_MIN_ACTION_SECONDS", 0.2):
            started = time.monotonic()
            await bj.cpu_turn(game.game_id)
            self.assertGreaterEqual(time.monotonic() - started, 0.19)

    async def test_slow_cpu_is_cut_off_and_stands(self):
        game = self.new_game(cpus=1)
        game.players[1].agent = ScriptedAgent([Action.HIT], delay=5)
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
        bj.stand(game.game_id)
        started = time.monotonic()
        view = await bj.cpu_turn(game.game_id)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(view["players"][1]["player_status"], "stood")
        self.assertEqual(len(view["players"][1]["hand"]), 2)

    async def test_failing_or_illegal_agent_stands(self):
        for agent in (ScriptedAgent(raises=True), ScriptedAgent(["banana"])):
            game = self.new_game(cpus=1)
            game.players[1].agent = agent
            await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
            bj.stand(game.game_id)
            view = await bj.cpu_turn(game.game_id)
            self.assertEqual(view["players"][1]["player_status"], "stood")

    async def test_cpu_can_double_and_surrender(self):
        game = self.new_game(cpus=2)
        game.players[1].agent = ScriptedAgent([Action.DOUBLE_DOWN])
        game.players[2].agent = ScriptedAgent([Action.SURRENDER])
        await self.deal(game, HUMAN_19 + CPU1_16 + CPU2_18 + DEALER_17 + ["5 of hearts"])
        bj.stand(game.game_id)
        view = await bj.cpu_turn(game.game_id)
        self.assertEqual(view["players"][1]["bet_amount"], 20.0)
        self.assertEqual(view["pot_amount"], 40.0)
        view = await bj.cpu_turn(game.game_id)
        self.assertEqual(view["players"][2]["result"], "surrender")
        self.assertEqual(view["players"][2]["bankroll"], 95.0)
        self.assertEqual(view["status"], "finished")

    async def test_agent_never_sees_hole_card(self):
        game = self.new_game(cpus=1)
        agent = ScriptedAgent()
        game.players[1].agent = agent
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
        bj.stand(game.game_id)
        await bj.cpu_turn(game.game_id)
        hole = DEALER_17[1]
        for ctx in agent.contexts:
            self.assertNotIn(hole, repr(ctx))
        self.assertEqual(agent.contexts[-1].dealer_upcard, DEALER_17[0])
        self.assertEqual(agent.contexts[-1].legal_actions[:2], [Action.HIT, Action.STAND])

    async def test_cpu_bet_choices_and_timeout(self):
        game = self.new_game(cpus=2)
        game.players[1].agent = ScriptedAgent(bet=BetChoice.PCT_50)
        game.players[2].agent = ScriptedAgent(bet=BetChoice.ALL_IN, delay=5)  # too slow -> MIN
        view = await self.deal(game, HUMAN_19 + CPU1_16 + CPU2_18 + DEALER_17)
        self.assertEqual([p["bet_amount"] for p in view["players"]], [10.0, 50.0, 10.0])
        self.assertEqual(view["pot_amount"], 70.0)

    async def test_broke_cpu_sits_out(self):
        game = self.new_game(cpus=1)
        game.players[1].bankroll = 0
        view = await self.deal(game, HUMAN_19 + DEALER_17)
        cpu = view["players"][1]
        self.assertEqual(cpu["player_status"], "out")
        self.assertEqual(cpu["hand"], [])
        self.assertEqual(view["pot_amount"], 10.0)
        view = bj.stand(game.game_id)
        self.assertEqual(view["status"], "finished")

    async def test_human_busts_cpus_still_play(self):
        game = self.new_game(cpus=1)
        await self.deal(game, ["10 of hearts", "6 of hearts"] + CPU1_16 + DEALER_17 + ["10 of spades", "2 of hearts"])
        view = bj.hit(game.game_id)
        self.assertEqual(view["players"][0]["result"], "loss")
        self.assertEqual(view["status"], "playing")
        self.assertEqual(view["current_player"], 1)

    async def test_default_agent_matches_framework_contract(self):
        ctx = cpu_agents.CpuContext(
            index=1, bankroll=100, bet_amount=10, hand=["10 of hearts", "6 of hearts"], score=16,
            dealer_upcard="9 of clubs", others=[], legal_actions=[Action.HIT, Action.STAND],
        )
        self.assertEqual(await DefaultCpuAgent().choose_action(ctx), Action.HIT)
        self.assertEqual(await DefaultCpuAgent().choose_bet(ctx), BetChoice.MIN)


class FakeInteractions:
    """Stands in for client.aio.interactions; replies are JSON strings or exceptions."""

    def __init__(self, replies, delay=0.0):
        self.replies = list(replies)
        self.delay = delay
        self.calls = []

    async def create(self, **request):
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return types.SimpleNamespace(id=f"int-{id(self)}-{len(self.calls)}", output_text=reply)


def fake_client(replies, delay=0.0):
    interactions = FakeInteractions(replies, delay)
    return types.SimpleNamespace(aio=types.SimpleNamespace(interactions=interactions)), interactions


class ApiError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def make_ctx(**overrides):
    values = dict(
        index=1, bankroll=100.0, bet_amount=10.0, hand=["10 of hearts", "6 of hearts"], score=16,
        dealer_upcard="9 of clubs", others=[], legal_actions=[Action.HIT, Action.STAND, Action.DOUBLE_DOWN],
        events=[], round_number=1,
    )
    values.update(overrides)
    return cpu_agents.CpuContext(**values)


class GeminiClientTests(BlackjackTestCase):
    """The real SDK client, but talking to a mock HTTP transport (no network, no API key use)."""

    async def requests_sent(self, **env):
        import httpx
        from google import genai
        from google.genai import types as gtypes

        hits = []

        def handler(request):
            hits.append(str(request.url))
            return httpx.Response(503, json={"error": {"code": 503, "message": "unavailable", "status": "UNAVAILABLE"}})

        real_client = genai.Client

        def client_with_mock_transport(**kwargs):
            kwargs["http_options"].httpx_async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return real_client(**kwargs)

        with mock.patch.dict(os.environ, env), mock.patch.object(genai, "Client", client_with_mock_transport):
            client = cpu_agents._build_client(genai, gtypes, "test-key")
        with self.assertRaises(Exception):
            await client.aio.interactions.create(model="m", input="hi", timeout=5)
        self.assertFalse(any("test-key" in url for url in hits))  # the key travels in a header, not the URL
        return len(hits)

    async def test_sdk_does_not_retry_by_default(self):
        self.assertEqual(await self.requests_sent(), 1)

    async def test_sdk_retries_are_configurable(self):
        self.assertEqual(await self.requests_sent(GEMINI_SDK_RETRIES="1"), 2)

    async def test_invalid_retry_setting_falls_back_to_no_retries(self):
        with self.assertLogs("cpu_agents", level="WARNING"):
            self.assertEqual(await self.requests_sent(GEMINI_SDK_RETRIES="lots"), 1)

    def test_api_keys_are_redacted_from_log_lines(self):
        record = logging.LogRecord("httpx", logging.INFO, __file__, 1, 'POST https://x/y?key=SECRET123&a=1 "200 OK"', (), None)
        cpu_agents._RedactKeys().filter(record)
        self.assertNotIn("SECRET123", record.getMessage())
        self.assertIn("key=REDACTED&a=1", record.getMessage())


class GeminiAgentTests(BlackjackTestCase):
    async def test_bet_and_action_are_parsed_and_share_one_chain(self):
        client, calls = fake_client(['{"choice": "25%"}', '{"action": "hit"}'])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        self.assertEqual(await agent.choose_bet(make_ctx(legal_actions=[])), BetChoice.PCT_25)
        self.assertEqual(await agent.choose_action(make_ctx()), Action.HIT)

        first, second = calls.calls
        self.assertNotIn("previous_interaction_id", first)
        self.assertEqual(second["previous_interaction_id"], f"int-{id(calls)}-1")
        for call in (first, second):
            self.assertTrue(call["store"])
            self.assertEqual(call["system_instruction"], cpu_agents.SYSTEM_INSTRUCTION)
            self.assertEqual(call["response_format"]["mime_type"], "application/json")
            self.assertLess(call["timeout"], cpu_agents.CPU_MAX_ACTION_SECONDS + 1)
        self.assertEqual(
            first["response_format"]["schema"]["properties"]["choice"]["enum"], [c.value for c in BetChoice]
        )

    async def test_thinking_level_is_sent_and_configurable(self):
        client, calls = fake_client(['{"action": "hit"}'] * 4)
        agent = cpu_agents.GeminiCpuAgent(client=client)
        with mock.patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": ""}):
            os.environ.pop("GEMINI_THINKING_LEVEL")
            await agent.choose_action(make_ctx())  # default
        with mock.patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "minimal"}):
            await agent.choose_action(make_ctx())
        with mock.patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "default"}):
            await agent.choose_action(make_ctx())  # explicitly left to the API
        with mock.patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "bogus"}):
            with self.assertLogs("cpu_agents", level="WARNING"):
                await agent.choose_action(make_ctx())  # invalid values are ignored
        levels = [c.get("generation_config", {}).get("thinking_level") for c in calls.calls]
        self.assertEqual(levels, [cpu_agents.GEMINI_THINKING_LEVEL, "minimal", None, None])

    async def test_latency_is_logged_for_success_failure_and_cancellation(self):
        client, calls = fake_client(['{"action": "hit"}', RuntimeError("boom")])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        with self.assertLogs("cpu_agents", level="INFO") as logs:
            await agent.choose_action(make_ctx(index=2))
            with self.assertRaises(RuntimeError):
                await agent.choose_action(make_ctx(index=2))
        text = "\n".join(logs.output)
        self.assertRegex(text, r"action \(seat 2, chain turn 1, thinking \w+, \d+ chars\) answered in \d+\.\d\ds")
        self.assertRegex(text, r"failed after \d+\.\d\ds: RuntimeError: boom")

        slow_client, slow_calls = fake_client(['{"action": "hit"}'], delay=5)
        slow = cpu_agents.GeminiCpuAgent(client=slow_client)
        with self.assertLogs("cpu_agents", level="WARNING") as logs:
            await cpu_agents.timed_cpu_action(slow, make_ctx())
        self.assertRegex("\n".join(logs.output), r"cancelled after \d+\.\d\ds \(hit the 0s CPU cap\)")

    async def test_action_schema_only_lists_legal_actions(self):
        client, calls = fake_client(['{"action": "stand"}'])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        await agent.choose_action(make_ctx(legal_actions=[Action.HIT, Action.STAND]))
        enum = calls.calls[0]["response_format"]["schema"]["properties"]["action"]["enum"]
        self.assertEqual(enum, ["hit", "stand"])

    async def test_no_legal_actions_means_stand_without_calling_api(self):
        client, calls = fake_client([])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        self.assertEqual(await agent.choose_action(make_ctx(legal_actions=[])), Action.STAND)
        self.assertEqual(calls.calls, [])

    async def test_each_seat_has_its_own_chain(self):
        client, calls = fake_client(['{"action": "hit"}'] * 4)
        seat1, seat2 = cpu_agents.GeminiCpuAgent(client=client), cpu_agents.GeminiCpuAgent(client=client)
        await seat1.choose_action(make_ctx(index=1))
        await seat2.choose_action(make_ctx(index=2))
        await seat1.choose_action(make_ctx(index=1))
        await seat2.choose_action(make_ctx(index=2))
        c1, c2, c3, c4 = calls.calls
        self.assertNotIn("previous_interaction_id", c1)
        self.assertNotIn("previous_interaction_id", c2)  # seat 2 does NOT continue seat 1's chain
        self.assertEqual(c3["previous_interaction_id"], f"int-{id(calls)}-1")
        self.assertEqual(c4["previous_interaction_id"], f"int-{id(calls)}-2")

    async def test_failed_or_timed_out_call_does_not_advance_chain(self):
        client, calls = fake_client(['{"action": "hit"}', RuntimeError("boom"), '{"action": "hit"}'])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        await agent.choose_action(make_ctx())
        with self.assertRaises(RuntimeError):
            await agent.choose_action(make_ctx())
        await agent.choose_action(make_ctx())
        self.assertEqual(calls.calls[2]["previous_interaction_id"], f"int-{id(calls)}-1")

        slow_client, slow_calls = fake_client(['{"action": "hit"}'] * 2, delay=0.0)
        slow = cpu_agents.GeminiCpuAgent(client=slow_client)
        await slow.choose_action(make_ctx())
        slow_calls.delay = 5
        with self.assertLogs("cpu_agents", level="WARNING"):
            self.assertEqual(await cpu_agents.timed_cpu_action(slow, make_ctx()), Action.STAND)
        self.assertEqual(slow._last_id, f"int-{id(slow_calls)}-1")

    async def test_rejected_chain_id_starts_a_new_chain(self):
        client, calls = fake_client(['{"action": "hit"}', ApiError(404), '{"action": "hit"}'])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        await agent.choose_action(make_ctx())
        with self.assertLogs("cpu_agents", level="WARNING"):
            with self.assertRaises(ApiError):
                await agent.choose_action(make_ctx())
        await agent.choose_action(make_ctx())
        self.assertNotIn("previous_interaction_id", calls.calls[2])

    async def test_chain_restarts_after_the_turn_cap(self):
        client, calls = fake_client(['{"action": "hit"}'] * 3)
        agent = cpu_agents.GeminiCpuAgent(client=client)
        with mock.patch.object(cpu_agents, "GEMINI_MAX_CHAIN_TURNS", 2):
            for _ in range(3):
                await agent.choose_action(make_ctx())
        self.assertIn("previous_interaction_id", calls.calls[1])
        self.assertNotIn("previous_interaction_id", calls.calls[2])

    async def test_bad_replies_fall_back_safely(self):
        for reply in ("not json", '{"action": "banana"}', '{"nope": 1}'):
            client, _ = fake_client([reply])
            agent = cpu_agents.GeminiCpuAgent(client=client)
            with self.assertLogs("cpu_agents", level="WARNING"):
                self.assertEqual(await cpu_agents.timed_cpu_action(agent, make_ctx()), Action.STAND)
        client, _ = fake_client(['{"choice": "banana"}'])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        with self.assertLogs("cpu_agents", level="WARNING"):
            self.assertEqual(await cpu_agents.timed_cpu_bet(agent, make_ctx(legal_actions=[])), BetChoice.MIN)

    async def test_prompts_only_carry_new_events_and_never_the_hole_card(self):
        client, calls = fake_client(['{"action": "hit"}'] * 3)
        agent = cpu_agents.GeminiCpuAgent(client=client)
        bet = {"actor": "player", "action": "bet", "index": 0, "amount": 10.0}
        hit = {"actor": "player", "action": "hit", "index": 0, "card": "5 of spades"}
        await agent.choose_action(make_ctx(events=[bet]))
        await agent.choose_action(make_ctx(events=[bet, hit]))
        await agent.choose_action(make_ctx(events=[bet], round_number=2))  # new round: everything is new again
        first, second, third = (c["input"] for c in calls.calls)
        self.assertIn("bet $10.00", first)
        self.assertNotIn("bet $10.00", second)
        self.assertIn("hit and drew 5 of spades", second)
        self.assertIn("bet $10.00", third)

    async def test_betting_prompt_reports_last_rounds_ending(self):
        client, calls = fake_client(['{"choice": "min"}'])
        agent = cpu_agents.GeminiCpuAgent(client=client)
        events = [{"actor": "dealer", "action": "flip", "card": "7 of clubs"}]
        await agent.choose_bet(make_ctx(events=events, result="loss", legal_actions=[]))
        prompt = calls.calls[0]["input"]
        self.assertIn("Dealer reveals the hole card: 7 of clubs", prompt)
        self.assertIn("result last round: loss", prompt)

    async def test_get_cpu_agent_falls_back_when_gemini_is_unavailable(self):
        with mock.patch.dict(os.environ, {"CPU_AGENT": "gemini"}):
            with self.assertLogs("cpu_agents", level="WARNING"):
                self.assertIsInstance(cpu_agents.get_cpu_agent(), DefaultCpuAgent)

    async def test_game_passes_round_number_result_and_previous_round_log(self):
        game = self.new_game(cpus=1)
        agent = ScriptedAgent([Action.HIT])
        game.players[1].agent = agent
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17 + ["5 of hearts"])
        bj.stand(game.game_id)
        await bj.cpu_turn(game.game_id)  # CPU1 hits to 21 and stands; dealer plays; round 1 over
        self.assertEqual(agent.contexts[-1].round_number, 1)

        agent.contexts.clear()
        await self.deal(game, HUMAN_19 + CPU1_16 + DEALER_17)
        betting_ctx = agent.contexts[0]  # the bet request for round 2
        self.assertEqual(betting_ctx.round_number, 1)  # still describes round 1
        self.assertEqual(betting_ctx.result, "win")
        self.assertTrue(any(e["actor"] == "dealer" and e["action"] == "flip" for e in betting_ctx.events))
        self.assertEqual(game.round, 2)


if __name__ == "__main__":
    unittest.main()
