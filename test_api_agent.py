"""Test script to reproduce the API agent issue."""
import io
import sys
from contextlib import redirect_stdout

# Add parent directory to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.langchain_agent import handle_input

def test_query(query):
    print(f"\n========== Testing: '{query}' ==========")
    output_buffer = io.StringIO()

    try:
        with redirect_stdout(output_buffer):
            handle_input(query)

        output_text = output_buffer.getvalue()
        print(f"[TEST] Captured {len(output_text)} chars")
        print(f"[TEST] Output:\n{output_text[:500]}")
        return output_text
    except Exception as e:
        print(f"[TEST] Exception: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Test the same queries that were problematic
    test_query("hi")
    test_query("what can you do")
    test_query("what are you capable of")
