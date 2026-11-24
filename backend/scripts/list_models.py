import os
import httpx
from dotenv import load_dotenv

load_dotenv()
res = httpx.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {os.environ.get("GROQ_API_KEY")}'})
models = res.json().get('data', [])
print([m['id'] for m in models])
