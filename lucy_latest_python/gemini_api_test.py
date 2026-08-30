import json
import re
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from lucy_logging import log, LogColors

def run_custom_gem():
    # -------------------------------------------------------------------------
    # 1. INITIALIZE CLIENT
    # -------------------------------------------------------------------------
    # The client automatically picks up the GEMINI_API_KEY environment variable.
    # Alternatively, pass it explicitly: client = genai.Client(api_key="...")
    client = genai.Client(api_key="KEY")

    # -------------------------------------------------------------------------
    # 2. DEFINE GEM BEHAVIOR (SYSTEM INSTRUCTION & CONFIG)
    # -------------------------------------------------------------------------
    # System Instructions act as the core personality and rules of your Custom Gem.

    # Model settings (system prompt, temperature, safety, top_p)
    gem_config = types.GenerateContentConfig(
        system_instruction="SYSTEM_INSTRUCTIONS",
        temperature=1.0,  # Lower value = more factual and precise. SET TO DEFAULT RECOMMENDED BY GOOGLE (1.0)
        top_p=0.95, 
    )

    # -------------------------------------------------------------------------
    # 3. CREATE CHAT SESSION
    # -------------------------------------------------------------------------
    # Using client.chats.create retains ongoing message context automatically.

#     NOTE: THIS IS THE OLD API THAT DOES NOT STORE CHAT HISTORY ON GOOGLE'S SERVERS, WE HAVE TO MANAGE IT MANUALLY. PRIVACY ISSUE.
# NOTE: THE INTERACTIONS API IS THE NEW API THAT STATEFUL AND RESERVES ALL CHAT HISTORY ON GOOGLE'S SERVERS BUT LOWERS COMPLEXITY AND MANAGEMENT AND COSTS.
    gem_chat = client.chats.create(
        model="gemini-3.6-flash",
        config=gem_config
    )

    print("Lucy Initialized! (Type 'quit' or 'exit' to stop)\n")

    # usage trackers across the session
    session_requests = 0
    session_tokens = 0

    # -------------------------------------------------------------------------
    # 4. INTERACTION LOOP
    # -------------------------------------------------------------------------
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ["quit", "exit"]:
                print("Ending session.")
                break
            
            # Send prompt to the chat session
            # Context and system instructions are preserved across calls
            response = gem_chat.send_message(user_input)


            # Track running totals
            session_requests += 1
            turn_tokens = response.usage_metadata.total_token_count if response.usage_metadata else 0
            session_tokens += turn_tokens

            print(f"\nLUCY:\n{response.text}\n")
            print(f"[METRICS] This Turn: {turn_tokens} tokens | Session Total: {session_tokens} tokens ({session_requests}/1500 daily requests)")
            print("-" * 50)


            # Print output directly
            log(f"\nLUCY:\n{response.text}\n", LogColors.CYAN)


            # --- USAGE LOGGING ---
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                total_tokens = response.usage_metadata.total_token_count
                
                print(f"[USAGE LOG] Prompt: {input_tokens} tokens | Response: {output_tokens} tokens | Total Turn: {total_tokens} tokens")
            # ---------------------

        except KeyboardInterrupt:
            print("\nSession interrupted.")
            break
        except ClientError as clientError:
         # Find the JSON substring inside the error message
         json_match = re.search(r'(\{.*\})', str(clientError), re.DOTALL)
         
         if json_match:
                  # Replace single quotes with double quotes for valid JSON parsing
                  raw_json = json_match.group(1).replace("'", '"')
                  data = json.loads(raw_json)
                  details = data.get('error', {}).get('details', [])
                  error_reason = next((d.get('reason') for d in details if 'reason' in d), None)

                  if error_reason == "API_KEY_INVALID":
                      log("fuck off, you don't have a VALID API KEY!", LogColors.RED)
                      break
                      
         raise
    
        except Exception as e:
            print(f"\nUnexpected Error: {e}\n")

if __name__ == "__main__":
    run_custom_gem()