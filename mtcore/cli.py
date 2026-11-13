"""mt — 自研综合工具箱 CLI 入口分发。

设计：一个入口 + 模块化子命令，子命令懒加载——
只有被点名的子命令模块才会被 import，加新模块不拖慢、不影响已有模块。
纯 Python 标准库，无第三方依赖。
"""

import importlib
import sys

# 子命令注册表：名称 -> (模块路径, 一句话说明)
# 新增模块时只在这里加一行，模块文件放 mtcore/modules/ 下。
COMMANDS = {
    "health": ("mtcore.modules.health", "统一健康检查与自愈（FreeLLMAPI 自愈；PerkRadar/n8n 探活）"),
}


def _usage() -> str:
    lines = ["用法: mt <子命令> [参数]", "", "子命令:"]
    for name, (_mod, desc) in sorted(COMMANDS.items()):
        lines.append(f"  {name:<10} {desc}")
    lines.append("")
    lines.append("每个子命令的口径与判定标准见 README.md")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0
    name = argv[0]
    if name not in COMMANDS:
        print(f"mt: 未知子命令 '{name}'\n", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    module = importlib.import_module(COMMANDS[name][0])
    return int(module.run(argv[1:]))
