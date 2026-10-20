import os
import sys
from pathlib import Path

# Must run before the app imports settings.
os.environ["RATE_LIMIT_ANALYZE"] = "3 per minute"
os.environ["RATE_LIMIT_ASK"] = "3 per minute"
os.environ["RATE_LIMIT_DEFAULT"] = "1000 per minute"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"] = "https://example.invalid"
os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"] = "test"
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://example.invalid"
os.environ["AZURE_OPENAI_KEY"] = "test"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
