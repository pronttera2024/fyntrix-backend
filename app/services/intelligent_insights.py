"""
Intelligent Insights Generator
Uses OpenAI to generate stock-specific, analyst-quality insights
"""

from typing import Dict, Any, Optional
from ..llm.openai_manager import llm_manager
from ..utils.trading_modes import normalize_mode


async def generate_stock_insights(
    symbol: str,
    scores: Dict[str, float],
    blend_score: float,
    recommendation: str,
    market_data: Optional[Dict[str, Any]] = None,
    trading_mode: Optional[str] = None,
    key_signals: Optional[Any] = None,
) -> Dict[str, str]:
    """
    Generate intelligent, stock-specific insights using OpenAI.
    
    Args:
        symbol: Stock symbol (e.g., "RELIANCE")
        scores: Individual agent scores dict
        blend_score: Overall blend score
        recommendation: Buy/Hold/Sell
        market_data: Optional market data (price, volume, etc.)
        trading_mode: Trading mode (Scalping, Intraday, Delivery, Options, Futures)
        key_signals: Key signals (especially chart patterns)
        
    Returns:
        Dict with 'key_findings' (2-3 lines) and 'strategy_rationale' (analyst commentary)
    """
    
    # Prepare agent insights summary
    agent_insights = []
    if scores.get('technical', 0) >= 70:
        agent_insights.append(f"Technical Analysis scored {scores.get('technical', 0)}% indicating strong technical setup")
    elif scores.get('technical', 0) >= 60:
        agent_insights.append(f"Technical Analysis scored {scores.get('technical', 0)}% showing positive momentum")
    
    if scores.get('sentiment', 0) >= 70:
        agent_insights.append(f"Sentiment Analysis scored {scores.get('sentiment', 0)}% reflecting bullish market sentiment")
    
    if scores.get('options', 0) >= 70:
        agent_insights.append(f"Options Flow scored {scores.get('options', 0)}% suggesting institutional accumulation")
    
    if scores.get('pattern', 0) >= 70 or scores.get('pattern_recognition', 0) >= 70:
        pattern_score = scores.get('pattern', scores.get('pattern_recognition', 0))
        agent_insights.append(f"Pattern Recognition scored {pattern_score}% identifying favorable patterns")
    
    if scores.get('global', 0) >= 65:
        agent_insights.append(f"Global Markets scored {scores.get('global', 0)}% showing supportive conditions")
    
    if scores.get('risk', 100) <= 40:  # Default 100 if not present (no risk concerns)
        agent_insights.append(f"Risk Assessment scored {scores.get('risk', 0)}% indicating attractive risk-reward")
    
    # Incorporate concrete signals from key_signals (especially chart patterns)
    if key_signals:
        try:
            pattern_highlights = []
            for sig in key_signals:
                # Accept both dicts from AgentCoordinator and pre-formatted strings
                if isinstance(sig, dict):
                    agent_name = str(sig.get('agent', '')).lower()
                    # Focus on PatternRecognitionAgent signals
                    if agent_name and agent_name not in ('pattern_recognition', 'pattern_recognition_agent'):
                        continue
                    name = sig.get('type') or sig.get('signal')
                    if not name:
                        continue
                    direction = sig.get('direction')
                    confidence = sig.get('confidence')
                    description = sig.get('description') or sig.get('signal')
                    piece = str(name)
                    if direction:
                        piece += f" ({str(direction).title()})"
                    if isinstance(confidence, (int, float)) and confidence > 0:
                        piece += f" {confidence:.0f}%"
                    if description and description != name:
                        piece += f" – {description}"
                    pattern_highlights.append(piece)
                elif isinstance(sig, str):
                    pattern_highlights.append(sig)
            if pattern_highlights:
                # Limit to top 3 to keep insights compact
                agent_insights.append("Key chart patterns: " + "; ".join(pattern_highlights[:3]))
        except Exception:
            # Never block insights generation because of malformed signals
            pass
    
    # Mode-specific context
    mode_context = ""
    if trading_mode:
        mode_requirements = {
            "Scalping": "ultra-short-term (seconds to minutes). Emphasize tight spread, high liquidity, volume spikes, and quick profit potential (0.2-0.3%). Mention why this stock is suitable for rapid entries and exits.",
            "Intraday": "same-day trading. Focus on intraday momentum, support/resistance levels for the day, and why this stock offers good intraday moves (1-2%).",
            "Swing": "swing/positional trading (1-2 weeks). Highlight trend strength, fundamental support, and why this stock has sustained move potential (5-8%).",
            "Options": "options strategies. Focus on IV levels, OI buildup, Greeks, and why this stock is suitable for options trades (15-25% on premium).",
            "Futures": "futures trading (1-7 days). Emphasize momentum, rollover premium, leverage potential, and why this stock suits futures positions (2.5-4% on margin)."
        }
        mode_key = normalize_mode(trading_mode)
        mode_req = mode_requirements.get(mode_key, "general trading")
        mode_context = f"\n\nTRADING MODE: {mode_key}\nThis pick is for {mode_req}\nIMPORTANT: Explain WHY {symbol} is specifically suitable for {mode_key} trading based on the analysis."
    
    # Build prompt for OpenAI
    prompt = f"""You are a professional equity analyst writing UNIQUE insights for {symbol}.

Overall Score: {blend_score}%
Recommendation: {recommendation}{mode_context}

Agent Analysis Summary:
{chr(10).join(f"- {insight}" for insight in agent_insights[:5])}

IMPORTANT: Make the insights UNIQUE and SPECIFIC to {symbol}. Do NOT use generic phrases like "Strong technical setup with bullish sentiment". Instead, highlight what makes THIS stock different from others.

Generate TWO types of insights:

1. KEY_FINDINGS (2-3 concise lines for quick table display):
   - Focus on SPECIFIC factors unique to {symbol}
   - Mention the ACTUAL highest-scoring agents (e.g., "Pattern recognition at 100%, Market regime favorable")
   - Reference specific setups (e.g., "Bullish engulfing on breakout", "RSI oversold bounce", "MACD golden cross")
   - {f'**CRITICAL**: Explain WHY this is good for {trading_mode} trading' if trading_mode else 'Be CONCRETE and DIFFERENT for each stock'}
   - Avoid generic phrases
   - Bad example: "Strong technical setup, bullish sentiment, favorable patterns" (TOO GENERIC)
   - Good example: "Pattern recognition 100%: bullish engulfing breakout; Market regime 75%: strong uptrend confirmed{f'; Ideal for {trading_mode} with high liquidity' if trading_mode == 'Scalping' else ''}"

2. STRATEGY_RATIONALE (3-4 sentences for detailed strategy modal):
   - Write like a professional analyst explaining the SPECIFIC trade setup for {symbol}
   - Mention actual pattern names (e.g., "Bullish Harami", "Three White Soldiers", "Cup and Handle")
   - Reference specific indicators that are strong for THIS stock
   - Explain WHY this stock is recommended based on the agent scores
   - {f'**MUST**: Explain why this setup is specifically good for {trading_mode} trading' if trading_mode else 'End with forward-looking statement'}
   - Example: "Today, shares of {symbol} formed a Bullish Engulfing pattern with high volume, breaking above the 20-day moving average. Pattern Recognition scored 100%, indicating a strong bullish reversal setup. Market Regime analysis confirms a favorable uptrend environment at 75%. Based on these factors, {symbol} shows potential for continued upward movement in the near term."

Format your response as:
KEY_FINDINGS: [your SPECIFIC findings for {symbol} here]
STRATEGY_RATIONALE: [your UNIQUE rationale for {symbol} here]"""

    try:
        print(f"  🤖 Generating AI insights for {symbol}...")
        # Call OpenAI with specified configuration
        response = await llm_manager.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional equity analyst. Write clear, actionable insights based on multi-agent analysis."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model="gpt-4o",  # Use GPT-4o (latest model)
            max_tokens=400,  # Allow more detailed responses
            temperature=0.7,  # Higher temperature for more unique responses
            use_cache=False  # Don't cache to ensure unique responses per stock
        )
        
        content = response.get('content', '')
        print(f"  ✓ AI response received for {symbol}")
        
        # Parse response
        key_findings = ""
        strategy_rationale = ""
        
        # DEBUG: Print raw OpenAI response
        print(f"  🔍 OpenAI raw response for {symbol}:")
        print(f"     {content[:200]}...")  # First 200 chars
        
        if "KEY_FINDINGS:" in content:
            parts = content.split("KEY_FINDINGS:")
            if len(parts) > 1:
                findings_part = parts[1].split("STRATEGY_RATIONALE:")
                key_findings = findings_part[0].strip()
                
                if len(findings_part) > 1:
                    strategy_rationale = findings_part[1].strip()
        else:
            print(f"  ⚠️  'KEY_FINDINGS:' not found in response for {symbol}")
        
        # Fallback if parsing fails
        if not key_findings:
            print(f"  ⚠️  Falling back to generic key findings for {symbol}")
            # Generate simple fallback from agent scores
            top_agents = sorted(
                [(k, v) for k, v in scores.items() if k not in ['trade_strategy', 'auto_monitoring', 'personalization']],
                key=lambda x: x[1],
                reverse=True
            )[:2]
            key_findings = ", ".join([f"{agent.replace('_', ' ')} strength" for agent, score in top_agents])
        
        if not strategy_rationale:
            strategy_rationale = f"Our multi-agent analysis of {symbol} shows a blend score of {blend_score}%, suggesting a {recommendation.lower()} opportunity with favorable risk-reward characteristics."
        
        return {
            "key_findings": key_findings,
            "strategy_rationale": strategy_rationale
        }
        
    except Exception as e:
        print(f"⚠️  ERROR generating insights for {symbol}: {e}")
        import traceback
        traceback.print_exc()  # Print full stack trace
        
        # Check if it's a quota error
        is_quota_error = 'insufficient_quota' in str(e).lower() or 'quota' in str(e).lower()
        if is_quota_error:
            print(f"⚠️  OpenAI quota exceeded. Please add credits at https://platform.openai.com/account/billing")
        
        # Enhanced fallback with more intelligent descriptions
        top_agents = sorted(
            [(k, v) for k, v in scores.items() if k not in ['trade_strategy', 'auto_monitoring', 'personalization']],
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        # Create more descriptive fallback based on agent scores
        agent_descriptions = {
            'technical': 'strong technical indicators',
            'pattern_recognition': 'bullish chart patterns detected',
            'market_regime': 'favorable market conditions',
            'sentiment': 'positive market sentiment',
            'options': 'bullish options activity',
            'microstructure': 'healthy market structure',
            'news': 'positive news catalyst'
        }
        
        findings = []
        for agent, score in top_agents:
            desc = agent_descriptions.get(agent, agent.replace('_', ' '))
            findings.append(f"{desc} ({score:.0f}%)")
        
        key_findings = "; ".join(findings) if findings else "Multi-agent analysis shows favorable setup"
        strategy_rationale = f"{symbol} presents a {recommendation.lower()} opportunity with {blend_score}% confidence. {top_agents[0][0].replace('_', ' ').title()} signal at {top_agents[0][1]:.0f}% supports this view."
        
        return {
            "key_findings": key_findings,
            "strategy_rationale": strategy_rationale
        }


async def generate_batch_insights(picks: list, trading_mode: Optional[str] = None) -> list:
    """
    Generate insights for multiple picks efficiently.
    
    Args:
        picks: List of pick dictionaries with symbol, scores, etc.
        trading_mode: Trading mode for mode-specific insights
        
    Returns:
        List of picks with added 'key_findings' and 'strategy_rationale' fields
    """
    import asyncio
    
    # Generate insights for all picks concurrently (with rate limiting)
    tasks = []
    for pick in picks:
        task = generate_stock_insights(
            symbol=pick.get('symbol', ''),
            scores=pick.get('scores', {}),
            blend_score=pick.get('score_blend', 50),
            recommendation=pick.get('recommendation', 'Hold'),
            market_data=pick.get('market_data'),
            trading_mode=trading_mode,
            key_signals=pick.get('key_signals'),
        )
        tasks.append(task)
    
    # Execute with concurrency limit to avoid rate limits
    insights_list = []
    batch_size = 3  # Process 3 at a time for faster generation
    
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        batch_results = await asyncio.gather(*batch, return_exceptions=True)
        insights_list.extend(batch_results)
        
        # Add small delay between batches to respect rate limits
        if i + batch_size < len(tasks):
            await asyncio.sleep(0.5)  # 500ms delay between batches
    
    # Add insights to picks
    for pick, insights in zip(picks, insights_list):
        if isinstance(insights, dict):
            pick['key_findings'] = insights.get('key_findings', 'Analysis in progress')
            pick['strategy_rationale'] = insights.get('strategy_rationale', 'Detailed analysis available soon')
        else:
            # Error case
            pick['key_findings'] = 'Analysis in progress'
            pick['strategy_rationale'] = 'Detailed analysis available soon'
    
    return picks
