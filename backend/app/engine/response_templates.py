"""Predefined Natural Response Template Library with slight human variations without LLMs."""

import random
from typing import Any, Dict, List, Optional


class ResponseTemplates:
    """Deterministic template collection providing human-sounding, low-latency responses."""

    TEMPLATES = {
        "ACK_FAST": [
            "Ji.",
            "Batao.",
            "Ji boliye.",
            "Haan, batao.",
        ],
        "ACK_CHECK": [
            "Ek minute, check karke batata hoon.",
            "Ruko, abhi check karta hoon.",
            "Ek second, records dekh raha hoon.",
        ],
        "ACK_TASK": [
            "Theek hai, main ye kaam karta hoon. Thoda time do.",
            "Done, ye kaam background mein start kar diya hai.",
        ],
        "ACK_STRATEGY": [
            "Bilkul, is week ki strategy bana raha hoon.",
            "Theek hai, is week ki strategy bana raha hoon. Thoda time do.",
            "Shuru kar raha hoon. Sales aur inventory analyze karke strategy banata hoon.",
        ],
        "COMPLETE": [
            "Kaam complete ho gaya hai.",
            "Done! Kaam poora ho gaya.",
        ],
        "STRATEGY_COMPLETE": [
            "Aapki weekly strategy complete ho gayi hai. Batau?",
            "Weekly strategy ready hai. Sunna chahoge?",
        ],
        "REPORT_COMPLETE": [
            "Aapki report ready ho gayi hai. Batau?",
        ],
        "FAILED": [
            "Ye kaam complete nahi ho paya. Dobara try karu?",
            "Kuch error aaya aur kaam poora nahi hua. Phir se try karein?",
        ],
        "CANCELLED": [
            "Theek hai, ye kaam cancel kar diya.",
            "Operation cancel kar diya gaya hai.",
        ],
        "BARGE_IN": [
            "Theek hai, bolna rok diya.",
            "Ruk gaya hoon. Agla command bataiye.",
            "Ji, bolna band kar diya.",
        ],
        "UNKNOWN": [
            "Mujhe pura samajh nahi aaya. Aap stock, billing ya customer payment ke baare mein pooch sakte ho.",
        ],
        "OFFLINE": [
            "Server se connection nahi hai.",
        ],
        "SERVER_ERROR": [
            "Data check nahi ho paya. Dobara try karu?",
        ],
        "GREETING": [
            "Hello! Batao, kya kaam hai?",
            "Namaste! Main MAX hoon. Batao aaj kya kaam hai?",
            "Namaskar! Shop ka kya kaam karna hai?",
        ],
        "HOW_ARE_YOU": [
            "Main badhiya hoon. Shop ka kaam batao.",
            "Main bilkul theek hoon! Aap bataiye aaj kya karna hai?",
        ],
        "BOT_STATUS": [
            "Main ready hoon. Shop inventory, billing aur appliances handle karne ke liye ready.",
            "Main online hoon aur sare systems active hain.",
        ],
        "HELP": [
            "Aap mujhse stock pooch sakte ho (jaise 'Maggi kitni hai'), rate pooch sakte ho, customer ka hisaab, ya 'Is week ki strategy bana' bol sakte ho.",
        ],
    }

    @classmethod
    def get(cls, key: str, **kwargs) -> str:
        """Fetch a template by key and format with provided parameters."""
        options = cls.TEMPLATES.get(key, ["Ji."])
        template = random.choice(options)
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    @classmethod
    def format_stock_response(cls, product_name: str, stock: float, unit: str = "packet", is_low: bool = False) -> str:
        stk_str = str(int(stock)) if stock % 1 == 0 else f"{stock:.1f}"
        msg = f"{product_name} ke {stk_str} {unit} baki hain."
        if is_low:
            msg += " Dhyaan rahe, stock kam ho raha hai!"
        return msg

    @classmethod
    def format_price_response(cls, product_name: str, price: float, unit: str = "packet") -> str:
        return f"{product_name} ka rate ₹{price:.2f} per {unit} hai."

    @classmethod
    def format_balance_response(cls, customer_name: str, balance: float) -> str:
        if balance > 0:
            return f"{customer_name} ka ₹{balance:.2f} baki hai."
        else:
            return f"{customer_name} ka koi baki nahi hai, hisaab clear hai."

    @classmethod
    def format_today_sales(cls, total_bills: int, total_revenue: float) -> str:
        if total_bills == 0:
            return "Aaj abhi tak koi bill generate nahi hua hai."
        return f"Aaj {total_bills} bills se total ₹{total_revenue:,.2f} ki sale hui hai."

    @classmethod
    def format_relay_response(cls, device_name: str, state: str) -> str:
        action_word = "on kar di" if state == "on" else "band kar diya"
        return f"Done. {device_name.capitalize()} {action_word}."
