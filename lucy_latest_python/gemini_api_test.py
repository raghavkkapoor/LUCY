import json
import re
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from lucy_logging import log, LogColors

KEY = "YOUR_GOOGLE_STUDIO_API_KEY_HERE"

def run_custom_gem():
    # -------------------------------------------------------------------------
    # 1. INITIALIZE CLIENT
    # -------------------------------------------------------------------------
    # The client automatically picks up the GEMINI_API_KEY environment variable.
    # Alternatively, pass it explicitly: client = genai.Client(api_key="...")
    client = genai.Client(api_key=KEY)

    # -------------------------------------------------------------------------
    # 2. DEFINE GEM BEHAVIOR (SYSTEM INSTRUCTION & CONFIG)
    # -------------------------------------------------------------------------
    # System Instructions act as the core personality and rules of your Custom Gem.
    gem_system_instruction = """
    You are 'DevPulse', an expert Senior Software Engineer assistant.
    Your rules:
    1. Provide concise, modern Python 3.12 code blocks.
    2. Focus strictly on performance, error handling, and typing.
    3. Keep text explanations to 2-3 sentences max unless asked for deep dives.
    """

    # Model settings (system prompt, temperature, safety, top_p)
    gem_config = types.GenerateContentConfig(
        system_instruction=gem_system_instruction,
        temperature=0.3,  # Lower value = more factual and precise
        top_p=0.95,
    )

    # -------------------------------------------------------------------------
    # 3. CREATE CHAT SESSION
    # -------------------------------------------------------------------------
    # gemini-2.5-flash is ideal for fast, lightweight assistant tasks.
    # Using client.chats.create retains ongoing message context automatically.

#     NOTE: THIS IS THE OLD API THAT DOES NOT STORE CHAT HISTORY ON GOOGLE'S SERVERS, WE HAVE TO MANAGE IT MANUALLY. PRIVACY ISSUE.
# NOTE: THE INTERACTIONS API IS THE NEW API THAT STATEFUL AND RESERVES ALL CHAT HISTORY ON GOOGLE'S SERVERS BUT LOWERS COMPLEXITY AND MANAGEMENT AND COSTS.
    gem_chat = client.chats.create(
        model="gemini-3.6-flash",
        config=gem_config
    )

    print("Custom Gem 'DevPulse' Initialized! (Type 'quit' or 'exit' to stop)\n")

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

            # Print output directly
            print(f"\nDevPulse:\n{response.text}\n")
            print("-" * 50)

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