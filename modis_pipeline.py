"""
Единая точка входа MODIS Pipeline.
Использование: python modis_pipeline.py <команда> [флаги]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli.main import main

if __name__ == "__main__":
    main()
