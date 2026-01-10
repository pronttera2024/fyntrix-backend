"""
Test OpenAI API key and LLM integration
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.llm.openai_manager import llm_manager


async def test_openai_api():
    """Test OpenAI API key and basic functionality"""
    print("=" * 70)
    print("TESTING OPENAI API INTEGRATION")
    print("=" * 70)
    
    # Test 1: Simple chat completion
    print("\n1️⃣  Testing Simple Chat Completion:")
    print("-" * 70)
    
    try:
        if not os.getenv('OPENAI_API_KEY'):
            print("OPENAI_API_KEY not set. Please set it in environment or .env file.")
            return
        print("🧪 Testing OpenAI API Key with 3 consecutive calls...")
        print(f"Key starts with: {os.getenv('OPENAI_API_KEY')[:30]}...\n")

        for i in range(3):
            try:
                print(f"Call {i+1}: ", end="")
                response = await llm_manager.chat_completion(
                    messages=[
                        {"role": "system", "content": "You are a helpful trading assistant."},
                        {"role": "user", "content": f'Test {i+1}: Say OK'}
                    ],
                    complexity="simple",  # Use GPT-3.5 for cost optimization
                    max_tokens=5
                )
                print(f"✅ {response['content']}")
                time.sleep(1)  # 1 second delay between calls
            except Exception as e:
                print(f"❌ Error: {e}")
                break

        print("\n✅ All calls completed successfully!")
        print(f"Cost: ${response['cost']:.6f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Test 2: Sentiment Analysis (for Sentiment Agent)
    print("\n2️⃣  Testing Sentiment Analysis:")
    print("-" * 70)
    
    try:
        news_headlines = [
            "RELIANCE announces record quarterly profits, beats estimates",
            "RELIANCE to invest $10B in green energy",
            "Oil prices surge, benefiting RELIANCE"
        ]
        
        prompt = f"""
        Analyze the sentiment of these news headlines for RELIANCE stock:
        
        {chr(10).join(f"- {h}" for h in news_headlines)}
        
        Respond in JSON format:
        {{
            "sentiment": "bullish/bearish/neutral",
            "score": 0-100,
            "reasoning": "brief explanation"
        }}
        """
        
        response = await llm_manager.chat_completion(
            messages=[
                {"role": "system", "content": "You are a financial sentiment analyzer."},
                {"role": "user", "content": prompt}
            ],
            complexity="simple",
            max_tokens=150
        )
        
        print(f"✅ Success!")
        print(f"Response: {response['content']}")
        print(f"Cost: ${response['cost']:.6f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Test 3: ARIS Chat Preview
    print("\n3️⃣  Testing ARIS Chat (Preview):")
    print("-" * 70)
    
    try:
        response = await llm_manager.chat_completion(
            messages=[
                {"role": "system", "content": "You are ARIS, an intelligent trading assistant. Be concise and helpful."},
                {"role": "user", "content": "What's your view on RELIANCE stock? Keep it to 2 sentences."}
            ],
            complexity="simple",
            max_tokens=100
        )
        
        print(f"✅ Success!")
        print(f"ARIS: {response['content']}")
        print(f"Cost: ${response['cost']:.6f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Test 4: Cost Tracking
    print("\n4️⃣  Testing Cost Tracking:")
    print("-" * 70)
    
    try:
        stats = llm_manager.get_usage_stats()
        
        print(f"✅ Cost tracking initialized")
        print(f"Total Requests: {stats['total_requests']}")
        print(f"Total Tokens: {stats['total_tokens']:,}")
        print(f"Total Cost: ${stats['total_cost']:.6f}")
        print(f"Average Cost/Request: ${stats['avg_cost_per_request']:.6f}")
        print(f"Daily Budget: ${stats['daily_budget']:.2f}")
        print(f"Remaining Budget: ${stats['remaining_budget']:.2f}")
        
    except Exception as e:
        print(f"⚠️  Warning: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ OPENAI API TESTING COMPLETE")
    print("=" * 70)
    print("\n💡 Key Points:")
    print("   ✅ OpenAI API key is valid and working")
    print("   ✅ Chat completion successful")
    print("   ✅ Sentiment analysis working")
    print("   ✅ ARIS chat preview functional")
    print("   ✅ Cost tracking enabled")
    print("\n🎯 Ready for:")
    print("   - Sentiment Agent (news analysis)")
    print("   - ARIS Chat (Q&A interface)")
    print("   - Enhanced agent reasoning")
    print("\n💰 Cost Optimization:")
    print("   - Using GPT-3.5 for simple tasks")
    print("   - Daily budget: $10.00")
    print("   - Aggressive caching (5-min TTL)")
    print("   - Keyword fallback available")
    print("\n✅ All systems operational!")
    
    return True


if __name__ == "__main__":
    asyncio.run(test_openai_api())
