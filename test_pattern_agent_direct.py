"""
Direct test of Pattern Recognition Agent
"""
import asyncio
import pandas as pd

async def test():
    print("\n" + "="*60)
    print("TESTING PATTERN RECOGNITION AGENT DIRECTLY")
    print("="*60)
    
    from app.agents.pattern_recognition_agent import pattern_recognition_agent
    
    print(f"\n1. Agent initialized: {pattern_recognition_agent is not None}")
    print(f"2. Agent name: {pattern_recognition_agent.name}")
    print(f"3. Agent weight: {pattern_recognition_agent.weight}")
    
    symbols_to_test = [
        "TCS",
        "INFY",
        "RELIANCE",
        "HDFCBANK",
        "SBIN",
    ]

    interesting_names = {
        "Rising Wedge",
        "Falling Wedge",
        "Triple Top",
        "Triple Bottom",
        "Rounding Top",
        "Rounding Bottom",
        "Rising Channel",
        "Falling Channel",
        "Gap Up",
        "Gap Down",
        "Bullish Island Reversal",
        "Bearish Island Reversal",
    }

    for sym in symbols_to_test:
        print("\n" + "="*60)
        print(f"RUNNING ANALYSIS ON {sym}")
        print("="*60)

        try:
            # Call analyze with debug_mode to see full pattern breakdown
            result = await pattern_recognition_agent.analyze(
                symbol=sym,
                context={"debug_mode": True}
            )

            print(f"\n✅ Analysis completed successfully for {sym}!")
            print(f"\nResult type: {type(result)}")
            print(f"Agent type: {result.agent_type}")
            print(f"Score: {result.score}")
            print(f"Confidence: {result.confidence}")
            print(f"Reasoning: {result.reasoning}")
            print(f"Signals count: {len(result.signals)}")

            if result.metadata:
                print(f"\nMetadata:")
                for key, value in result.metadata.items():
                    if key != 'patterns_detail':
                        print(f"  {key}: {value}")
                patterns_detail = result.metadata.get('patterns_detail', [])
                if patterns_detail:
                    print("\nTop patterns (patterns_detail):")
                    for p in patterns_detail:
                        name = p.get('name')
                        ptype = p.get('type', 'NEUTRAL')
                        conf = p.get('confidence', 0)
                        status = p.get('status')
                        print(f"  - {name} ({ptype}, {conf}%)" + (f" [{status}]" if status else ""))

                    interesting_hits = [p for p in patterns_detail if p.get('name') in interesting_names]
                    if interesting_hits:
                        print("\n*** Interesting structural patterns detected: ***")
                        for p in interesting_hits:
                            name = p.get('name')
                            ptype = p.get('type', 'NEUTRAL')
                            conf = p.get('confidence', 0)
                            status = p.get('status')
                            print(f"  -> {name} ({ptype}, {conf}%)" + (f" [{status}]" if status else ""))

                patterns_by_name = result.metadata.get('patterns_by_name') if result.metadata else None
                if patterns_by_name:
                    print("\nFull pattern counts (patterns_by_name):")
                    for name, count in sorted(patterns_by_name.items(), key=lambda kv: (-kv[1], kv[0])):
                        print(f"  {name}: {count}")

        except Exception as e:
            print(f"\n❌ ERROR while analyzing {sym}: {e}")
            import traceback
            traceback.print_exc()
    
    # Synthetic rising wedge sanity test
    print("\n" + "="*60)
    print("RUNNING SYNTHETIC RISING WEDGE TEST")
    print("="*60)

    try:
        periods = 60
        idx = pd.date_range(end=pd.Timestamp.today(), periods=periods, freq="D")
        lows = []
        highs = []
        opens = []
        closes = []

        # Construct a synthetic rising wedge: support and resistance both trend up,
        # the band contracts over time, and we add a small oscillation to create
        # multiple peaks/troughs for the peak/trough detector.
        osc_pattern = [0.0, 0.3, 0.6, 0.3, 0.0, -0.3, -0.6, -0.3]

        for i in range(periods):
            center = 100 + 0.2 * i
            # Contracting band
            amplitude = 10 - 0.1 * i
            if amplitude < 2:
                amplitude = 2

            osc = osc_pattern[i % len(osc_pattern)]

            high = center + amplitude / 2 + osc
            low = center - amplitude / 2 + osc
            open_ = low + (high - low) * 0.4
            close = low + (high - low) * 0.6

            lows.append(low)
            highs.append(high)
            opens.append(open_)
            closes.append(close)

        df = pd.DataFrame({
            "time": idx,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [100000] * periods,
        })

        wedge_patterns = pattern_recognition_agent._detect_wedges(df)
        print(f"\nSynthetic wedge patterns detected: {len(wedge_patterns)}")
        for p in wedge_patterns:
            name = p.get("name")
            ptype = p.get("type")
            conf = p.get("confidence", 0)
            status = p.get("status")
            print(f"  - {name} ({ptype}, {conf}%) status={status}")
    except Exception as e:
        print(f"\n❌ ERROR in synthetic wedge test: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(test())
