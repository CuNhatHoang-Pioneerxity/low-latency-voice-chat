# backend_llm.py
"""Backend LLM (Brain) - Handles logic, state, and tool execution."""
import logging
from typing import Generator, List, Dict, Any, Optional
from llm_module import LLM
from tools import ToolExecutor, parse_tool_calls, TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

BACKEND_SYSTEM_PROMPT = f"""You are ORDER MANAGEMENT, the backend brain of a Vietnamese coffee shop ordering system.

Your role:
- Process user input and decide what actions to take
- Manage order state, execute tools, handle business logic
- NEVER speak directly to the customer - that's the Speaker LLM's job

Output rules:
- Output JSON tool calls only, one per line
- No prose, no explanations, no conversational text
- Always end with speak_to_customer to tell the Speaker LLM what to say

{TOOL_DEFINITIONS}

Behavior:
1. When customer orders: add_to_order, then speak_to_customer with what happened
2. When customer asks for menu: get_menu, then speak_to_customer
3. When customer wants to confirm: confirm_order, then speak_to_customer
4. When customer wants to pay/check out: IMMEDIATELY call show_payment_qr (no delays, no "bill preparation"), then speak_to_customer
5. Always use speak_to_customer to provide context for the response

CRITICAL: When customer says "check out", "pay", "bill", or wants to finish order:
- First call confirm_order if not already confirmed
- Then IMMEDIATELY call show_payment_qr (do not say "preparing bill" or similar)
- The QR should appear instantly on the screen

IMPORTANT: Map common customer requests to exact menu item_ids:
- "black coffee" or "coffee without milk" → ca_phe_den
- "coffee with milk" or "milk coffee" → ca_phe_sua
- "white coffee" or "bac xiu" → bac_xiu
- "fresh milk coffee" → ca_phe_sua_tuoi
- "latte" → latte
- "capuchino" → capuchino
- "salt coffee" → ca_phe_muoi
- "milo" or "cacao" → milo_cacao
- "lemon tea" or "tea with lemon" → tra_chanh
- "honey lemon tea" → tra_chanh_mat_ong
- "strawberry tea" → tra_dau
- "matcha" → matcha_latte
- "water" → nuoc_suoi
- Default for unspecified coffee: ca_phe_den (black coffee)
- Default for unspecified tea: tra_chanh (lemon tea)

Menu items (use these exact item_ids):
- Coffee: ca_phe_den, ca_phe_den_l, ca_phe_sua, ca_phe_sua_l, bac_xiu, bac_xiu_l, ca_phe_sua_tuoi, ca_phe_sua_tuoi_l, milo_cacao, milo_cacao_l, latte, latte_l, capuchino, capuchino_l, ca_phe_muoi, ca_phe_muoi_l
- Tea: tra_chanh, tra_chanh_l, tra_chanh_mat_ong, tra_chanh_mat_ong_l, chanh_day_mat_ong, tra_dau, tra_chanh_day_kiwi, tra_mix, tra_mix_l, matcha_latte, matcha_latte_l, sua_chua_mix, lipton_xi_muoi, milo_da_xay_kem
- Juice: nuoc_ep_thom, nuoc_ep_dua_hau, rau_ma_dau_xanh, rau_ma_nguyen_chat, nuoc_ngot_lon, bo_cung, nuoc_suoi
- Smoothie: sinh_to_bo, sinh_to_dau, sinh_to_sapoche, sinh_to_chanh_day

Example interaction:
User: "I want a black coffee"
Your output:
{{"name": "add_to_order", "args": {{"item_id": "ca_phe_den", "quantity": 1}}}}
{{"name": "speak_to_customer", "args": {{"context": "Customer ordered black coffee, added to order successfully"}}}}
"""


class BackendLLM:
    """
    Backend LLM (Brain) - Handles logic, state, and tool execution.
    Outputs JSON tool calls only.
    """
    
    def __init__(
        self,
        backend: str = "xai",
        model: str = "grok-3",
    ):
        self.llm = LLM(
            backend=backend,
            model=model,
            system_prompt=BACKEND_SYSTEM_PROMPT,
        )
        self.executor = ToolExecutor()
        self.history: List[Dict[str, str]] = []
        
        logger.info(f"BackendLLM initialized with {backend}/{model}")
    
    def process(
        self,
        user_input: str,
        use_history: bool = True,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Process user input and yield tool results.
        
        Yields:
            Dict with keys:
            - 'type': 'tool_result'
            - 'tool': tool name
            - 'success': bool
            - 'ui_update': data for UI (visual only)
            - 'speak_context': context for Speaker LLM
        """
        full_output = ""
        
        # Generate tool calls from LLM
        history = self.history if use_history else None
        for chunk in self.llm.generate(user_input, history=history):
            full_output += chunk
        
        # Parse tool calls from output
        tool_calls = parse_tool_calls(full_output)
        
        if not tool_calls:
            # No valid tool calls found - generate a fallback speak context
            logger.warning(f"No valid tool calls found in output: {full_output[:100]}")
            yield {
                'type': 'tool_result',
                'tool': 'fallback',
                'success': True,
                'ui_update': None,
                'speak_context': f"Customer said: {user_input}. Please respond naturally."
            }
            return
        
        # Execute each tool call
        for tool_call in tool_calls:
            result = self.executor.execute(tool_call)
            
            yield {
                'type': 'tool_result',
                'tool': tool_call.get('name', 'unknown'),
                'success': result.success,
                'ui_update': result.ui_update,
                'speak_context': result.speak_context,
            }
        
        # Update history
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": full_output})
    
    def get_speak_contexts(self) -> str:
        """Get all collected speak contexts."""
        return self.executor.get_speak_contexts()
    
    def reset(self):
        """Reset state for new session."""
        self.history.clear()
        self.executor.reset()
    
    def prewarm(self) -> bool:
        """Prewarm the LLM connection."""
        return self.llm.prewarm()
