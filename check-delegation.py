#!/usr/bin/env python3
"""Show how much work this machine hands off to assistants vs does in the main session.

Higher "delegated" is the goal: the expensive model plans and decides, the cheap
models do the grinding.

Reads only the local Claude logs in ~/.claude/projects. It never reads prompts, file
contents, paths, or branch names, and prints only aggregate numbers.

    python3 check-delegation.py            # last 30 days
    python3 check-delegation.py --days 7   # last week
    python3 check-delegation.py --days 0   # everything
"""

import argparse
import collections
import datetime as dt
import glob
import json
import os

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def collect(days):
    cutoff = None
    if days:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    main, delegated = collections.Counter(), collections.Counter()
    output = {"main": collections.Counter(), "delegated": collections.Counter()}
    sessions, files = set(), 0

    pattern = os.path.expanduser("~/.claude/projects/**/*.jsonl")
    for path in glob.glob(pattern, recursive=True):
        files += 1
        try:
            handle = open(path, errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") != "assistant":
                    continue
                if cutoff:
                    stamp = record.get("timestamp")
                    if not stamp:
                        continue
                    try:
                        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=dt.timezone.utc)
                    if when < cutoff:
                        continue

                message = record.get("message") or {}
                usage = message.get("usage") or {}
                tokens = sum(usage.get(field, 0) for field in TOKEN_FIELDS)
                if not tokens:
                    continue

                model = message.get("model", "unknown")
                side = "delegated" if record.get("isSidechain") else "main"
                bucket = delegated if side == "delegated" else main
                bucket[model] += tokens
                output[side][model] += usage.get("output_tokens", 0)
                if record.get("sessionId"):
                    sessions.add(record["sessionId"])

    return main, delegated, output, sessions, files


def show_models(label, counter):
    total = sum(counter.values())
    if not total:
        return
    print(f"\n{label}")
    for model, tokens in counter.most_common(6):
        print(f"  {model:<34}{100 * tokens / total:>6.1f}%")


def expensive_share(counter):
    """Share of these tokens running on an Opus- or Fable-tier model."""
    total = sum(counter.values())
    if not total:
        return 0.0
    pricey = sum(n for model, n in counter.items() if "opus" in model or "fable" in model)
    return 100 * pricey / total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="0 for all history")
    args = parser.parse_args()

    main_tokens, delegated_tokens, output, sessions, files = collect(args.days)
    total = sum(main_tokens.values()) + sum(delegated_tokens.values())
    out_total = sum(output["main"].values()) + sum(output["delegated"].values())

    window = f"last {args.days} days" if args.days else "all history"
    print(f"\nDelegation check ({window})")

    if not total:
        print(f"\nNo activity found in {files} transcripts. Try --days 0.\n")
        return

    print(f"{len(sessions)} sessions across {files} transcripts")

    print("\nTHE TWO NUMBERS THAT MATTER\n")
    if out_total:
        share = 100 * sum(output["delegated"].values()) / out_total
        print(f"  Work done by assistants          {share:>5.0f}%   (want: up)")
    print(f"  Delegated work on Opus/Fable     {expensive_share(delegated_tokens):>5.0f}%"
          f"   (want: near zero)")

    print("\nRaw volume, for reference")
    for label, counter in (("Main session", main_tokens), ("Delegated", delegated_tokens)):
        tokens = sum(counter.values())
        print(f"  {label:<14}{tokens / 1e6:>9,.0f} Mtok{100 * tokens / total:>7.0f}%")

    show_models("Main session runs on:", main_tokens)
    show_models("Delegated work runs on:", delegated_tokens)

    print(
        "\nThe first number uses output tokens, the closest proxy for work actually\n"
        "performed. Raw volume below is ~95% cached reads, which mostly tracks how\n"
        "long a session ran rather than where the work went.\n"
    )


if __name__ == "__main__":
    main()
