"""Real-API diagnostic: does the configured model accept our json_schema call?

Isolates the GenericVisionProvider -> OpenAI boundary. No OCR, no grid, no
Docker, no desktop: a synthetic screenshot goes straight to the model so the
ONLY thing under test is the chat.completions call with response_format=
json_schema strict. Prints the ProviderResponse (never the API key).
"""
import asyncio
import os
import sys

from adaptivecua.env import load_dotenv

load_dotenv()
print("OPENAI_API_KEY present:", bool(os.environ.get("OPENAI_API_KEY")))
model = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.4-mini"
print("model:", model)

from PIL import Image, ImageDraw  # noqa: E402
from adaptivecua.providers.vision.imaging import encode  # noqa: E402
from adaptivecua.providers.vision.provider import GenericVisionProvider  # noqa: E402
from adaptivecua.core.history import History  # noqa: E402

# synthetic 400x240 screenshot with one labelled button
img = Image.new("RGB", (400, 240), (245, 245, 245))
d = ImageDraw.Draw(img)
d.rectangle([140, 100, 260, 150], fill=(40, 120, 220))
d.text((165, 118), "Open Edge", fill=(255, 255, 255))
shot = encode(img)

import openai  # noqa: E402

client = openai.OpenAI()
provider = GenericVisionProvider(
    client, model=model, display_size=(400, 240),
    use_marks=False, use_grid=False, zoom=False,
)

h = History()
h.add_user("Click the Open Edge button")
resp = asyncio.run(provider.next_actions(shot, h))

print("\n=== ProviderResponse ===")
print("actions       :", resp.actions)
print("done          :", resp.done)
print("flagged_risky :", resp.model_flagged_risky)
print("assistant_text:", repr(resp.assistant_text))
