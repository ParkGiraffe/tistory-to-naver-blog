import AppKit
import requests
from bs4 import BeautifulSoup
import os
import time
import hashlib
import sys

# Configuration
TEMP_DIR = os.path.expanduser("~/Desktop/Coding/TistoryToNaver/temp_images")
os.makedirs(TEMP_DIR, exist_ok=True)

def get_pasteboard():
    return AppKit.NSPasteboard.generalPasteboard()

def read_content_from_clipboard():
    """Reads clipboard, preferring HTML but falling back to Text."""
    pb = get_pasteboard()
    content = ""
    if AppKit.NSPasteboardTypeHTML in pb.types():
        content = pb.stringForType_(AppKit.NSPasteboardTypeHTML)
    elif AppKit.NSPasteboardTypeString in pb.types():
        content = pb.stringForType_(AppKit.NSPasteboardTypeString)
    return content

def download_image(url):
    """Downloads image and returns local path."""
    try:
        # Generate filename from hash of URL to avoid duplicates/invalid chars
        filename = hashlib.md5(url.encode('utf-8')).hexdigest() + ".jpg" # Assuming jpg for simplicity, headers check better
        filepath = os.path.join(TEMP_DIR, filename)

        if os.path.exists(filepath):
            return filepath

        print(f"Downloading: {url}...")
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"Saved image to: {filepath}")
            return filepath
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return None

def parse_tistory_tags(content):
    """
    Finds Tistory [##_Image|...] tags, downloads images, and replaces tags with <img src="...">.
    """
    import re
    
    # Regex to capture the Image block
    # Pattern: [##_Image|PATH_INFO|..._##]
    # We want to capture the whole tag to replace it, and the PATH_INFO to get the URL
    pattern = re.compile(r'\[##_Image\|(.*?)\|.*?_##\]', re.DOTALL)
    
    def replacer(match):
        path_info = match.group(1) # e.g. kage@.../img.jpg?cred...
        
        # Clean up path info to get the image URL
        # Logic: Replace 'kage@' with 'https://blog.kakaocdn.net/dn/' 
        # But we need to handle the structure carefully.
        # Example: kage@ID/path/file.jpg?...
        
        # Remove query params for clean download if possible, or keep them?
        # Let's try to keep them first, but Tistory usually works without.
        
        if path_info.startswith("kage@"):
            # kage@... -> https://blog.kakaocdn.net/dn/...
            # "kage@" is 5 chars.
            url_path = path_info[5:] 
            image_url = f"https://blog.kakaocdn.net/dn/{url_path}"
        else:
            # Fallback for other patterns if any (e.g. legacy)
            image_url = path_info
            
        print(f"Found Tistory Tag. URL: {image_url}")
        
        local_path = download_image(image_url)
        if local_path:
            # Return new HTML image tag
            return f'<img src="file://{local_path}" style="max-width:100%;">'
        
        return match.group(0) # Return original if failed

    # Execute regex substitution
    new_content = pattern.sub(replacer, content)
    
    # If the content was plain text, we should wrap it in basic HTML structure 
    # so NSAttributedString treats it as HTML
    if not content.strip().startswith("<html"):
        new_content = new_content.replace("\n", "<br>") # Preserve line breaks
        new_content = f"<html><body>{new_content}</body></html>"
        
    return new_content

def process_html(html_content):
    """Parses HTML, downloads images, replaces src with local file paths."""
    soup = BeautifulSoup(html_content, 'html.parser')
    updated = False
    
    # Identify images
    # Tistory images usually contain 'tistory.com' or 'kakaocdn.net' or 'daumcdn.net'
    # But generally we want to download ALL remote images to ensure they paste correctly
    for img in soup.find_all('img'):
        src = img.get('src')
        if src and src.startswith(('http://', 'https://')):
            local_path = download_image(src)
            if local_path:
                # Convert to file URL
                file_url = f"file://{local_path}"
                img['src'] = file_url
                # Remove srcset to force using the downloaded source
                if img.has_attr('srcset'):
                    del img['srcset']
                updated = True
                
    return str(soup) if updated else None

def write_to_clipboard_as_attributed_string(html_content):
    """Writes HTML to clipboard as NSAttributedString (Rich Text)."""
    data = html_content.encode('utf-8')
    ns_data = AppKit.NSData.dataWithBytes_length_(data, len(data))
    
    # Create NSAttributedString from HTML
    # PyObjC signature adjustment
    attr_str, doc_attrs = AppKit.NSAttributedString.alloc().initWithHTML_documentAttributes_(
        ns_data, None
    )
    
    # Check if object is created (PyObjC might return None or raise exception on real failure)
    if not attr_str:
        print(f"Error creating AttributedString")
        return False
        
    pb = get_pasteboard()
    pb.clearContents()
    pb.writeObjects_([attr_str])
    return True

def main():
    print("Reading clipboard...")
    content = read_content_from_clipboard()
    
    if not content:
        print("No content found in clipboard.")
        return

    print(f"Content found ({len(content)} chars). Processing...")
    
    # Check if it looks like Tistory HTML Source (contains [##_Image)
    if "[##_Image" in content:
        print("Detected Tistory HTML Source codes.")
        new_html = parse_tistory_tags(content)
    else:
        print("Standard HTML processing...")
        new_html = process_html(content)
    
    if new_html and new_html != content:
        print("Images processed and Content updated.")
        print("Updating clipboard with valid Rich Text...")
        if write_to_clipboard_as_attributed_string(new_html):
            print("Success! Clipboard updated.")
            print("IMPORTANT: If specific images are still missing, check if their Tistory links are expired.")
        else:
            print("Failed to write to clipboard.")
    else:
        print("No remote images/tags found or processed.")

if __name__ == "__main__":
    main()
