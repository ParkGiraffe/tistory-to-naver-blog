#!/usr/bin/env python3
import sys
import os
import subprocess
import time
try:
	import AppKit
except ImportError:
    pass

def install_dependencies():
    print("Checking dependencies...")
    try:
        import AppKit
        import requests
        import bs4
    except ImportError:
        print("Installing required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyobjc-framework-Cocoa", "requests", "beautifulsoup4"])
        print("Dependencies installed.")

def get_clipboard_text():
    try:
        import AppKit
        pb = AppKit.NSPasteboard.generalPasteboard()
        content = pb.stringForType_(AppKit.NSPasteboardTypeString)
        return content
    except:
        return None

def run_migration():
    install_dependencies()
    print("--- Tistory to Naver Blog Migrator ---")
    
    import migrate_from_url
    migrate_from_url.clear_temp_images()
    
    url = None
    # 1. Check CLI args
    if len(sys.argv) > 1:
        url = sys.argv[1]
    
    # 2. Check Clipboard if no arg
    if not url:
        clip_text = get_clipboard_text()
        if clip_text and clip_text.startswith("http"):
             print(f"Detected URL in clipboard: {clip_text}")
             choice = input("Use this URL? (Y/n): ").strip().lower()
             if choice in ['', 'y', 'yes']:
                 url = clip_text
    
    # 3. Prompt if still no URL
    if not url:
        url = input("Enter Tistory Post URL: ").strip()
        
    if not url:
        print("No URL provided. Exiting.")
        return

    try:
        print(f"Starting migration for: {url}")
        post = migrate_from_url.fetch_post(url)
        soup = post['content']
        if soup:
            print("Splitting content into chunks for Sequential Macro...")
            chunks = migrate_from_url.split_content_into_chunks(
                soup,
                source_url=post['source_url'],
                published_iso=post['published_iso'],
                tags=post.get('tags'),
            )
            print(f"Prepared {len(chunks)} chunks (Text/Images).")
            if post['published_iso']:
                print(f"Original post date: {post['published_iso']} → footer auto-appended.")
            if post.get('tags'):
                print(f"Tags ({len(post['tags'])}): {', '.join(post['tags'])} → hashtag line appended.")
            
            print("\n*** CHOICE ***")
            print("1. Auto Mode (Requires Accessibility Permission for Terminal)")
            print("2. Manual Mode (Press Enter to copy each part, then you Cmd+V)")
            mode = input("Select Mode (1/2): ").strip()
            
            if mode == "1":
                print("\n*** AUTO MACRO STARTING In 3 Seconds ***")
                print("Focus on Naver Editor NOW!")
                time.sleep(3)

                # Per-chunk verification: pasting blindly loses chunks when
                # the editor is busy (image upload in flight swallows Cmd+V).
                # Images must add one .se-component.se-image; html chunks must
                # grow the .se-text paragraph count (SE merges consecutive
                # text pastes into one component, so component count is not
                # reliable for text).
                def editor_counts():
                    js = ("JSON.stringify({img: document.querySelectorAll("
                          "'.se-component.se-image').length, p: document."
                          "querySelectorAll('.se-component.se-text p').length})")
                    script = ('tell application "Google Chrome"\n'
                              'repeat with w in windows\n'
                              'repeat with t in tabs of w\n'
                              'if URL of t contains "/postwrite" then\n'
                              f'return execute t javascript "{js}"\n'
                              'end if\nend repeat\nend repeat\nend tell')
                    try:
                        import json as _json
                        out = subprocess.run(["osascript", "-e", script],
                                             capture_output=True, text=True, timeout=10)
                        return _json.loads(out.stdout.strip())
                    except Exception:
                        return None

                def wait_for_growth(kind, before, timeout=8.0):
                    """Poll until the relevant count grows; returns True/False."""
                    if before is None:
                        time.sleep(1.5 if kind == 'image' else 0.6)
                        return True  # verification unavailable — fall back to delay
                    deadline = time.time() + timeout
                    while time.time() < deadline:
                        now = editor_counts()
                        if now:
                            if kind == 'image' and now['img'] > before['img']:
                                return True
                            if kind == 'html' and now['p'] > before['p']:
                                return True
                        time.sleep(0.4)
                    return False

                for i, chunk in enumerate(chunks):
                    label = "Text" if chunk['type'] == 'html' else "Image"
                    print(f"[{i+1}/{len(chunks)}] Pasting {label}...", end=" ", flush=True)

                    for attempt in (1, 2, 3):
                        before = editor_counts()
                        if chunk['type'] == 'html':
                            migrate_from_url.copy_html_to_clipboard(chunk['content'])
                        elif chunk['type'] == 'image':
                            migrate_from_url.copy_image_file_to_clipboard(chunk['path'])
                        migrate_from_url.paste_cmd()
                        time.sleep(0.5 if chunk['type'] == 'html' else 1.0)
                        if wait_for_growth(chunk['type'], before):
                            print("OK" if attempt == 1 else f"OK (retry {attempt - 1})")
                            break
                        if attempt < 3:
                            print(f"\n    -> not registered, retrying ({attempt})...", end=" ", flush=True)
                            time.sleep(1.0)
                    else:
                        print("FAILED after 3 attempts — continuing")
            else:
                print("\n*** MANUAL MODE ***")
                print("Tip: Enable 'Terminal' in System Settings > Privacy > Accessibility availability to use Auto Mode next time.")
                
                for i, chunk in enumerate(chunks):
                    label = "Text" if chunk['type'] == 'html' else "Image"
                    preview = ""
                    if chunk['type'] == 'html':
                        # Show first 30 chars
                        import bs4
                        text_preview = bs4.BeautifulSoup(chunk['content'], 'html.parser').get_text().strip()[:30]
                        preview = f" ('{text_preview}...') "
                    
                    print(f"\n[{i+1}/{len(chunks)}] Next item: {label}{preview}")
                    input("Press Enter to copy to clipboard...")
                    
                    if chunk['type'] == 'html':
                        if migrate_from_url.copy_html_to_clipboard(chunk['content']):
                             print(f"-> Text Copied. Paste (Cmd+V) now.")
                    elif chunk['type'] == 'image':
                         if migrate_from_url.copy_image_file_to_clipboard(chunk['path']):
                             print(f"-> Image Copied. Paste (Cmd+V) now.")

            print("\n[SUCCESS] Migration Finished.")
        else:
            print("[ERROR] Failed to fetch/parse content.")
            
    except Exception as e:
        print(f"Error executing migration: {e}")

if __name__ == "__main__":
    run_migration()
    input("\nPress Enter to exit...")
