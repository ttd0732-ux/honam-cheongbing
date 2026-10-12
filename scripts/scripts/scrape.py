#!/usr/bin/env python3
"""호남신학대학교 미니스트리카페 청빙게시판(ministry_009) 공고 수집 스크립트.
사용법: python3 scrape.py [페이지수]  -> dataset.json 생성
보드 인코딩: EUC-KR
"""
import re, json, time, sys, urllib.request, html as h

BASE = "https://ministry.htus.ac.kr"

# 사용법: python3 scrape.py [페이지수] | python3 scrape.py --since YYYY-MM-DD | python3 scrape.py --lastdays 30
ARGS = sys.argv[1:]
SINCE = None
PAGES = 5
if ARGS and ARGS[0] == '--since':
    SINCE = ARGS[1]
elif ARGS and ARGS[0] == '--lastdays':
    import datetime as _dt
    SINCE = (_dt.date.today() - _dt.timedelta(days=int(ARGS[1]))).isoformat()
elif ARGS:
    PAGES = int(ARGS[0])

def get(url, retries=4):
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=45).read().decode('euc-kr', errors='replace')
        except Exception as e:
            last = e
            time.sleep(2)
    raise last

KEYMAP = {"주소": "교회주소", "모집분야": "모집부서", "서류제출": "제출서류",
          "이메일주소": "제출처", "사례": "사례비", "문의": "전화번호",
          "청빙직분": "모집직분", "사역분야": "모집부서", "모집부분": "모집부서",
          "연락처": "전화번호"}

def parse_star_body(body):
    lines = [l.strip() for l in body.split('\n')]
    clean = [l for l in lines if l]
    fields = {}
    i = 0
    while i < len(clean):
        if clean[i] == '*':
            if i + 1 < len(clean):
                key = KEYMAP.get(clean[i + 1], clean[i + 1])
                k = i + 2
                if k < len(clean) and clean[k] == ':':
                    k += 1
                vals = []
                while k < len(clean) and clean[k] != '*':
                    vals.append(clean[k]); k += 1
                v = ' '.join(vals).strip()
                if key and v and len(key) <= 12:
                    fields[key] = v
                i = k
            else:
                i += 1
        else:
            i += 1
    return fields

def parse_colon_body(body):
    fields = {}
    for line in body.split('\n'):
        m = re.match(r'^\s*([가-힣a-zA-Z()·/\s]{2,12}?)\s*[:：]\s*(.+)$', line.strip())
        if m:
            k = KEYMAP.get(m.group(1).strip(), m.group(1).strip())
            v = m.group(2).strip()
            if k not in fields and 0 < len(v) < 300:
                fields[k] = v
    return fields

def church_from_title(title):
    m = re.match(r'^\s*(?:[\[\(][^\]\)]*[\]\)]\s*)?(.+?교회)', title)
    return m.group(1).strip() if m else None

def loose_field(body, keys):
    for k in keys:
        m = re.search(rf'{k}\s*[:：\-]\s*([^\n]{{1,80}})', body)
        if m:
            v = m.group(1).strip()
            if v and len(v) < 80:
                return v
    return None

REGIONS = ["서울","경기","인천","강원","충북","충남","대전","세종","전북","전남",
           "광주","경북","경남","대구","울산","부산","제주"]
REGION_ALIASES = {"경기도":"경기","전라북도":"전북","전라남도":"전남","경상북도":"경북",
                  "경상남도":"경남","충청북도":"충북","충청남도":"충남","강원도":"강원",
                  "제주도":"제주"}

def extract_facets(p, today):
    text = p['title'] + ' ' + ' '.join(p['fields'].values()) + ' ' + p.get('body', '')
    f = {}
    region = None
    for rk, rv in REGION_ALIASES.items():
        if rk in text:
            region = rv; break
    if not region:
        for r in REGIONS:
            if r in text:
                region = r; break
    f['region'] = region or '기타'
    positions = []
    for kw in ['부목사','전임전도사','준전임','교육전도사','심방전도사','파트타임',
               '찬양사역자','반주자','전도사','목사']:
        if kw in text:
            positions.append(kw)
    if '전도사' in positions and any(x != '전도사' and '전도사' in x for x in positions):
        positions.remove('전도사')
    f['positions'] = positions[:3] if positions else ['기타']
    if '준전임' in text: f['etype'] = '준전임'
    elif '파트' in text: f['etype'] = '파트타임'
    elif '전임' in text: f['etype'] = '전임'
    else: f['etype'] = '기타'
    depts = []
    for kw in ['아동부','유초등부','초등부','중고등부','청소년부','청년부','대학부',
               '교구','심방','찬양','예배','행정','교육부','유년부','유치부']:
        if kw in text:
            depts.append(kw)
    f['depts'] = depts[:3]
    deadline = p['fields'].get('제출기한', '')
    f['deadline_raw'] = deadline
    f['open'] = True
    if deadline:
        if any(x in deadline for x in ['청빙시','채용시','마감시','수시','충원시']):
            f['open'] = True
        else:
            m = re.search(r'(\d{2,4})[년.\-/\s]+(\d{1,2})[월.\-/\s]+(\d{1,2})', deadline)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 100: y += 2000
                f['open'] = (y, mo, d) >= today
                f['deadline'] = f"{y}-{mo:02d}-{d:02d}"
    return f

