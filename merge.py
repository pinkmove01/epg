#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""두 EPG 소스를 병합해 epg-kr-merged.xml 생성"""
import re, html, gzip, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"}

SRC_A = "https://raw.githubusercontent.com/kenpark76/kenpark76.github.io/refs/heads/main/koreatvEPG.xml"   # kenpark76
SRC_B = "https://iptv-epg.org/files/epg-kr.xml"                                                            # iptv-epg.org
M3U   = "koreatv-final.m3u"   # 저장소 안 M3U 경로
OUT   = "epg-kr-merged.xml"   # 생성될 병합 EPG

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", "replace")

def parse(xml):
    chans = {}
    for m in re.finditer(r'<channel\b[^>]*id="([^"]*)"[^>]*>(.*?)</channel>', xml, re.S):
        cid = html.unescape(m.group(1))
        dns = [html.unescape(x) for x in re.findall(r"<display-name[^>]*>(.*?)</display-name>", m.group(2), re.S)]
        chans.setdefault(cid, dns or [cid])
    progs = {}
    for m in re.finditer(r'<programme\b[^>]*channel="([^"]*)"[^>]*>.*?</programme>', xml, re.S):
        progs.setdefault(html.unescape(m.group(1)), []).append(m.group(0).strip())
    return chans, progs

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))

def main():
    m3u = open(M3U, encoding="utf-8").read()
    ids = list(dict.fromkeys(html.unescape(i) for i in re.findall(r'tvg-id="([^"]+)"', m3u)))
    print("M3U 채널:", len(ids))

    a_ch, a_pr = parse(fetch(SRC_A))
    b_ch, b_pr = parse(fetch(SRC_B))
    print("A(kenpark): channel %d / programme %d" % (len(a_ch), sum(map(len, a_pr.values()))))
    print("B(iptv-epg): channel %d / programme %d" % (len(b_ch), sum(map(len, b_pr.values()))))

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
