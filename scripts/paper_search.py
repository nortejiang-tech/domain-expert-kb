#!/usr/bin/env python3
"""
文献检索 —— 输出直接可粘进 _kb/landscape/PAPERS.md 的条目格式。

用法:
    python3 paper_search.py "four wheel independent steering"
    python3 paper_search.py "4WIS control" --source arxiv --limit 10
    python3 paper_search.py "steer by wire" --source crossref
    python3 paper_search.py "..." --ids 2412.02953,2403.12487     # 按 arXiv ID 取完整摘要

后端:
    arxiv     预印本，摘要完整，无需 key            [默认]
    crossref  正式期刊/会议（含中文期刊），题录为主  [默认]
    s2        Semantic Scholar，含引用数，无 key 常 429（可选）

设计要点:
  - 摘要**完整输出不截断**，因为知识库要在无外网环境离线使用，链接在那边打不开
  - 输出即 PAPERS.md 的条目格式，减少二次加工
  - 任一后端失败不影响其他后端，末尾统一汇报
"""
import argparse, json, sys, textwrap, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

UA = "kb-builder/1.0 (academic research)"
ERRORS = []


def _get(url, timeout=40, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()


def arxiv(query=None, ids=None, limit=8):
    """arXiv API。注意必须用 https，http 会 301 且 urllib 不自动跟随到结果。"""
    if ids:
        p = {"id_list": ",".join(ids), "max_results": str(len(ids) + 5)}
    else:
        p = {"search_query": query, "max_results": str(limit), "sortBy": "relevance"}
    root = ET.fromstring(_get("https://export.arxiv.org/api/query?" + urllib.parse.urlencode(p)))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        aid = e.find("a:id", ns).text
        out.append({
            "title": " ".join(e.find("a:title", ns).text.split()),
            "url": aid,
            "id": aid.rsplit("/", 1)[-1],
            "date": e.find("a:published", ns).text[:10],
            "authors": [a.find("a:name", ns).text for a in e.findall("a:author", ns)],
            "abstract": " ".join(e.find("a:summary", ns).text.split()),
            "venue": "arXiv (预印本)",
        })
    return out


def crossref(query, limit=8):
    """正式发表文献。覆盖中文期刊，是 arXiv 的重要补充。"""
    p = {"query.bibliographic": query, "rows": str(limit),
         "select": "title,DOI,issued,container-title,author,abstract,URL"}
    d = json.loads(_get("https://api.crossref.org/works?" + urllib.parse.urlencode(p)))
    out = []
    for i in d["message"]["items"]:
        parts = (i.get("issued", {}).get("date-parts") or [[None]])[0]
        au = [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in i.get("author", [])]
        abst = i.get("abstract", "")
        if abst:  # Crossref 摘要常含 JATS 标签
            import re
            abst = re.sub(r"<[^>]+>", "", abst).strip()
        out.append({
            "title": (i.get("title") or ["?"])[0],
            "url": i.get("URL") or f'https://doi.org/{i.get("DOI")}',
            "id": i.get("DOI", "?"),
            "date": str(parts[0]) if parts and parts[0] else "?",
            "authors": au,
            "abstract": abst,
            "venue": (i.get("container-title") or ["?"])[0],
        })
    return out


def s2(query, limit=8):
    """Semantic Scholar。无 key 时限流严重，仅作补充。"""
    p = {"query": query, "limit": str(limit),
         "fields": "title,year,venue,citationCount,abstract,externalIds,url"}
    d = json.loads(_get("https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(p)))
    if "data" not in d:
        raise RuntimeError(d.get("message", "no data"))
    out = []
    for i in d["data"]:
        out.append({
            "title": i.get("title", "?"),
            "url": i.get("url", ""),
            "id": (i.get("externalIds") or {}).get("DOI", i.get("paperId", "?")),
            "date": str(i.get("year", "?")),
            "authors": [],
            "abstract": i.get("abstract") or "",
            "venue": f'{i.get("venue","?")} · 被引 {i.get("citationCount","?")}',
        })
    return out


def render(items, src):
    print(f"\n{'='*70}\n## 来源: {src}   命中 {len(items)} 条\n{'='*70}\n")
    for it in items:
        au = ", ".join(it["authors"][:4]) + (" 等" if len(it["authors"]) > 4 else "")
        print(f'### {it["title"]}')
        print(f'`{it["id"]}` · {it["date"]}' + (f' · {au}' if au else ''))
        print(f'{it["venue"]}')
        print(f'{it["url"]}\n')
        print('**与本项目关联**：<待填 —— 不填这条，日后没人知道当初为什么收录它>\n')
        if it["abstract"]:
            print("> " + it["abstract"].replace("\n", " ") + "\n")
        else:
            print("> （该来源未提供摘要，需打开原文补录——离线环境下这条会不可用）\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default=None)
    ap.add_argument("--source", default="arxiv,crossref")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--ids", default=None, help="arXiv ID 列表，逗号分隔，用于补全完整摘要")
    a = ap.parse_args()

    if a.ids:
        try:
            render(arxiv(ids=a.ids.split(",")), "arXiv (按 ID)")
        except Exception as e:
            ERRORS.append(f"arxiv/ids: {e}")
    else:
        if not a.query:
            ap.error("需要 query 或 --ids")
        for src in [s.strip() for s in a.source.split(",")]:
            try:
                fn = {"arxiv": arxiv, "crossref": crossref, "s2": s2}[src]
                render(fn(a.query, limit=a.limit), src)
            except KeyError:
                ERRORS.append(f"{src}: 未知后端")
            except urllib.error.HTTPError as e:
                ERRORS.append(f"{src}: HTTP {e.code}" + ("（限流，稍后重试或申请 key）" if e.code == 429 else ""))
            except Exception as e:
                ERRORS.append(f"{src}: {e}")

    if ERRORS:
        print("\n" + "!"*70, file=sys.stderr)
        for e in ERRORS:
            print("检索失败:", e, file=sys.stderr)
        print("以上后端均为境外站点。若在公司内网，属预期失败——改走 "
              "_kb/landscape/国内检索入口.md 的国内途径。", file=sys.stderr)
        print("!"*70, file=sys.stderr)


if __name__ == "__main__":
    main()
