"""reprotrace —— 把一次生成结果写成可重跑的档案。

设计原则：
1. **跑不出来等于没发生**。所以档案要包含跑起来所需的一切。
2. **诚实标注不可控的部分**。模型权重会变、服务端会改，
   这些本来就不可能完全复现，与其假装能做到，不如标出来。
3. **只记录，不重跑**。这个工具不发起任何模型调用。

仅依赖 Python 标准库。

用法:
    python reprotrace.py --help
    python reprotrace.py --capture run.json --out archive.json
    python reprotrace.py --capture run.json --out archive.json --verify archive.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ("prompt", "model", "params")
OPTIONAL_FIELDS = ("inputs", "output", "seed", "system", "tools",
                   "response_format", "request_id")


def capture(payload: dict) -> dict:
    """把一次调用的现场收成一份档案。"""
    missing = [f for f in REQUIRED_FIELDS
               if f not in payload or payload.get(f) is None]
    if missing:
        raise ValueError(f"档案缺少必需字段：{'、'.join(missing)}")

    # 环境快照
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }

    # 输入指纹：只存哈希，不存原文，方便比对
    inputs = payload.get("inputs")
    fingerprint = None
    if inputs is not None:
        blob = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        fingerprint = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # 输出指纹
    output = payload.get("output")
    out_fingerprint = None
    if output is not None:
        out_fingerprint = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    # 不可控因素：明确列出来
    uncontrollable = [
        "服务端模型权重可能已更新（同一模型名不同时间行为可能不同）",
        "服务端采样实现与超参数可能已调整",
        "网络与服务端负载会影响延迟，但不直接影响输出内容",
    ]
    if payload.get("seed") is None:
        uncontrollable.append("未记录随机种子：即使参数相同也无法保证逐字复现")

    return {
        "schema": "reprotrace/1",
        "prompt": payload.get("prompt"),
        "system": payload.get("system"),
        "model": payload.get("model"),
        "params": payload.get("params"),
        "inputs": inputs,
        "inputs_sha256": fingerprint,
        "output": output,
        "output_sha256": out_fingerprint,
        "seed": payload.get("seed"),
        "tools": payload.get("tools"),
        "response_format": payload.get("response_format"),
        "request_id": payload.get("request_id"),
        "environment": env,
        "uncontrollable": uncontrollable,
        "reproducibility": assess(payload, fingerprint),
    }


def assess(payload: dict, fingerprint: str | None) -> dict:
    """评估这次调用的可复现程度。"""
    factors: list[str] = []
    level = "high"

    if payload.get("seed") is None:
        factors.append("没有随机种子")
        level = "low"
    if payload.get("model") is None:
        factors.append("没有记录模型版本")
        level = "low"
    if not payload.get("params"):
        factors.append("没有记录采样参数")
        level = "low" if level != "low" else level
    if fingerprint is None:
        factors.append("没有记录输入")
        level = "medium" if level == "high" else level

    return {
        "level": level,
        "factors": factors,
        "note": ("参数与输入齐备且固定了种子时，可以复现到「高度接近」；"
                 "但服务端权重变更始终是外部因素。"),
    }


# ---------------------------------------------------------------------------
# 核对
# ---------------------------------------------------------------------------

def verify(archive: dict, current: dict) -> dict:
    """拿新一次调用与档案核对。"""
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "match": ok, "detail": detail})

    add("提示词一致", archive.get("prompt") == current.get("prompt"),
        "完全相同" if archive.get("prompt") == current.get("prompt")
        else "有差异")

    add("模型一致", archive.get("model") == current.get("model"),
        f"档案 {archive.get('model')} / 本次 {current.get('model')}")

    add("参数一致", archive.get("params") == current.get("params"),
        "完全相同" if archive.get("params") == current.get("params")
        else "有差异")

    add("输入一致", archive.get("inputs_sha256") == current.get("inputs_sha256"),
        f"档案 {str(archive.get('inputs_sha256'))[:12]}… / "
        f"本次 {str(current.get('inputs_sha256'))[:12]}…")

    if archive.get("output_sha256") and current.get("output_sha256"):
        add("输出一致", archive["output_sha256"] == current["output_sha256"],
            "完全相同" if archive["output_sha256"] == current["output_sha256"]
            else "内容不同（可能是采样随机性，也可能是行为变化）")

    matched = sum(1 for c in checks if c["match"])
    return {
        "checks": checks,
        "matched": matched,
        "total": len(checks),
        "all_match": matched == len(checks),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render_archive(arc: dict) -> str:
    out: list[str] = []
    out.append("生成结果档案")
    out.append("=" * 60)
    out.append(f"模型 {arc.get('model')}")
    out.append(f"参数 {json.dumps(arc.get('params'), ensure_ascii=False)}")
    if arc.get("seed") is not None:
        out.append(f"种子 {arc.get('seed')}")
    else:
        out.append("种子 未记录")
    out.append(f"输入指纹 {str(arc.get('inputs_sha256'))[:16] or '未记录'}")
    out.append(f"输出指纹 {str(arc.get('output_sha256'))[:16] or '未记录'}")
    out.append(f"记录于 {arc.get('environment', {}).get('recorded_at')}")
    out.append("")

    r = arc.get("reproducibility", {})
    out.append(f"可复现程度：{r.get('level', 'unknown')}")
    if r.get("factors"):
        out.append("  影响因素：")
        for f in r["factors"]:
            out.append(f"    · {f}")
    out.append("")

    out.append("不可控因素（这个工具不假装能解决它们）：")
    for u in arc.get("uncontrollable", []):
        out.append(f"  · {u}")
    out.append("")
    out.append(f"提示词（前 200 字）：{str(arc.get('prompt'))[:200]}")
    return "\n".join(out).rstrip()


def render_verify(v: dict) -> str:
    out: list[str] = []
    out.append("复现核对")
    out.append("=" * 60)
    for c in v["checks"]:
        mark = "✓" if c["match"] else "✗"
        out.append(f"  {mark} {c['name']}：{c['detail']}")
    out.append("")
    out.append(f"一致 {v['matched']}/{v['total']}")
    if v["all_match"]:
        out.append("完全复现。")
    else:
        out.append("存在差异。差异可能来自采样随机性，也可能来自服务端行为变化——"
                   "两者无法只凭这一份档案区分。")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="reprotrace",
        description="把一次生成结果写成可重跑的档案（仅依赖标准库）",
        epilog=(
            "采集输入：\n"
            "  {\"prompt\":\"...\",\"model\":\"...\",\"params\":{\"temperature\":0},"
            "\"seed\":42,\"inputs\":{...},\"output\":{...}}\n"
            "  python reprotrace.py --capture run.json --out archive.json\n"
            "  python reprotrace.py --capture run.json --verify archive.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--capture", required=True, help="一次调用的现场 JSON")
    ap.add_argument("--out", help="档案输出路径")
    ap.add_argument("--verify", help="拿本次调用与已有档案核对")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        with open(args.capture, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"读不了现场文件：{e}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict):
        print("现场文件应该是一个 JSON 对象。", file=sys.stderr)
        return 2

    try:
        arc = capture(payload)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.verify:
        try:
            with open(args.verify, "r", encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"读不了档案：{e}", file=sys.stderr)
            return 2
        v = verify(old, arc)
        if args.json:
            print(json.dumps(v, ensure_ascii=False, indent=2))
        else:
            print(render_verify(v))
        return 0 if v["all_match"] else 1

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(arc, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"写不了档案：{e}", file=sys.stderr)
            return 2
        print(f"已写入档案 {args.out}")

    if args.json:
        print(json.dumps(arc, ensure_ascii=False, indent=2))
    else:
        print(render_archive(arc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
