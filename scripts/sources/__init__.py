"""比赛源注册表。

新增一个比赛源：
1. 在 sources/ 下新建模块，暴露 SOURCE / LABEL / fetch() -> list[Contest]；
2. 在下面的 SOURCES 元组里登记；
3. 重新跑一次 scripts/build.py 即可。
"""

from __future__ import annotations

from . import atcoder, codeforces

SOURCES = (atcoder, codeforces)
