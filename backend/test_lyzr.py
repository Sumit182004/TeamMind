
import os
from pathlib import Path

from dotenv import load_dotenv
from lyzr import Studio

load_dotenv(Path(__file__).resolve().parent / ".env")

api_key = os.getenv("LYZR_API_KEY")

if not api_key:
    raise RuntimeError("LYZR_API_KEY is missing from backend/.env")

studio = Studio(api_key=api_key)

agent = studio.create_agent(
    name="TeamMind Researcher",
    provider="gpt-4o",
    role="Decision Researcher",
    goal="Identify decision options and important trade-offs.",
    instructions=(
        "You are the Researcher agent in TeamMind. "
        "Analyze the user's decision, identify the main options, "
        "list potential benefits and risks, and clearly label "
        "assumptions. Do not invent sources or claim research "
        "was performed when it was not."
    ),
    temperature=0.2,
)

print("Agent created successfully.")

response = agent.run(
    "Should a small development team build its own authentication "
    "system or use an established authentication provider? "
    "Compare the main trade-offs."
)

print("\nAgent response:")
print(response.response)
