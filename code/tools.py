# tools.py
"""Tool definitions for the Backend LLM (Brain)."""
import json
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Menu data for the restaurant
MENU = {
    "ca_phe_den": {"name": "Cà phê đen", "price": 20000, "category": "Coffee"},
    "ca_phe_den_l": {"name": "Cà phê đen (L)", "price": 22000, "category": "Coffee"},
    "ca_phe_sua": {"name": "Cà phê sữa", "price": 22000, "category": "Coffee"},
    "ca_phe_sua_l": {"name": "Cà phê sữa (L)", "price": 27000, "category": "Coffee"},
    "bac_xiu": {"name": "Bạc xỉu", "price": 22000, "category": "Coffee"},
    "bac_xiu_l": {"name": "Bạc xỉu (L)", "price": 28000, "category": "Coffee"},
    "ca_phe_sua_tuoi": {"name": "Cà phê sữa tươi", "price": 22000, "category": "Coffee"},
    "ca_phe_sua_tuoi_l": {"name": "Cà phê sữa tươi (L)", "price": 27000, "category": "Coffee"},
    "milo_cacao": {"name": "Milo / Cacao", "price": 22000, "category": "Coffee"},
    "milo_cacao_l": {"name": "Milo / Cacao (L)", "price": 28000, "category": "Coffee"},
    "latte": {"name": "Latte", "price": 25000, "category": "Coffee"},
    "latte_l": {"name": "Latte (L)", "price": 30000, "category": "Coffee"},
    "capuchino": {"name": "Capuchino", "price": 25000, "category": "Coffee"},
    "capuchino_l": {"name": "Capuchino (L)", "price": 30000, "category": "Coffee"},
    "ca_phe_muoi": {"name": "Cà phê muối", "price": 25000, "category": "Coffee"},
    "ca_phe_muoi_l": {"name": "Cà phê muối (L)", "price": 30000, "category": "Coffee"},
    "tra_chanh": {"name": "Trà chanh", "price": 15000, "category": "Tea"},
    "tra_chanh_l": {"name": "Trà chanh (L)", "price": 20000, "category": "Tea"},
    "tra_chanh_mat_ong": {"name": "Trà chanh mật ong", "price": 20000, "category": "Tea"},
    "tra_chanh_mat_ong_l": {"name": "Trà chanh mật ong (L)", "price": 25000, "category": "Tea"},
    "chanh_day_mat_ong": {"name": "Chanh dây mật ong", "price": 30000, "category": "Tea"},
    "tra_dau": {"name": "Trà dâu", "price": 30000, "category": "Tea"},
    "tra_chanh_day_kiwi": {"name": "Trà chanh dây kiwi", "price": 30000, "category": "Tea"},
    "tra_mix": {"name": "Trà ổi/dâu/đào/việt quất/kiwi", "price": 25000, "category": "Tea"},
    "tra_mix_l": {"name": "Trà ổi/dâu/đào/việt quất/kiwi (L)", "price": 30000, "category": "Tea"},
    "matcha_latte": {"name": "Matcha latte", "price": 25000, "category": "Tea"},
    "matcha_latte_l": {"name": "Matcha latte (L)", "price": 30000, "category": "Tea"},
    "sua_chua_mix": {"name": "Sữa chua (đào/việt quất/dâu/kiwi)", "price": 30000, "category": "Tea"},
    "lipton_xi_muoi": {"name": "Lipton xí muội", "price": 25000, "category": "Tea"},
    "milo_da_xay_kem": {"name": "Milo đá xay kem", "price": 30000, "category": "Tea"},
    "nuoc_ep_thom": {"name": "Nước ép thơm", "price": 25000, "category": "Juice"},
    "nuoc_ep_dua_hau": {"name": "Nước ép dưa hấu", "price": 25000, "category": "Juice"},
    "rau_ma_dau_xanh": {"name": "Rau má đậu xanh", "price": 25000, "category": "Juice"},
    "rau_ma_nguyen_chat": {"name": "Rau má nguyên chất", "price": 20000, "category": "Juice"},
    "nuoc_ngot_lon": {"name": "Nước ngọt lon", "price": 20000, "category": "Juice"},
    "bo_cung": {"name": "Bò cụng", "price": 25000, "category": "Juice"},
    "nuoc_suoi": {"name": "Nước suối", "price": 15000, "category": "Juice"},
    "sinh_to_bo": {"name": "Sinh tố bơ", "price": 35000, "category": "Smoothie"},
    "sinh_to_dau": {"name": "Sinh tố dâu", "price": 35000, "category": "Smoothie"},
    "sinh_to_sapoche": {"name": "Sinh tố sapoche", "price": 25000, "category": "Smoothie"},
    "sinh_to_chanh_day": {"name": "Sinh tố chanh dây", "price": 35000, "category": "Smoothie"},
}


