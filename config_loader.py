"""Single-point environment loader."""
from dotenv import load_dotenv

def load_env():
    load_dotenv(override=True)

