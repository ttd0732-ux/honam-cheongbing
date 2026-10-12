#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dataset.json(수집 결과)을 index.html의 POSTS 데이터로 변환해 매일 갱신한다.
사용법: 저장소 루트에서 python3 scripts/build.py
"""
import json, re, os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime('%Y-%m-%d')

EMPLOYMENT = {'전임': '전임(추정)', '준전임': '준전임', '파트타임': '파트타임'}


CITY_TO_REGION = {
    # 전남
    '목포시': '전남', '여수시': '전남', '순천시': '전남', '나주시': '전남',
    '광양시': '전남', '담양군': '전남', '곡성군': '전남', '구례군': '전남',
    '고흥군': '전남', '보성군': '전남', '화순군': '전남', '장흥군': '전남',
    '강진군': '전남', '해남군': '전남', '영암군': '전남', '무안군': '전남',
    '함평군': '전남', '영광군': '전남', '장성군': '전남', '완도군': '전남',
    '진도군': '전남', '신안군': '전남',
    # 전북
    '전주시': '전북', '군산시': '전북', '익산시': '전북', '정읍시': '전북',
    '남원시': '전북', '김제시': '전북', '완주군': '전북', '진안군': '전북',
    '무주군': '전북', '장수군': '전북', '임실군': '전북', '순창군': '전북',
    '고창군': '전북', '부안군': '전북',
    # 광주
    '광주시': '광주', '동구': '광주', '서구': '광주', '남구': '광주',
    '북구': '광주', '광산구': '광주',
    # 제주
    '제주시': '제주', '서귀포시': '제주',
}


def detail_region(base, addr):
    """'전남' + '순천시 삼산로 4' -> '전남 순천시'.
    지역을 못 찾았으면(기타) 주소의 시/군/구에서 도를 역추적한다."""
    city = None
    for tok in re.findall(r'[가-힣]+', addr or ''):
        if tok.endswith(('광역시', '특별시', '특별자치시', '특별자치도')):
            continue
        if tok.endswith(('시', '군', '구')) and len(tok) <= 5:
            city = tok
            break
    if (not base or base == '기타') and city:
        base = CITY_TO_REGION.get(city, '')
    if city and base and base != '기타':
        return base + ' ' + city
    return city or base or '기타'


def headcount_text(hc):
    hc = str(hc or '').strip().replace(' ', '')
    if not hc:
        return '1명'
    if hc[-1] == '명' or not hc[-1].isdigit():
        return str(hc or '').strip()
    return hc + '명'


def make_summary(p, region_d):
    head = region_d + ' ' + p['church']
    if p.get('presbytery'):
        head += '(' + p['presbytery'] + ')'
    head += '에서 ' + p['role'] + ' ' + headcount_text(p.get('headcount')) + ' 청빙.'
    parts = [head]
    if p.get('dept'):
        parts.append(p['dept'].rstrip('.') + ' 담당.')
    if p.get('qual'):
        parts.append(p['qual'].rstrip('.') + '.')
    if p.get('pay'):
        parts.append(p['pay'].rstrip('.') + '.')
    if p.get('deadline_parsed'):
        parts.append('마감 ' + p['deadline_parsed'] + '.')
    return ' '.join(parts)


def to_compact(p):
    region_d = detail_region(p.get('region', ''), p.get('addr', ''))
    depts = p.get('depts') or []
    dept = ', '.join(depts) if isinstance(depts, list) else (p.get('dept') or '')
    role = (p.get('positions') or ['목회자'])[0]
    contact = (p.get('contact') or '').strip()
    phone = (p.get('phone') or '').strip()
    if phone and phone not in contact:
        contact = (contact + ' / ' + phone).strip(' /')
    c = {
        'n': int(p['id']),
        'title': p.get('title', ''),
        'date': (p.get('date') or '')[:10],
        'views': int(p.get('views') or 0),
        'church': p.get('church', ''),
        'region': region_d,
        'role': role,
        'employment': EMPLOYMENT.get(p.get('etype', ''), ''),
        'dept': dept,
        'pay': p.get('pay', ''),
        'deadlineText': p.get('deadline_raw', ''),
        'deadline_parsed': (p.get('deadline') or '')[:10],
        'status': 'open' if p.get('open') else 'closed',
        'url': p.get('url', ''),
        'qual': p.get('qual', ''),
        'docs': p.get('docs', ''),
        'contact': contact,
        'address': p.get('addr', ''),
        'homepage': '',
        'denomination': '예장통합',
        'presbytery': p.get('presbytery', ''),
        'start': '',
    }
    c['summary'] = make_summary({**p, 'role': role, 'dept': dept,
                                 'deadline_parsed': c['deadline_parsed']}, region_d)
    return c


def replace_posts_array(html, new_json):
    marker = 'var POSTS = '
    i = html.find(marker)
    if i < 0:
        raise RuntimeError('var POSTS 를 찾지 못했습니다')
    j = i + len(marker)
    if html[j] != '[':
        raise RuntimeError('POSTS 배열 시작을 찾지 못했습니다')
    depth, in_str, esc, k = 0, False, False, j
    while k < len(html):
        ch = html[k]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    k += 1
                    break
        k += 1
    return html[:j] + new_json + html[k:]


def main():
    ds_path = os.path.join(ROOT, 'dataset.json')
    posts = json.load(open(ds_path, encoding='utf-8'))
    total = len(posts)

    # 끌어올림/재공고 묶음: 교회+직분 기준 최신 글 하나만
    best = {}
    for p in posts:
        key = (p.get('church', ''), (p.get('positions') or [''])[0])
        if key not in best or int(p['id']) > int(best[key]['id']):
            best[key] = p
    uniq = sorted(best.values(), key=lambda p: int(p['id']), reverse=True)
    dupes = total - len(uniq)

    compact = [to_compact(p) for p in uniq]
    posts_json = json.dumps(compact, ensure_ascii=False, separators=(',', ':'))

    dates = sorted((p.get('date') or '')[:10] for p in uniq if p.get('date'))
    drange = dates[0] + ' ~ ' + dates[-1] if dates else TODAY + ' ~ ' + TODAY
    note = (drange + ' 공고 <b>' + str(total) + '건</b> 정리 '
            '(끌어올림 등으로 다시 올라온 글 <b>' + str(dupes) + '건</b>은 하나로 묶음)')

    # posts.js에 데이터 분리 저장 (index.html은 가볍게 유지)
    posts_js_path = os.path.join(ROOT, 'posts.js')
    open(posts_js_path, 'w', encoding='utf-8').write('var POSTS = ' + posts_json + ';')

    html_path = os.path.join(ROOT, 'index.html')
    html = open(html_path, encoding='utf-8').read()
    html, n1 = re.subn(
        r'\d{4}-\d{2}-\d{2} ~ \d{4}-\d{2}-\d{2} 공고 <b>\d+건</b> 정리 '
        r'\(끌어올림 등으로 다시 올라온 글 <b>\d+건</b>은 하나로 묶음\)', note, html)
    html, n2 = re.subn(r'자료 업데이트 날: \d{4}-\d{2}-\d{2}',
                       '자료 업데이트 날: ' + TODAY, html)
    if n1 == 0 or n2 == 0:
        raise RuntimeError('헤더 문구 교체 실패 (n1=%d, n2=%d)' % (n1, n2))
    open(html_path, 'w', encoding='utf-8').write(html)
    print('OK: %s, 공고 %d건(중복 %d건 묶음), 표시 %d건'
          % (TODAY, total, dupes, len(uniq)))


if __name__ == '__main__':
    main()
