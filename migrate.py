#!/usr/bin/env python3
"""One-shot Tistory -> Naver blog migration orchestrator.

Runs the whole pipeline in a single process, no step-by-step babysitting:

  1. fetch the Tistory post, download images in PARALLEL, split into chunks
  2. find (or open) the blog.naver.com/<id>/postwrite tab, dismiss the
     draft-restore dialog
  3. paste the TITLE first (focus is freshest at the start)
  4. paste body chunks with per-chunk verification (poll, retry up to 3)
  5. inject native code components for [[CODE-n]] placeholders (pass 2)
  6. style pass: every <hr> -> line3 (center-notch) + center align,
     every image -> center align  (pure synthetic JS, no real input)
  7. final audit (component counts, leftover markers, title)

Real input (Quartz CGEvent click + Cmd+V) is used only for: body focus,
title paste, chunk pastes. Keep hands off keyboard/mouse while it runs.

Usage:
  python3 migrate.py <TISTORY_URL> [--clear] [--no-style] [--blog-id op5321]

  --clear     wipe the editor body first if it is not empty (otherwise the
              script aborts to avoid eating an unsaved draft)
  --no-style  skip step 6
"""

import base64
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import Quartz

import migrate_from_url as m

BLOG_ID = "op5321"
POSTWRITE_URL = "https://blog.naver.com/{blog_id}/postwrite"


# ------------------------------------------------------------ chrome plumbing

def osa(*lines, timeout=15):
    args = []
    for line in lines:
        args += ["-e", line]
    out = subprocess.run(["osascript"] + args, capture_output=True, text=True,
                         timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"osascript: {out.stderr.strip()}")
    return out.stdout.strip()


def chrome_js(js_source, timeout=10):
    """Run JS in the postwrite tab (re-located by URL every call)."""
    b64 = base64.b64encode(js_source.encode("utf-8")).decode("ascii")
    wrapped = f"eval(decodeURIComponent(escape(atob('{b64}'))))"
    script = (
        'tell application "Google Chrome"\n'
        "repeat with w in windows\n"
        "repeat with t in tabs of w\n"
        'if URL of t contains "/postwrite" then\n'
        f'return execute t javascript "{wrapped}"\n'
        "end if\nend repeat\nend repeat\n"
        'return "NO_TAB"\n'
        "end tell"
    )
    out = subprocess.run(["osascript", "-e", script], capture_output=True,
                         text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"chrome_js: {out.stderr.strip()}")
    return out.stdout.strip()


def ensure_postwrite_tab(blog_id):
    if chrome_js("'ping'") == "NO_TAB":
        url = POSTWRITE_URL.format(blog_id=blog_id)
        osa('tell application "Google Chrome" to tell window 1 to make new tab '
            f'at end of tabs with properties {{URL:"{url}"}}')
        for _ in range(20):
            time.sleep(1)
            if chrome_js("document.querySelector('.se-canvas') ? 'ready' : 'loading'") == "ready":
                break
    # raise the window that holds the tab and activate Chrome
    osa('tell application "Google Chrome"',
        "set wIdx to 0",
        "repeat with w in windows",
        "set wIdx to wIdx + 1",
        "set tIdx to 0",
        "repeat with t in tabs of w",
        "set tIdx to tIdx + 1",
        'if URL of t contains "/postwrite" then',
        "set active tab index of w to tIdx",
        "set index of w to 1",
        "end if",
        "end repeat",
        "end repeat",
        "activate",
        "end tell")
    time.sleep(0.8)


# ----------------------------------------------------------------- real input

def click(x, y):
    for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        ev = Quartz.CGEventCreateMouseEvent(None, t, (x, y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.05)


def triple_click(x, y):
    """Select the clicked line (paragraph-scoped — unlike Cmd+A, which in
    SmartEditor selects the WHOLE document including the body)."""
    for n in (1, 2, 3):
        for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            ev = Quartz.CGEventCreateMouseEvent(None, t, (x, y), Quartz.kCGMouseButtonLeft)
            Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, n)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.04)
        time.sleep(0.08)


