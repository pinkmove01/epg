#!/usr/bin/env python3
"""koreatv-final.m3u 의 만료되는 스트림 주소만 원본(koreatv.json) 최신본으로 교체한다.
- 갱신 대상 호스트: tvlive.sbs.co.kr (2시간 JWT), *.gscdn.kbs.co.kr (CloudFront Policy 서명)
- 만료가 없는 주소(backup.760515.xyz, ebsonair, imbc, vod.ikbc.co.kr, ottera 등)는 그대로 둔다.
- pjy 원본(koreatv.json)에만 있는 신규 채널은 m3u 끝에 자동 추가한다.
- 중국(中国-*)·영어(ENGLISH) 채널은 한국 전용 필터로 제거한다. (지역 SBS 포함 한국 채널은 모두 유지)
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
def filter_korea_only(out):
    """중국(中国-*)·영어(ENGLISH) 채널만 걸러낸다. 한국 채널(지역 SBS 포함)은 모두 유지."""
    keep, removed, block = [], [], []

    def flush():
        if not block:
            return
        e = block[0]
        g = re.search(r'group-title="([^"]*)"', e)
        group = g.group(1) if g else ""
        name = e.rsplit(",", 1)[-1].strip()
        if group.startswith("中国") or group == "ENGLISH":
            removed.append((name, group or "?"))
        else:
            keep.extend(block)
            keep.append("")
        block.clear()

    for ln in out:
        if ln.startswith("#EXTINF"):
            flush()
        block.append(ln)
    flush()
    if keep and keep[-1] == "":
        keep.pop()
    for n, g in removed:
        print(f"  [제거] [{g}] {n}")
    kept_n = sum(1 for l in keep if l.startswith("#EXTINF"))
    print(f"한국 전용 필터: {len(removed)}개 제거, {kept_n}개 남음")
    return keep


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
        if group.startswith("中国") or group == "ENGLISH":
            continue                       # 중국·영어 채널은 아예 추가하지 않음
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

    out = filter_korea_only(out)
    added_n = append_new_channels(out, raw)

    open(M3U, "w", encoding="utf-8").write("\n".join(out).rstrip("\n") + "\n")

    for n, oe, ne in replaced:
        left = f"+{int((ne - now) / 60)}분" if ne else "만료시각 미상"
        print(f"  교체 {n}: {oe} -> {ne} ({left})")
    for n, oe, ne in held:
        print(f"  [보류] {n}: 원본 토큰도 갱신 안 됨 (현재 {oe} / 원본 {ne})")
    if unmatched:
        print("  [원본에 없음] " + ", ".join(unmatched))
    print(f"URL 교체: {len(replaced)} / 신규 채널: {added_n}")


if __name__ == "__main__":
    main()
