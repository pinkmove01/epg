#!/usr/bin/env python3
"""koreatv-final.m3u 의 만료되는 스트림 주소만 원본(koreatv.json) 최신본으로 교체한다.
- 갱신 대상 호스트: tvlive.sbs.co.kr (2시간 JWT), *.gscdn.kbs.co.kr (CloudFront Policy 서명)
- 만료가 없는 주소(backup.760515.xyz, ebsonair, imbc, ottera 등)는 그대로 둔다.
- pjy 원본(koreatv.json)에만 있는 신규 채널은 m3u 끝에 자동 추가한다.
"""
import json, re, base64, time, urllib.request

M3U = "koreatv-final.m3u"
SRC = "https://raw.githubusercontent.com/kenpark76/kenpark76.github.io/main/koreatv.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36")
EXPIRING = ("tvlive.sbs.co.kr", "gscdn.kbs.co.kr")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _jwt(token):
    """JWT 는 header.payload.signature 3부분 → 가운데 payload 만 디코드."""
    t = token.split(".")[1]
    t += "=" * (-len(t) % 4)
    return json.loads(base64.urlsafe_b64decode(t))


def _cf(text):
    """CloudFront Policy: = + / 를 _ - ~ 로 치환해 쓴다."""
    from urllib.parse import unquote
    t = unquote(text).replace("-", "+").replace("_", "=").replace("~", "/")
    t += "=" * (-len(t) % 4)
    return json.loads(base64.urlsafe_b64decode(t))


def exp_of(url):
    """JWT exp 또는 CloudFront Policy 의 AWS:EpochTime. 못 읽으면 None."""
    m = re.search(r"[?&]token=(ey[A-Za-z0-9_.-]+)", url)
    if m:
        try:
            return int(_jwt(m.group(1))["exp"])
        except Exception:
            return None
    m = re.search(r"[?&]Policy=([^&]+)", url)
    if m:
        try:
            d = _cf(m.group(1))
            return int(d["Statement"][0]["Condition"]["DateLessThan"]["AWS:EpochTime"])
        except Exception:
            from urllib.parse import unquote
            m2 = re.search(r'EpochTime"?:?\s*:?(\d{9,})', unquote(m.group(1)))
            return int(m2.group(1)) if m2 else None
    return None


def append_new_channels(out, raw):
    """pjy 원본에만 있는 채널을 m3u 끝에 덧붙인다. (기존 형식: EXTINF / EXTVLCOPT / URL)"""
    have = set()
    for ln in out:
        if ln.startswith("#EXTINF"):
            have.add(ln.rsplit(",", 1)[-1].strip().lower())

    added, names = [], []
    for e in raw:
        name = (e.get("name") or e.get("title") or "").strip()
        uris = e.get("uris") or e.get("urls") or []
        if not name or not uris or name.lower() in have:
            continue
        logo = (e.get("logo") or "").replace('"', "")
        group = (e.get("group") or "").replace('"', "")
        hdr = e.get("headers") or {}
        ua = (hdr.get("user-agent") or hdr.get("User-Agent") or "")
        added.append(f'#EXTINF:-1 tvg-id="" tvg-logo="{logo}" group-title="{group}",{name}')
        if ua:
            added.append(f"#EXTVLCOPT:http-user-agent={ua}")
        added.append(uris[0])
        names.append(name)

    if added:
        out.append("")          # 채널 블록 사이 빈 줄 (기존 형식 유지)
        out.extend(added)
        print("신규 채널 추가: " + ", ".join(names))
    else:
        print("신규 채널 없음")
    return len(names)


def main():
    now = int(time.time())
    try:
        raw = json.loads(fetch(SRC))
    except Exception as e:
        print(f"
