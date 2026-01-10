import clipboard_manager
import fix_clipboard
import os
import shutil
import time

def test_fix():
    print("--- Starting Test ---")
    
    # Clean temp dir
    if os.path.exists(fix_clipboard.TEMP_DIR):
        shutil.rmtree(fix_clipboard.TEMP_DIR)
    os.makedirs(fix_clipboard.TEMP_DIR)
    
    # 1. Seed Clipboard with Mock Tistory HTML
    # Using a reliable image source for testing
    test_image_url = "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png" 
    mock_html = f'<html><body><h1>Migrated Post</h1><p>Image below:</p><img src="{test_image_url}"></body></html>'
    
    print("Seeding clipboard with mock HTML...")
    clipboard_manager.set_clipboard_content(html_content=mock_html)
    
    # Verify Seed
    content = clipboard_manager.get_clipboard_content()
    if 'html' not in content:
        print("FAIL: Could not seed clipboard.")
        return
        
    print("Clipboard seeded. Running implementation...")
    
    # 2. Run the Fixer
    fix_clipboard.main()
    
    # 3. Verify Result
    print("\n--- Verifying Result ---")
    content = clipboard_manager.get_clipboard_content()
    
    # Check if files exist in temp
    files = os.listdir(fix_clipboard.TEMP_DIR)
    print(f"Downloaded files: {files}")
    
    if len(files) == 0:
        print("FAIL: No images downloaded.")
    else:
        print("PASS: Image downloaded.")
        
    # Check clipboard types
    # If successful, we expect RTF or HTML that references local files
    print("New Clipboard Types:")
    clipboard_manager.debug_clipboard_types()
    
    # Note: When we write NSAttributedString, it usually provides multiple types (RTF, String, etc.)
    # We can check if 'public.rtf' or 'text' is present.
    
    if 'rtf' in content or 'NeXT rich text format v1.0 pasteboard type' in clipboard_manager.get_pasteboard().types():
         print("PASS: Clipboard contains RTF data (Rich Text).")
    else:
         print("WARNING: RTF type not explicitly found (might be under a diverse type name).")

if __name__ == "__main__":
    test_fix()
