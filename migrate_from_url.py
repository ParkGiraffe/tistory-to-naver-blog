import sys
import os
import requests
from bs4 import BeautifulSoup
import AppKit
import hashlib
import time
import re

# Configuration
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(TEMP_DIR, exist_ok=True)

def clear_temp_images():
    """Clears all files in the temporary images directory."""
    if os.path.exists(TEMP_DIR):
        print(f"Cleaning previous images in {TEMP_DIR}...")
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

def get_pasteboard():
    return AppKit.NSPasteboard.generalPasteboard()

def download_image(url):
    """Downloads image and returns local path."""
    try:
        # Generate filename from hash of URL
        filename = hashlib.md5(url.encode('utf-8')).hexdigest() + ".jpg"
        filepath = os.path.join(TEMP_DIR, filename)

        # Allow re-download for verification or check size? 
        # For now, if it exists, assume it's fine but print it.
        if os.path.exists(filepath):
            return filepath

        print(f"Downloading: {url}...")
        
        # Tistory/Kakao CDN sometimes needs headers or just handles straightforward get
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://tistory.com/' 
        }
        
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"Saved: {filename}")
            return filepath
        else:
            print(f"Failed to download {url}: Status {response.status_code}")
            
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return None

def fetch_and_parse(url):
    print(f"Fetching URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Target selectors based on Tistory structure
    # Common ones: .tt_article_useless_p_margin, .entry-content, .article_view
    content_candidate = soup.select_one('.tt_article_useless_p_margin')
    if not content_candidate:
        content_candidate = soup.select_one('.entry-content')
    if not content_candidate:
        content_candidate = soup.select_one('article')
        
    if not content_candidate:
        print("Could not find content container (looked for .tt_article_useless_p_margin, .entry-content).")
        return None
        
    # Cleanup: Remove scripts, ads, iframes
    for useless in content_candidate.select('script, iframe, ins, .adsbygoogle, .revenue_unit_wrap, .container_postbtn'):
        useless.decompose()
        
    return content_candidate

import plistlib

def create_web_archive(html_content, images):
    """
    Creates a WebArchive dictionary structure.
    html_content: str
    images: list of dict {'url': str, 'data': bytes, 'mime': str}
    """
    main_resource = {
        'WebResourceData': html_content.encode('utf-8'),
        'WebResourceFrameName': '',
        'WebResourceMIMEType': 'text/html',
        'WebResourceTextEncodingName': 'UTF-8',
        'WebResourceURL': 'about:blank'
    }
    
    subresources = []
    for img in images:
        subresources.append({
            'WebResourceData': img['data'],
            'WebResourceMIMEType': img['mime'],
            'WebResourceResponse': None, # Optional
            'WebResourceURL': img['url']
        })
        
    return {
        'WebMainResource': main_resource,
        'WebSubresources': subresources
    }

def process_content_for_webarchive(soup):
    """
    Downloads images and prepares them for WebArchive.
    Returns:
        html_str: The modified HTML string.
        images: List of image objects for the archive.
    """
    images = []
    
    # Process standard <img> tags
    for img in soup.find_all('img'):
        src = img.get('src')
        if not src:
            continue
            
        # Handle Tistory/Kakao specific image handling
        if img.get('data-url'):
            src = img.get('data-url')
        elif img.get('data-src'):
            src = img.get('data-src')
            
        if src.startswith('//'):
            src = 'https:' + src
            
        if src.startswith(('http://', 'https://')):
            local_path = download_image(src)
            if local_path:
                try:
                    with open(local_path, "rb") as f:
                        img_data = f.read()
                    
                    # Strategy Change:
                    # Use absolute local 'file://' URI.
                    # This mimics pasting from MS Word or Pages.
                    # Naver Smart Editor often treats file:// URIs as "This is a local file, I should upload it" 
                    # IF the clipboard data supports it (which WebArchive does).
                    
                    # Note: We need absolute path.
                    abs_path = os.path.abspath(local_path)
                    file_url = f"file://{abs_path}"

                    # Determine mime
                    ext = os.path.splitext(local_path)[1].lower()
                    mime = "image/jpeg"
                    if ext == ".png": mime = "image/png"
                    elif ext == ".gif": mime = "image/gif"
                    
                    images.append({
                        'url': file_url, # Key: Local File URL
                        'data': img_data,
                        'mime': mime
                    })
                    
                    # Update the IMG tag in HTML to match this local URL
                    img['src'] = file_url
                    
                    # Update style for consistency
                    img['style'] = "max-width: 100%; display: block; margin: 10px 0;"
                    # Clear attributes that might confuse the editor (lazy loading etc)
                    for attr in ['srcset', 'data-src', 'data-url', 'loading', 'onerror']:
                        if img.has_attr(attr):
                            del img[attr]
                            
                except Exception as e:
                    print(f"Error processing image {local_path}: {e}")

    return str(soup), images

def write_multi_format_to_clipboard(web_archive_dict, html_content, plain_text):
    """Writes Text, HTML, and WebArchive to clipboard simultaneously."""
    try:
        pb = get_pasteboard()
        pb.clearContents()
        
        # 1. Prepare WebArchive Data
        archive_data = plistlib.dumps(web_archive_dict, fmt=plistlib.FMT_BINARY)
        ns_archive_data = AppKit.NSData.dataWithBytes_length_(archive_data, len(archive_data))
        
        # 2. Prepare HTML Data
        # For public.html, we might want to use Base64 images if possible, 
        # but since that failed, we stick to the HTML that worked best for text or whatever the user validated.
        # Actually, let's use the HTML that matches the WebArchive structure (URLs pointing to subresources).
        html_data = html_content.encode('utf-8')
        ns_html_data = AppKit.NSData.dataWithBytes_length_(html_data, len(html_data))
        
        # 3. Prepare Plain Text
        # ns_text = str(plain_text) # AppKit handles strings directly usually
        
        # Write Objects
        # We need to use declareTypes_owner_ (deprecated) or simply writeObjects_ with custom data
        # Using specific setData_forType_ calls is more explicit for multi-format.
        
        # We must declare types first
        types = [
            "com.apple.webarchive", 
            "public.html", 
            "public.utf8-plain-text",
            AppKit.NSPasteboardTypeString
        ]
        pb.declareTypes_owner_(types, None)
        
        pb.setData_forType_(ns_archive_data, "com.apple.webarchive")
        pb.setData_forType_(ns_html_data, "public.html")
        pb.setString_forType_(plain_text, "public.utf8-plain-text")
        pb.setString_forType_(plain_text, AppKit.NSPasteboardTypeString)
        
        return True
    except Exception as e:
        print(f"Error writing to clipboard: {e}")
        return False

def split_content_into_chunks(soup):
    """
    Splits the soup content into a list of chunks:
    [{'type': 'html', 'content': '...'}, {'type': 'image', 'path': '...'}]
    """
    chunks = []
    current_html_parts = []
    
    # We iterate over top-level elements of the content
    # If content_candidate is a container, get its children
    # This assumes a flat structure mainly (p, div, figure...)
    
    # Flatten checks: Tistory often puts img inside figure or p
    # We want to break at any IMG.
    
    # Recursive walker or logical split? 
    # Logical split: stringify everything until an img, then img, then stringify...
    # But simple string split might break tags.
    # Better: Iterate recursive, but flattened? 
    # Let's iterate find_all(['p', 'div', 'figure', 'img', 'table', 'h1', 'h2', 'h3', 'ul', 'ol', 'blockquote']) recursive=False?
    # No, 'img' might be deep.
    
    # Robust approach: 
    # 1. Find all `img` tags.
    # 2. Use them as delimiters.
    # 3. Everything before img1 is HTML chunk 1.
    # 4. img1 is Image chunk 1.
    # 5. Between img1 and img2 is HTML chunk 2...
    
    # Using `soup.decode_contents()` gives full string.
    # We can use regex to split, but that's risky for HTML.
    
    # Alternative:
    # Walk the tree. If we hit an IMG, we flush the current buffer and yield an Image chunk.
    # This is tricky with nesting.
    
    # Let's try a simplified approach:
    # 1. Identify all `img` nodes.
    # 2. Create a list of "Nodes to Process".
    # 3. If a node contains an img, decompose it? No.
    
    # Best approach for "One Line by One Line" macro as requested:
    # Just iterate top-level tags!
    # Tistory structure:
    # <p>Text</p>
    # <figure><img></figure>
    # <p>Text</p>
    
    # If the img is inside a P or Figure, we treat that whole block as "Image" if it's dominant?
    # User said "Text or line -> Photo".
    
    top_level_elements = list(soup.children)
    current_html = ""
    
    for element in top_level_elements:
        if element.name is None:
            # NavigableString (text/whitespace)
            text = str(element)
            if text.strip():
                current_html += text
            continue
            
        # Check if element HAS an image
        imgs = element.find_all('img')
        if imgs:
            # If it has images, we might need to split this element if it also has text?
            # Usually Tistory wraps img in <figure> or <p> with just the image.
            # If there is text + image in one <p>, it's hard to separate cleanly without destructuring.
            # For now, let's assuming images are block-levelish.
            
            # If multiple images?
            for img in imgs:
                # Flush previous html
                if current_html.strip():
                    chunks.append({'type': 'html', 'content': current_html})
                    current_html = ""
                
                src = img.get('src') or img.get('data-url')
                if src:
                    # Resolve protocol
                    if src.startswith('//'): src = 'https:' + src
                    
                    local_path = download_image(src)
                    if local_path:
                        chunks.append({'type': 'image', 'path': local_path})
            
            # What if there was text *around* the image in that same P?
            # We lose it if we don't handle it. 
            # But extracting text from a node ignoring img is easy (get_text), but formatting...
            # This 'simple splitter' assumes images are their own blocks. 
            # If mixed, we might skip the text.
            # Given "TistoryToNaver", usually distinct blocks.
        else:
            # Just HTML
            # Strategy: preserve layout but remove style.
            
            # 1. Protect <br>
            # We accept that 'element' might be modified, so we work on a copy if needed, 
            # but here modifying the soup in place is fine as we are consuming it.
            for br in element.find_all('br'):
                br.replace_with('__BR_TOKEN__')
            
            # 2. Get text
            # strip=True removes leading/trailing whitespace including &nbsp; if it's the only thing.
            clean_text = element.get_text(separator=' ', strip=True) 
            
            # Restore tokens
            clean_html_content = clean_text.replace('__BR_TOKEN__', '<br>')
            
            # 3. Check for specific Tistory "Empty Line" patterns if result is empty
            # Tistory often uses <p>&nbsp;</p> for blank lines.
            if not clean_html_content:
                # If it's a block element (p, div, blockquote) and has &nbsp;, treat as newline
                if element.name in ['p', 'div', 'blockquote', 'li', 'h1', 'h2', 'h3', 'h4']:
                    original_text = element.get_text() # Raw text without strip
                    if '\u00a0' in original_text or '&nbsp;' in str(element):
                        clean_html_content = "<br>"
            
            if clean_html_content:
                # Wrap in P to ensure block behavior in Naver
                # Naver Editor likes <p> for lines.
                current_html += f"<p>{clean_html_content}</p>"
            
    # Flush remaining
    if current_html.strip():
        chunks.append({'type': 'html', 'content': current_html})
        
    return chunks

def copy_image_file_to_clipboard(filepath):
    """Copies the FILE itself to clipboard (NSFilenamesPboardType)."""
    if not os.path.exists(filepath):
        print(f"[ERROR] Image file not found: {filepath}")
        return False
        
    pb = get_pasteboard()
    pb.clearContents()
    
    # Logic for copying "File" in macOS (so it acts like a file copied from Finder)
    # We use 'NSFilenamesPboardType' (legacy but reliable) and 'public.file-url'
    
    # 1. URLs (modern)
    ns_url = AppKit.NSURL.fileURLWithPath_(filepath)
    pb.writeObjects_([ns_url])
    
    return True

def copy_html_to_clipboard(html_content):
    """Copies plain HTML string to clipboard."""
    # Wrap to stop bleeding and enforce encoding
    # Adding <meta charset='utf-8'> is crucial for partial HTML pastes.
    safe_html = f"""
    <html>
    <head><meta charset='utf-8'></head>
    <body style='font-family: -apple-system, sans-serif;'>
        {html_content}
        <br>
    </body>
    </html>
    """
    
    pb = get_pasteboard()
    pb.clearContents()
    
    # HTML Type
    ns_html = safe_html.encode('utf-8')
    ns_data = AppKit.NSData.dataWithBytes_length_(ns_html, len(ns_html))
    
    # Plain Text Fallback (so user can see something if HTML fails)
    # plain_text = BeautifulSoup(html_content, 'html.parser').get_text()
    
    types = ["public.html", AppKit.NSPasteboardTypeString]
    pb.declareTypes_owner_(types, None)
    
    pb.setData_forType_(ns_data, "public.html")
    pb.setString_forType_(html_content, AppKit.NSPasteboardTypeString) # Raw text fallback
    
    return True

import time
import subprocess

def paste_cmd():
    """Simulates Cmd+V using AppleScript with error checking."""
    # Give clipboard a moment to settle before pasting
    time.sleep(0.2)
    
    cmd = """
    osascript -e 'try' -e 'tell application "System Events" to key code 9 using command down' -e 'end try'
    """
    try:
        # Run synchronous and check for errors
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[ERROR] Auto-paste failed: {result.stderr.strip()}")
    except Exception as e:
        print(f"[ERROR] Paste command exception: {e}")



if __name__ == "__main__":
    main()
