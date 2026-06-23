#!/usr/bin/env python3
"""Inspect the open Naver SmartEditor postwrite tab via osascript JS.
Reuses helpers from inject_code_blocks. Prints whatever the JS returns."""
import json
import sys
from inject_code_blocks import find_postwrite_tab, chrome_js, osa

JS = sys.argv[1] if len(sys.argv) > 1 else "document.title"

loc = find_postwrite_tab()
if not loc:
    print("[ERROR] no postwrite tab found")
    sys.exit(1)
win, tab = loc
# bring to front so it behaves like the real editor
osa(f'tell application "Google Chrome" to set active tab index of window {win} to {tab}')
osa(f'tell application "Google Chrome" to set index of window {win} to 1')
win = 1
tab = int(osa('tell application "Google Chrome" to get active tab index of window 1'))
out = chrome_js(win, tab, JS)
print(out)
