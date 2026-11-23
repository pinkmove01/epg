#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""두 EPG 소스를 병합해 epg-kr-merged.xml 생성 (소스 하나 죽어도 계속 진행)"""
import re, html, gzip, time, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"}

SRC_A = "https://raw.githubusercontent.com/kenpark76/kenpark76.github.io/refs/heads/main/koreatvEPG.xml"   # kenpark76
SRC_B = "https://iptv-epg.org/files/epg-kr.xml"                                                            # iptv-epg.org
M3U   = "koreatv-final.m3u"   # 저장소 안 M3U 경로
OUT   = "epg-kr-merged.xml"   # 생성될 병합 EPG

# 껍데기 편성. 이 제목은 '편성 있음'으로 세지 않는다.
NO_DATA = ("no data", "n/a")


def fetch(url, required=True, tries=3):
    """3회 재시도. required=False 인 소스가 끝내 실패하면 빈 문자열을 돌려주고 계속 진행."""
    last = None
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return data.decode("utf-8", "replace")
        except Exception as e:
            last = e
            print(f"  [warn] {url} 실패 ({i}/{tries}): {e}")
            if i < tries:
                time.sleep(5 * i)
    if required:
        raise last
    print(f"  [warn] {url} 건너뜀 — 이 소스 없이 병합합니다")
    return ""


def parse(xml):
    chans = {}
    for m in re.finditer(r'<channel\b[^>]*id="([^"]*)"[^>]*>(.*?)</channel>', xml, re.S):
        cid = html.unescape(m.group(1))
        dns = [html.unescape(x) for x in re.findall(r"<display-name[^>]*>(.*?)</display-name>", m.group(2), re.S)]
        chans.setdefault(cid, dns or [cid])

    progs, skipped = {}, 0
    for m in re.finditer(r'<programme\b[^>]*channel="([^"]*)"[^>]*>.*?</programme>', xml, re.S):
        block = m.group(0)
        t = re.search(r'<title[^>]*>(.*?)</title>', block, re.S)
        title = html.unescape(t.group(1)).strip() if t else ""
        if title.lower() in NO_DATA:
            skipped += 1
            continue
        progs.setdefault(html.unescape(m.group(1)), []).append(block.strip())

    if skipped:
        print("  [parse] No Data 편성 %d건 제외" % skipped)
    return chans, progs


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


def main():
    m3u = open(M3U, encoding="utf-8").read()
    ids = list(dict.fromkeys(html.unescape(i) for i in re.findall(r'tvg-id="([^"]+)"', m3u)))
    print("M3U 채널:", len(ids))

    a_ch, a_pr = parse(fetch(SRC_A, required=False))   # A도 죽으면 B 단독으로 시도
    b_ch, b_pr = parse(fetch(SRC_B, required=False))
    print("A(kenpark): channel %d / programme %d" % (len(a_ch), sum(map(len, a_pr.values()))))
    print("B(iptv-epg): channel %d / programme %d" % (len(b_ch), sum(map(len, b_pr.values()))))

    # 두 소스가 모두 비었으면 기존 파일을 건드리지 않고 실패 (파이프라인에 알림)
    if not a_pr and not b_pr:
        raise SystemExit("모든 EPG 소스 수집 실패 - 기존 %s 유지" % OUT)

    out_ch, out_pr, picked, missing = [], [], {}, []
    for cid in ids:
        ka, kb = len(a_pr.get(cid, [])), len(b_pr.get(cid, []))
        if ka == 0 and kb == 0:
            missing.append(cid); continue
        src, chans, progs, cnt = ("B", b_ch, b_pr, kb) if kb > ka else ("A", a_ch, a_pr, ka)
        out_ch.append((cid, chans.get(cid, [cid])))
        out_pr.extend(progs[cid])
        picked[cid] = (src, cnt)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="kenpark76 + iptv-epg.org merged">']
    for cid, dns in out_ch:
        lines.append('  <channel id="%s">' % esc(cid))
        lines += ["    <display-name>%s</display-name>" % esc(d) for d in dns]
        lines.append("  </channel>")
    lines += ["  " + p for p in out_pr]
    lines.append("</tv>")
    xml_out = "\n".join(lines) + "\n"
    open(OUT, "w", encoding="utf-8").write(xml_out)

    print("병합 채널: %d | 편성 합계: %d" % (len(out_ch), len(out_pr)))
    print("소스별 채택: A=%d, B=%d" % (sum(1 for v in picked.values() if v[0]=="A"),
                                        sum(1 for v in picked.values() if v[0]=="B")))
    print("편성 없는 id:", missing)


if __name__ == "__main__":
    main()
