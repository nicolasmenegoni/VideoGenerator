from pathlib import Path
import sys

# Garante que os testes importem o app.py da raiz mesmo quando o pytest muda o sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