@dataclass
class OrderState:
    """Holds the current order state."""
    items: Dict[str, int] = field(default_factory=dict)  # item_id -> quantity
    confirmed: bool = False
    
    def add_item(self, item_id: str, quantity: int = 1) -> bool:
        """Add item to order. Returns True if successful."""
        if item_id in MENU:
            self.items[item_id] = self.items.get(item_id, 0) + quantity
            return True
        return False
    
    def update_item(self, item_id: str, quantity: int) -> bool:
        """Update item quantity. Returns True if successful."""
        if item_id in MENU:
            if quantity <= 0:
                return self.remove_item(item_id)
            self.items[item_id] = quantity
            return True
        return False
    
    def remove_item(self, item_id: str) -> bool:
        """Remove item from order. Returns True if successful."""
        if item_id in self.items:
            del self.items[item_id]
            return True
        return False
    
    def clear(self):
        """Clear the order."""
        self.items.clear()
        self.confirmed = False
    
    def get_summary(self) -> List[Dict[str, Any]]:
        """Get order summary with item details."""
        summary = []
        for item_id, qty in self.items.items():
            if item_id in MENU:
                item = MENU[item_id]
                summary.append({
                    "id": item_id,
                    "name": item["name"],
                    "price": item["price"],
                    "quantity": qty,
                    "total": item["price"] * qty
                })
        return summary
    
    def get_total(self) -> int:
        """Get total price in VND."""
        return sum(item["total"] for item in self.get_summary())


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    ui_update: Optional[Dict[str, Any]] = None  # Data to show in UI (not spoken)
    speak_context: Optional[str] = None  # Context for Speaker LLM


class ToolExecutor:
    """Executes tools based on Backend LLM output."""
    
    def __init__(self):
        self.order = OrderState()
        self.speak_contexts: List[str] = []  # Collected contexts for Speaker LLM
    
    def execute(self, tool_call: Dict[str, Any]) -> ToolResult:
        """Execute a tool call and return the result."""
        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        
        method = getattr(self, f"_tool_{name}", None)
        if method:
            return method(**args)
        else:
            return ToolResult(
                success=False,
                message=f"Unknown tool: {name}"
            )
    
    def _tool_add_to_order(self, item_id: str, quantity: int = 1) -> ToolResult:
        """Add item to order."""
        if item_id not in MENU:
            return ToolResult(
                success=False,
                message=f"Item '{item_id}' not found in menu",
                speak_context=f"Customer tried to order an item not on the menu: {item_id}"
            )
        
        success = self.order.add_item(item_id, quantity)
        item = MENU[item_id]
        
        if success:
            return ToolResult(
                success=True,
                message=f"Added {quantity}x {item['name']} to order",
                ui_update={
                    "type": "order_update",
                    "order": self.order.get_summary(),
                    "total": self.order.get_total()
                },
                speak_context=f"Customer ordered {item['name']} (quantity: {quantity}), added to order successfully"
            )
        return ToolResult(success=False, message="Failed to add item")
    
    def _tool_update_order(self, item_id: str, quantity: int) -> ToolResult:
        """Update item quantity in order."""
        if item_id not in MENU:
            return ToolResult(success=False, message=f"Item '{item_id}' not found")
        
        success = self.order.update_item(item_id, quantity)
        item = MENU[item_id]
        
        if success:
            return ToolResult(
                success=True,
                message=f"Updated {item['name']} to {quantity}",
                ui_update={
                    "type": "order_update",
                    "order": self.order.get_summary(),
                    "total": self.order.get_total()
                },
                speak_context=f"Customer updated {item['name']} to quantity {quantity}"
            )
        return ToolResult(success=False, message="Item not in order")
    
    def _tool_remove_from_order(self, item_id: str) -> ToolResult:
        """Remove item from order."""
        if item_id not in self.order.items:
            return ToolResult(
                success=False,
                message=f"Item '{item_id}' not in order",
                speak_context="Customer tried to remove an item that wasn't in their order"
            )
        
        item = MENU.get(item_id, {})
        name = item.get("name", item_id)
        success = self.order.remove_item(item_id)
        
        if success:
            return ToolResult(
                success=True,
                message=f"Removed {name} from order",
                ui_update={
                    "type": "order_update",
                    "order": self.order.get_summary(),
                    "total": self.order.get_total()
                },
                speak_context=f"Customer removed {name} from their order"
            )
        return ToolResult(success=False, message="Failed to remove item")
    
    def _tool_get_order_summary(self) -> ToolResult:
        """Get current order summary."""
        summary = self.order.get_summary()
        if not summary:
            return ToolResult(
                success=True,
                message="Order is empty",
                ui_update={
                    "type": "order_update",
                    "order": [],
                    "total": 0
                },
                speak_context="Customer asked for order summary, but order is empty"
            )
        
        return ToolResult(
            success=True,
            message=f"Order has {len(summary)} items, total: {self.order.get_total():,} VND",
            ui_update={
                "type": "order_update",
                "order": summary,
                "total": self.order.get_total()
            },
            speak_context=f"Customer asked for order summary. Order has {len(summary)} items totaling {self.order.get_total():,} VND"
        )
    
    def _tool_get_menu(self, category: Optional[str] = None) -> ToolResult:
        """Get menu items, optionally filtered by category."""
        items = []
        for item_id, item in MENU.items():
            if category is None or item["category"].lower() == category.lower():
                items.append({
                    "id": item_id,
                    "name": item["name"],
                    "price": item["price"],
                    "category": item["category"]
                })
        
        return ToolResult(
            success=True,
            message=f"Found {len(items)} menu items",
            ui_update={
                "type": "menu_display",
                "items": items,
                "category": category
            },
            speak_context=f"Customer asked for the menu. There are {len(items)} items available"
        )
    
    def _tool_confirm_order(self) -> ToolResult:
        """Confirm the order."""
        if not self.order.items:
            return ToolResult(
                success=False,
                message="Cannot confirm empty order",
                speak_context="Customer tried to confirm but order is empty"
            )
        
        self.order.confirmed = True
        total = self.order.get_total()
        
        return ToolResult(
            success=True,
            message=f"Order confirmed! Total: {total:,} VND",
            ui_update={
                "type": "order_confirmed",
                "order": self.order.get_summary(),
                "total": total
            },
            speak_context=f"Order confirmed! Total is {total:,} VND. Thank you for your order!"
        )
    
    def _tool_show_payment_qr(self) -> ToolResult:
        """Show payment QR code."""
        if not self.order.confirmed:
            return ToolResult(
                success=False,
                message="Order not confirmed yet",
                speak_context="Customer asked for payment QR but order isn't confirmed yet"
            )
        
        total = self.order.get_total()
        # In real implementation, generate actual QR
        qr_data = f"payment://{total}"
        
        return ToolResult(
            success=True,
            message=f"Payment QR generated for {total:,} VND",
            ui_update={
                "type": "payment_qr",
                "amount": total,
                "qr_data": qr_data
            },
            speak_context=f"Payment QR displayed for {total:,} VND. Please scan to pay."
        )
    
    def _tool_clear_order(self) -> ToolResult:
        """Clear the order."""
        self.order.clear()
        return ToolResult(
            success=True,
            message="Order cleared",
            ui_update={
                "type": "order_update",
                "order": [],
                "total": 0
            },
            speak_context="Order has been cleared"
        )
    
    def _tool_speak_to_customer(self, context: str) -> ToolResult:
        """Special tool - provides context for Speaker LLM."""
        # This doesn't execute immediately - context is collected for Speaker LLM
        self.speak_contexts.append(context)
        return ToolResult(
            success=True,
            message=f"Speak context queued: {context}",
            speak_context=context
        )
    
    def get_speak_contexts(self) -> str:
        """Get all collected speak contexts and clear them."""
        contexts = self.speak_contexts.copy()
        self.speak_contexts.clear()
        return " | ".join(contexts) if contexts else ""
    
    def reset(self):
        """Reset state for new session."""
        self.order.clear()
        self.speak_contexts.clear()


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Parse JSON tool calls from Backend LLM output."""
    tool_calls = []
    
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        
        try:
            # Try to parse as JSON
            tool_call = json.loads(line)
            if "name" in tool_call:
                tool_calls.append(tool_call)
        except json.JSONDecodeError:
            # Not a valid JSON line, skip
            continue
    
    return tool_calls


# Tool definitions for Backend LLM system prompt
TOOL_DEFINITIONS = """
You have access to the following tools. Output ONE tool call per line as JSON.

