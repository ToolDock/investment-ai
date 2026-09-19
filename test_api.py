import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "S&P500が暴落しています。長期投資家として今どうすべきか、一言で答えてください。"}
    ]
)

print(response.content[0].text)