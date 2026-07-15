import logging
import json
from google.genai import types
from ai.router import get_ai_client, is_mock_enabled
from ai.tools import compare_periods, top_movers, run_anomaly_scan, wasted_spend

logger = logging.getLogger(__name__)

tools_map = {
    "compare_periods": compare_periods,
    "top_movers": top_movers,
    "run_anomaly_scan": run_anomaly_scan,
    "wasted_spend": wasted_spend
}

def run_agent_query(user_query: str, account_id: str) -> str:
    """
    Executes an agentic investigation using Gemini Pro.
    Maintains a tool-use loop, executes local python queries against the database,
    and returns a fully grounded analysis report with a reasoning trace.
    
    :param user_query: The performance query from the user.
    :param account_id: Restricted account ID scope.
    """
    if is_mock_enabled():
        logger.info(f"[AI AGENT MOCK] Processing query: '{user_query}' for account {account_id}")
        trace = (
            "### Agent Reasoning Trace:\n"
            f"1. Decided to call tool: `compare_periods(account_id='{account_id}', level='campaign', start_a='2026-07-01', end_a='2026-07-07', start_b='2026-07-08', end_b='2026-07-14')`\n"
            "   - Tool returned: Campaign 'US - Prospecting - Broad Match' ROAS dropped from 3.2 to 1.4; spend rose +38%, conversions fell -12%.\n"
            f"2. Decided to call tool: `wasted_spend(account_id='{account_id}', min_cost=50.0)`\n"
            "   - Tool returned: 'free widgets' spent $167.44 and 'cheap widgets for sale' spent $120.00, both with 0 conversions.\n"
            f"3. Decided to call tool: `run_anomaly_scan(account_id='{account_id}', metric='cost')`\n"
            "   - Tool returned: Cost anomaly flagged on 2026-07-15 (Z-Score=16.52, Cost=$3,177.43 actual vs $961.55 expected).\n\n"
            "### Executive Agent Investigation Report\n\n"
            f"For Account **{account_id}**, the recent ROAS drop is primarily driven by the **US - Prospecting - Broad Match** campaign (ROAS fell from 3.2 to 1.4).\n\n"
            "**Key Findings**:\n"
            "1. **Prospecting Spend Inflation**: Campaign spend rose 38% while conversions dropped 12%.\n"
            "2. **Wasted Search Terms**: $287.44 of spend went to non-converting terms (such as *'free widgets'* and *'cheap widgets for sale'*).\n"
            "3. **Cost Anomaly**: A massive 16.5x cost anomaly was flagged on 2026-07-15 ($3,177.43 actual vs $961.55 average), suggesting an unintended budget adjustment.\n\n"
            "**Recommendations**:\n"
            "- Immediately add *'free widgets'* and *'cheap widgets'* as exact match negative keywords.\n"
            "- Audit the campaign budget and bidding changes that occurred on 2026-07-15."
        )
        return trace

    client = get_ai_client()
    system_instruction = (
        "You are an agentic ad analyst. You are given tools to query the database. "
        "Your task is to analyze user queries, determine which tools to call, inspect their outputs, "
        "reason about the cause of performance changes, and synthesize a clear, factual, "
        "and grounded report. Always state your step-by-step reasoning trace. Do not guess or make up numbers."
    )

    # Expose functions directly to Gemini. The modern SDK parses signature docstrings for parameter info.
    tools_list = [compare_periods, top_movers, run_anomaly_scan, wasted_spend]

    try:
        logger.info("Starting live agent tool-use loop with gemini-2.5-pro...")
        history = [
            types.Content(
                role="user", 
                parts=[types.Part.from_text(text=f"Account context: {account_id}. User question: {user_query}")]
            )
        ]
        
        trace_steps = []
        max_turns = 5
        
        for turn in range(max_turns):
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools_list
            )
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=history,
                config=config
            )
            
            # Save the candidate content in history
            history.append(response.candidates[0].content)
            
            # Check for requested function calls
            function_calls = response.function_calls
            if not function_calls:
                # Agent is finished reasoning and has written a text response
                final_answer = response.text or ""
                break
                
            function_responses = []
            for call in function_calls:
                func_name = call.name
                func_args = call.args
                call_id = call.id
                
                # Force account_id to the query context for security isolation
                if "account_id" in func_args:
                    func_args["account_id"] = account_id
                
                trace_steps.append(f"Called tool `{func_name}` with args {func_args}")
                logger.info(f"Agent call: {func_name} args={func_args}")
                
                if func_name in tools_map:
                    tool_func = tools_map[func_name]
                    try:
                        result = tool_func(**func_args)
                        result_str = json.dumps(result)
                    except Exception as e:
                        logger.error(f"Error executing local tool {func_name}: {e}")
                        result_str = json.dumps({"error": str(e)})
                else:
                    result_str = json.dumps({"error": f"Tool '{func_name}' is not registered."})
                    
                function_responses.append(
                    types.Part.from_function_response(
                        name=func_name,
                        response={"result": result_str},
                        id=call_id
                    )
                )
            
            # Append responses back into history
            history.append(
                types.Content(
                    role="tool",
                    parts=function_responses
                )
            )
        else:
            final_answer = "Error: Agent exceeded maximum tool execution turns without a conclusion."

        # Compile final trace details
        trace_header = "### Agent Reasoning Trace:\n"
        for idx, step in enumerate(trace_steps, start=1):
            trace_header += f"{idx}. {step}\n"
        trace_header += "\n"
        
        return trace_header + final_answer
        
    except Exception as e:
        logger.error(f"Error running agent query: {e}", exc_info=True)
        return f"Agent failed to execute: {e}"
