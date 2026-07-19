import asyncio
import json
from agent.orchestrator import handle_query
from utils.tracing import generate_session_id

async def run_demo():
    print("==========================================")
    print(" ATLASCARE AGENTIC WORKFLOW DEMO")
    print("==========================================\n")
    
    session_id = generate_session_id()
    customer_id = "CUST-001"
    
    journeys = [
        ("J1 (Tracking)", "Where is my order ORD-J1?"),
        ("J2 (Compound)", "Cancel my order ORD-J2 item 1, refund me 85000, and update my address to New Address."),
        ("J3 (Escalation)", "Cancel order ORD-J3 and refund me 42000.")
    ]
    
    for name, query in journeys:
        print(f"--- Running {name} ---")
        print(f"Query: {query}")
        print("Agent thinking...\n")
        
        response = await handle_query(query, session_id, customer_id)
        
        print("Agent Response:")
        print(f"{response.response}\n")
        
        print("Structured Trace:")
        trace = response.trace.model_dump()
        print(json.dumps(trace, indent=2))
        print("\n" + "="*42 + "\n")
        await asyncio.sleep(5)  # Add delay to avoid 429 Too Many Requests

if __name__ == "__main__":
    asyncio.run(run_demo())