def main():
    import datetime
    today = datetime.date.today()
    today_t = (today.year, today.month, today.day)
    posts = []
    page = 0
    while True:
        page += 1
        html = get(f"{BASE}/board/board.php?b_id=ministry_009&page={page}&m=")
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
        page_dates = []
        for r in rows:
            m = re.search(r"<a href='(/board/board\.php\?b_id=ministry_009[^']*w_id=(\d+)[^']*)'>([^<]+)</a>", r)
            if not m:
                continue
            href, wid, title = m.group(1), m.group(2), m.group(3).strip()
            tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)
            author = re.sub(r'<[^>]+>', '', tds[2]).strip() if len(tds) > 2 else ''
            date = re.sub(r'<[^>]+>', '', tds[3]).strip() if len(tds) > 3 else ''
            views = re.sub(r'<[^>]+>', '', tds[5]).strip() if len(tds) > 5 else ''
            is_notice = '공지' in (tds[0] if tds else '')
            if re.match(r'\d{4}-\d{2}-\d{2}', date):
                page_dates.append(date)
            if SINCE and not is_notice and re.match(r'\d{4}-\d{2}-\d{2}', date) and date < SINCE:
                continue
            posts.append({"wid": wid, "title": title, "author": author,
                          "date": date, "views": views, "notice": is_notice,
                          "url": BASE + href.replace('&amp;', '&')})
        time.sleep(0.5)
        if SINCE:
            if page_dates and min(page_dates) < SINCE:
                break
            if page > 40:  # 안전장치
                break
        elif page >= PAGES:
            break
    print(f"list done: {len(posts)} posts (since={SINCE or f'{PAGES} pages'})", flush=True)

    for i, p in enumerate(posts):
        if p["notice"]:
            p["fields"] = {}; p["body"] = ""
            continue
        try:
            html = get(p["url"])
            idx = html.find('board_view')
            seg = html[idx:idx + 15000]
            m = re.search(r'조회수</th>.*?</tr>(.*)', seg, re.S)
            rest = m.group(1) if m else seg
            rest = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', rest, flags=re.S | re.I)
            cut = re.search(r'다음글|관련 사이트 바로가기', rest)
            if cut:
                rest = rest[:cut.start()]
            txt = re.sub(r'<br[^>]*>', '\n', rest)
            txt = re.sub(r'</(p|div|tr)>', '\n', txt)
            txt = re.sub(r'<[^>]+>', '', txt)
            txt = h.unescape(txt)
            txt = re.sub(r'[ \t\xa0]+', ' ', txt)
            txt = re.sub(r'\n\s*\n+', '\n', txt).strip()
            fields = parse_colon_body(txt)
            if '*' in txt:
                for k, v in parse_star_body(txt).items():
                    fields[k] = v
            body = txt
            if not fields.get("교회명"):
                c = church_from_title(p["title"])
                if c:
                    fields["교회명"] = c
            if not fields.get("담임목사"):
                m2 = re.search(r'담임목사?\s*[:：]?\s*([가-힣]{2,4})\s*목사', body)
                if m2:
                    fields["담임목사"] = m2.group(1) + ' 목사'
            if not fields.get("교회주소"):
                v = loose_field(body, ['위치', '주소', '교회주소'])
                if v:
                    fields["교회주소"] = v
            if not fields.get("제출기한"):
                v = loose_field(body, ['제출기한', '마감', '접수기한'])
                if v:
                    fields["제출기한"] = v
            if not fields.get("사례비"):
                v = loose_field(body, ['사례비', '사례'])
                if v and len(v) < 100:
                    fields["사례비"] = v
            if not fields.get("제출처"):
                m2 = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', body)
                if m2:
                    fields["제출처"] = m2.group(0)
            if not fields.get("모집부서"):
                v = loose_field(body, ['모집부서', '모집분야', '담당사역', '담당'])
                if v and len(v) < 60:
                    fields["모집부서"] = v
            p["fields"] = fields
            p["body"] = body[:1500]
        except Exception as e:
            p["fields"] = {}; p["body"] = ""; p["error"] = str(e)[:80]
        if (i + 1) % 10 == 0:
            print(f"{i+1}/{len(posts)} details done", flush=True)
        time.sleep(0.3)

    for p in posts:
        p["facets"] = {} if p["notice"] else extract_facets(p, today_t)

    out = []
    for p in posts:
        if p["notice"]:
            continue
        f = p["fields"]; fc = p["facets"]
        out.append({
            "id": p["wid"], "title": p["title"],
            "church": f.get("교회명", ""), "pastor": f.get("담임목사", ""),
            "addr": f.get("교회주소", ""), "presbytery": f.get("노회명", ""),
            "dept": f.get("모집부서", ""), "headcount": f.get("모집인원", ""),
            "qual": f.get("지원자격", ""), "docs": f.get("제출서류", ""),
            "deadline": fc.get("deadline", f.get("제출기한", "")),
            "deadline_raw": f.get("제출기한", ""),
            "pay": f.get("사례비", ""), "contact": f.get("제출처", ""),
            "phone": f.get("전화번호", ""), "etc": f.get("기타사항", ""),
            "date": p["date"], "views": p["views"], "url": p["url"],
            "region": fc.get("region", "기타"),
            "positions": fc.get("positions", ["기타"]),
            "etype": fc.get("etype", "기타"), "depts": fc.get("depts", []),
            "open": fc.get("open", True),
        })
    json.dump(out, open('dataset.json', 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump({"date": today.isoformat(), "count": len(out)},
              open('dataset_meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"DONE: {len(out)} posts, date={today.isoformat()}", flush=True)

if __name__ == "__main__":
    main()
