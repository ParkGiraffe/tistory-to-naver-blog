#!/usr/bin/env python3
"""Pass 2 of the Tistory -> Naver migration: native code components.

Reads /tmp/naver_code_blocks.json (written by migrate_from_url.py when the
Tistory post contains <pre> code blocks) and replaces each [[CODE-n]]
placeholder paragraph in the open Naver SmartEditor tab with a real
SmartEditor code component (se-code), source injected and Prism-highlighted.

Why this works while clipboard paste does not: the paste sanitizer
normalizes any external component markup to plain body text, but
 - osascript "execute javascript" runs in-page, so clicking the toolbar
   code button creates a legit component through the editor's own handlers
 - the code textarea (.se-code-source-editor) accepts a programmatic value
   + input event
 - placeholder selection/deletion needs OS-trusted events, so we use Quartz
   CGEvent for the triple-click and Backspace.

Prerequisites:
 - Chrome menu: View > Developer > Allow JavaScript from Apple Events
 - Accessibility permission for the terminal (same as Auto paste mode)
 - The blog.naver.com/<id>/postwrite tab open, placeholders already pasted

Usage: python3 inject_code_blocks.py [path/to/code_blocks.json]
"""

import base64
import json
import subprocess
import sys
import time

import Quartz

CODE_BLOCKS_JSON = "/tmp/naver_code_blocks.json"


# ---------------------------------------------------------------- osascript

