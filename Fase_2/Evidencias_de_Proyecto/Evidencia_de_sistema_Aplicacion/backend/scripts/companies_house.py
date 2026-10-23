#!/usr/bin/env python3
"""CLI Companies House (Reino Unido)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dossier.companies_house.cli import main

if __name__ == "__main__":
    main()