Available tools:
- add_to_order: Add item to order. Args: item_id (string), quantity (number, default 1)
- update_order: Update item quantity. Args: item_id (string), quantity (number)
- remove_from_order: Remove item from order. Args: item_id (string)
- get_order_summary: Get current order. No args.
- get_menu: Get menu items. Args: category (optional string: "Main", "Side", "Drink")
- confirm_order: Confirm the order. No args.
- show_payment_qr: Show payment QR code. No args.
- clear_order: Clear the order. No args.
- speak_to_customer: Provide context for what to say to customer. Args: context (string)

Menu items:
- burger_bo: Burger Bo Pho Mai (75,000 VND) - Main
- burger_ga: Burger Ga Gion (65,000 VND) - Main
- mi_y: Mi Y Sot Bo Bam (85,000 VND) - Main
- com_ga: Com Ga Teriyaki (70,000 VND) - Main
- salad: Salad Ca Ngu (60,000 VND) - Main
- khoai_chien: Khoai Tay Chien (35,000 VND) - Side
- khoai_phomai: Khoai Tay Lac Pho Mai (40,000 VND) - Side
- nuggets: Ga Nuggets (45,000 VND) - Side
- tra_dao: Tra Dao (35,000 VND) - Drink
- tra_sua: Tra Sua Tran Chau (45,000 VND) - Drink
- ca_phe: Ca Phe Sua Da (30,000 VND) - Drink
- cola: Coca Cola (25,000 VND) - Drink
- nuoc_suoi: Nuoc Suoi (15,000 VND) - Drink

Output format: One JSON object per line, no other text.
Example:
{"name": "add_to_order", "args": {"item_id": "burger_bo", "quantity": 1}}
{"name": "speak_to_customer", "args": {"context": "Customer ordered a burger, added to order"}}
"""
