#!/usr/bin/env python3
"""Daily market scanner - find and execute trading opportunities.

Strategies:
  1. Endgame (终局交易): Markets >90% probability, buy the winning side cheap
  2. Mispricing (定价偏差): YES+NO prices don't sum to ~$1.00
  3. Expiring Soon (即将结算): Markets ending within 24h with clear direction

Usage:
    daily_scan.py scan                    # Scan only, report opportunities
    daily_scan.py scan --auto             # Scan + auto-execute within limits
    daily_scan.py scan --query "Bitcoin"  # Scan specific topic
    daily_scan.py scan --max-bet 3        # Max bet per trade (default $3)
    daily_scan.py scan --min-edge 0.05    # Min expected edge (default 5%)
"""

import sys
import os
import json
import asyncio
import argparse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from lib.gamma_client import GammaClient, Market


@dataclass
class Opportunity:
    """A detected trading opportunity."""
    strategy: str
    market_id: str
    question: str
    side: str
    price: float
    edge: float
    confidence: str
    end_date: str
    reasoning: str

    @property
    def expected_return(self) -> float:
        return 1.0 - self.price


class DailyScanner:
    """Scans Polymarket for trading opportunities."""

    def __init__(self, min_edge: float = 0.05, min_volume: float = 5000):
        self.min_edge = min_edge
        self.min_volume = min_volume
        self.gamma = GammaClient()

    async def scan_all(self, query: Optional[str] = None, limit: int = 50) -> list[Opportunity]:
        """Run all strategies, return combined opportunities sorted by edge."""
        if query:
            markets = await self.gamma.search_markets(query)
        else:
            markets = await self.gamma.get_trending_markets(limit=limit)

        markets = [m for m in markets
                   if m.active and not m.resolved and not m.closed
                   and m.volume > self.min_volume]

        opps = []
        opps.extend(self._endgame(markets))
        opps.extend(self._mispricing(markets))
        opps.extend(self._expiring(markets))
        opps.sort(key=lambda o: o.edge, reverse=True)
        return opps

    def _endgame(self, markets: list[Market]) -> list[Opportunity]:
        """终局交易: >90% on one side, buy the near-certain winner."""
        opps = []
        for m in markets:
            for side, price in [("YES", m.yes_price), ("NO", m.no_price)]:
                if 0.90 <= price < 1.0:
                    edge = 1.0 - price
                    if edge >= self.min_edge:
                        conf = "high" if price >= 0.95 else "medium"
                        opps.append(Opportunity(
                            strategy="endgame", market_id=m.id, question=m.question,
                            side=side, price=price, edge=edge, confidence=conf,
                            end_date=m.end_date,
                            reasoning=f"{side} at {price:.0%}, {edge:.0%} edge"
                        ))
        return opps

    def _mispricing(self, markets: list[Market]) -> list[Opportunity]:
        """定价偏差: YES+NO < $0.95 means buy both for guaranteed profit."""
        opps = []
        for m in markets:
            total = m.yes_price + m.no_price
            if total < 0.95:
                edge = 1.0 - total
                opps.append(Opportunity(
                    strategy="mispricing", market_id=m.id, question=m.question,
                    side="BOTH", price=total, edge=edge, confidence="high",
                    end_date=m.end_date,
                    reasoning=f"YES({m.yes_price:.2f})+NO({m.no_price:.2f})={total:.2f}, arb {edge:.0%}"
                ))
        return opps

    def _expiring(self, markets: list[Market]) -> list[Opportunity]:
        """即将结算: Markets ending within 24h with clear direction (>80%)."""
        opps = []
        now = datetime.now(timezone.utc)
        for m in markets:
            try:
                end = datetime.fromisoformat(m.end_date.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            hours_left = (end - now).total_seconds() / 3600
            if 0 < hours_left <= 24:
                for side, price in [("YES", m.yes_price), ("NO", m.no_price)]:
                    if 0.80 <= price < 0.95:
                        edge = 1.0 - price
                        if edge >= self.min_edge:
                            opps.append(Opportunity(
                                strategy="expiring", market_id=m.id,
                                question=m.question, side=side, price=price,
                                edge=edge, confidence="medium",
                                end_date=m.end_date,
                                reasoning=f"{hours_left:.0f}h left, {side} at {price:.0%}"
                            ))
        return opps


def format_report(opps: list[Opportunity]) -> str:
    """Format opportunities as readable report."""
    if not opps:
        return "🔍 No opportunities found matching criteria."

    lines = [f"🎯 Found {len(opps)} opportunities:\n"]
    for i, o in enumerate(opps, 1):
        emoji = {"endgame": "🏁", "mispricing": "💰", "expiring": "⏰"}.get(o.strategy, "📊")
        conf_emoji = "🟢" if o.confidence == "high" else "🟡"
        lines.append(f"{i}. {emoji} [{o.strategy}] {conf_emoji}")
        lines.append(f"   Q: {o.question[:70]}")
        lines.append(f"   Side: {o.side} @ ${o.price:.2f} | Edge: {o.edge:.1%} | ID: {o.market_id}")
        lines.append(f"   {o.reasoning}")
        lines.append("")
    return "\n".join(lines)


async def auto_execute(opps: list[Opportunity], max_bet: float, max_total: float) -> list[dict]:
    """Auto-execute high-confidence opportunities within limits."""
    from lib.wallet_manager import WalletManager
    from lib.clob_client import ClobClientWrapper

    wm = WalletManager()
    bal = wm.get_balances()
    available = min(bal.usdc_e, max_total)
    spent = 0.0
    results = []

    # Only auto-execute high confidence
    eligible = [o for o in opps if o.confidence == "high" and o.side != "BOTH"]

    for o in eligible:
        if spent >= available:
            break
        bet = min(max_bet, available - spent)
        if bet < 1.0:
            break

        print(f"⚡ Auto-executing: {o.side} ${bet:.0f} on #{o.market_id} ({o.reasoning})")
        try:
            from scripts.trade import TradeExecutor
            executor = TradeExecutor()
            result = await executor.execute(o.market_id, o.side, bet)
            results.append({"opp": asdict(o), "bet": bet, "result": asdict(result)})
            if result.success:
                spent += bet
                print(f"  ✅ Filled! Spent ${spent:.2f} total")
            else:
                print(f"  ❌ Failed: {result.error}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append({"opp": asdict(o), "bet": bet, "error": str(e)})

    return results


async def cmd_scan(args):
    """Main scan command."""
    scanner = DailyScanner(min_edge=args.min_edge, min_volume=args.min_volume)
    print(f"🔍 Scanning markets (min edge: {args.min_edge:.0%}, min volume: ${args.min_volume:,.0f})...")
    if args.query:
        print(f"   Filter: '{args.query}'")

    opps = await scanner.scan_all(query=args.query, limit=args.limit)
    print(format_report(opps))

    # JSON output
    if args.json:
        print(json.dumps([asdict(o) for o in opps], indent=2, ensure_ascii=False))

    # Auto-execute
    if args.auto and opps:
        print(f"\n⚡ Auto-execute mode (max ${args.max_bet}/trade, ${args.max_total} total)")
        results = await auto_execute(opps, args.max_bet, args.max_total)
        if results:
            print(f"\n📊 Executed {len(results)} trades")
            print(json.dumps(results, indent=2, ensure_ascii=False))

    return opps


def main():
    p = argparse.ArgumentParser(description="Daily Polymarket scanner")
    p.add_argument("command", choices=["scan"], help="Command to run")
    p.add_argument("--query", "-q", help="Filter by keyword")
    p.add_argument("--auto", action="store_true", help="Auto-execute trades")
    p.add_argument("--max-bet", type=float, default=3.0, help="Max $ per trade")
    p.add_argument("--max-total", type=float, default=10.0, help="Max $ total spend")
    p.add_argument("--min-edge", type=float, default=0.05, help="Min edge threshold")
    p.add_argument("--min-volume", type=float, default=5000, help="Min market volume")
    p.add_argument("--limit", type=int, default=50, help="Markets to scan")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args()

    if args.command == "scan":
        asyncio.run(cmd_scan(args))


if __name__ == "__main__":
    main()
