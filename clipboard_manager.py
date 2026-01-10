import AppKit

def get_pasteboard():
    return AppKit.NSPasteboard.generalPasteboard()

def get_clipboard_content():
    """Reads the clipboard and returns a dictionary with available types."""
    pb = get_pasteboard()
    types = pb.types()
    
    content = {}
    
    if AppKit.NSPasteboardTypeHTML in types:
        content['html'] = pb.stringForType_(AppKit.NSPasteboardTypeHTML)
    
    if AppKit.NSPasteboardTypeString in types:
        content['text'] = pb.stringForType_(AppKit.NSPasteboardTypeString)
        
    if AppKit.NSPasteboardTypeRTF in types:
        content['rtf'] = pb.dataForType_(AppKit.NSPasteboardTypeRTF)
        
    return content

def set_clipboard_content(html_content=None, text_content=None):
    """Sets the clipboard content with HTML and/or plain text."""
    pb = get_pasteboard()
    pb.clearContents()
    
    objects_to_write = []
    
    if html_content:
        # Create an NSPasteboardItem for HTML
        # In modern macOS, it's often better to just write objects directly if simple strings
        # But for mixed types, we might need to set string for type
        pb.setString_forType_(html_content, AppKit.NSPasteboardTypeHTML)
        
    if text_content:
        pb.setString_forType_(text_content, AppKit.NSPasteboardTypeString)
        
    return True

def debug_clipboard_types():
    """Prints all types currently in the clipboard."""
    pb = get_pasteboard()
    print("Available Clipboard Types:")
    for t in pb.types():
        print(f"- {t}")
