import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv()

from mpalerts.main import main

if __name__ == "__main__":
    main()