def key(code, cmd=False):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(src, code, down)
        if cmd:
            Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.04)


KEY_V, KEY_A, KEY_BACKSPACE = 9, 0, 51


def wait_for_window_focus(retries=6):
    for _ in range(retries):
        if chrome_js("String(document.hasFocus())") == "true":
            return True
        osa('tell application "Google Chrome" to activate')
        time.sleep(1.0)
    return False


# ------------------------------------------------------------------ js blocks

JS_DISMISS_DIALOG = """
(() => {
  const btn = Array.from(document.querySelectorAll('.se-popup button'))
    .find(b => b.innerText.trim() === '취소');
  if (btn) { btn.click(); return 'dismissed'; }
  return 'no-dialog';
})()"""

JS_COMPONENT_COUNT = "String(document.querySelectorAll('.se-component').length)"

JS_BODY_COORDS = """
(() => {
  const para = Array.from(document.querySelectorAll('.se-component.se-text p')).pop();
  para.scrollIntoView({block: 'center'});
  const r = para.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(window.screenX + r.left + Math.min(r.width/2, 60)),
    y: Math.round(window.screenY + (window.outerHeight - window.innerHeight) + r.top + r.height/2)
  });
})()"""

JS_TITLE_COORDS = """
(() => {
  const t = document.querySelector('.se-documentTitle p') || document.querySelector('.se-documentTitle');
  t.scrollIntoView({block: 'center'});
  const r = t.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(window.screenX + r.left + Math.min(r.width/2, 100)),
    y: Math.round(window.screenY + (window.outerHeight - window.innerHeight) + r.top + r.height/2)
  });
})()"""

JS_TITLE_TEXT = "document.querySelector('.se-documentTitle').innerText.trim()"

JS_PASTE_COUNTS = """
JSON.stringify({img: document.querySelectorAll('.se-component.se-image').length,
                p: document.querySelectorAll('.se-component.se-text p').length})"""

# style pass: transform ONE not-yet-styled hr, store result in window.__sr
JS_STYLE_NEXT_HR = """
(() => {
  const hr = Array.from(document.querySelectorAll('.se-component.se-horizontalLine'))
    .find(c => {
      const s = c.querySelector('.se-section').className;
      return !(s.includes('se-l-line3') && s.includes('se-section-align-center'));
    });
  if (!hr) return 'done';
  hr.scrollIntoView({block: 'center'});
  const mod = hr.querySelector('.se-module-horizontalLine') || hr.querySelector('hr') || hr;
  ['mousedown','mouseup','click'].forEach(t =>
    mod.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,button:0})));
  window.__sr = 'pending';
  setTimeout(() => {
    const lay = Array.from(document.querySelectorAll('button[data-name=horizontal-line-layout]'))
      .find(b => b.getAttribute('data-value') === 'line3' && b.offsetParent);
    if (lay) lay.click();
    setTimeout(() => {
      const al = Array.from(document.querySelectorAll('button[data-name=align]'))
        .find(b => b.getAttribute('data-value') === 'center' && b.offsetParent);
      if (al) al.click();
      setTimeout(() => {
        const s = hr.querySelector('.se-section').className;
        window.__sr = (s.includes('se-l-line3') && s.includes('se-section-align-center')) ? 'ok' : 'failed:' + s;
      }, 250);
    }, 300);
  }, 450);
  return 'working';
})()"""

JS_STYLE_NEXT_IMG = """
(() => {
  const img = Array.from(document.querySelectorAll('.se-component.se-image'))
    .find(c => !c.querySelector('.se-section').className.includes('se-section-align-center'));
  if (!img) return 'done';
  img.scrollIntoView({block: 'center'});
  const mod = img.querySelector('.se-module-image') || img;
  ['mousedown','mouseup','click'].forEach(t =>
    mod.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,button:0})));
  window.__sr = 'pending';
  setTimeout(() => {
    const al = Array.from(document.querySelectorAll('button[data-name=align]'))
      .find(b => b.getAttribute('data-value') === 'center' && b.offsetParent);
    if (al) al.click();
    setTimeout(() => {
      const s = img.querySelector('.se-section').className;
      window.__sr = s.includes('se-section-align-center') ? 'ok' : 'failed:' + s;
    }, 250);
  }, 450);
  return 'working';
})()"""

