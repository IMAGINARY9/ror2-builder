import os
import sys

# ensure project root is on sys.path so ror2tools can be imported
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root not in sys.path:
    sys.path.insert(0, root)
