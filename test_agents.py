"""
Test script for Phase 2 agents
Tests Technical, Global Market, and Policy/Macro agents
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.agents.technical_agent import TechnicalAgent
from app.agents.global_market_agent import GlobalMarketAgent
from app.agents.policy_macro_agent import PolicyMacroAgent
from app.agents.options_agent import OptionsAgent
from app.agents.sentiment_agent import SentimentAgent
from app.agents.microstructure_agent import MicrostructureAgent
from app.agents.risk_agent import RiskAgent
from app.agents.coordinator import AgentCoordinator


async def test_individual_agents():
    """Test each agent individually"""
    print("=" * 60)
    print("TESTING INDIVIDUAL AGENTS")
    print("=" * 60)
    
    # Test symbols
    symbols = ["RELIANCE", "TCS", "HDFCBANK"]
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Testing Symbol: {symbol}")
        print(f"{'='*60}")
        
        # Technical Agent
        print("\n📊 Technical Agent:")
        print("-" * 40)
        tech_agent = TechnicalAgent()
        try:
            tech_result = await tech_agent.analyze(symbol)
            print(f"  Score: {tech_result.score}/100")
            print(f"  Confidence: {tech_result.confidence}")
            print(f"  Signals: {len(tech_result.signals)} indicators")
            print(f"  Reasoning: {tech_result.reasoning[:100]}...")
            print(f"  Levels: Entry={tech_result.metadata.get('entry')}, "
                  f"SL={tech_result.metadata.get('stop_loss')}, "
                  f"T1={tech_result.metadata.get('target_1')}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        # Global Market Agent
        print("\n🌍 Global Market Agent:")
        print("-" * 40)
        global_agent = GlobalMarketAgent()
        try:
            global_result = await global_agent.analyze(symbol)
            print(f"  Score: {global_result.score}/100")
            print(f"  Confidence: {global_result.confidence}")
            print(f"  Signals: {len(global_result.signals)} signals")
            print(f"  Reasoning: {global_result.reasoning[:100]}...")
            print(f"  Gap Prediction: {global_result.metadata.get('gap_prediction', {}).get('gap_direction', 'N/A')}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        # Policy/Macro Agent
        print("\n📰 Policy/Macro Agent:")
        print("-" * 40)
        policy_agent = PolicyMacroAgent()
        try:
            policy_result = await policy_agent.analyze(symbol)
            print(f"  Score: {policy_result.score}/100")
            print(f"  Confidence: {policy_result.confidence}")
            print(f"  Signals: {len(policy_result.signals)} events")
            print(f"  Reasoning: {policy_result.reasoning[:100]}...")
            print(f"  RBI Stance: {policy_result.metadata.get('rbi_stance', 'N/A')}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        await asyncio.sleep(1)  # Rate limiting


async def test_coordinated_analysis():
    """Test all agents working together via coordinator"""
    print("\n" + "=" * 60)
    print("TESTING COORDINATED MULTI-AGENT ANALYSIS (ALL 7 AGENTS)")
    print("=" * 60)
    
    # Create coordinator
    coordinator = AgentCoordinator()
    
    # Register all 7 agents
    coordinator.register_agent(TechnicalAgent(weight=0.25))
    coordinator.register_agent(GlobalMarketAgent(weight=0.15))
    coordinator.register_agent(PolicyMacroAgent(weight=0.10))
    coordinator.register_agent(OptionsAgent(weight=0.15))
    coordinator.register_agent(SentimentAgent(weight=0.15))
    coordinator.register_agent(MicrostructureAgent(weight=0.10))
    coordinator.register_agent(RiskAgent(weight=0.10))
    
    # Set weights for all 7 agents
    coordinator.set_weights({
        'technical': 0.25,       # 25%
        'global': 0.15,          # 15%
        'policy': 0.10,          # 10%
        'options': 0.15,         # 15%
        'sentiment': 0.15,       # 15%
        'microstructure': 0.10,  # 10%
        'risk': 0.10             # 10%
    })
    
    # Test coordinated analysis
    symbols = ["RELIANCE", "TCS"]
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Analyzing {symbol} with 3-Agent Coordinator")
        print(f"{'='*60}")
        
        try:
            result = await coordinator.analyze_symbol(symbol)
            
            print(f"\n🎯 BLEND SCORE: {result['blend_score']}/100")
            print(f"💪 CONFIDENCE: {result['confidence']}")
            print(f"📈 RECOMMENDATION: {result['recommendation']}")
            print(f"🤖 AGENTS: {result['agent_count']} agents analyzed")
            
            print(f"\n{'Agent Breakdown':^60}")
            print("-" * 60)
            for agent_result in result['agents']:
                print(f"  {agent_result['agent'].upper():<12} "
                      f"Score: {agent_result['score']:>5.1f}  "
                      f"Confidence: {agent_result['confidence']:<8}  "
                      f"Weight: {agent_result['weight']:.0%}")
            
            print(f"\n{'Key Signals (Top 5)':^60}")
            print("-" * 60)
            for i, signal in enumerate(result['key_signals'][:5], 1):
                print(f"  {i}. [{signal.get('agent', 'N/A').upper()}] "
                      f"{signal.get('type', 'N/A')}: {signal.get('signal', 'N/A')}")
            
        except Exception as e:
            print(f"  ✗ Coordination failed: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(1)


async def test_batch_analysis():
    """Test batch analysis of multiple stocks"""
    print("\n" + "=" * 60)
    print("TESTING BATCH ANALYSIS (5 Nifty 50 Stocks - ALL 7 AGENTS)")
    print("=" * 60)
    
    coordinator = AgentCoordinator()
    coordinator.register_agent(TechnicalAgent(weight=0.25))
    coordinator.register_agent(GlobalMarketAgent(weight=0.15))
    coordinator.register_agent(PolicyMacroAgent(weight=0.10))
    coordinator.register_agent(OptionsAgent(weight=0.15))
    coordinator.register_agent(SentimentAgent(weight=0.15))
    coordinator.register_agent(MicrostructureAgent(weight=0.10))
    coordinator.register_agent(RiskAgent(weight=0.10))
    
    coordinator.set_weights({
        'technical': 0.25,
        'global': 0.15,
        'policy': 0.10,
        'options': 0.15,
        'sentiment': 0.15,
        'microstructure': 0.10,
        'risk': 0.10
    })
    
    # Nifty 50 sample
    symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
    
    print(f"\nAnalyzing {len(symbols)} stocks in parallel...")
    print("-" * 60)
    
    try:
        results = await coordinator.batch_analyze(
            symbols, 
            max_concurrent=3  # Process 3 at a time
        )
        
        # Sort by blend score
        results_sorted = sorted(results, key=lambda x: x['blend_score'], reverse=True)
        
        print(f"\n{'Rank':<6}{'Symbol':<12}{'Blend Score':<15}{'Recommendation':<20}{'Confidence'}")
        print("=" * 70)
        
        for i, result in enumerate(results_sorted, 1):
            print(f"{i:<6}{result['symbol']:<12}{result['blend_score']:<15.1f}"
                  f"{result['recommendation']:<20}{result['confidence']}")
        
        print(f"\n✅ Batch analysis complete: {len(results)}/{len(symbols)} successful")
        
    except Exception as e:
        print(f"✗ Batch analysis failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all tests"""
    print("\n" + "🚀 " * 30)
    print("ARISE PHASE 2 - AGENT TESTING SUITE")
    print("Testing: ALL 7 AGENTS - Full Multi-Agent System")
    print("Technical | Global | Policy | Options | Sentiment | Microstructure | Risk")
    print("🚀 " * 30 + "\n")
    
    # Run tests
    await test_individual_agents()
    await test_coordinated_analysis()
    await test_batch_analysis()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 60)
    print("\nNext Steps:")
    print("1. Review agent outputs above")
    print("2. Check blend scores from all 7 agents")
    print("3. Verify signals make sense")
    print("4. Configure data sources (NSE/Alpha Vantage/Finnhub)")
    print("5. Ready for Production: API integration & UI")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
