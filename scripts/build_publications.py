#!/usr/bin/env python3
"""content-source/*.tsv から data/publications.yaml を生成する。

TSV形式(3列、タブ区切り、ヘッダ無し):
  1. 種別見出し(原本の節見出し文字列)
  2. 引用文字列(raw)
  3. 既存リンク(無ければ空文字列)

publications_source.tsv は凍結された原本(現行サイトからの取り込み結果)であり、
このスクリプトは一切書き換えない。今後の追加は publications_add.tsv に行ごと足す。
"""
import csv
import hashlib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE_TSV = ROOT / "content-source" / "publications_source.tsv"
ADD_TSV = ROOT / "content-source" / "publications_add.tsv"
OUT_YAML = ROOT / "data" / "publications.yaml"

TYPE_MAP = {
    "Ⅰ．論文（査読付き）": "journal",
    "Ⅱ．国際会議Proceedings": "intl_conf",
    "Ⅲ. 解説論文": "review",
    "招待講演": "invited_talk",
    "総説": "survey",
    "Ⅳ. 国内口頭発表（主要なもの，査読なし）": "domestic",
}

# 原本(publications_source.tsv)側にのみ存在する既知の誤記・重複に対する
# 手動補正。private issueとして先生への報告と合わせて運用側で承認済み。
# TSV自体は書き換えず、YAML生成の段階でのみ補正する。
MANUAL_TEXT_CORRECTIONS = {
    # 行42: "20243" は "20" + "243" のような混入で西暦4桁として認識できない誤記。
    # 単独の5桁の数字列で、前後に他の解釈の余地が無いため "2023" への置換と判断。
    42: [("20243", "2023")],
}

# 行141: 1つの箇条書きに2件の引用が連結しており、後半は行143と完全に同一の
# 文字列。後半を残すと表示上も行143と全く同じ内容が重複するため、
# 最初の引用の終端("2023年2月.")で切り、後半を削除する。
MANUAL_TRUNCATIONS = {
    141: "2023年2月.",
}

# 行163⇄165、164⇄166: 信学技報の号(No.432 / No.431)だけが違う内容同一の
# 二重掲載疑い。自動削除はせず、双方にフラグを立てて報告する。
DUPLICATE_SUSPECTED_PAIRS = {
    163: 165,
    165: 163,
    164: 166,
    166: 164,
}

DOI_URL_STRIP_RE = re.compile(r"(doi:\s*\S+)|(https?://\S+)|(10\.\d{4,9}/\S+)", re.IGNORECASE)
YEAR_RE = re.compile(r"(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)")
WAREKI_RE = re.compile(r"(令和|平成|昭和)(\d+)年")
WAREKI_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}

DOI_PATTERN_RE = re.compile(r"10\.\d{4,9}/[^\s,\"'）)]+")

REFEREED_TRUE_RE = re.compile(r"査読(有り|あり)")
REFEREED_FALSE_RE = re.compile(r"査読なし")

AWARD_KEYWORDS = ["受賞", "Award", "award", "優秀", "Recognition of merit"]
AWARD_PAREN_RE = re.compile(
    r"[（(]([^（）()]*(?:" + "|".join(re.escape(k) for k in AWARD_KEYWORDS) + r")[^（）()]*)[）)]"
)


def read_tsv(path):
    """3列TSVを読み、(line_no, section, raw, existing_link) のリストを返す。"""
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for i, cols in enumerate(reader, start=1):
            if not cols or all(c.strip() == "" for c in cols):
                continue
            cols = cols + [""] * (3 - len(cols))
            section, raw, link = cols[0], cols[1], cols[2]
            rows.append((i, section.strip(), raw, link.strip()))
    return rows


def apply_manual_corrections(source, line_no, raw):
    flags = []
    if source == "import" and line_no in MANUAL_TEXT_CORRECTIONS:
        for find, replace in MANUAL_TEXT_CORRECTIONS[line_no]:
            if find in raw:
                raw = raw.replace(find, replace)
                flags.append("manual_text_correction")
    if source == "import" and line_no in MANUAL_TRUNCATIONS:
        marker = MANUAL_TRUNCATIONS[line_no]
        idx = raw.find(marker)
        if idx != -1:
            raw = raw[: idx + len(marker)]
            flags.append("truncated_duplicate_tail")
    return raw, flags


def determine_year(raw):
    stripped = DOI_URL_STRIP_RE.sub(" ", raw)
    years = YEAR_RE.findall(stripped)
    if years:
        return int(years[-1]), None
    wareki = WAREKI_RE.findall(stripped)
    if wareki:
        era, num = wareki[-1]
        return WAREKI_BASE[era] + int(num), "year_from_wareki"
    return None, "year_unresolved"


def determine_refereed(raw):
    if REFEREED_FALSE_RE.search(raw):
        return False
    if REFEREED_TRUE_RE.search(raw):
        return True
    return None


