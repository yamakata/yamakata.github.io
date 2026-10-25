#!/usr/bin/env python3
"""外部の公式サイトへのリンクが無い業績について、Crossrefへ照会し候補リンクを探す。

手元で実行し、結果を data/publications.yaml と
docs/業績リンク確認一覧.md にコミットする運用とする(CIには組み込まない)。
外部APIの結果は日によって変わるため、ビルドの再現性を壊さないための方針。

origin: suggested として追加したリンクは、テンプレート側では描画しない
(layouts/publications/list.html は existing / derived のみを表示する)。
先生の確認を経てから origin: existing に格上げする運用を想定している。
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = ROOT / "data" / "publications.yaml"
REPORT_PATH = ROOT / "docs" / "業績リンク確認一覧.md"

# Crossrefのpolite poolを使うための連絡先メールアドレス。
# 実行者本人のメールアドレスを、実行前にここへ書き換えること。
# 未設定のまま実行するとエラーで止まる(推測で埋めない)。
CONTACT_EMAIL = "TODO(確認): 連絡先メールアドレスを入れる"

CROSSREF_API = "https://api.crossref.org/works"
REQUEST_INTERVAL_SEC = 1.5  # 1件ずつ順に照会し、間隔を空ける(並列で叩かない)

# 一致度のしきい値。0.0-1.0のtitle類似度(正規化Jaccard, 後述)で判定する。
# 0.72は、和文・英文混在かつ表記ゆれ(引用符・全角半角)の多いこのデータセットで
# 手動サンプルから「タイトルが実質同一と言える下限」として設定した経験値。
# これを下回るものは suggested にせず「未確認」として扱う。
MATCH_THRESHOLD = 0.72


def require_contact_email():
    if CONTACT_EMAIL.startswith("TODO"):
        print(
            "ERROR: CONTACT_EMAIL が未設定です。スクリプト冒頭の CONTACT_EMAIL に"
            "実行者本人の連絡先メールアドレスを設定してから実行してください。",
            file=sys.stderr,
        )
        sys.exit(1)


TITLE_QUOTE_RE = re.compile(r'["“”‘’`]')


def guess_title(raw):
    """rawから引用符で囲まれた部分(タイトルらしき箇所)を抜き出す。

    引用符が4系統(ASCII / 曲がり“” / 曲がり’‘ / TeX風``'')あるため、
    まとめて除去してから最初の引用区間をタイトル候補として使う。
    見つからない場合はraw全体を使う(Crossrefの検索クエリとしてはそれでも機能する)。
    """
    m = re.search(r'["“].*?["”]', raw)
    if m:
        return TITLE_QUOTE_RE.sub("", m.group(0))
    m = re.search(r"[`‘].*?['’]", raw)
    if m:
        return TITLE_QUOTE_RE.sub("", m.group(0))
    return raw


def normalize_for_match(s):
    s = TITLE_QUOTE_RE.sub("", s)
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)
    return s.lower().strip()


def title_similarity(a, b):
    """正規化後の単語集合によるJaccard類似度(0.0-1.0)。"""
    wa = set(normalize_for_match(a).split())
    wb = set(normalize_for_match(b).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def query_crossref(title):
    params = urllib.parse.urlencode({"query.bibliographic": title, "rows": 3})
    url = f"{CROSSREF_API}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"yamakata-lab-publications-enrich/1.0 (mailto:{CONTACT_EMAIL})"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def best_candidate(raw):
    title = guess_title(raw)
    try:
        data = query_crossref(title)
    except Exception as exc:  # ネットワーク不調・該当なしも含め、異常として扱わない
        return None, 0.0, f"error: {exc}"

    items = data.get("message", {}).get("items", [])
    best = None
    best_score = 0.0
    for item in items:
        cand_title = " ".join(item.get("title", []))
        if not cand_title:
            continue
        score = title_similarity(title, cand_title)
        if score > best_score:
            best_score = score
            best = item
    if best is None:
        return None, 0.0, None
    doi = best.get("DOI")
    url = f"https://doi.org/{doi}" if doi else best.get("URL")
    return url, best_score, None


def main():
    require_contact_email()

    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    entries = data["entries"]

    targets = [e for e in entries if not e["links"]]
    print(f"照会対象(既存・derivedリンクが無いもの): {len(targets)} 件")

    report_rows = []
    hit = 0
    above = 0
    below = 0
    none_found = 0
    per_type_total = {}
    per_type_hit = {}

    for i, entry in enumerate(targets, start=1):
        per_type_total[entry["type"]] = per_type_total.get(entry["type"], 0) + 1
        url, score, error = best_candidate(entry["raw"])
        status = ""
        if error:
            status = "該当なし(照会エラー)"
            none_found += 1
        elif url is None:
            status = "該当なし"
            none_found += 1
        elif score >= MATCH_THRESHOLD:
            status = "採用(suggested)"
            hit += 1
            above += 1
            per_type_hit[entry["type"]] = per_type_hit.get(entry["type"], 0) + 1
            entry["links"].append({"url": url, "origin": "suggested"})
        else:
            status = "しきい値未満(未確認)"
            hit += 1
            below += 1

        report_rows.append(
            {
                "source_line": entry["source_line"],
                "raw": entry["raw"],
                "url": url or "",
                "score": f"{score:.2f}" if url else "-",
                "status": status,
            }
        )
        print(f"[{i}/{len(targets)}] line={entry['source_line']} score={score:.2f} status={status}")
        time.sleep(REQUEST_INTERVAL_SEC)

    YAML_PATH.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    lines = [
        "# 業績リンク確認一覧",
        "",
        f"Crossref (`{CROSSREF_API}`) への機械照会結果。原本の文字列・提案URL・一致度を並べています。",
        f"一致度は正規化タイトルのJaccard類似度(0.0-1.0)。しきい値 {MATCH_THRESHOLD} 以上のみ",
        "`origin: suggested` として `data/publications.yaml` に追加済みです(サイトのHTMLには出しません)。",
        "",
        f"- 照会件数: {len(targets)}",
        f"- ヒット件数(何らかの候補が見つかった): {hit}",
        f"- しきい値以上: {above}",
        f"- しきい値未満: {below}",
        f"- 該当なし: {none_found}",
        "",
        "| 行番号 | 原本の文字列 | 提案URL | 一致度 | 照会先 | 判定 |",
        "|---|---|---|---|---|---|",
    ]
    for row in report_rows:
        raw_escaped = row["raw"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row['source_line']} | {raw_escaped} | {row['url']} | {row['score']} | Crossref | {row['status']} |"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"照会件数: {len(targets)}")
    print(f"ヒット件数: {hit} / しきい値以上: {above} / しきい値未満: {below} / 該当なし: {none_found}")
    print("種別ごとのヒット率:")
    for t, total in per_type_total.items():
        h = per_type_hit.get(t, 0)
        print(f"  {t}: {h}/{total}")
    print(f"レポートを {REPORT_PATH.relative_to(ROOT)} に出力しました。")


if __name__ == "__main__":
    main()
