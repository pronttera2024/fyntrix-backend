"""
Fyntrix Chat Service
Intelligent, context-aware conversational AI for trading
"Trading Simplified" - AI answers your questions naturally
"""

import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from ..llm.openai_manager import llm_manager
from ..agents.coordinator import AgentCoordinator
from ..agents.technical_agent import TechnicalAgent
from ..agents.global_market_agent import GlobalMarketAgent
from ..agents.policy_macro_agent import PolicyMacroAgent
from ..agents.options_agent import OptionsAgent
from ..agents.sentiment_agent import SentimentAgent
from ..agents.microstructure_agent import MicrostructureAgent
from ..agents.risk_agent import RiskAgent
from ..agents.pattern_recognition_agent import PatternRecognitionAgent
from ..agents.market_regime_agent import MarketRegimeAgent
from ..agents.trade_strategy_agent import TradeStrategyAgent
from ..agents.watchlist_intelligence_agent import WatchlistIntelligenceAgent
from ..agents.auto_monitoring_agent import AutoMonitoringAgent
from ..agents.personalization_agent import PersonalizationAgent
from ..agents.scalping_agent import ScalpingAgent
from ..services.top_picks_engine import get_latest_picks
from ..providers.finnhub_provider import get_finnhub_provider
from ..providers.alphavantage_provider import get_alphavantage_provider
from ..providers.zerodha_provider import get_zerodha_provider
from ..services.news_aggregator import get_symbol_news
from ..services.external_fundamentals import fetch_external_fundamentals
from ..services.redis_client import get_json
from ..services.memory import MEMORY
from pathlib import Path
import json as _json


