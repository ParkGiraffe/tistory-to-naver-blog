from clipboard_manager import debug_clipboard_types, get_clipboard_content
import sys

def main():
    print("Analyzing clipboard content...")
    debug_clipboard_types()
    
    content = get_clipboard_content()
    
    if 'html' in content:
        print("\n--- HTML Content Sample (First 500 chars) ---")
        print(content['html'][:500])
    else:
        print("\nNo HTML content found.")
        
    if 'text' in content:
        print("\n--- Text Content Sample (First 100 chars) ---")
        print(content['text'][:100])
        
if __name__ == "__main__":
    main()
