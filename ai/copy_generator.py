import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from ai.router import generate_text, is_mock_enabled

logger = logging.getLogger(__name__)

def parse_copy(text_content: str) -> tuple[list[str], list[str]]:
    """
    Parses ad copy response text into lists of headlines and descriptions.
    """
    headlines = []
    descriptions = []
    current_section = None
    
    for line in text_content.split("\n"):
        line = line.strip()
        if not line:
            continue
            
        if "HEADLINES" in line.upper():
            current_section = "headlines"
            continue
        elif "DESCRIPTIONS" in line.upper():
            current_section = "descriptions"
            continue
            
        # Clean prefix markers (e.g. "- ", "1. ", etc.)
        if line.startswith("-"):
            val = line[1:].strip()
        elif line[0].isdigit() and (line[1] == '.' or (len(line) > 2 and line[2] == '.')):
            val = line.split(".", 1)[1].strip()
        else:
            val = line
            
        if current_section == "headlines":
            headlines.append(val)
        elif current_section == "descriptions":
            descriptions.append(val)
            
    return headlines, descriptions

def generate_rsa_copy(session: Session, account_id: str) -> dict[str, list[str]]:
    """
    Generate Google Responsive Search Ad (RSA) headlines and descriptions, grounded in
    the account's top-performing search terms and keywords. Enforces strict length limits
    (headlines <= 30 chars, descriptions <= 90 chars) via a Python self-correction loop.
    
    :param session: SQLAlchemy database session.
    :param account_id: Native account ID string.
    :return: A dict with lists of valid 'headlines' and 'descriptions'.
    """
    # 1. Fetch top converting search terms
    st_query = text("""
        SELECT e.name, SUM(m.conversions) as total_conv
        FROM metrics_daily m
        JOIN entities e ON m.entity_key = e.entity_key
        WHERE m.account_id = :account_id AND m.level = 'search_term'
        GROUP BY e.name
        HAVING SUM(m.conversions) > 0
        ORDER BY total_conv DESC
        LIMIT 5;
    """)
    st_rows = session.execute(st_query, {"account_id": account_id}).all()
    top_search_terms = [r.name for r in st_rows]

    # 2. Fetch top keywords by click-through-rate (CTR)
    kw_query = text("""
        SELECT e.name, CASE WHEN SUM(m.impressions) > 0 THEN CAST(SUM(m.clicks) AS FLOAT) / SUM(m.impressions) ELSE 0.0 END as ctr
        FROM metrics_daily m
        JOIN entities e ON m.entity_key = e.entity_key
        WHERE m.account_id = :account_id AND m.level = 'keyword'
        GROUP BY e.name
        HAVING SUM(m.impressions) > 0
        ORDER BY ctr DESC
        LIMIT 5;
    """)
    kw_rows = session.execute(kw_query, {"account_id": account_id}).all()
    top_keywords = [r.name for r in kw_rows]

    # 3. Compile prompt
    prompt = f"""
Generate Google Responsive Search Ad (RSA) ad copy variations for an account.
Ground your generation in these high-performing search terms and keywords from the account history:
Top Converting Search Terms: {", ".join(top_search_terms) if top_search_terms else "None"}
Top Click-Through Keywords: {", ".join(top_keywords) if top_keywords else "None"}

Requirements:
1. Generate up to 10 HEADLINES. Every headline MUST be strictly 30 characters or less.
2. Generate up to 4 DESCRIPTIONS. Every description MUST be strictly 90 characters or less.
3. Make them professional, compelling, and relevant to the keywords.

Respond EXACTLY in this format:
HEADLINES:
- Headline 1
- Headline 2
DESCRIPTIONS:
- Description 1
- Description 2
"""
    
    logger.info(f"Triggering copy generation for account {account_id}")
    system_instruction = "You are an expert digital copywriter specialized in search engine marketing."
    response_text = generate_text(prompt=prompt, model_type="flash", system_instruction=system_instruction)
    
    headlines, descriptions = parse_copy(response_text)
    
    # 4. Perform length validation
    invalid_h = [h for h in headlines if len(h) > 30]
    invalid_d = [d for d in descriptions if len(d) > 90]
    
    valid_h = [h for h in headlines if len(h) <= 30]
    valid_d = [d for d in descriptions if len(d) <= 90]
    
    # 5. Self-Correction Loop (only executed in live-key mode when violations occur)
    if (invalid_h or invalid_d) and not is_mock_enabled():
        logger.info(f"Violations detected in generated copy. Triggering self-correction loop.")
        correction_prompt = f"""
The following ad copies exceeded their respective character limits. Rewrite them to be shorter and strictly under the limits.

EXCEEDED HEADLINES (Must be <= 30 characters):
{chr(10).join(f"- {h} (length: {len(h)} chars)" for h in invalid_h)}

EXCEEDED DESCRIPTIONS (Must be <= 90 characters):
{chr(10).join(f"- {d} (length: {len(d)} chars)" for d in invalid_d)}

Respond in the same format:
HEADLINES:
[Shortened headlines]
DESCRIPTIONS:
[Shortened descriptions]
"""
        try:
            correction_text = generate_text(prompt=correction_prompt, model_type="flash", system_instruction=system_instruction)
            cor_h, cor_d = parse_copy(correction_text)
            # Filter and append valid ones
            valid_h.extend([h for h in cor_h if len(h) <= 30])
            valid_d.extend([d for d in cor_d if len(d) <= 90])
        except Exception as e:
            logger.error(f"Copy generator self-correction API error: {e}")

    return {
        "headlines": valid_h[:15],
        "descriptions": valid_d[:4]
    }
