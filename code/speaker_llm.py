# speaker_llm.py
"""Speaker LLM (Waiter) - Generates natural speech for the customer."""
import logging
from typing import Generator, Optional, List, Dict, Any
from llm_module import LLM

logger = logging.getLogger(__name__)

SPEAKER_SYSTEM_PROMPT = """You are a friendly restaurant waiter. Your job is to speak naturally to customers.

Rules:
- Respond in Vietnamese only
- Keep responses SHORT: maximum 1-2 sentences
- Be friendly, helpful, and natural
- Act like a real human waiter, not a chatbot
- No "As an AI..." or "I am programmed to..."
- Just say what needs to be said, nothing more

You will receive CONTEXT that includes:
1. What the customer said (their question)
2. What happened (tool result/context)

Your job is to respond appropriately to the customer's specific question, not just repeat the context.

Examples:
Context: "Customer said: 'how much for it'. Context: Customer ordered nước suối (quantity: 1), added to order successfully"
Your response: "Nước suối is 15k dong."

Context: "Customer said: 'what item are we talking about'. Context: Customer ordered cà phê sữa (quantity: 1), added to order successfully"
Your response: "We're talking about cà phê sữa, which you just ordered."

Context: "Customer said: 'what's on the menu'. Context: Customer asked for the menu. There are 40 items available"
Your response: "We've got coffee, tea, juice, and smoothies - 40 items total. What would you like?"

Context: "Customer ordered a burger and peach tea, both added to order successfully"
Your response: "Got it! One burger and a peach tea coming right up."

Context: "Customer asked for order summary. Order has 2 items totaling 110,000 VND"
Your response: "You've got a burger and a drink, total is 110k dong."

Remember: Answer the customer's specific question using the context provided. Don't give generic responses.
"""


class SpeakerLLM:
    """
    Speaker LLM (Waiter) - Generates natural speech for the customer.
    Takes context from Backend LLM and produces brief, natural responses.
    """
    
    def __init__(
        self,
        backend: str = "xai",
        model: str = "grok-3",
    ):
        self.llm = LLM(
            backend=backend,
            model=model,
            system_prompt=SPEAKER_SYSTEM_PROMPT,
        )
        
        logger.info(f"SpeakerLLM initialized with {backend}/{model}")
    
    def generate_response(
        self,
        context: str,
    ) -> Generator[str, None, None]:
        """
        Generate natural speech response from context.
        
        Args:
            context: The context from Backend LLM's speak_to_customer tool
            
        Yields:
            Text chunks of the natural speech response
        """
        # Use context directly as the prompt
        for chunk in self.llm.generate(context, use_system_prompt=True):
            yield chunk
    
    def generate_response_sync(self, context: str) -> str:
        """
        Generate complete response synchronously.
        
        Args:
            context: The context from Backend LLM
            
        Returns:
            Complete natural speech text
        """
        full_response = ""
        for chunk in self.generate_response(context):
            full_response += chunk
        return full_response.strip()
    
    def prewarm(self) -> bool:
        """Prewarm the LLM connection."""
        return self.llm.prewarm()
