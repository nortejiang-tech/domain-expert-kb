#!/usr/bin/env python3
"""
专利检索 —— 输出直接可粘进 _kb/landscape/PRIOR_ART.md 的条目格式。

用法:
    python3 patent_search.py '"four wheel independent steering"'
    python3 patent_search.py '"steer-by-wire" redundancy' --limit 15
    python3 patent_search.py '"四轮独立转向"' --limit 10
    python3 patent_search.py 'assignee:"吉林大学" 转向' --count-only

说明:
  - 后端为 Google Patents 公开检索接口，**公司内网不可达**，需在可联网环境使用
  - 检索式支持 Google Patents 语法：引号短语、assignee:、inventor:、before:/after: 等
  - 中文检索式同样有效，且中文专利是最相关的现有技术，别只用英文检索

⚠️ 本脚本产出的是**初筛线索，不是检索报告**。
   未做同族合并、未做权利要求比对、未做法律状态核验。
   任何 FTO 判断或专利申请决策，必须由专利代理人/专业检索机构出具正式报告。
   脚本刻意不输出"风险等级"字段 —— 没有依据的风险判断比留空更危险。
"""
import argparse, json, sys, time, urllib.error, urllib.parse, urllib.request


def query_gp(q, limit=10, retries=3):
    """Google Patents 对连续请求会返回 503 限流，退避重试即可恢复。
    连续多个检索式时建议在调用之间自行留几秒间隔，别把重试当常态。"""
    url = "https://patents.google.com/xhr/query?" + urllib.parse.urlencode({"url": "q=" + q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(retries):
        try:
            raw = urllib.request.urlopen(req, timeout=40).read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  [限流 {e.code}，{wait}s 后重试 {attempt+2}/{retries}]", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    d = json.loads(raw)["results"]
    items = []
    for c in d.get("cluster", []):
        for it in c.get("result", [])[:limit]:
            p = it["patent"]
            items.append({
                "no": p.get("publication_number", "?"),
                "title": p.get("title", "").strip(),
                "assignee": p.get("assignee", "?"),
                "inventor": p.get("inventor", ""),
                "prio": p.get("priority_date", "?"),
                "pub": p.get("publication_date", "?"),
                "snippet": (p.get("snippet", "")
                            .replace("<b>", "").replace("</b>", "")
                            .replace("&hellip;", "…").replace("&#39;", "'").strip()),
            })
    return d.get("total_num_results", 0), items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--count-only", action="store_true",
                    help="只看命中总量。用于判断某方向专利有多挤——密度高说明新颖性空间小")
    a = ap.parse_args()

    try:
        total, items = query_gp(a.query, a.limit)
    except urllib.error.HTTPError as e:
        if e.code in (429, 503):
            sys.exit(f"HTTP {e.code}：重试后仍被限流。稍等几分钟再跑，"
                     f"或降低连续检索的频率（多个检索式之间隔几秒）。")
        sys.exit(f"HTTP {e.code}。若在公司内网，Google Patents 不可达属预期——"
                 f"改用国家知识产权局检索系统，见 _kb/landscape/国内检索入口.md")
    except Exception as e:
        sys.exit(f"检索失败: {e}\n若在公司内网，改走 _kb/landscape/国内检索入口.md")

    print(f"\n检索式: `{a.query}`")
    print(f"**命中总数: {total}**  （本次输出 {len(items)} 条）\n")

    if total > 3000:
        print("> ⚠️ 命中量很大，说明该方向专利密度高、新颖性空间可能较窄。"
              "建议收窄检索式，并把创新点往更具体的组合上聚焦。\n")

    if a.count_only:
        return

    for it in items:
        who = it["assignee"] if it["assignee"] != "?" else f'（发明人 {it["inventor"]}）'
        print(f'### {it["no"]}　{it["title"]}')
        print(f'申请人：{who} ｜ 优先权日 {it["prio"]} ｜ 公开日 {it["pub"]}')
        print(f'https://patents.google.com/patent/{it["no"]}/en\n')
        if it["snippet"]:
            print(f'{it["snippet"]}\n')
        print('**与我方方案的关系**：相似点 <待填> ／ **区别点** <待填>')
        print('**风险等级**：<留空，待代理人填 —— 需逐条比对权利要求才能判断>\n')

    if any(it["no"].startswith("CN") for it in items):
        print("\n> 💡 结果中含 CN 中国专利：这些在公司内网可通过国家知识产权局检索系统"
              "直接查阅全文，是对标层里少数能在公司环境自主核验的内容。")


if __name__ == "__main__":
    main()
