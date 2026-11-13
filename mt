#!/usr/bin/env python3
"""mt — 自研综合工具箱统一入口。

用法: ./mt <子命令> [参数]，如 `mt health`。
子命令懒加载逻辑在 mtcore/cli.py；本文件只负责定位包路径。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mtcore.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
