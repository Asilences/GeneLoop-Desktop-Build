"""Compatibility entry: proposal/repair machinery is shared across scenes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from src.adapters.capability_proposal import *

if __name__=='__main__':main()
