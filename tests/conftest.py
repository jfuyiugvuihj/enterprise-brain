"""conftest: 共享 fixtures"""
import pytest
import os
import sys

# 确保项目根在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
