import clipboard_manager
import fix_clipboard
import os
import shutil
import time

def test_tistory_tag():
    print("--- Starting Tistory Tag Test ---")
    
    # Clean temp dir
    if os.path.exists(fix_clipboard.TEMP_DIR):
        shutil.rmtree(fix_clipboard.TEMP_DIR)
    os.makedirs(fix_clipboard.TEMP_DIR)
    
    # 1. Seed Clipboard with Mock Tistory Code
    # The URL in the tag will be a real image to test download
    # We use a known working image but wrap it in the Tistory compatible format
    # The fixer logic: kage@REST -> https://blog.kakaocdn.net/dn/REST
    # So we need a real Kakaocdn URL to test fully, or just any URL if we bypass the check?
    # The logic *forces* kage@ replacement.
    # Let's use a real Tistory image URL from the user's snippet to see if it even exists/works
    # "https://blog.kakaocdn.net/dn/cTmR8T/btszOPbh0Y3/AAAAAAAAAAAAAAAAAAAAAOYdwfLU72pymdi512ZG_EfIJHiaWIZk-McyQ5q_l_S6/img.jpg"
    
    real_path_segment = "cTmR8T/btszOPbh0Y3/AAAAAAAAAAAAAAAAAAAAAOYdwfLU72pymdi512ZG_EfIJHiaWIZk-McyQ5q_l_S6/img.jpg"
    mock_input = f"""
    Here is an image:
    [##_Image|kage@{real_path_segment}|CDM|1.3|{{...}}_##]
    End of text.
    """
    
    print("Seeding clipboard with Mock Tistory Source Code...")
    clipboard_manager.set_clipboard_content(text_content=mock_input)
    
    # 2. Run the Fixer
    fix_clipboard.main()
    
    # 3. Verify Result
    print("\n--- Verifying Result ---")
    files = os.listdir(fix_clipboard.TEMP_DIR)
    print(f"Downloaded files: {files}")
    
    if len(files) > 0:
        print("PASS: Image downloaded from Tistory CDN.")
    else:
        print("FAIL: No images downloaded.")
        
    # Check if content looks like HTML now
    content = clipboard_manager.get_clipboard_content()
    # We expect HTML in 'html' or RTF types.
    # Since we are writing NSAttributedString, we can't easily read back the HTML string directly via simple types 
    # unless we use 'public.html' text if provided.
    # But let's check if the script claimed success.

if __name__ == "__main__":
    test_tistory_tag()
