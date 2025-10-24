from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
resp = client.embeddings.create(model="text-embedding-3-small", input=["hello world"])
print("OK, embedding dim:", len(resp.data[0]["embedding"] if isinstance(resp.data[0], dict) else resp.data[0].embedding))