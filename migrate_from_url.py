import sys
import os
import json
import requests
from bs4 import BeautifulSoup
import AppKit
import hashlib
import time
import re

# Configuration
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(TEMP_DIR, exist_ok=True)

# Sidecar file consumed by inject_code_blocks.py (pass 2: native code components)
CODE_BLOCKS_JSON = "/tmp/naver_code_blocks.json"

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
    """Backwards-compatible wrapper — returns just the content soup."""
    post = fetch_post(url)
    return post['content']


def fetch_post(url):
    """Fetch a Tistory post and return both content soup and post metadata.

    Returns: dict with keys
        - 'content': BeautifulSoup of the article body (or None on failure)
        - 'source_url': the URL passed in
        - 'published_iso': ISO 8601 publish timestamp from
          <meta property="article:published_time"> (or None if absent)
    """
    print(f"Fetching URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return {'content': None, 'source_url': url, 'published_iso': None, 'tags': []}

    full_soup = BeautifulSoup(resp.text, 'html.parser')

    # Target selectors based on Tistory structure
    content_candidate = full_soup.select_one('.tt_article_useless_p_margin')
    if not content_candidate:
        content_candidate = full_soup.select_one('.entry-content')
    if not content_candidate:
        content_candidate = full_soup.select_one('article')

    if not content_candidate:
        print("Could not find content container (looked for .tt_article_useless_p_margin, .entry-content).")
        return {'content': None, 'source_url': url, 'published_iso': None, 'tags': []}

    # Cleanup: Remove scripts, ads, iframes
    for useless in content_candidate.select('script, iframe, ins, .adsbygoogle, .revenue_unit_wrap, .container_postbtn'):
        useless.decompose()

    pub_meta = full_soup.find('meta', attrs={'property': 'article:published_time'})
    published_iso = pub_meta.get('content') if pub_meta and pub_meta.has_attr('content') else None

    title_meta = full_soup.find('meta', attrs={'property': 'og:title'})
    post_title = title_meta.get('content') if title_meta and title_meta.has_attr('content') else None

    # Tags: Tistory renders them as <div class="tags"><a rel="tag">...</a>, ...</div>
    tags = []
    tag_container = full_soup.select_one('div.tags')
    if tag_container:
        for a in tag_container.select('a[rel="tag"]'):
            t = a.get_text(strip=True)
            if t and t not in tags:
                tags.append(t)

    return {'content': content_candidate, 'source_url': url, 'published_iso': published_iso, 'tags': tags, 'title': post_title}

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

# Naver SmartEditor-compatible HTML styles, copied from
# giraffe-skills/blog/scripts/paste_to_naver.py so this script and the /blog
# skill produce visually identical output (yellow-highlighted bold headings +
# explicit body span reset to block style bleed from headings).
HEADING_SPAN_STYLE = "font-size:24px;background-color:#fff593;"
BODY_SPAN_STYLE = (
    "font-size:15px;font-weight:normal;background-color:transparent;"
    "color:#212529;"
)
BARRIER_HTML = '<p><br></p>'


def _html_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _heading_html(text):
    """Emit a yellow-highlighted bold heading paragraph.

    Native se-sectionTitle 컴포넌트 시도는 실패 (네이버 paste sanitizer 가
    chromium source-rfh-token + 자체 input-buffer 토큰을 검사해서 외부
    매크로에서 들어온 component markup 을 모두 본문으로 normalize 함 —
    외부에서 native 컴포넌트 inject 원천 차단). 시각적 헤딩 표시만이라도
    유지하기 위해 /blog 스킬과 동일한 노란 배경(#fff593) 24px 볼드로 복귀.
    컴포넌트 타입은 "본문"이지만 시각적으로 명확히 구분됨.
    """
    return (
        f'<p><span style="{HEADING_SPAN_STYLE}"><b>{_html_escape(text)}</b></span></p>'
        + BARRIER_HTML
    )


def _body_html_from_text(text_with_br_tokens):
    """Wrap a paragraph of text into a body-styled <p>. The input may contain
    raw __BR_TOKEN__ markers which are converted to <br> after escaping so the
    surrounding text stays HTML-safe."""
    escaped = _html_escape(text_with_br_tokens).replace('__BR_TOKEN__', '<br>')
    return f'<p><span style="{BODY_SPAN_STYLE}">{escaped}</span></p>'


BODY_BOLD_SPAN_STYLE = (
    "font-size:15px;font-weight:bold;background-color:transparent;"
    "color:#212529;"
)


def _inline_segments(element):
    """Walk element children and yield (text, bold) tuples. <b>/<strong>
    descendants flip the bold flag; <br> becomes a __BR_TOKEN__ marker."""
    segments = []

    def walk(node, bold):
        for child in node.children:
            if child.name is None:
                segments.append((str(child), bold))
            elif child.name == 'br':
                segments.append(('__BR_TOKEN__', bold))
            elif child.name in ('b', 'strong'):
                walk(child, True)
            else:
                walk(child, bold)

    walk(element, False)
    return segments


_WS_RE = re.compile(r'[ \t\n\r]+')


def _body_html_from_element(element):
    """Body paragraph that preserves inline <b>/<strong> + <br>.

    Outputs alternating <span> segments inside a single <p>: normal text uses
    BODY_SPAN_STYLE (with font-weight:normal to block heading bleed); bold
    text uses BODY_BOLD_SPAN_STYLE which overrides weight. Whitespace inside
    each text node is collapsed to single spaces, but   is preserved."""
    raw_segments = _inline_segments(element)
    if not raw_segments:
        return ''

    # Merge consecutive same-bold segments so we emit one <span> per run.
    merged = []
    for text, bold in raw_segments:
        if merged and merged[-1][1] == bold:
            merged[-1] = (merged[-1][0] + text, bold)
        else:
            merged.append([text, bold])

    # Collapse whitespace within each segment, but keep __BR_TOKEN__ intact.
    normalized = []
    for text, bold in merged:
        pieces = text.split('__BR_TOKEN__')
        pieces = [_WS_RE.sub(' ', p) for p in pieces]
        text = '__BR_TOKEN__'.join(pieces)
        normalized.append([text, bold])

    # Trim leading/trailing whitespace across the whole paragraph.
    if normalized:
        normalized[0][0] = normalized[0][0].lstrip()
    if normalized:
        normalized[-1][0] = normalized[-1][0].rstrip()
    normalized = [(t, b) for t, b in normalized if t]
    if not normalized:
        return ''

    parts = []
    for text, bold in normalized:
        escaped = _html_escape(text).replace('__BR_TOKEN__', '<br>')
        style = BODY_BOLD_SPAN_STYLE if bold else BODY_SPAN_STYLE
        parts.append(f'<span style="{style}">{escaped}</span>')
    return f'<p>{"".join(parts)}</p>'


def _build_footer_html(source_url, published_iso, tags=None):
    """Build the Tistory-migration footer HTML.

    Format (matches user spec):
        <blank>
        \ud574\ub2f9 \uae00\uc740 \ud2f0\uc2a4\ud1a0\ub9ac \ube14\ub85c\uadf8 <URL>\uc758 \uae00\uc744 \ub9c8\uc774\uadf8\ub808\uc774\uc158\ud55c \uae00\uc785\ub2c8\ub2e4.
        <blank>
        \uc6d0\ubcf8 \uc791\uc131\uc77c : YYYY\ub144 MM\uc6d4 DD\uc77c

    Returns the assembled HTML string, or '' if neither value is provided.
    """
    if not source_url and not published_iso and not tags:
        return ''
    parts = [BARRIER_HTML, BARRIER_HTML]
    if source_url:
        u = _html_escape(source_url)
        parts.append(
            f'<p><span style="{BODY_SPAN_STYLE}">'
            f'\ud574\ub2f9 \uae00\uc740 \ud2f0\uc2a4\ud1a0\ub9ac \ube14\ub85c\uadf8 '
            f'<a href="{u}">{u}</a>'
            f'\uc758 \uae00\uc744 \ub9c8\uc774\uadf8\ub808\uc774\uc158\ud55c \uae00\uc785\ub2c8\ub2e4.</span></p>'
        )
    if published_iso:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(published_iso)
            date_kr = dt.strftime('%Y\ub144 %m\uc6d4 %d\uc77c')
        except Exception:
            date_kr = published_iso
        parts.append(
            f'<p><span style="{BODY_SPAN_STYLE}">'
            f'\uc6d0\ubcf8 \uc791\uc131\uc77c : {_html_escape(date_kr)}</span></p>'
        )
    if tags:
        # Plain-text hashtag line. Internal whitespace inside each tag is removed
        # so multi-word Tistory tags (e.g. "\uc81c\ub2e4 \uc0ac\ub2f9 \uacf5\ub7b5") become a single
        # hashtag token (#\uc81c\ub2e4\uc0ac\ub2f9\uacf5\ub7b5). These are NOT real Naver tags \u2014
        # they're visual decoration only; the user must enter real tags in the
        # SmartEditor sidebar separately.
        import re as _re
        hashtags = ' '.join('#' + _re.sub(r'\s+', '', t) for t in tags if t and t.strip())
        if hashtags:
            parts.append(BARRIER_HTML)
            parts.append(
                f'<p><span style="{BODY_SPAN_STYLE}">{_html_escape(hashtags)}</span></p>'
            )
    return ''.join(parts)


def split_content_into_chunks(soup, source_url=None, published_iso=None, tags=None):
    """Split the parsed Tistory content into ordered chunks for the paste loop.

    Each chunk is either {'type': 'html', 'content': str} or
    {'type': 'image', 'path': str}. Top-level elements are walked once and
    classified:
      - <hr>                \u2192 '<hr>' literal (Naver promotes this to its
                              SmartEditor horizontal-line block on paste)
      - <h1>..<h6>          \u2192 yellow-highlighted bold heading + barrier <p>
      - element with <img>  \u2192 flush html buffer, emit image chunk(s)
      - <blockquote>/other  \u2192 body-styled paragraph

    If source_url and/or published_iso are provided, a Tistory-migration
    footer chunk is appended after all body chunks.
    """
    chunks = []
    current_html = ""
    code_blocks = []

    for element in list(soup.children):
        if element.name is None:
            text = str(element).strip()
            if text:
                current_html += _body_html_from_text(text)
            continue

        # Section divider \u2014 preserve as Naver paste-time hr.
        # native \ucef4\ud3ec\ub10c\ud2b8(se-horizontalLine se-l-line3 \ub4f1) \ub9c8\ud06c\uc5c5 \uc2dc\ub3c4\ub294
        # sanitizer\uac00 line type class\ub97c \ubaa8\ub450 default \ub85c \ub5a8\uc5b4\ub728\ub824 \uc2e4\ud328.
        # \uc815\ud655\ud55c paste payload \ub97c \uc54c\uc544\ub0bc \ubc29\ubc95\uc774 \uc5c6\uc5b4 \ub2e8\uc21c <hr> \ub85c \uc720\uc9c0.
        if element.name == 'hr':
            current_html += '<hr>'
            continue

        # Headings \u2014 Tistory wraps section titles in <h1>..<h4>, sometimes
        # with an inner <span style="background-color:#f6e199;">. We always
        # convert to the blog skill's canonical highlighted heading.
        if element.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            text = element.get_text(separator=' ', strip=True)
            if text:
                current_html += _heading_html(text)
            continue

        # Code blocks \u2014 Tistory <pre> \u2192 placeholder paragraph [[CODE-n]].
        # paste sanitizer \ub54c\ubb38\uc5d0 \ucf54\ub4dc \ucef4\ud3ec\ub10c\ud2b8\ub3c4 paste \ub85c\ub294 \uc8fc\uc785 \ubd88\uac00 \u2014
        # \uc6d0\ubcf8 \ucf54\ub4dc\ub294 CODE_BLOCKS_JSON \uc73c\ub85c \ub118\uae30\uace0, paste \uc885\ub8cc \ud6c4
        # inject_code_blocks.py (pass 2) \uac00 placeholder \uc790\ub9ac\uc5d0 native
        # SmartEditor \ucf54\ub4dc \ucef4\ud3ec\ub10c\ud2b8\ub97c \uc0bd\uc785\ud55c\ub2e4.
        pres = [element] if element.name == 'pre' else element.find_all('pre')
        if pres:
            for pre in pres:
                code_blocks.append({
                    'index': len(code_blocks) + 1,
                    'language': ' '.join(pre.get('class') or []) or None,
                    'code': pre.get_text(),
                })
                current_html += _body_html_from_text(f'[[CODE-{len(code_blocks)}]]')
            continue

        # Images \u2014 split out as separate paste chunks so Naver uploads each
        imgs = element.find_all('img')
        if imgs:
            for img in imgs:
                if current_html.strip():
                    chunks.append({'type': 'html', 'content': current_html})
                    current_html = ""
                src = img.get('data-url') or img.get('data-src') or img.get('src')
                if not src:
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                local_path = download_image(src)
                if local_path:
                    chunks.append({'type': 'image', 'path': local_path})
            continue

        # Generic block \u2014 preserve inline <b>/<strong> + <br>, emit body paragraph
        html_para = _body_html_from_element(element)
        if html_para:
            current_html += html_para
            continue
        # Tistory uses <p>&nbsp;</p> for visual blank lines \u2014 keep as barrier
        if element.name in ('p', 'div', 'br'):
            original = element.get_text()
            if '\u00a0' in original or '&nbsp;' in str(element):
                current_html += BARRIER_HTML

    if current_html.strip():
        chunks.append({'type': 'html', 'content': current_html})

    footer = _build_footer_html(source_url, published_iso, tags=tags)
    if footer:
        chunks.append({'type': 'html', 'content': footer})

    if code_blocks:
        try:
            with open(CODE_BLOCKS_JSON, 'w', encoding='utf-8') as f:
                json.dump(code_blocks, f, ensure_ascii=False, indent=2)
            print(f"[CODE] {len(code_blocks)} code block(s) -> [[CODE-n]] placeholders")
            print(f"[CODE] source saved: {CODE_BLOCKS_JSON}")
            print("[CODE] after pasting finishes, run: python3 inject_code_blocks.py")
        except OSError as e:
            print(f"[CODE][WARN] could not write {CODE_BLOCKS_JSON}: {e}")

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
