#!/usr/bin/env python3
"""koreatv-final.m3u 의 만료되는 스트림 주소만 원본(koreatv.json) 최신본으로 교체한다.
- 갱신 대상 호스트: tvlive.sbs.co.kr (2시간 JWT), *.gscdn.kbs.co.kr (CloudFront Policy 서명)
- 만료가 없는 주소(backup.760515.xyz, ebsonair, imbc, ottera 등)는 그대로 둔다.
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


def main():
    now = int(time.time())
    try:
        raw = json.loads(fetch(SRC))
    except Exception as e:
        print(f"[SKIP] 원본 JSON 로드 실패: {e}")
        return

    fresh = {}
    for e in raw:
        name = (e.get("name") or e.get("title") or "").strip()
        uris = e.get("uris") or e.get("urls") or []
        if name and uris:
            fresh[name] = uris[0]

    lines = open(M3U, encoding="utf-8").read().splitlines()
    out, replaced, held, unmatched = [], [], [], []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.startswith("#EXTINF"):
            out.append(ln); i += 1; continue

        name = ln.rsplit(",", 1)[-1].strip()
        j = i + 1
        while j < len(lines) and lines[j].startswith("#"):
            j += 1
        url = lines[j] if j < len(lines) else ""

        if not any(h in url for h in EXPIRING):
            out.extend(lines[i:j + 1]); i = j + 1; continue

        new = fresh.get(name)
        if not new or not any(h in new for h in EXPIRING):
            unmatched.append(name)
            out.extend(lines[i:j + 1]); i = j + 1; continue

        oe, ne = exp_of(url), exp_of(new)
        if ne is not None and ne < now:      # 원본 토큰도 이미 만료 -> 손대지 않음
            held.append((name, oe, ne))
            out.extend(lines[i:j + 1]); i = j + 1; continue
        worth = (ne is None) or (oe is None) or (ne > oe)
        if not worth:
            held.append((name, oe, ne))
            out.extend(lines[i:j + 1]); i = j + 1; continue

        out.extend(lines[i:j]); out.append(new)
        replaced.append((name, oe, ne)); i = j + 1

    open(M3U, "w", encoding="utf-8").write("\n".join(out).rstrip("\n") + "\n")

    for n, oe, ne in replaced:
        left = f"+{int((ne - now) / 60)}분" if ne else "만료시각 미상"
        print(f"  교체 {n}: {oe} -> {ne} ({left})")
    for n, oe, ne in held:
        print(f"  [보류] {n}: 원본 토큰도 갱신 안 됨 (현재 {oe} / 원본 {ne})")
    if unmatched:
        print("  [원본에 없음] " + ", ".join(unmatched))
    print(f"URL 교체: {len(replaced)}")


if __name__ == "__main__":
    main()