def osa(*lines):
    args = []
    for line in lines:
        args += ["-e", line]
    result = subprocess.run(["osascript"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def chrome_js(win, tab, js_source):
    """Run JS in the given Chrome tab; returns the last expression (string).

    The source is base64-wrapped so no escaping survives the
    bash -> osascript -> JS round trip. UTF-8 safe via escape/decodeURI.
    """
    b64 = base64.b64encode(js_source.encode("utf-8")).decode("ascii")
    wrapped = f"eval(decodeURIComponent(escape(atob('{b64}'))))"
    return osa(
        f'tell application "Google Chrome" to execute tab {tab} '
        f'of window {win} javascript "{wrapped}"'
    )


def find_postwrite_tab():
    out = osa(
        'tell application "Google Chrome"',
        "set out to \"\"",
        "set wIdx to 0",
        "repeat with w in windows",
        "set wIdx to wIdx + 1",
        "set tIdx to 0",
        "repeat with t in tabs of w",
        "set tIdx to tIdx + 1",
        'if URL of t contains "/postwrite" then',
        'set out to (wIdx as string) & " " & (tIdx as string)',
        "end if",
        "end repeat",
        "end repeat",
        "return out",
        "end tell",
    )
    if not out:
        return None
    w, t = out.split()
    return int(w), int(t)


# ------------------------------------------------------------------- Quartz

def _mouse(event_type, x, y, clicks=1):
    ev = Quartz.CGEventCreateMouseEvent(
        None, event_type, (x, y), Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, clicks)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def triple_click(x, y):
    for n in (1, 2, 3):
        _mouse(Quartz.kCGEventLeftMouseDown, x, y, n)
        time.sleep(0.04)
        _mouse(Quartz.kCGEventLeftMouseUp, x, y, n)
        time.sleep(0.08)


def press_key(keycode, cmd=False):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for keydown in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(src, keycode, keydown)
        if cmd:
            Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        time.sleep(0.05)


BACKSPACE = 51


# ------------------------------------------------------------- JS templates

def js_scroll_to_marker(marker):
    return f"""
(() => {{
  const para = Array.from(document.querySelectorAll('.se-component.se-text p'))
    .find(p => p.innerText.includes({json.dumps(marker)}));
  if (!para) return 'missing';
  para.scrollIntoView({{block: 'center'}});
  return 'ok';
}})()"""


def js_marker_coords(marker):
    return f"""
(() => {{
  const para = Array.from(document.querySelectorAll('.se-component.se-text p'))
    .find(p => p.innerText.includes({json.dumps(marker)}));
  if (!para) return JSON.stringify({{err: 'missing'}});
  const rect = para.getBoundingClientRect();
  return JSON.stringify({{
    sx: Math.round(window.screenX + rect.left + Math.min(rect.width / 2, 60)),
    sy: Math.round(window.screenY + (window.outerHeight - window.innerHeight)
        + rect.top + rect.height / 2)
  }});
}})()"""


JS_LIST_CODE_IDS_AND_INSERT = """
(() => {
  const ids = Array.from(document.querySelectorAll('.se-component.se-code'))
    .map(c => c.getAttribute('data-compid') || '?');
  const btn = document.querySelector('button[data-name=code]');
  if (!btn) return JSON.stringify({err: 'no code button'});
  btn.click();
  return JSON.stringify({before: ids});
})()"""


def js_inject_code(before_ids, code):
    return f"""
(() => {{
  const before = new Set({json.dumps(before_ids)});
  const fresh = Array.from(document.querySelectorAll('.se-component.se-code'))
    .find(c => !before.has(c.getAttribute('data-compid') || '?'));
  if (!fresh) return JSON.stringify({{err: 'no new component'}});
  const ta = fresh.querySelector('.se-code-source-editor');
  if (!ta) return JSON.stringify({{err: 'no textarea'}});
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
    .set.call(ta, {json.dumps(code)});
  ta.dispatchEvent(new Event('input', {{bubbles: true}}));
  return JSON.stringify({{ok: true, len: ta.value.length}});
}})()"""


JS_COMMIT = """
(() => {
  const tm = document.querySelector('.se-component.se-text .se-module-text');
  if (tm) ['mousedown', 'mouseup', 'click'].forEach(t =>
    tm.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window})));
  return 'ok';
})()"""


def js_verify(code_prefix):
    return f"""
(() => {{
  const pres = Array.from(document.querySelectorAll('.se-code-source-highlighted pre'));
  const hit = pres.find(p => p.innerText.startsWith({json.dumps(code_prefix)}));
  return hit ? 'ok' : 'not-rendered';
}})()"""


# --------------------------------------------------------------------- main

def main():
    json_path = sys.argv[1] if len(sys.argv) > 1 else CODE_BLOCKS_JSON
    try:
        with open(json_path, encoding="utf-8") as f:
            blocks = json.load(f)
    except OSError:
        print(f"[ERROR] no sidecar file at {json_path} — run migration (pass 1) first")
        sys.exit(1)
    if not blocks:
        print("No code blocks to inject.")
        return

    loc = find_postwrite_tab()
    if not loc:
        print("[ERROR] no blog.naver.com/*/postwrite tab found in Chrome")
        sys.exit(1)
    win, tab = loc
    print(f"Editor tab: window {win}, tab {tab} — {len(blocks)} block(s) to inject")

    osa(
        f'tell application "Google Chrome" to set active tab index of window {win} to {tab}',
        f'tell application "Google Chrome" to set index of window {win} to 1',
        'tell application "Google Chrome" to activate',
    )
    time.sleep(0.8)
    # window raise may renumber windows — the active tab of window 1 is ours now
    win, tab = 1, int(osa('tell application "Google Chrome" to get active tab index of window 1'))

    failures = []
    for block in blocks:
        marker = f"[[CODE-{block['index']}]]"
        code = block["code"].rstrip("\n")
        print(f"  {marker} ({len(code)} chars)...", end=" ", flush=True)

        if chrome_js(win, tab, js_scroll_to_marker(marker)) != "ok":
            print("SKIP (placeholder not found)")
            failures.append(marker)
            continue
        time.sleep(0.6)

        coords = json.loads(chrome_js(win, tab, js_marker_coords(marker)))
        if "err" in coords:
            print("SKIP (coords)")
            failures.append(marker)
            continue

        triple_click(coords["sx"], coords["sy"])
        time.sleep(0.3)
        press_key(BACKSPACE)
        time.sleep(0.5)

        res = json.loads(chrome_js(win, tab, JS_LIST_CODE_IDS_AND_INSERT))
        if "err" in res:
            print(f"FAIL ({res['err']})")
            failures.append(marker)
            continue
        time.sleep(1.0)

        inj = json.loads(chrome_js(win, tab, js_inject_code(res["before"], code)))
        if "err" in inj:
            print(f"FAIL ({inj['err']})")
            failures.append(marker)
            continue
        time.sleep(0.3)

        chrome_js(win, tab, JS_COMMIT)
        time.sleep(0.4)

        verdict = chrome_js(win, tab, js_verify(code[:30]))
        print("OK" if verdict == "ok" else f"WARN ({verdict})")

    if failures:
        print(f"\nDone with {len(failures)} failure(s): {', '.join(failures)}")
        print("Failed placeholders are left as [[CODE-n]] text — fix manually or rerun.")
        sys.exit(2)
    print("\nAll code blocks injected. Review the editor, set languages if needed.")


if __name__ == "__main__":
    main()
