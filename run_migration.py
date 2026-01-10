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
        migrate_from_url.fetch_and_parse(url) # Verify fetching logic
        # Actually calling main logic via subprocess or direct call
        # Since migrate_from_url is importable, let's use its main logic but refactored or just call its functions.
        # Calling its main() might rely on argv, so let's set argv or call logic directly.
        
        # Better: use the functions directly
        soup = migrate_from_url.fetch_and_parse(url)
        if soup:
            print("Splitting content into chunks for Sequential Macro...")
            chunks = migrate_from_url.split_content_into_chunks(soup)
            print(f"Prepared {len(chunks)} chunks (Text/Images).")
            
            print("\n*** CHOICE ***")
            print("1. Auto Mode (Requires Accessibility Permission for Terminal)")
            print("2. Manual Mode (Press Enter to copy each part, then you Cmd+V)")
            mode = input("Select Mode (1/2): ").strip()
            
            if mode == "1":
                print("\n*** AUTO MACRO STARTING In 3 Seconds ***")
                print("Focus on Naver Editor NOW!")
                time.sleep(3)
                for i, chunk in enumerate(chunks):
                    label = "Text" if chunk['type'] == 'html' else "Image"
                    print(f"[{i+1}/{len(chunks)}] Pasting {label}...")
                    
                    if chunk['type'] == 'html':
                        migrate_from_url.copy_html_to_clipboard(chunk['content'])
                    elif chunk['type'] == 'image':
                        migrate_from_url.copy_image_file_to_clipboard(chunk['path'])
                    
                    migrate_from_url.paste_cmd()
                    time.sleep(0.5 if chunk['type'] == 'html' else 1.0)
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
