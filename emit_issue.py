#!/usr/bin/env python3
"""Emit one issue's 24 topics to Firestore issues/{date}, so the public
per-topic share pages (/t/<date>-<category>-<n>) can render them server-side.

Reads the committed index.html and extracts D.<cat>[offset] (offset 0 = the
current week). Run automatically each Monday by emit-issue.yml; also runnable
by hand with WEEK_OFFSET set, to backfill a past week.

Env:  GMAIL_SA_JSON  (service account; Firestore access)
Opt:  WEEK_OFFSET    (default 0; 1 = last week, 2 = the week before, ...)
      INDEX_PATH     (default index.html)
"""
from __future__ import annotations
import os, json, subprocess, tempfile, datetime

CATS = ["leadership", "markets", "psychology", "technology", "geopolitics", "philosophy"]
PROJECT_ID = "pi-briefing-38ddc"


def monday_for_offset(offset: int) -> str:
    d = datetime.date.today()
    monday = d - datetime.timedelta(days=d.weekday())          # this week's Monday
    monday = monday - datetime.timedelta(days=7 * offset)      # step back N weeks
    return monday.isoformat()


def extract(index_path: str, offset: int) -> dict:
    """Pull D.<cat>[offset] out of index.html by evaluating the D.* statements
    in Node (they are JS object literals, not JSON)."""
    src = open(index_path, encoding="utf-8").read()
    stmts = []
    for cat in CATS:
        k = "D.%s=[" % cat
        i = src.find(k)
        if i < 0:
            continue
        j = src.index("\n];", i) + 3
        stmts.append(src[i:j])
    js = ("var D={};\n" + "\n".join(stmts) +
          "\nvar o={};Object.keys(D).forEach(function(k){o[k]=(D[k][" + str(offset) + "]||[])});" +
          "console.log(JSON.stringify(o));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        tmp = f.name
    try:
        out = subprocess.check_output(["node", tmp], text=True)
    finally:
        os.unlink(tmp)
    return json.loads(out)


def main():
    offset = int(os.environ.get("WEEK_OFFSET", "0") or "0")
    index_path = os.environ.get("INDEX_PATH", "index.html")
    date = monday_for_offset(offset)
    topics = extract(index_path, offset)
    total = sum(len(v) for v in topics.values())
    if total == 0:
        print("No topics found at offset %d — nothing emitted." % offset)
        return
    week = datetime.date.fromisoformat(date).isocalendar()[1]

    raw = os.environ.get("GMAIL_SA_JSON")
    if not raw:
        raise RuntimeError("GMAIL_SA_JSON env var not set")
    from google.oauth2 import service_account
    from google.cloud import firestore
    creds = service_account.Credentials.from_service_account_info(json.loads(raw))
    db = firestore.Client(project=PROJECT_ID, credentials=creds)
    db.collection("issues").document(date).set({
        "date": date,
        "week": week,
        "topics": topics,
        "updatedAt": datetime.datetime.utcnow().isoformat() + "Z",
    })
    print("Wrote issues/%s — %d topics across %d categories (offset %d)." %
          (date, total, len(topics), offset))


if __name__ == "__main__":
    main()
