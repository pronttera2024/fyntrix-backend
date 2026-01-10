"""
OpenAI Manager with Cost Optimization
Smart model selection, caching, and usage tracking
"""

import os
from typing import Dict, List, Any, Optional
import hashlib
import json
from datetime import datetime, timedelta
from openai import OpenAI, AsyncOpenAI
from .cost_tracker import cost_tracker


class OpenAIManager:
    """
    Manages OpenAI API calls with cost optimization strategies:
    1. Tiered model usage (GPT-3.5 for simple, GPT-4 for complex)
    2. Aggressive response caching
    3. Prompt optimization
    4. Response length limits
    5. Batch processing where possible
    """
    
    # Model pricing (per 1K tokens)
    PRICING = {
        'gpt-3.5-turbo': {'input': 0.0015, 'output': 0.002},
        'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
        'gpt-4': {'input': 0.03, 'output': 0.06}
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if not self.api_key:
            print("[WARN] OpenAI API key not found. LLM features will be disabled.")
            self.client = None
            self.async_client = None
        else:
            print(f"[OK] OpenAI API key loaded (first 20 chars): {self.api_key[:20]}...")
            self.client = OpenAI(api_key=self.api_key)
            self.async_client = AsyncOpenAI(api_key=self.api_key)
        
        # Optional SambaNova fallback (OpenAI-compatible API)
        # Uses separate credentials so we never mix provider keys.
        self.sambanova_async_client: Optional[AsyncOpenAI] = None
        self.sambanova_model: str = os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.1-70B-Instruct")

        sambanova_key = os.getenv("SAMBANOVA_API_KEY")
        sambanova_base = os.getenv("SAMBANOVA_BASE_URL")

        if sambanova_key and sambanova_base:
            try:
                self.sambanova_async_client = AsyncOpenAI(
                    api_key=sambanova_key,
                    base_url=sambanova_base,
                )
                print("[OK] SambaNova fallback client configured.")
            except Exception as e:
                print(f"[WARN] Failed to initialize SambaNova client: {e}")
                self.sambanova_async_client = None
        
        # Response cache (in-memory)
        self.cache: Dict[str, tuple[datetime, Any]] = {}
        self.cache_ttl = 300  # 5 minutes default
        
        # Usage limits
        self.daily_budget = float(os.getenv('OPENAI_DAILY_BUDGET', '10.0'))  # $10 default
        self.rate_limit_per_minute = int(os.getenv('OPENAI_RATE_LIMIT', '60'))
    
    def _get_cache_key(self, prompt: str, model: str, **kwargs) -> str:
        """Generate cache key from prompt and params"""
        cache_data = {
            'prompt': prompt,
            'model': model,
            **kwargs
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[Any]:
        """Get cached response if available and not expired"""
        if cache_key in self.cache:
            cached_time, response = self.cache[cache_key]
            age = (datetime.utcnow() - cached_time).total_seconds()
            
            if age < self.cache_ttl:
                print(f"  ⚡ LLM cache hit (age: {int(age)}s)")
                return response
        
        return None
    
    def _cache_response(self, cache_key: str, response: Any):
        """Store response in cache"""
        self.cache[cache_key] = (datetime.utcnow(), response)
    
    def select_model(self, complexity: str = 'medium') -> str:
        """
        Select appropriate model based on query complexity.
        
        Args:
            complexity: 'simple', 'medium', or 'complex'
            
        Returns:
            Model name
        """
        if complexity == 'simple':
            return 'gpt-3.5-turbo'
        elif complexity == 'medium':
            return 'gpt-4-turbo'
        else:
            return 'gpt-4'
    
    def optimize_prompt(self, prompt: str, max_length: int = 2000) -> str:
        """
        Optimize prompt to reduce token usage.
        
        Args:
            prompt: Original prompt
            max_length: Maximum character length
            
        Returns:
            Optimized prompt
        """
        # Trim excessive whitespace
        optimized = ' '.join(prompt.split())
        
        # Truncate if too long
        if len(optimized) > max_length:
            optimized = optimized[:max_length] + '...'
        
        return optimized
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        complexity: str = 'medium',
        max_tokens: int = 500,
        temperature: float = 0.3,
        use_cache: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get chat completion with cost optimization.
        
        Args:
            messages: List of chat messages
            model: Model name (auto-selected if None)
            complexity: Query complexity for model selection
            max_tokens: Maximum response tokens
            temperature: Randomness (lower = more focused)
            use_cache: Whether to use response cache
            **kwargs: Additional OpenAI parameters
            
        Returns:
            Response dictionary with content and metadata
        """
        if not self.async_client:
            print("[LLM] chat_completion called but OpenAI async client is not initialized.")
            raise RuntimeError("OpenAI client not initialized. Check API key.")
        
        # Auto-select model if not specified
        if model is None:
            model = self.select_model(complexity)

        print(f"[LLM] chat_completion starting model={model} complexity={complexity} max_tokens={max_tokens} temp={temperature}")
        
        # Check budget
        if not await cost_tracker.check_budget_available(self.daily_budget):
            # Fallback to cheaper model
            if model == 'gpt-4':
                model = 'gpt-4-turbo'
                print("  ⚠️  Budget limit approaching, using GPT-4-turbo instead")
            elif model == 'gpt-4-turbo':
                model = 'gpt-3.5-turbo'
                print("  ⚠️  Budget limit approaching, using GPT-3.5-turbo instead")
        
        # Generate cache key
        cache_key = self._get_cache_key(
            json.dumps(messages),
            model,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        # Check cache
        if use_cache:
            cached = self._get_cached_response(cache_key)
            if cached:
                return cached
        
        try:
            # Make API call
            response = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            # Extract response
            content = response.choices[0].message.content
            usage = response.usage
            
            # Track cost
            await cost_tracker.log_request(
                model=model,
                tokens_input=usage.prompt_tokens,
                tokens_output=usage.completion_tokens
            )
            
            result = {
                'content': content,
                'model': model,
                'usage': {
                    'prompt_tokens': usage.prompt_tokens,
                    'completion_tokens': usage.completion_tokens,
                    'total_tokens': usage.total_tokens
                },
                'finish_reason': response.choices[0].finish_reason
            }
            
            # Cache response
            if use_cache:
                self._cache_response(cache_key, result)
            
            print(f"[LLM] chat_completion success model={model} total_tokens={usage.total_tokens}")
            return result
            
        except Exception as e:
            print(f"[LLM] ✗ OpenAI API error: {e}")
            # Try SambaNova fallback if configured
            if self.sambanova_async_client:
                try:
                    print("[LLM] ↪ Falling back to SambaNova chat completion...")
                    response = await self.sambanova_async_client.chat.completions.create(
                        model=self.sambanova_model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        **kwargs
                    )

                    content = response.choices[0].message.content
                    usage = getattr(response, 'usage', None)
                    prompt_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                    completion_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
                    total_tokens = getattr(usage, 'total_tokens', prompt_tokens + completion_tokens) if usage else 0

                    # Track cost generically under a SambaNova label
                    await cost_tracker.log_request(
                        model=f"sambanova:{self.sambanova_model}",
                        tokens_input=prompt_tokens,
                        tokens_output=completion_tokens,
                    )

                    result = {
                        'content': content,
                        'model': f"sambanova:{self.sambanova_model}",
                        'usage': {
                            'prompt_tokens': prompt_tokens,
                            'completion_tokens': completion_tokens,
                            'total_tokens': total_tokens,
                        },
                        'finish_reason': response.choices[0].finish_reason,
                    }

                    if use_cache:
                        self._cache_response(cache_key, result)

                    print("[LLM] SambaNova fallback success")
                    return result
                except Exception as se:
                    print(f"[LLM] ✗ SambaNova API error: {se}")
            raise
    
    def chat_completion_sync(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        complexity: str = 'medium',
        max_tokens: int = 500,
        **kwargs
    ) -> Dict[str, Any]:
        """Synchronous version of chat_completion"""
        if not self.client:
            raise RuntimeError("OpenAI client not initialized. Check API key.")
        
        if model is None:
            model = self.select_model(complexity)
        
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs
        )
        
        content = response.choices[0].message.content
        usage = response.usage
        
        # Track cost (sync version doesn't check budget)
        cost_tracker.log_request_sync(
            model=model,
            tokens_input=usage.prompt_tokens,
            tokens_output=usage.completion_tokens
        )
        
        return {
            'content': content,
            'model': model,
            'usage': {
                'prompt_tokens': usage.prompt_tokens,
                'completion_tokens': usage.completion_tokens,
                'total_tokens': usage.total_tokens
            }
        }
    
    async def analyze_with_tools(
        self,
        query: str,
        tools: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        model: str = 'gpt-4-turbo'
    ) -> Dict[str, Any]:
        """
        Analyze query with function calling (MCP tools).
        
        Args:
            query: User query
            tools: List of available tools (MCP functions)
            context: Additional context
            model: Model to use
            
        Returns:
            Analysis result with function calls
        """
        if not self.async_client:
            raise RuntimeError("OpenAI client not initialized")
        
        messages = [
            {
                'role': 'system',
                'content': 'You are Fyntrix, an intelligent trading assistant. Use the available tools to answer user queries accurately.'
            }
        ]
        
        if context:
            messages.append({
                'role': 'system',
                'content': f'Context: {json.dumps(context)}'
            })
        
        messages.append({
            'role': 'user',
            'content': query
        })
        
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice='auto'
        )
        
        choice = response.choices[0]
        usage = response.usage
        
        # Track cost
        await cost_tracker.log_request(
            model=model,
            tokens_input=usage.prompt_tokens,
            tokens_output=usage.completion_tokens
        )
        
        result = {
            'content': choice.message.content,
            'tool_calls': []
        }
        
        if choice.message.tool_calls:
            result['tool_calls'] = [
                {
                    'id': tc.id,
                    'type': tc.type,
                    'function': {
                        'name': tc.function.name,
                        'arguments': json.loads(tc.function.arguments)
                    }
                }
                for tc in choice.message.tool_calls
            ]
        
        return result
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.utcnow()
        valid_items = 0
        
        for cached_time, _ in self.cache.values():
            age = (now - cached_time).total_seconds()
            if age < self.cache_ttl:
                valid_items += 1
        
        return {
            'total_cached': len(self.cache),
            'valid_cached': valid_items,
            'cache_ttl_seconds': self.cache_ttl,
            'daily_budget_usd': self.daily_budget
        }
    
    def clear_cache(self):
        """Clear response cache"""
        self.cache.clear()
        print("✓ LLM cache cleared")


# Global LLM manager instance
llm_manager = OpenAIManager()