class ARISChat:
    """
    Fyntrix - Intelligent Trading Assistant
    
    Capabilities:
    - Stock analysis on demand
    - Comparison between stocks
    - Top picks retrieval
    - Educational responses
    - Context-aware conversations
    """
    
    def __init__(self):
        """Initialize Fyntrix Chat"""
        
        print("[CHAT] ARISChat initializing (Fyntrix multi-agent chat service)...")

        # Initialize multi-agent coordinator (10+ agents), aligned with agents router
        self.coordinator = AgentCoordinator()

        # 11 scoring agents
        self.coordinator.register_agent(TechnicalAgent(weight=0.20))
        self.coordinator.register_agent(PatternRecognitionAgent(weight=0.18))
        self.coordinator.register_agent(MarketRegimeAgent(weight=0.15))
        self.coordinator.register_agent(GlobalMarketAgent(weight=0.12))
        self.coordinator.register_agent(OptionsAgent(weight=0.12))
        self.coordinator.register_agent(SentimentAgent(weight=0.10))
        self.coordinator.register_agent(PolicyMacroAgent(weight=0.08))
        self.coordinator.register_agent(ScalpingAgent(weight=0.03))
        self.coordinator.register_agent(WatchlistIntelligenceAgent(weight=0.01))
        self.coordinator.register_agent(MicrostructureAgent(weight=0.01))
        self.coordinator.register_agent(RiskAgent(weight=0.00))

        # Super / utility agents (0 weight - do not affect blend score)
        self.coordinator.register_agent(TradeStrategyAgent(weight=0.00))
        self.coordinator.register_agent(AutoMonitoringAgent(weight=0.00))
        self.coordinator.register_agent(PersonalizationAgent(weight=0.00))
        
        self.coordinator.set_weights({
            'technical': 0.2037,
            'pattern_recognition': 0.1833,
            'market_regime': 0.1528,
            'global': 0.12,
            'options': 0.12,
            'sentiment': 0.10,
            'policy': 0.08,
            'scalping': 0.03,
            'watchlist_intelligence': 0.00,
            'microstructure': 0.0102,
            'risk': 0.00,
            'trade_strategy': 0.00,
            'auto_monitoring': 0.00,
            'personalization': 0.00,
        })
        
        # Conversation memory (in-memory for now)
        self.conversations: Dict[str, List[Dict[str, str]]] = {}

        # Lazy-initialised providers for richer symbol deep-dives
        self._zerodha = None

        # Lightweight FAQ knowledge base
        self._faq: List[Dict[str, Any]] = []
        try:
            faq_path = Path(__file__).parent.parent / "knowledge" / "faq.json"
            if faq_path.exists():
                with faq_path.open("r", encoding="utf-8") as f:
                    data = _json.load(f)
                    if isinstance(data, list):
                        self._faq = data
                        print(f"[CHAT] Loaded {len(self._faq)} FAQ entries for educational/general queries")
        except Exception as e:
            print(f"[CHAT] FAQ load failed: {e}")
    
    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process user message and generate intelligent response.
        
        Args:
            message: User's message
            conversation_id: Optional conversation ID for context
            user_context: Optional user context (portfolio, preferences)
            
        Returns:
            Response dictionary with text, data, and suggestions
        """
        print(f"[CHAT] ARISChat.chat called conv_id={conversation_id} message='{message[:80]}'")

        # Get conversation history
        conversation_id = conversation_id or f"conv_{datetime.now().timestamp()}"
        history = self.conversations.get(conversation_id, [])

        # Normalized user profile (merged in router from MEMORY + frontend prefs)
        base_user_profile: Dict[str, Any] = {}
        if isinstance(user_context, dict):
            up = user_context.get("user_profile") or {}
            if isinstance(up, dict):
                base_user_profile = up

        # Add user message to history
        history.append({"role": "user", "content": message})

        # Opportunistically learn basic user preferences (risk, style) from phrasing
        self._maybe_update_user_memory(conversation_id, message)
        
        # Parse intent and extract entities using AI
        intent, entities = await self._parse_intent(message, history)
        
        # Route to appropriate handler
        if intent == "stock_analysis":
            response = await self._handle_stock_analysis(entities, history, user_context=user_context)
        
        elif intent == "comparison":
            response = await self._handle_comparison(entities, history, user_profile=base_user_profile)
        
        elif intent == "top_picks":
            response = await self._handle_top_picks(message, history, user_profile=base_user_profile)
        
        elif intent == "educational":
            response = await self._handle_educational(message, history, user_profile=base_user_profile)
        
        elif intent == "market_outlook":
            response = await self._handle_market_outlook(message, history, user_profile=base_user_profile)
        
        elif intent == "greeting":
            response = self._handle_greeting(message)
        
        else:
            response = await self._handle_general(message, history, user_profile=base_user_profile)
        
        # Add assistant response to history
        history.append({"role": "assistant", "content": response['response']})
        
        # Update conversation memory
        self.conversations[conversation_id] = history[-10:]  # Keep last 10 turns
        
        # Add conversation_id to response
        response['conversation_id'] = conversation_id
        response['timestamp'] = datetime.now().isoformat() + 'Z'
        
        return response

    def _maybe_update_user_memory(self, conversation_id: str, message: str) -> None:
        """Extract very simple preferences from free-text and persist via MEMORY.

        This is intentionally lightweight (regex/keyword based) so that it
        complements, rather than replaces, the richer Preferences panel which
        already writes to /v1/memory/upsert from the frontend.
        """

        try:
            text = (message or "").lower()
            updates: Dict[str, Any] = {}

            # Risk profile hints
            if any(kw in text for kw in ["conservative", "low risk", "capital preservation"]):
                updates["risk"] = "Conservative"
            elif any(kw in text for kw in ["moderate", "balanced", "medium risk"]):
                updates["risk"] = "Moderate"
            elif any(kw in text for kw in ["aggressive", "high risk", "risk taker"]):
                updates["risk"] = "Aggressive"

            # Primary trading style hints
            if any(kw in text for kw in ["scalp", "scalping"]):
                updates["primary_mode"] = "Scalping"
            elif "intraday" in text or "day trade" in text or "day trading" in text:
                updates["primary_mode"] = "Intraday"
            elif "swing" in text:
                updates["primary_mode"] = "Swing"
            elif "options" in text:
                updates["primary_mode"] = "Options"
            elif "futures" in text:
                updates["primary_mode"] = "Futures"

            if not updates:
                return

            MEMORY.upsert(conversation_id, updates)
        except Exception:
            return
    
    def _build_user_profile_hint(self, user_profile: Optional[Dict[str, Any]]) -> str:
        """Return a short, human-readable summary of user profile for prompts."""

        if not isinstance(user_profile, dict) or not user_profile:
            return ""

        parts: List[str] = []

        risk_val = user_profile.get("risk") or user_profile.get("risk_profile")
        if risk_val:
            parts.append(f"risk profile: {risk_val}")

        mode_val = user_profile.get("primary_mode") or user_profile.get("trading_style")
        if mode_val:
            parts.append(f"style: {mode_val}")

        universe_val = user_profile.get("universe")
        if isinstance(universe_val, list) and universe_val:
            parts.append("universe: " + ", ".join(str(u) for u in universe_val[:3]))
        elif isinstance(universe_val, str) and universe_val:
            parts.append(f"universe: {universe_val}")

        exp_val = user_profile.get("experience") or user_profile.get("experience_level")
        if exp_val:
            parts.append(f"experience: {exp_val}")

        if not parts:
            return ""

        return "User profile context: " + ", ".join(parts) + ". Tailor tone, risk framing, and suggestions to this profile."
    
    def _extract_user_profile(self, ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract a normalized user_profile dict from either base context or deep-dive context.

        The router passes a base context with a nested "user_profile" field. The symbol
        deep-dive helper then stores that base context under ctx["user_profile"]. This
        helper unwraps that pattern so downstream code always sees just the merged
        profile fields (risk, primary_mode, universe, etc.).
        """

        if not isinstance(ctx, dict):
            return {}

        profile = ctx.get("user_profile")
        if isinstance(profile, dict):
            nested = profile.get("user_profile")
            if isinstance(nested, dict):
                return nested
            return profile
        return {}

    def _dedupe_suggestions(self, items: List[str], limit: int = 6) -> List[str]:
        """Deduplicate and lightly trim suggestion strings while preserving order."""

        seen: List[str] = []
        for raw in items:
            s = str(raw).strip()
            if not s or s in seen:
                continue
            seen.append(s)
            if len(seen) >= limit:
                break
        return seen

    def _build_stock_suggestions(
        self,
        symbol: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Build context-aware follow-up suggestions after a stock analysis."""

        ctx = context or {}
        symbol_clean = (symbol or "").upper() or "this stock"

        user_profile = self._extract_user_profile(ctx)
        portfolio_pos = ctx.get("portfolio_position") or {}
        watchlist_entry = ctx.get("watchlist_entry") or {}

        risk = ""
        mode = ""
        if isinstance(user_profile, dict):
            risk = str(user_profile.get("risk") or user_profile.get("risk_profile") or "").lower()
            mode = str(user_profile.get("primary_mode") or user_profile.get("trading_style") or "").lower()

        suggestions: List[str] = []

        # Core next actions around this symbol
        suggestions.append(f"Show entry/exit levels for {symbol_clean}")
        suggestions.append(f"What's the risk in {symbol_clean}?")

        # If already in portfolio or watchlist, surface management questions
        if isinstance(portfolio_pos, dict) and portfolio_pos:
            suggestions.append(f"Review my position in {symbol_clean}")
            suggestions.append(f"Help with an exit plan for {symbol_clean}")

        if isinstance(watchlist_entry, dict) and watchlist_entry:
            suggestions.append(f"Help me plan entries for {symbol_clean}")

        # Adjust by risk profile / style
        if risk.startswith("conservative") or "low" in risk:
            suggestions.append("Check if my overall portfolio risk is conservative enough")
            suggestions.append(f"Show top picks suitable for conservative risk instead of {symbol_clean}")
        elif "aggressive" in risk or "high" in risk:
            suggestions.append(f"Show short-term trade ideas around {symbol_clean}")
            if "scalp" in mode:
                suggestions.append(f"Can I scalp {symbol_clean} today?")

        # Navigation to other capabilities
        suggestions.append(f"Compare {symbol_clean} vs NIFTY")
        suggestions.append("Show today's top picks")

        return self._dedupe_suggestions(suggestions)

    def _build_top_picks_suggestions(
        self,
        picks: List[Dict[str, Any]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Build suggestions after showing Top Picks, tailored by profile."""

        if not isinstance(picks, list) or not picks:
            return [
                "Show today's top picks",
                "Analyze RELIANCE",
            ]

        suggestions: List[str] = []

        first = picks[0] or {}
        first_sym = str(first.get("symbol") or "this stock").upper()

        suggestions.append(f"Tell me more about {first_sym}")
        suggestions.append(f"Why is {first_sym} in today's top picks?")

        if len(picks) > 1:
            second = picks[1] or {}
            second_sym = str(second.get("symbol") or "").upper() or first_sym
            suggestions.append(f"Compare {first_sym} vs {second_sym}")

        suggestions.append(f"Show entry/exit plan for {first_sym}")

        risk = ""
        mode = ""
        if isinstance(user_profile, dict):
            risk = str(user_profile.get("risk") or user_profile.get("risk_profile") or "").lower()
            mode = str(user_profile.get("primary_mode") or user_profile.get("trading_style") or "").lower()

        if risk.startswith("conservative") or "low" in risk:
            suggestions.append("Show top picks suitable for conservative risk")
        elif "aggressive" in risk or "high" in risk:
            suggestions.append("Show aggressive or high-momentum top picks")

        if "scalp" in mode or "intraday" in mode:
            suggestions.append("Show intraday or scalping top picks for today")

        suggestions.append("Analyze my portfolio using today's top picks")

        return self._dedupe_suggestions(suggestions)

    def _build_educational_suggestions(
        self,
        message: str,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Build follow-up suggestions after an educational answer."""

        concept = (message or "").lower()
        suggestions: List[str] = []

        if "rsi" in concept:
            suggestions.append("Analyze RELIANCE and explain how RSI applies")
            suggestions.append("Show example RSI levels on NIFTY")
        elif "macd" in concept:
            suggestions.append("Show a MACD-based example trade on TCS")

        risk = ""
        if isinstance(user_profile, dict):
            risk = str(user_profile.get("risk") or user_profile.get("risk_profile") or "").lower()

        if risk.startswith("conservative") or "low" in risk:
            suggestions.append("Show low-risk ways to use this indicator")
        elif "aggressive" in risk or "high" in risk:
            suggestions.append("Show aggressive setups using this indicator")

        suggestions.append("Show top picks where this concept is important today")
        suggestions.append("Analyze NIFTY")
        suggestions.append("What is MACD?")

        return self._dedupe_suggestions(suggestions)

    def _build_market_outlook_suggestions(
        self,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Build suggestions after a market outlook response."""

        suggestions: List[str] = [
            "Analyze NIFTY",
            "Analyze BANKNIFTY",
            "Show today's top picks",
        ]

        risk = ""
        mode = ""
        if isinstance(user_profile, Dict):
            risk = str(user_profile.get("risk") or user_profile.get("risk_profile") or "").lower()
            mode = str(user_profile.get("primary_mode") or user_profile.get("trading_style") or "").lower()

        if risk.startswith("conservative") or "low" in risk:
            suggestions.append("Check if my portfolio is overexposed to risky sectors")
            suggestions.append("Show defensive or low-volatility top picks")
        elif "aggressive" in risk or "high" in risk:
            suggestions.append("Show high beta sectors or momentum ideas")

        if "scalp" in mode or "intraday" in mode:
            suggestions.append("Show intraday opportunities for today")

        suggestions.append("What sectors are hot?")

        return self._dedupe_suggestions(suggestions)

    def _build_general_suggestions(
        self,
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Build suggestions for general queries based on stored preferences."""

        suggestions: List[str] = [
            "Show today's top picks",
            "Analyze RELIANCE",
            "Compare TCS vs INFY",
        ]

        risk = ""
        mode = ""
        if isinstance(user_profile, Dict):
            risk = str(user_profile.get("risk") or user_profile.get("risk_profile") or "").lower()
            mode = str(user_profile.get("primary_mode") or user_profile.get("trading_style") or "").lower()

        if risk.startswith("conservative") or "low" in risk:
            suggestions.append("Review my overall portfolio risk")
        elif "aggressive" in risk or "high" in risk:
            suggestions.append("Suggest a few aggressive ideas for today")

        if "scalp" in mode or "intraday" in mode:
            suggestions.append("Show intraday or scalping ideas for today")

        return self._dedupe_suggestions(suggestions)
    
    async def _parse_intent(
        self,
        message: str,
        history: List[Dict[str, str]]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Parse user intent using OpenAI for intelligent understanding.
        
        Returns:
            (intent, entities) tuple
        """
        
        # Quick pattern matching and fallback-based routing for common cases
        message_lower = message.lower()

        if message_lower.strip() in ['hi', 'hello', 'hey']:
            return ('greeting', {})

        fallback_intent, fallback_entities = self._parse_intent_fallback(message)
        if fallback_intent != 'general' or fallback_entities.get('symbols'):
            return (fallback_intent, fallback_entities)

        # Use OpenAI only when pattern-based parsing is inconclusive
        try:
            intent_prompt = f"""Analyze this trading/market query and classify the intent.

User Query: "{message}"

Available Intents:
1. greeting - Simple greetings (hi, hello, etc.)
2. stock_analysis - User wants analysis of a specific stock (e.g., "outlook for Nifty", "analyze RELIANCE", "view on TCS")
3. comparison - Comparing multiple stocks (e.g., "compare TCS vs INFY", "which is better RELIANCE or HDFC")
4. top_picks - Asking for stock recommendations (e.g., "show top picks", "best stocks", "what should I buy", "top 5 picks")
5. educational - Asking to explain a concept (e.g., "what is RSI", "explain moving average")
6. market_outlook - General market questions (e.g., "how is the market", "market outlook", "what's happening")
7. general - Other trading-related questions

Extract:
- Intent: One of the above
- Symbols: Any stock symbols or index names mentioned (NIFTY, BANKNIFTY, TCS, RELIANCE, etc.)
- Query Type: The specific type of question

Respond ONLY in this JSON format:
{{"intent": "...", "symbols": [...], "query_details": "..."}}"""

            response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=[{"role": "user", "content": intent_prompt}],
                    complexity="simple",
                    max_tokens=150,
                    temperature=0.1,  # Low temperature for consistent classification
                ),
                timeout=12.0,
            )
            
            # Parse OpenAI response
            import json
            content = response['content'].strip()
            
            # Extract JSON from response (handle cases where it's wrapped in markdown)
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            result = json.loads(content)
            
            intent = result.get('intent', 'general')
            symbols = result.get('symbols', [])
            query_details = result.get('query_details', '')

            # Defensive post-processing so that substantive queries are not
            # misclassified as greetings, especially when they mention
            # concrete symbols like RELIANCE, TCS, INFY, etc.
            if intent == 'greeting':
                # Reuse quick lowercased form
                # Treat greeting tokens as whole words/phrases, not substrings
                word_greetings = ['hi', 'hello', 'hey']
                phrase_greetings = ['good morning', 'good evening']

                words = re.findall(r'\b\w+\b', message_lower)
                has_word_greeting = any(w in words for w in word_greetings)
                has_phrase_greeting = any(phrase in message_lower for phrase in phrase_greetings)
                has_clear_greeting_token = has_word_greeting or has_phrase_greeting

                # Try to infer symbols if the classifier did not return any
                if not symbols:
                    inferred_symbols = self._extract_symbols(message)
                    if inferred_symbols:
                        symbols = inferred_symbols

                has_symbol = bool(symbols)

                # If the message contains a symbol or richer wording and is
                # not a clear standalone greeting, treat it as analysis or
                # general rather than a pure greeting.
                if not has_clear_greeting_token and has_symbol:
                    intent = 'stock_analysis'
                elif not has_clear_greeting_token and not has_symbol:
                    intent = 'general'
            
            entities = {
                'symbols': symbols,
                'query_details': query_details
            }
            
            print(f"  🤖 AI Intent: {intent}, Symbols: {symbols}")
            
            return (intent, entities)
            
        except Exception as e:
            print(f"  ⚠️ Intent classification failed: {e}, falling back to patterns")
            # Fallback to pattern matching
            return self._parse_intent_fallback(message)
    
    def _parse_intent_fallback(self, message: str) -> Tuple[str, Dict[str, Any]]:
        """Fallback pattern-based intent parsing"""
        message_lower = message.lower()
        entities = {}
        
        # Extract stock symbols
        symbols = self._extract_symbols(message)
        if symbols:
            entities['symbols'] = symbols
        
        # Intent patterns
        # Treat greeting tokens as whole words/phrases, not substrings (to avoid 'hi' matching 'this')
        greeting_words = ['hello', 'hi', 'hey']
        greeting_phrases = ['good morning', 'good evening']
        words = re.findall(r'\b\w+\b', message_lower)
        if any(w in words for w in greeting_words) or any(phrase in message_lower for phrase in greeting_phrases):
            return ('greeting', entities)
        
        # More flexible patterns for top picks
        if any(phrase in message_lower for phrase in ['top pick', 'top five', 'top 5', 'best stock', 'recommend', 'what should i', 'which stock']):
            return ('top_picks', entities)
        
        # Outlook and market questions
        if any(phrase in message_lower for phrase in ['outlook', 'view on', 'opinion on', 'thoughts on', 'analysis']):
            if symbols:
                return ('stock_analysis', entities)
            else:
                return ('market_outlook', entities)
        
        if ('compare' in message_lower or 'vs' in message or 'versus' in message_lower) and len(symbols) >= 2:
            return ('comparison', entities)
        
        if symbols:
            return ('stock_analysis', entities)
        
        if any(word in message_lower for word in ['what is', 'explain', 'how does', 'what does', 'meaning of']):
            return ('educational', entities)
        
        return ('general', entities)
    
    def _extract_symbols(self, message: str) -> List[str]:
        """Extract stock symbols from message"""
        
        # Common stock names to symbols (expanded)
        symbol_map = {
            # Indices
            'nifty': 'NIFTY',
            'nifty 50': 'NIFTY',
            'nifty50': 'NIFTY',
            'bank nifty': 'BANKNIFTY',
            'banknifty': 'BANKNIFTY',
            'sensex': 'SENSEX',
            
            # Stocks
            'reliance': 'RELIANCE',
            'tcs': 'TCS',
            'tata consultancy': 'TCS',
            'hdfc': 'HDFCBANK',
            'hdfc bank': 'HDFCBANK',
            'infosys': 'INFY',
            'infy': 'INFY',
            'icici': 'ICICIBANK',
            'icici bank': 'ICICIBANK',
            'wipro': 'WIPRO',
            'it': 'ITC',
            'itc': 'ITC',
            'sbi': 'SBIN',
            'state bank': 'SBIN',
            'airtel': 'BHARTIARTL',
            'bharti': 'BHARTIARTL',
            'bharti airtel': 'BHARTIARTL',
            'bajaj': 'BAJFINANCE',
            'asian paints': 'ASIANPAINT',
            'maruti': 'MARUTI',
            'titan': 'TITAN',
            'hul': 'HINDUNILVR',
            'hindustan unilever': 'HINDUNILVR',

            # Additional large-caps
            'nestle': 'NESTLEIND',
            'nestle india': 'NESTLEIND',
            'nestleind': 'NESTLEIND',
        }
        
        symbols = []
        message_lower = message.lower()
        
        # Check for mapped names (sorted by length to match longer phrases first)
        for name in sorted(symbol_map.keys(), key=len, reverse=True):
            if name in message_lower:
                symbol = symbol_map[name]
                if symbol not in symbols:
                    symbols.append(symbol)
        
        # Check for uppercase symbols
        words = message.split()
        for word in words:
            # Remove punctuation
            word_clean = word.strip('.,!?')
            if word_clean.isupper() and len(word_clean) >= 2 and word_clean not in symbols:
                symbols.append(word_clean)
        
        return symbols  # Maintain order, no duplicates

    def _match_faq(self, message: str) -> Optional[Dict[str, Any]]:
        """Return FAQ entry matching the message, if any."""

        if not self._faq:
            return None

        text = (message or "").lower()
        if not text:
            return None

        for entry in self._faq:
            patterns = entry.get("patterns") or []
            for pat in patterns:
                try:
                    p = str(pat or "").lower()
                    if p and p in text:
                        return entry
                except Exception:
                    continue

        return None

    async def _build_symbol_deep_dive_context(
        self,
        symbol: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {
            "symbol": symbol,
            "live": None,
            "top_pick": None,
            "news": [],
            "external": None,
            "user_profile": user_context or {},
            "portfolio_position": None,
            "watchlist_entry": None,
        }

        sym_upper = (symbol or "").upper()

        tasks = []

        async def fetch_live() -> None:
            try:
                if self._zerodha is None:
                    self._zerodha = get_zerodha_provider()
                z = self._zerodha
                if not z or not z.is_authenticated():
                    return

                def _get_quote() -> Dict[str, Any] | None:
                    try:
                        return z.get_quote([sym_upper])
                    except Exception:
                        return None

                data = await asyncio.to_thread(_get_quote)
                if isinstance(data, dict) and sym_upper in data:
                    ctx["live"] = data[sym_upper]
            except Exception:
                return

        tasks.append(fetch_live())

        async def fetch_news() -> None:
            try:
                items = await get_symbol_news(symbol, 5)
                ctx["news"] = items or []
            except Exception:
                ctx["news"] = []

        tasks.append(fetch_news())

        async def fetch_external() -> None:
            try:
                ext = await fetch_external_fundamentals(symbol)
                ctx["external"] = ext
            except Exception:
                ctx["external"] = None

        tasks.append(fetch_external())

        try:
            picks_data = get_latest_picks()
            if picks_data and isinstance(picks_data.get("picks"), list):
                for pick in picks_data["picks"]:
                    s = str(pick.get("symbol") or "").upper()
                    if s == sym_upper:
                        ctx["top_pick"] = pick
                        break
        except Exception:
            ctx["top_pick"] = None

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Attach portfolio / watchlist context from Redis snapshots when available
        try:
            positions_payload = get_json("portfolio:monitor:positions:last")
            if isinstance(positions_payload, dict):
                for pos in positions_payload.get("positions", []):
                    psym = str(pos.get("symbol") or "").upper()
                    if psym == sym_upper:
                        ctx["portfolio_position"] = pos
                        break
        except Exception:
            pass

        try:
            watchlist_payload = get_json("portfolio:monitor:watchlist:last")
            if isinstance(watchlist_payload, dict):
                for entry in watchlist_payload.get("entries", []):
                    wsym = str(entry.get("symbol") or "").upper()
                    if wsym == sym_upper:
                        ctx["watchlist_entry"] = entry
                        break
        except Exception:
            pass

        return ctx
    
    async def _handle_stock_analysis(
        self,
        entities: Dict[str, Any],
        history: List[Dict[str, str]],
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle stock analysis queries"""
        
        symbols = entities.get('symbols', [])
        if not symbols:
            return {
                'response': "I'd be happy to analyze a stock for you! Which stock would you like me to look at?",
                'suggestions': [
                    "Analyze RELIANCE",
                    "What's your view on TCS?",
                    "Show me top picks"
                ]
            }
        
        symbol = symbols[0]
        
        try:
            result = await self.coordinator.analyze_symbol(symbol)
            context = await self._build_symbol_deep_dive_context(symbol, user_context or {})
            response_text = await self._generate_intelligent_analysis(symbol, result, history, context)
            
            return {
                'response': response_text,
                'data': result,
                'context': context,
                'suggestions': self._build_stock_suggestions(symbol, context),
            }
            
        except Exception as e:
            return {
                'response': f"I had trouble analyzing {symbol}. The error was: {str(e)}. Would you like me to try another stock?",
                'suggestions': self._dedupe_suggestions([
                    "Show today's top picks",
                    "Analyze TCS",
                    "Analyze RELIANCE",
                ])
            }
    
    async def _generate_intelligent_analysis(
        self, 
        symbol: str, 
        result: Dict[str, Any],
        history: List[Dict[str, str]],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate intelligent, conversational analysis using OpenAI"""
        
        blend_score = result.get('blend_score', 0)
        recommendation = result.get('recommendation', 'Hold')
        confidence = result.get('confidence', 'Medium')
        agents = result.get('agents', [])
        key_signals = result.get('key_signals', [])[:3]

        extra_context = extra_context or {}
        live = extra_context.get('live') or {}
        top_pick = extra_context.get('top_pick')
        news_items = extra_context.get('news') or []
        external = extra_context.get('external') or {}
        user_profile = extra_context.get('user_profile') or {}
        portfolio_pos = extra_context.get('portfolio_position') or {}
        watchlist_entry = extra_context.get('watchlist_entry') or {}

        live_snapshot = ""
        if isinstance(live, dict) and live:
            parts: List[str] = []
            price = live.get('price') or live.get('last_price')
            change_pct = live.get('change_percent')
            volume = live.get('volume')
            if price is not None:
                try:
                    parts.append(f"Price {float(price):.2f}")
                except Exception:
                    parts.append(f"Price {price}")
            if change_pct is not None:
                try:
                    parts.append(f"{float(change_pct):+.2f}% today")
                except Exception:
                    parts.append(f"{change_pct}% today")
            if volume is not None:
                parts.append(f"Volume {volume}")
            if parts:
                live_snapshot = " | ".join(parts)

        top_pick_text = ""
        if isinstance(top_pick, dict) and top_pick:
            tp_parts: List[str] = []
            score_val = top_pick.get('blend_score') or top_pick.get('score_blend')
            mode_val = top_pick.get('mode') or top_pick.get('primary_mode')
            view_val = top_pick.get('recommendation') or top_pick.get('trade_view')
            conf_val = top_pick.get('confidence')
            if score_val is not None:
                try:
                    tp_parts.append(f"Score {float(score_val):.1f}")
                except Exception:
                    tp_parts.append(f"Score {score_val}")
            if mode_val:
                tp_parts.append(f"Mode {mode_val}")
            if view_val:
                tp_parts.append(f"View {view_val}")
            if conf_val:
                tp_parts.append(f"Confidence {conf_val}")
            if tp_parts:
                top_pick_text = ", ".join(tp_parts)

        news_lines: List[str] = []
        for item in news_items[:3]:
            if not isinstance(item, dict):
                continue
            title = item.get('title') or item.get('headline') or ''
            if not title:
                continue
            src = item.get('source') or item.get('provider') or ''
            sent = item.get('sentiment') or ''
            extras: List[str] = []
            if src:
                extras.append(str(src))
            if sent:
                extras.append(str(sent))
            suffix = f" ({', '.join(extras)})" if extras else ""
            news_lines.append(f"- {title}{suffix}")
        news_block = "\n".join(news_lines)

        external_block = ""
        if isinstance(external, dict):
            bullets = external.get('bullets') or []
            if isinstance(bullets, list) and bullets:
                external_block = "\n".join(f"- {str(b)[:200]}" for b in bullets[:3])

        profile_parts: List[str] = []
        exp = user_profile.get('experience') or user_profile.get('experience_level')
        if exp:
            profile_parts.append(f"experience: {exp}")
        style = user_profile.get('trading_style') or user_profile.get('primary_mode')
        if style:
            profile_parts.append(f"style: {style}")
        risk_pref = user_profile.get('risk') or user_profile.get('risk_profile')
        if risk_pref:
            profile_parts.append(f"risk: {risk_pref}")
        profile_text = ", ".join(profile_parts)

        portfolio_section = ""
        if isinstance(portfolio_pos, dict) and portfolio_pos:
            try:
                qty = portfolio_pos.get('quantity')
                entry_px = portfolio_pos.get('entry_price')
                ret_pct = portfolio_pos.get('return_pct')
                urgency = portfolio_pos.get('urgency')
                parts_pf: List[str] = []
                if qty is not None:
                    parts_pf.append(f"qty {qty}")
                if entry_px is not None:
                    parts_pf.append(f"entry {entry_px}")
                if ret_pct is not None:
                    parts_pf.append(f"pnl {ret_pct:+.2f}%")
                if urgency:
                    parts_pf.append(f"urgency {urgency}")
                if parts_pf:
                    portfolio_section = "\n**Current Portfolio Position (Zerodha)**:\n- " + ", ".join(str(p) for p in parts_pf)
            except Exception:
                portfolio_section = ""

        watchlist_section = ""
        if isinstance(watchlist_entry, dict) and watchlist_entry:
            try:
                desired = watchlist_entry.get('desired_entry')
                dist = watchlist_entry.get('distance_to_entry_pct')
                urgency_w = watchlist_entry.get('urgency')
                parts_w: List[str] = []
                if desired is not None:
                    parts_w.append(f"desired entry {desired}")
                if dist is not None:
                    parts_w.append(f"distance to entry {dist:+.2f}%")
                if urgency_w:
                    parts_w.append(f"urgency {urgency_w}")
                if parts_w:
                    watchlist_section = "\n**Watchlist Context**:\n- " + ", ".join(str(p) for p in parts_w)
            except Exception:
                watchlist_section = ""

        live_section = f"\n**Live Snapshot (Zerodha)**:\n- {live_snapshot}\n" if live_snapshot else ""
        top_pick_section = f"\n**Fyntrix Top Picks Context**:\n- {top_pick_text}\n" if top_pick_text else ""
        news_section = f"\n**Recent News (Fyntrix News Engine)**:\n{news_block}\n" if news_block else ""
        external_section = f"\n**External Fundamentals (3rd-party)**:\n{external_block}\n" if external_block else ""
        profile_section = f"\n**User Profile**: {profile_text}\n" if profile_text else ""
        
        # Extract user's original question from history
        user_question = history[-1]['content'] if history else f"What's your view on {symbol}?"
        
        # Build context for OpenAI
        agent_summary = []
        for agent in agents:
            agent_name = agent.get('agent', 'unknown')
            agent_score = agent.get('score', 0)
            agent_conf = agent.get('confidence', 'Medium')
            agent_summary.append(f"- {agent_name}: {agent_score:.0f}/100 ({agent_conf} confidence)")
        
        signals_text = "\n".join([f"- {s.get('type', 'Signal')}: {s.get('signal', '')}" for s in key_signals])
        
        # Get technical levels if available
        tech_levels = ""
        for agent in agents:
            if agent.get('agent') == 'technical':
                metadata = agent.get('metadata', {})
                entry = metadata.get('entry_price')
                target = metadata.get('target_price')
                sl = metadata.get('stop_loss')
                if entry and target and sl:
                    tech_levels = f"\nTechnical Levels:\n- Entry: ₹{entry:.0f}\n- Target: ₹{target:.0f} (+{((target-entry)/entry*100):.1f}%)\n- Stop Loss: ₹{sl:.0f} (-{((entry-sl)/entry*100):.1f}%)"
                break
        
        # Create intelligent prompt for OpenAI
        prompt = f"""User asked: "{user_question}"

You are Fyntrix, an intelligent trading assistant. Provide a comprehensive, conversational analysis of {symbol} based on this multi-agent analysis and the additional context below.

**Overall Score:** {blend_score:.1f}/100
**Recommendation:** {recommendation}
**Confidence:** {confidence}

**Agent Breakdown:**
{chr(10).join(agent_summary)}

**Key Signals:**
{signals_text}
{tech_levels}{portfolio_section}{watchlist_section}{live_section}{top_pick_section}{news_section}{external_section}{profile_section}
INSTRUCTIONS:
1. Begin with 2–3 short sentences that directly answer the user's question and state your stance.
2. Then provide a short "Why this view" section with 2–4 concise bullet points tied to the strongest signals above.
3. Highlight the most important factors (2–3 key points) for the user's decision, including risk/return trade-offs.
4. Provide actionable guidance that includes entry/exit levels if available and always mention stop-loss/exit thinking.
5. Keep it CONCISE - maximum 120 words.
6. Use "I" perspective as Fyntrix and keep the tone professional but easy to understand.
7. Focus on key insights - no fluff; avoid generic textbook explanations.
8. Respect the user's profile and risk preferences when provided (experience, style, risk).
9. When external fundamentals bullets include valuations or key ratios (for example PE, ROE, debt/equity, operating margin), quote the 1–3 most relevant numbers explicitly and briefly interpret what they imply for the trade.
10. Clearly separate pros and cons so the user can weigh trade-offs.
11. Always include a brief risk disclaimer (no guarantees of returns) and end with exactly one short guiding follow-up question that helps the user decide next steps (e.g., time horizon, risk appetite, or whether they want a comparison or levels).

Generate a concise, intelligent response (max ~120 words):"""

        try:
            llm_response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": """You are Fyntrix, a highly intelligent AI trading assistant for Indian equity markets. You analyze stocks using a multi-agent system (technical, global markets, policy, options flow, sentiment, microstructure, risk) plus live market data, Fyntrix Top Picks, curated news, and external fundamentals.

Your responses must:
- Be professional yet conversational and easy to follow.
- Start with a brief (2–3 sentence) direct answer and stance for the user.
- Then give 2–4 concise bullet points explaining why, tying back to the strongest signals.
- Optionally add 1–2 bullets on key risks or trade-offs if they are important.
- Stay concise (target under 120 words) and focused on the user's question.
- Be insight-driven with clear reasoning tied back to concrete signals.
- Provide structured pros and cons and, when appropriate, a trade stance with entry/exit thinking and stop-loss guidance.
- Explicitly acknowledge uncertainty and key risks; never promise profits or certain outcomes.
- Respect the user's experience level and risk profile when given.
- Always end with exactly one short guiding follow-up question to keep the conversation going."""
                        },
                        {"role": "user", "content": prompt}
                    ],
                    complexity="medium",
                    max_tokens=200,  # Limit to ~100 words
                    temperature=0.7,  # More creative
                ),
                timeout=18.0,
            )
            
            response_text = llm_response['content']
            print(f"  ✅ Generated intelligent analysis for {symbol}")
            
            return response_text
            
        except Exception as e:
            print(f"  ⚠️ OpenAI analysis failed: {e}, falling back to template")
            # Fallback to simple template if OpenAI fails
            return self._format_analysis_response_fallback(symbol, result)
    
    def _format_analysis_response_fallback(self, symbol: str, result: Dict[str, Any]) -> str:
        """Fallback template formatting if OpenAI fails"""
        
        blend_score = result.get('blend_score', 0)
        recommendation = result.get('recommendation', 'Hold')
        confidence = result.get('confidence', 'Medium')
        
        prefix = "Based on my multi-agent (10+ agents) analysis"
        
        response = f"{prefix}, {symbol} scores {blend_score:.1f}/100 with a {recommendation} recommendation (confidence: {confidence}). "
        
        key_signals = result.get('key_signals', [])[:2]
        if key_signals:
            response += "Key factors: "
            response += ", ".join([s.get('signal', '') for s in key_signals])
        
        return response
    
    async def _handle_comparison(
        self,
        entities: Dict[str, Any],
        history: List[Dict[str, str]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle stock comparison queries"""
        
        symbols = entities.get('symbols', [])
        if len(symbols) < 2:
            return {
                'response': "To compare stocks, please mention at least 2 stocks. For example: 'Compare RELIANCE vs TCS'",
                'suggestions': ["Compare RELIANCE vs TCS", "Compare INFY vs WIPRO"]
            }
        
        symbol1, symbol2 = symbols[0], symbols[1]
        
        try:
            # Analyze both stocks
            results = await self.coordinator.batch_analyze([symbol1, symbol2])
            
            if len(results) < 2:
                return {
                    'response': f"I could only analyze one of the stocks. Please try again.",
                    'suggestions': ["Analyze RELIANCE", "Show top picks"]
                }
            
            # Generate INTELLIGENT comparison using OpenAI
            response_text = await self._generate_intelligent_comparison(results[0], results[1], history, user_profile=user_profile)
            
            return {
                'response': response_text,
                'data': {'stocks': results},
                'suggestions': [
                    f"Tell me more about {symbol1}",
                    f"Tell me more about {symbol2}",
                    "Show top picks"
                ]
            }
            
        except Exception as e:
            return {
                'response': f"I had trouble comparing those stocks: {str(e)}",
                'suggestions': ["Show top picks", "Analyze RELIANCE"]
            }
    
    async def _generate_intelligent_comparison(
        self,
        result1: Dict,
        result2: Dict,
        history: List[Dict[str, str]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate intelligent stock comparison using OpenAI"""
        
        symbol1 = result1.get('symbol')
        symbol2 = result2.get('symbol')
        score1 = result1.get('blend_score', 0)
        score2 = result2.get('blend_score', 0)
        rec1 = result1.get('recommendation', 'Hold')
        rec2 = result2.get('recommendation', 'Hold')
        
        # Extract user's question
        user_question = history[-1]['content'] if history else f"Compare {symbol1} vs {symbol2}"

        profile_hint = self._build_user_profile_hint(user_profile)
        
        # Build comparison context
        prompt = f"""User asked: "{user_question}"

{profile_hint}

Compare these two stocks based on Fyntrix's multi-agent analysis:

**{symbol1}:**
- Score: {score1:.1f}/100
- Recommendation: {rec1}
- Top Agents: {', '.join([f"{a.get('agent')}: {a.get('score', 0):.0f}" for a in result1.get('agents', [])[:3]])}

**{symbol2}:**
- Score: {score2:.1f}/100
- Recommendation: {rec2}
- Top Agents: {', '.join([f"{a.get('agent')}: {a.get('score', 0):.0f}" for a in result2.get('agents', [])[:3]])}

INSTRUCTIONS:
1. Start with 2–3 short sentences clearly stating which stock currently suits this user better and why.
2. Then give 2–3 concise bullet points under "Why this view" focusing on the most important differences (technical, sentiment, risk, etc.).
3. Highlight any major risk or position-sizing considerations given the user profile (if provided).
4. Keep it CONCISE - maximum 100 words.
5. Use a calm, coaching tone and avoid hype.
6. End with exactly one short follow-up question to keep the conversation going (for example, about time horizon, risk tolerance, or wanting specific levels).

Generate intelligent comparison (max 100 words):"""

        try:
            llm_response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are Fyntrix, an intelligent trading assistant. Provide concise, well-structured stock comparisons (max 100 words) based on multi-agent analysis data. Start with a brief conclusion, then bullets for reasons and risks, and finish with one short guiding question."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    complexity="medium",
                    max_tokens=200,
                    temperature=0.7,
                ),
                timeout=18.0,
            )
            
            print(f"  ✅ Generated intelligent comparison: {symbol1} vs {symbol2}")
            return llm_response['content']
            
        except Exception as e:
            print(f"  ⚠️ OpenAI comparison failed: {e}")
            # Fallback
            return f"Comparing {symbol1} ({score1:.1f}/100, {rec1}) vs {symbol2} ({score2:.1f}/100, {rec2}): {symbol1 if score1 > score2 else symbol2} shows stronger signals by {abs(score1-score2):.1f} points."
    
    async def _handle_top_picks(
        self,
        message: str,
        history: List[Dict[str, str]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle top picks requests with intelligent OpenAI responses"""
        
        # Get latest picks
        picks_data = get_latest_picks()
        
        if not picks_data or not picks_data.get('picks'):
            return {
                'response': "I don't have today's top picks yet. They're generated daily at 6 AM IST. Would you like me to analyze a specific stock instead?",
                'suggestions': self._dedupe_suggestions([
                    "Analyze RELIANCE",
                    "Analyze TCS",
                    "Compare stocks",
                ])
            }
        
        picks = picks_data['picks'][:5]  # Top 5
        
        # Build context for OpenAI
        picks_summary = []
        for pick in picks:
            symbol = pick.get('symbol')
            score = pick.get('blend_score', 0)
            rec = pick.get('recommendation', 'Hold')
            key_findings = pick.get('key_findings', '')
            upside = pick.get('upside_pct', 0)
            
            picks_summary.append(
                f"- {symbol}: {score:.1f}/100 ({rec}), Upside: {upside:+.1f}%, Key: {key_findings[:100]}"
            )
        
        # Generate intelligent response using OpenAI
        try:
            profile_hint = self._build_user_profile_hint(user_profile)

            prompt = f"""User asked: "{message}"

{profile_hint}

Today's Top 5 Picks from Fyntrix's multi-agent analysis (10+ agents):

{chr(10).join(picks_summary)}

INSTRUCTIONS:
1. Start with 2–3 short sentences summarizing the key idea for this user.
2. Then add 2–3 concise bullet points explaining why these ideas fit the current market and the user's profile (if provided).
3. Highlight basic risk management in plain language (for example, position sizing or stop-loss thinking).
4. Keep it CONCISE - maximum 100 words.
5. Use a calm, conversational tone and avoid jargon unless you briefly explain it.
6. End with exactly one short guiding follow-up question (for example, whether they want a deep dive on a specific pick or filtered ideas by risk level).

Generate intelligent response (max 100 words):"""

            llm_response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are Fyntrix, an intelligent trading assistant. Provide concise (max 100 words), structured insights about top stock picks based on a multi-agent ensemble (10+ agents). Start with a short summary, then key reasons, and always end with one guiding follow-up question."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    complexity="medium",
                    max_tokens=200,
                    temperature=0.7,
                ),
                timeout=18.0,
            )
            
            response_text = llm_response['content']
            print(f"  ✅ Generated intelligent top picks response")
            
        except Exception as e:
            print(f"  ⚠️ OpenAI top picks failed: {e}, using fallback")
            # Fallback
            response_text = f"Today's Top 5: " + ", ".join([f"{p['symbol']} ({p.get('blend_score', 0):.0f}/100)" for p in picks])
        
        return {
            'response': response_text,
            'data': picks_data,
            'suggestions': self._build_top_picks_suggestions(picks, user_profile=user_profile),
        }
    
    async def _handle_educational(
        self,
        message: str,
        history: List[Dict[str, str]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle educational/definitional queries with comprehensive data sources"""
        faq_entry = self._match_faq(message)
        if faq_entry:
            answer = str(faq_entry.get("answer") or "").strip()
            if answer:
                return {
                    'response': answer,
                    'suggestions': faq_entry.get(
                        'suggestions',
                        [
                            "Show top picks",
                            "Analyze NIFTY",
                            "What is RSI?",
                        ],
                    ),
                }

        # Extract the concept being asked about
        concept = message.lower()
        
        # Try to get data from Alpha Vantage for technical indicators
        alphavantage_context = ""
        try:
            av = get_alphavantage_provider()
            
            if av and av.is_configured():
                if "rsi" in concept:
                    # Get RSI for a sample stock to provide real example (SYNC call)
                    rsi_data = av.get_rsi("TCS", interval="daily", time_period=14)
                    if rsi_data:
                        current_rsi = rsi_data.get('value')
                        interpretation = rsi_data.get('interpretation', '')
                        signal = rsi_data.get('signal', 'neutral')
                        if current_rsi:
                            alphavantage_context = f"\n\nReal Example: TCS currently has RSI of {current_rsi:.1f} ({signal.upper()}). {interpretation}"
                
                elif "macd" in concept:
                    # Get MACD for a sample stock (SYNC call)
                    macd_data = av.get_macd("TCS", interval="daily")
                    if macd_data:
                        macd_value = macd_data.get('MACD', 'N/A')
                        signal_value = macd_data.get('MACD_Signal', 'N/A')
                        alphavantage_context = f"\n\nReal Example: TCS MACD - Value: {macd_value}, Signal: {signal_value}"
        
        except Exception as e:
            print(f"  ⚠️  Alpha Vantage lookup failed: {e}")
        
        # Try Finnhub for market context
        finnhub_context = ""
        try:
            finnhub = get_finnhub_provider()
            
            # Get recent market news for context
            if finnhub and finnhub.is_configured():
                if "market" in concept or "sentiment" in concept:
                    news = finnhub.get_market_news(category="general", count=3)
                    if news and len(news) > 0:
                        finnhub_context = f"\n\nCurrent Market Context: Based on recent news, {news[0].get('headline', '')[:100]}..."
        
        except Exception as e:
            print(f"  ⚠️  Finnhub lookup failed: {e}")
        
        # Get comprehensive response from OpenAI with all context
        try:
            profile_hint = self._build_user_profile_hint(user_profile)

            enhanced_prompt = f"""User is asking about: {message}

{profile_hint}

Provide a clear, structured explanation that includes:
1. A 2–3 sentence plain-language overview that a non-expert can follow.
2. How it's used in trading with 2–3 concise bullet points of practical tips.
3. 1–2 important pitfalls or risk points to watch out for.

Make it educational yet actionable. Avoid heavy jargon or formulas unless needed, and keep it under ~180 words.
Always end with exactly one short follow-up question to keep the conversation going.

{alphavantage_context}
{finnhub_context}"""
            
            llm_response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": """You are Fyntrix, a highly intelligent trading education assistant with access to:
- Real-time market data from Alpha Vantage
- Global news from Finnhub
- Multi-agent analysis system
- Technical and fundamental analysis expertise

Provide comprehensive, professional, and actionable explanations. Include real examples when available. Make every response unique and valuable."""
                        },
                        {
                            "role": "user",
                            "content": enhanced_prompt
                        }
                    ],
                    complexity="medium",
                    max_tokens=500,  # Allow for more detailed responses
                ),
                timeout=20.0,
            )
            
            response_text = llm_response['content']
            
        except Exception as e:
            print(f"  ⚠️  OpenAI failed: {e}")
            # Fallback to informative error
            response_text = f"I'd be happy to explain {concept}! However, I'm having trouble accessing my analysis systems right now. Could you try again in a moment?"
        
        return {
            'response': response_text,
            'suggestions': self._build_educational_suggestions(message, user_profile=user_profile),
        }
    
    def _handle_greeting(self, message: str) -> Dict[str, Any]:
        """Handle greeting messages"""
        
        greetings = [
            "Hi! I'm Fyntrix, your intelligent trading assistant. I can analyze stocks, show you top picks, and answer your trading questions. What would you like to know?",
            "Hello! I'm Fyntrix and I'm here to help simplify trading for you. I can analyze any stock, compare options, or show today's top picks. What interests you?",
            "Hey there! I'm Fyntrix – I analyze stocks using 10+ AI agents to give you clear recommendations. Want to see today's top picks?"
        ]
        
        # Simple rotation
        import random
        response_text = random.choice(greetings)
        
        return {
            'response': response_text,
            'suggestions': [
                "Show me today's top picks",
                "Analyze RELIANCE",
                "Compare TCS vs INFY",
                "What is RSI?"
            ]
        }
    
    async def _handle_market_outlook(
        self,
        message: str,
        history: List[Dict[str, str]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle market outlook and general market questions"""
        
        try:
            # Use OpenAI to generate market outlook
            profile_hint = self._build_user_profile_hint(user_profile)

            market_prompt = f"""User is asking about market outlook: "{message}"

{profile_hint}

You are Fyntrix, an AI trading assistant. Provide a concise market outlook based on general market conditions.

Focus on:
1. Overall market sentiment (bullish/bearish/neutral).
2. Key factors affecting the market.
3. Major indices (NIFTY, BANKNIFTY if India, S&P if global).
4. Key sectors to watch.
5. Risk factors and how a trader with this profile might think about exposure.

Structure your answer as: (a) 2–3 sentences with the key takeaway, (b) 2–4 short bullets with reasons/risks, and (c) exactly one short follow-up question to guide the next step.
Keep response under ~150 words and actionable."""

            llm_response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=[
                        {"role": "system", "content": "You are Fyntrix, an intelligent trading assistant providing market insights. Be concise, structured, and always finish with one guiding follow-up question."},
                        {"role": "user", "content": market_prompt}
                    ],
                    complexity="medium",
                    max_tokens=200,
                ),
                timeout=18.0,
            )
            
            response_text = llm_response['content']
            
        except Exception:
            response_text = "I can provide detailed market analysis. Would you like me to analyze specific indices like NIFTY or BANKNIFTY, or show you today's top picks?"
        
        return {
            'response': response_text,
            'suggestions': self._build_market_outlook_suggestions(user_profile=user_profile),
        }
    
    async def _handle_general(
        self,
        message: str,
        history: List[Dict[str, str]],
        user_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle general queries with OpenAI"""
        faq_entry = self._match_faq(message)
        if faq_entry:
            answer = str(faq_entry.get("answer") or "").strip()
            if answer:
                return {
                    'response': answer,
                    'suggestions': faq_entry.get(
                        'suggestions',
                        [
                            "Show top picks",
                            "Analyze RELIANCE",
                            "What is RSI?",
                        ],
                    ),
                }

        try:
            profile_hint = self._build_user_profile_hint(user_profile)

            # Build context from history
            system_content = "You are Fyntrix, an intelligent trading assistant. Be helpful, concise, and guide users towards actionable insights. "
            if profile_hint:
                system_content += profile_hint + " "
            system_content += (
                "Always structure your answer in three parts: (1) 2–3 sentences answering the user's latest question directly; "
                "(2) 2–3 concise bullet points with key reasons and risks; (3) exactly one short follow-up question to keep the conversation going. "
                "Keep responses under ~140 words."
            )

            messages = [
                {"role": "system", "content": system_content}
            ]
            
            # Add recent history
            for turn in history[-4:]:  # Last 4 turns
                messages.append({
                    "role": turn['role'],
                    "content": turn['content']
                })
            
            llm_response = await asyncio.wait_for(
                llm_manager.chat_completion(
                    messages=messages,
                    complexity="simple",
                    max_tokens=250,
                ),
                timeout=15.0,
            )
            
            response_text = llm_response['content']
            
        except Exception:
            response_text = "I'm not sure I understand. Could you rephrase that, or would you like me to analyze a stock or show top picks?"
        
        return {
            'response': response_text,
            'suggestions': self._build_general_suggestions(user_profile=user_profile),
        }


# Global instance
aris_chat = ARISChat()


# Convenience function
async def chat_with_aris(
    message: str,
    conversation_id: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Chat with ARIS (convenience function).
    Can be called from API endpoints.
    """
    return await aris_chat.chat(
        message=message,
        conversation_id=conversation_id,
        user_context=user_context
    )
