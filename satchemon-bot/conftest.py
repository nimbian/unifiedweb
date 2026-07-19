"""Pytest bootstrap for the satchemon-bot fork.

Two jobs, both so the DB helpers can be imported and unit-tested without the
bot's full runtime:

1. Put the fork root on ``sys.path`` so ``import sqlhelper`` / ``import mydb``
   resolve here regardless of pytest's import mode.
2. Stub ``table2ascii`` — ``sqlhelper`` imports it at module load only to format
   chat tables (display, no DB), so a lightweight stub lets the module import
   with just pytest installed. ``mydb`` already defers psycopg2/yaml to first
   connect, so importing it needs no database.
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "table2ascii" not in sys.modules:
    _stub = types.ModuleType("table2ascii")
    _stub.table2ascii = lambda *args, **kwargs: ""
    _stub.PresetStyle = types.SimpleNamespace(thin_compact=None)
    sys.modules["table2ascii"] = _stub
