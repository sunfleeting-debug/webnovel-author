#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webnovel-author · 项目检查器

零依赖（只用 Python 标准库），用于长篇写作的日常体检：
  1. 项目结构是否齐全（总表、伏笔账本、时间线、上下文卡）
  2. 伏笔是否过期（当前章 > 计划回收章 + 5）
  3. 正文章号是否连续、有无缺号或重复
  4. 逐章记录是否超字数上限（软限 1500，硬上限 3000）

用法：
    python 检查.py <项目根目录> [--current N]

示例：
    python 检查.py "F:/MyProject/NovelWriting/万相书" --current 60
"""

import argparse
import os
import re
import sys

SOFT_LIMIT = 1500
HARD_LIMIT = 3000
OVERDUE_TOLERANCE = 5
INACTIVE_CHAPTERS = 15

REQUIRED = [
    ("追踪/总表.md", "唯一真源"),
    ("追踪/伏笔账本.md", "伏笔账本"),
    ("追踪/时间线/作者真相.md", "作者真相时间线"),
    ("追踪/时间线/读者已知.md", "读者已知时间线"),
    ("追踪/上下文.md", "定长上下文卡"),
]


def read(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        return "__ERR__%s" % e


def count_chars(text):
    """中文语境下的字数：去掉空白后计数。"""
    return len(re.sub(r"\s", "", text))


def check_structure(root):
    print("=" * 60)
    print("[1] 项目结构")
    missing = []
    for rel, desc in REQUIRED:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            print("    OK   %-28s (%s)" % (rel, desc))
        else:
            print("    缺失 %-28s (%s)" % (rel, desc))
            missing.append(rel)
    if missing:
        print("    -> 缺 %d 项。总表缺失时，所有派生文件都无法重渲染。" % len(missing))
    return missing


def parse_table_row(line):
    """解析 markdown 表格的一行为单元格列表。"""
    line = line.strip()
    if not line.startswith("|"):
        return None
    cells = [c.strip() for c in line.strip("|").split("|")]
    return cells


def check_foreshadowing(root, current):
    print("=" * 60)
    print("[2] 伏笔扫描（当前第 %s 章，容差 %d 章）" % (current, OVERDUE_TOLERANCE))
    path = os.path.join(root, "追踪", "伏笔账本.md")
    text = read(path)
    if text is None:
        print("    跳过：未找到 追踪/伏笔账本.md")
        return
    if text.startswith("__ERR__"):
        print("    跳过：无法读取（%s）" % text[7:])
        return

    overdue, pending = [], 0
    for line in text.splitlines():
        cells = parse_table_row(line)
        if not cells or len(cells) < 7:
            continue
        no, content, _type, planted, planned, actual, status = cells[:7]
        if no.upper() in ("编号", "---", ""):
            continue
        if not re.fullmatch(r"F?\d+", no):
            continue
        if "已回收" in status:
            continue
        pending += 1
        m = re.search(r"\d+", planned)
        if not m or current is None:
            continue
        planned_n = int(m.group())
        if current > planned_n + OVERDUE_TOLERANCE:
            overdue.append((no, content, planted, planned_n, current - planned_n))

    print("    未回收伏笔：%d 条" % pending)
    if overdue:
        print("    !! 过期 %d 条（必须处理：提前回收 / 显式延后 / 就地烂尾）：" % len(overdue))
        for no, content, planted, planned_n, over in overdue:
            print("       %-6s 埋于第%s章，计划第%d章回收，已超期 %d 章 —— %s"
                  % (no, planted, planned_n, over, content[:30]))
    else:
        print("    无过期伏笔。")


def check_chapters(root):
    print("=" * 60)
    print("[3] 章号连续性（扫描 正文/ 与 正文全.md）")
    nums = {}
    pat = re.compile(r"^#\s*第\s*([0-9]+)\s*章", re.M)

    prose_dir = os.path.join(root, "正文")
    if os.path.isdir(prose_dir):
        for name in sorted(os.listdir(prose_dir)):
            if not name.endswith(".md"):
                continue
            text = read(os.path.join(prose_dir, name))
            if text:
                for m in pat.finditer(text):
                    nums.setdefault(int(m.group(1)), []).append(name)
    # 正文目录之外，也兼容根目录下名字含"正文"的合并稿（如「第一卷-正文全.md」）
    candidates = [os.path.join(root, "正文全.md")]
    try:
        for name in sorted(os.listdir(root)):
            if name.endswith(".md") and "正文" in name and name != "正文全.md":
                candidates.append(os.path.join(root, name))
    except OSError:
        pass
    for combined in candidates:
        if os.path.exists(combined):
            text = read(combined)
            if text:
                for m in pat.finditer(text):
                    nums.setdefault(int(m.group(1)), []).append(os.path.basename(combined))

    if not nums:
        print("    跳过：未在任何正文文件中找到 `# 第N章` 标题。")
        return None

    keys = sorted(nums)
    gaps = [i for i in range(keys[0], keys[-1] + 1) if i not in nums]

    # 区分「合并稿」与「分段稿」：覆盖 90% 以上章号的文件视为合并稿，不参与重复判定
    total = len(keys)
    file_nums = {}
    for n, files in nums.items():
        for f in files:
            file_nums.setdefault(f, set()).add(n)
    master = {f for f, s in file_nums.items() if len(s) >= max(1, int(total * 0.9))}

    dup = []
    for n in keys:
        parts = [f for f in nums[n] if f not in master]
        if len(parts) > 1:
            dup.append((n, parts))

    print("    章号范围：第 %d — 第 %d 章，共 %d 章" % (keys[0], keys[-1], len(keys)))
    if master:
        print("    合并稿：%s（覆盖大部分章号，属预期）" % "、".join(sorted(master)))
    if gaps:
        print("    !! 缺号：%s" % ", ".join("第%d章" % g for g in gaps[:20]))
    else:
        print("    无缺号。")
    if dup:
        print("    !! 真重复（同一章号出现在多份分段稿中）：")
        for n, parts in dup[:20]:
            print("       第%d章 —— %s" % (n, "、".join(parts)))
    else:
        print("    无重复。")
    return keys[-1]


def check_records(root):
    print("=" * 60)
    print("[4] 逐章记录字数（软限 %d，硬上限 %d）" % (SOFT_LIMIT, HARD_LIMIT))
    rec_dir = os.path.join(root, "追踪", "逐章记录")
    if not os.path.isdir(rec_dir):
        print("    跳过：未找到 追踪/逐章记录/")
        return
    bad, warn = [], 0
    for name in sorted(os.listdir(rec_dir)):
        if not name.endswith(".md"):
            continue
        text = read(os.path.join(rec_dir, name))
        if not text:
            continue
        n = count_chars(text)
        if n > HARD_LIMIT:
            bad.append((name, n))
        elif n > SOFT_LIMIT:
            warn += 1
    print("    超标文件：%d（软限预警：%d）" % (len(bad), warn))
    for name, n in bad[:20]:
        print("       !! %s —— %d 字，超出硬上限 %d，必须压缩" % (name, n, HARD_LIMIT))
    if not bad:
        print("    全部在硬上限内。")


def check_context_card(root):
    print("=" * 60)
    print("[5] 上下文卡大小（定长纪律：硬上限 12KB）")
    p = os.path.join(root, "追踪", "上下文.md")
    text = read(p)
    if text is None:
        print("    跳过：未找到 追踪/上下文.md")
        return
    size = len(text.encode("utf-8")) / 1024.0
    print("    当前 %.1f KB" % size)
    if size > 12:
        print("    !! 超过 12KB，长篇上下文会膨胀，请压缩到 7 栏各留核心信息。")


def main():
    ap = argparse.ArgumentParser(description="webnovel-author 项目检查器")
    ap.add_argument("root", help="项目根目录")
    ap.add_argument("--current", type=int, default=None, help="当前最新章号（用于伏笔过期判定）")
    args = ap.parse_args()

    root = args.root
    if not os.path.isdir(root):
        print("错误：不是目录 —— %s" % root)
        sys.exit(1)

    print("项目：%s" % root)
    if args.current is None:
        print("（未指定 --current，伏笔过期判定将跳过；可用它给出当前最新章号）")
    print()

    check_structure(root)
    check_foreshadowing(root, args.current)
    latest = check_chapters(root)
    check_records(root)
    check_context_card(root)

    if args.current is None and latest is not None:
        print()
        print("提示：可用 --current %d 重跑，以获得伏笔过期判定。" % latest)


if __name__ == "__main__":
    main()
