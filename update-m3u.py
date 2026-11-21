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
