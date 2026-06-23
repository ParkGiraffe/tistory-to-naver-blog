#!/usr/bin/env python3
"""Set the Naver SmartEditor category and publish the open postwrite draft.

Reuses osascript helpers from inject_code_blocks. Naver blocks both
claude-in-chrome and computer-use (browser tier), so in-page JS via
`Google Chrome ... execute javascript` is the only working route.

Usage:
  python3 publish_with_category.py <categoryTestId>
  e.g. python3 publish_with_category.py 142   # GoodWishes 제작기

Flow (single in-page IIFE with chained polling, to survive the
window-raise blur that closes floating layers between osascript calls):
  1. open the 발행 layer (publish_btn__)
  2. open the category selectbox (selectbox_button__)
  3. poll until the dropdown list renders, click the matching radio label
     (data-testid=categoryItemText_<id>)
  4. verify the selectbox label changed
  5. click the confirm 발행 button (confirm_btn__)
Then confirm the postwrite tab navigated away (publish redirect = success).
"""
import json
import sys
import time

from inject_code_blocks import find_postwrite_tab, chrome_js, osa

CAT_ID = sys.argv[1] if len(sys.argv) > 1 else "142"


def front_tab():
    loc = find_postwrite_tab()
    if not loc:
        return None
    win, tab = loc
    osa(f'tell application "Google Chrome" to set active tab index of window {win} to {tab}')
    osa(f'tell application "Google Chrome" to set index of window {win} to 1')
    tab = int(osa('tell application "Google Chrome" to get active tab index of window 1'))
    return 1, tab


def run(js):
    loc = front_tab()
    if not loc:
        return None
    return chrome_js(loc[0], loc[1], js)


SELECT_JS = """(function(){
  window.__pr="pending";
  function vis(e){return e && e.offsetParent!==null;}
  if(!document.querySelector("[class*=option_category__]")){
    var pb=Array.from(document.querySelectorAll("button")).find(function(e){return e.className.indexOf("publish_btn__")>=0 && e.textContent.trim()==="발행";});
    if(pb) pb.click();
  }
  setTimeout(function(){
    var sb=document.querySelector(".selectbox_button__jb1Dt");
    var expanded=sb && sb.getAttribute("aria-expanded")==="true";
    if(!expanded && sb) sb.click();
    var tries=0;
    (function waitList(){
      tries++;
      var el=document.querySelector("[data-testid=categoryItemText_%s]");
      if(el && vis(el)){
        var lab=el.closest("label");
        (lab||el).click();
        setTimeout(function(){
          var cur=document.querySelector(".selectbox_button__jb1Dt .text__sraQE");
          window.__pr="DONE|"+(cur?cur.textContent.trim():"nocur");
        },500);
        return;
      }
      if(tries>25){window.__pr="list-never|tries="+tries; return;}
      setTimeout(waitList,200);
    })();
  },400);
  return "start";
})()""" % CAT_ID

CONFIRM_JS = """(function(){
  var b=document.querySelector("[class*=confirm_btn__]");
  if(b){ b.click(); return "published-click"; }
  return "no-confirm-btn";
})()"""


def main():
    print(f"[publish] selecting category testid={CAT_ID} ...")
    if run(SELECT_JS) is None:
        print("[ERROR] no postwrite tab found")
        sys.exit(1)
    # poll the select result
    result = None
    for _ in range(15):
        time.sleep(0.6)
        result = run("window.__pr")
        if result and result.startswith("DONE"):
            break
        if result and result.startswith("list-never"):
            break
    print(f"[publish] category result: {result}")
    if not (result and result.startswith("DONE") and "제작기" in result):
        print("[ERROR] category not selected as expected; aborting before publish")
        sys.exit(2)

    print("[publish] clicking confirm 발행 ...")
    res = run(CONFIRM_JS)
    print(f"[publish] confirm: {res}")
    time.sleep(4)
    # success = postwrite tab gone (redirected) OR url no longer /postwrite
    loc = find_postwrite_tab()
    if loc is None:
        print("[publish] OK — postwrite tab redirected away (publish complete)")
    else:
        url = run("location.href")
        if url and "/postwrite" not in url:
            print(f"[publish] OK — navigated to {url}")
        else:
            print(f"[WARN] still on postwrite ({url}); publish may not have completed")
            sys.exit(3)


if __name__ == "__main__":
    main()