def extract_awards(raw):
    awards = []
    for m in AWARD_PAREN_RE.finditer(raw):
        awards.append(m.group(1).strip())
    if not awards:
        for kw in AWARD_KEYWORDS:
            idx = raw.find(kw)
            if idx == -1:
                continue
            # 括弧に入っていない場合は、直前の句読点(全角読点・カンマ・句点・
            # ピリオド+空白)から該当語の終端までを拾う
            boundaries = [
                raw.rfind("、", 0, idx),
                raw.rfind(",", 0, idx),
                raw.rfind("。", 0, idx),
                raw.rfind(". ", 0, idx),
            ]
            start = max(boundaries)
            start = start + 2 if raw[start : start + 2] == ". " else (start + 1 if start != -1 else 0)
            end = idx + len(kw)
            if raw[end : end + 1] == "。":
                end += 1
            snippet = raw[start:end].strip()
            if snippet:
                awards.append(snippet)
            break
    return awards


def extract_doi(raw):
    m = DOI_PATTERN_RE.search(raw)
    if not m:
        return None
    return m.group(0).rstrip(".")


def build_links(raw, existing_link, doi):
    """TSV3列目からリンクを作る。

    行45・行50では既存リンク欄に空白区切りで2つのURLが入っている
    (例: "https://doi.org/... https://dl.acm.org/doi/abs/...")。
    どちらも実在する正規のURLであり、片方を選ぶ理由が無いため両方とも
    existing として残す(順序は原本の記載順)。
    """
    links = []
    seen_urls = set()
    for url in existing_link.split():
        if url not in seen_urls:
            links.append({"url": url, "origin": "existing"})
            seen_urls.add(url)
    if doi:
        derived_url = f"https://doi.org/{doi}"
        if derived_url not in seen_urls:
            links.append({"url": derived_url, "origin": "derived"})
            seen_urls.add(derived_url)
    return links


def make_id(entry_type, year, source, line_no, raw):
    digest = hashlib.sha256(f"{source}:{line_no}:{raw}".encode("utf-8")).hexdigest()
    year_part = str(year) if year is not None else "unknown"
    return f"{entry_type}-{year_part}-{digest[:6]}"


def build_entries(rows, source):
    entries = []
    for line_no, section, raw_orig, existing_link in rows:
        raw, correction_flags = apply_manual_corrections(source, line_no, raw_orig)
        entry_type = TYPE_MAP.get(section)
        if entry_type is None:
            print(
                f"ERROR: 未知の種別見出し '{section}' (source={source}, line={line_no})",
                file=sys.stderr,
            )
            sys.exit(1)

        year, year_flag = determine_year(raw)
        doi = extract_doi(raw)
        refereed = determine_refereed(raw)
        awards = extract_awards(raw)
        links = build_links(raw, existing_link, doi)

        flags = list(correction_flags)
        if year_flag:
            flags.append(year_flag)
        if source == "import" and line_no in DUPLICATE_SUSPECTED_PAIRS:
            flags.append(f"duplicate_suspected:{DUPLICATE_SUSPECTED_PAIRS[line_no]}")
        if len(existing_link.split()) > 1:
            flags.append("multiple_existing_links")

        entry = {
            "id": make_id(entry_type, year, source, line_no, raw),
            "source": source,
            "source_line": line_no,
            "type": entry_type,
            "year": year,
            "raw": raw,
            "doi": doi,
            "refereed": refereed,
            "awards": awards,
            "links": links,
            "flags": flags,
        }
        entries.append(entry)
    return entries


class OrderedDumper(yaml.SafeDumper):
    pass


def _represent_dict(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


OrderedDumper.add_representer(dict, _represent_dict)

FIELD_ORDER = [
    "id",
    "source",
    "source_line",
    "type",
    "year",
    "raw",
    "doi",
    "refereed",
    "awards",
    "links",
    "flags",
]


def ordered_entry(entry):
    return {k: entry[k] for k in FIELD_ORDER}


def load_previous_suggested_links(path):
    """前回出力のYAMLから、id別の suggested リンクを取り出す。

    このスクリプトはTSVだけから毎回全件を作り直すため、そのままでは
    enrich_publication_links.py が付け足した suggested リンクを
    上書きで消してしまう。id(TSVの行内容から決まる安定なキー)を頼りに
    既存の suggested リンクだけを引き継ぐことで、その事故を防ぐ。
    """
    if not path.exists():
        return {}
    try:
        previous = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    result = {}
    for e in previous.get("entries", []):
        suggested = [l for l in e.get("links", []) if l.get("origin") == "suggested"]
        if suggested:
            result[e["id"]] = suggested
    return result


def main():
    import_rows = read_tsv(SOURCE_TSV)
    add_rows = read_tsv(ADD_TSV)
    previous_suggested = load_previous_suggested_links(OUT_YAML)

    entries = build_entries(import_rows, "import") + build_entries(add_rows, "add")

    for e in entries:
        for link in previous_suggested.get(e["id"], []):
            if link["url"] not in {l["url"] for l in e["links"]}:
                e["links"].append(link)

    ordered = [ordered_entry(e) for e in entries]

    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    with OUT_YAML.open("w", encoding="utf-8") as f:
        yaml.dump(
            {"entries": ordered},
            f,
            Dumper=OrderedDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=1000,
        )

    print(f"{len(ordered)} 件を {OUT_YAML.relative_to(ROOT)} に出力しました。")


if __name__ == "__main__":
    main()
