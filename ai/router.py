import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Check API key presence
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
IS_MOCK = not bool(GEMINI_API_KEY)

_client = None
if not IS_MOCK:
    try:
        # Initialize Google GenAI Client
        _client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.warning(f"Failed to initialize google-genai client: {e}. Falling back to dry-run mock mode.")
        IS_MOCK = True
else:
    logger.warning("GEMINI_API_KEY env variable not found. Running in dry-run mock mode.")

def get_ai_client():
    return _client

def is_mock_enabled() -> bool:
    return IS_MOCK

def generate_text(prompt: str, model_type: str = "flash", system_instruction: str = None) -> str:
    """
    Generate text using Gemini models with system instructions.
    
    :param prompt: User prompt string.
    :param model_type: 'flash' for speed/cost (gemini-2.5-flash), 'pro' for deep reasoning (gemini-2.5-pro).
    :param system_instruction: Optional system instructions for the LLM.
    """
    model_name = "gemini-2.5-flash" if model_type == "flash" else "gemini-2.5-pro"
    
    if IS_MOCK:
        logger.info(f"[AI ROUTER MOCK] Request to {model_name} with system_instruction='{system_instruction}'")
        prompt_lower = prompt.lower()
        # Mock responses representing typical outputs for testing validation
        if "summary" in prompt_lower or "diagnostics" in prompt_lower:
            return (
                "**MOCK PERFORMANCE SUMMARY**\n\n"
                "- **Overall Health**: The account's overall CPA is $45.62. Broad match search campaigns are performing well, but budget pacing indicates overspending.\n"
                "- **Wasted Spend Alert**: 5 search terms have exceeded the budget threshold with 0 conversions (e.g. 'free widgets' spent $167.44). Recommend adding negative keywords immediately.\n"
                "- **Underperforming Ad Group**: Ad Group 'Gizmos Search' has a CPA of $102.56, which is 2.2x higher than the account average CPA. Recommend reviewing copy or bids.\n"
                "- **Cost Anomaly**: An unexpected 16.5x cost spike was detected on 2026-07-15 ($3177.43 actual vs $961.55 expected), driven by the prospecting campaign."
            )
        elif "headlines" in prompt_lower or "description" in prompt_lower or "rsa" in prompt_lower:
            return """
HEADLINES:
1. Buy Premium Widgets Online
2. Top Acme Widgets On Sale
3. Affordable Widgets Store
4. Get Free Shipping Today
5. Best Widgets for Sale
6. Quality Widgets Coupon
7. Order Acme Widgets
8. Durable Widgets Online
DESCRIPTIONS:
1. Shop our collection of high-quality widgets. Enjoy affordable prices and free shipping.
2. Get the best deals on premium widgets today. Use our exclusive coupons for discounts.
3. Order online from the official Acme Widgets store and experience top-tier product quality.
"""
        return f"[Mock response for prompt length {len(prompt)}]"

    try:
        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction
            
        response = _client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        return response.text or ""
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}. Falling back to mock message.")
        return f"[API Error Fallback response. Original error: {e}]"