JS_DESELECT = """
(() => {
  const tm = document.querySelector('.se-component.se-text .se-module-text');
  if (tm) ['mousedown','mouseup','click'].forEach(t =>
    tm.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,button:0})));
  return 'ok';
})()"""

JS_FINAL_AUDIT = """
(() => {
  const counts = {};
  Array.from(document.querySelectorAll('.se-component')).forEach(c => {
    const k = c.className.split(' ')[1];
    counts[k] = (counts[k] || 0) + 1;
  });
  const leftover = Array.from(document.querySelectorAll('.se-component.se-text p'))
    .filter(p => /\\[\\[CODE-\\d+\\]\\]/.test(p.innerText)).length;
  return JSON.stringify({
    title: document.querySelector('.se-documentTitle').innerText.trim(),
    counts, leftover
  });
})()"""


# -------------------------------------------------------------------- helpers

def copy_text(text):
    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    p.communicate(text.encode("utf-8"))


def paste_at(coords_js):
    c = json.loads(chrome_js(coords_js))
    click(c["x"], c["y"])
    time.sleep(0.5)
    key(KEY_V, cmd=True)


def predownload_images(soup):
    urls = []
    for img in soup.find_all("img"):
        src = img.get("data-url") or img.get("data-src") or img.get("src")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        urls.append(src)
    if not urls:
        return
    print(f"[1/6] downloading {len(urls)} image(s) in parallel...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(m.download_image, urls))


def paste_chunks(chunks):
    def counts():
        try:
            return json.loads(chrome_js(JS_PASTE_COUNTS, timeout=8))
        except Exception:
            return None

    failures = []
    for i, chunk in enumerate(chunks):
        kind = chunk["type"]
        ok = False
        for attempt in (1, 2, 3):
            before = counts()
            if kind == "html":
                m.copy_html_to_clipboard(chunk["content"])
            else:
                m.copy_image_file_to_clipboard(chunk["path"])
            m.paste_cmd()
            time.sleep(0.15)
            deadline = time.time() + (10 if kind == "image" else 6)
            while time.time() < deadline:
                now = counts()
                if before is None or now is None:
                    time.sleep(1.0)
                    ok = True
                    break
                if kind == "image" and now["img"] > before["img"]:
                    ok = True
                    break
                if kind == "html" and now["p"] > before["p"]:
                    ok = True
                    break
                time.sleep(0.2)
            if ok:
                break
            print(f"      chunk {i+1}/{len(chunks)} retry {attempt}...")
        print(f"\r      chunk {i+1}/{len(chunks)} {'OK' if ok else 'FAILED'}",
              end="", flush=True)
        if not ok:
            failures.append(i + 1)
    print()
    return failures


def style_pass():
    results = {"hr": 0, "img": 0}
    for kind, js in (("hr", JS_STYLE_NEXT_HR), ("img", JS_STYLE_NEXT_IMG)):
        for _ in range(150):
            r = chrome_js(js)
            if r == "done":
                break
            if r != "working":
                print(f"      [WARN] style {kind}: {r}")
                break
            for _ in range(12):
                time.sleep(0.15)
                sr = chrome_js("window.__sr || 'pending'")
                if sr != "pending":
                    break
            if sr == "ok":
                results[kind] += 1
            else:
                print(f"      [WARN] style {kind}: {sr}")
                break
    chrome_js(JS_DESELECT)
    return results


# ----------------------------------------------------------------------- main

def main():
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    url = args[0]
    blog_id = BLOG_ID
    if "--blog-id" in flags:
        blog_id = sys.argv[sys.argv.index("--blog-id") + 1]

    t0 = time.time()

    print("[1/6] fetching post...")
    post = m.fetch_post(url)
    if post["content"] is None:
        print("[ERROR] could not fetch post content")
        sys.exit(1)
    title = post.get("title")
    predownload_images(post["content"])
    chunks = m.split_content_into_chunks(
        post["content"], source_url=post["source_url"],
        published_iso=post["published_iso"], tags=post.get("tags"))
    n_img = sum(1 for c in chunks if c["type"] == "image")
    print(f"      {len(chunks)} chunks ({n_img} images) | title: {title}")

    print("[2/6] preparing editor tab...")
    ensure_postwrite_tab(blog_id)
    chrome_js(JS_DISMISS_DIALOG)
    time.sleep(0.5)
    if not wait_for_window_focus():
        print("[ERROR] Chrome window never got OS focus — is something else grabbing it?")
        sys.exit(1)
    n = int(chrome_js(JS_COMPONENT_COUNT))
    if n > 2:
        if "--clear" in flags:
            print(f"      editor has {n} components -> clearing (--clear)")
            paste_at_coords = json.loads(chrome_js(JS_BODY_COORDS))
            click(paste_at_coords["x"], paste_at_coords["y"])
            time.sleep(0.4)
            key(KEY_A, cmd=True)
            time.sleep(0.5)
            key(KEY_BACKSPACE)
            time.sleep(0.8)
        else:
            print(f"[ABORT] editor is not empty ({n} components). "
                  "Re-run with --clear to wipe it.")
            sys.exit(3)

    if title:
        print("[3/6] pasting title...")
        copy_text(title)
        ok = False
        for attempt in range(3):
            c = json.loads(chrome_js(JS_TITLE_COORDS))
            # triple-click selects the existing title line, so a retry
            # REPLACES instead of appending (the v1 bug pasted 3x)
            triple_click(c["x"], c["y"])
            time.sleep(0.4)
            key(KEY_V, cmd=True)
            # SmartEditor renders spaces as NBSP (\xa0) — normalize before
            # comparing or the check never passes (the v1 triple-paste bug)
            norm = lambda s: s.replace("\xa0", " ").strip()
            for _ in range(10):
                time.sleep(0.4)
                if norm(chrome_js(JS_TITLE_TEXT)) == norm(title):
                    ok = True
                    break
            if ok:
                break
            osa('tell application "Google Chrome" to activate')
            time.sleep(1.0)
        if not ok:
            print("      [WARN] title did not register — set it manually at the end")

    print("[4/6] pasting body chunks...")
    c = json.loads(chrome_js(JS_BODY_COORDS))
    click(c["x"], c["y"])
    time.sleep(0.5)
    failures = paste_chunks(chunks)

    print("[5/6] injecting code blocks...")
    try:
        with open(m.CODE_BLOCKS_JSON, encoding="utf-8") as f:
            has_code = bool(json.load(f))
    except OSError:
        has_code = False
    if has_code:
        import os
        r = subprocess.run([sys.executable, "inject_code_blocks.py"],
                           cwd=os.path.dirname(os.path.abspath(__file__)))
        if r.returncode != 0:
            print("      [WARN] code injection reported failures")
    else:
        print("      no code blocks — skipped")

    print("[6/6] style pass (hr line3+center, images center)...")
    styled = style_pass()
    print(f"      hr styled: {styled['hr']}, images centered: {styled['img']}")

    audit = json.loads(chrome_js(JS_FINAL_AUDIT))
    dt = time.time() - t0
    print(f"\n=== DONE in {dt:.0f}s ===")
    print(f"title:    {audit['title']}")
    print(f"counts:   {audit['counts']}")
    print(f"leftover code markers: {audit['leftover']}")
    if failures:
        print(f"FAILED chunks: {failures}")
        sys.exit(2)


if __name__ == "__main__":
    main()
