#!/usr/bin/env python3
import customtkinter as ctk
import threading
import sys
import os
import subprocess
from tkinter import messagebox

# Add the current directory to sys.path so we can import migrate_from_url
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import migrate_from_url

ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class TistoryMigratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Tistory to Naver Blog Migrator")
        self.geometry("600x550")
        self.minsize(500, 500)

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Top Frame (URL Input) ---
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.top_frame.grid_columnconfigure(0, weight=1)

        self.url_label = ctk.CTkLabel(self.top_frame, text="Tistory Post URL:", font=ctk.CTkFont(size=14, weight="bold"))
        self.url_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        self.url_entry = ctk.CTkEntry(self.top_frame, placeholder_text="https://yourblog.tistory.com/123", width=400)
        self.url_entry.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")

        self.paste_btn = ctk.CTkButton(self.top_frame, text="Paste", width=80, command=self.paste_from_clipboard)
        self.paste_btn.grid(row=1, column=1, padx=(0, 10), pady=(5, 10))

        # --- Middle Frame (Options) ---
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.mode_label = ctk.CTkLabel(self.options_frame, text="Migration Mode:", font=ctk.CTkFont(size=14, weight="bold"))
        self.mode_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")

        self.mode_var = ctk.StringVar(value="manual")

        self.manual_radio = ctk.CTkRadioButton(self.options_frame, text="Manual Mode (Step-by-step Cmd+V)", variable=self.mode_var, value="manual")
        self.manual_radio.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        self.auto_radio = ctk.CTkRadioButton(self.options_frame, text="Auto Mode (Requires Accessibility Permissions)", variable=self.mode_var, value="auto")
        self.auto_radio.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="w")

        # --- Bottom Frame (Logs and Action) ---
        self.log_textbox = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(size=12))
        self.log_textbox.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        self.log_textbox.insert("0.0", "Welcome to Tistory to Naver Blog Migrator.\nReady.\n")
        self.log_textbox.configure(state="disabled")

        self.start_btn = ctk.CTkButton(self, text="Start Migration", font=ctk.CTkFont(size=15, weight="bold"), height=40, command=self.start_migration_thread)
        self.start_btn.grid(row=3, column=0, padx=20, pady=(10, 20), sticky="ew")

        self.migration_thread = None

    def log(self, message):
        """Helper to safely append text to the log box."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
        # Force update to show changes immediately if called from main thread, 
        # but since we'll call from another thread, we should use after()
        self.update_idletasks()

    def paste_from_clipboard(self):
        try:
            import AppKit
            pb = AppKit.NSPasteboard.generalPasteboard()
            content = pb.stringForType_(AppKit.NSPasteboardTypeString)
            if content:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, content)
        except Exception as e:
            self.log(f"Error reading clipboard: {e}")

    def start_migration_thread(self):
        if self.migration_thread and self.migration_thread.is_alive():
            messagebox.showwarning("Warning", "Migration is already running!")
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL.")
            return

        mode = self.mode_var.get()
        
        self.start_btn.configure(state="disabled", text="Running...")
        self.log("\n" + "="*40)
        
        self.migration_thread = threading.Thread(target=self.run_migration_logic, args=(url, mode))
        self.migration_thread.daemon = True
        self.migration_thread.start()

    def run_migration_logic(self, url, mode):
        try:
            self.log("Cleaning temporary images...")
            migrate_from_url.clear_temp_images()

            self.log(f"Fetching and parsing URL: {url}")
            soup = migrate_from_url.fetch_and_parse(url)
            
            if not soup:
                self.log("[ERROR] Failed to fetch or parse content.")
                self.reset_ui()
                return

            self.log("Splitting content into chunks for Sequential Macro...")
            chunks = migrate_from_url.split_content_into_chunks(soup)
            self.log(f"Prepared {len(chunks)} chunks (Text/Images).")

            if mode == "auto":
                self.log("\n*** AUTO MACRO STARTING In 3 Seconds ***")
                self.log("Focus on Naver Editor NOW!")
                import time
                for i in range(3, 0, -1):
                    self.log(f"Starting in {i}...")
                    time.sleep(1)

                for i, chunk in enumerate(chunks):
                    label = "Text" if chunk['type'] == 'html' else "Image"
                    self.log(f"[{i+1}/{len(chunks)}] Pasting {label}...")
                    
                    if chunk['type'] == 'html':
                        migrate_from_url.copy_html_to_clipboard(chunk['content'])
                    elif chunk['type'] == 'image':
                        migrate_from_url.copy_image_file_to_clipboard(chunk['path'])
                    
                    migrate_from_url.paste_cmd()
                    time.sleep(0.5 if chunk['type'] == 'html' else 1.0)
                
                self.log("\n[SUCCESS] Auto Migration Finished.")
            else:
                self.log("\n*** MANUAL MODE ***")
                self.log("You must press 'Next Step' to copy each chunk to the clipboard, then paste (Cmd+V) into Naver Editor.")
                
                # In a GUI, manual mode block means pausing the thread and waiting for user input.
                # To do this gracefully, we pop up a secondary window or use a threading Event.
                
                # Simple implementation: we'll use a messagebox for each step, acting as "Press Enter"
                for i, chunk in enumerate(chunks):
                    label = "Text" if chunk['type'] == 'html' else "Image"
                    preview = ""
                    if chunk['type'] == 'html':
                        import bs4
                        text_preview = bs4.BeautifulSoup(chunk['content'], 'html.parser').get_text().strip()[:30]
                        preview = f" ('{text_preview}...') "
                    
                    msg = f"[{i+1}/{len(chunks)}] Next item: {label}{preview}\n\nClick OK to copy to clipboard, then go to Naver Editor and press Cmd+V to paste."
                    self.log(f"Waiting for user for part {i+1}: {label}...")
                    
                    # We have to show messagebox from main thread or it might crash tkinter on mac
                    # But we are in a background thread. Let's use self.winfo_toplevel() via event or just simple block
                    # Actually messagebox is mostly thread-safe enough for blocking, but to be 100% safe let's copy first then popup
                    
                    if chunk['type'] == 'html':
                        migrate_from_url.copy_html_to_clipboard(chunk['content'])
                    elif chunk['type'] == 'image':
                        migrate_from_url.copy_image_file_to_clipboard(chunk['path'])
                    
                    self.log(f"-> {label} Copied.")
                    
                    # Blocking call via tk messagebox
                    # We can use a simple input dialog, or messagebox.showinfo
                    messagebox.showinfo(f"Step {i+1} of {len(chunks)}", msg)
                
                self.log("\n[SUCCESS] Manual Migration Finished.")
                
        except Exception as e:
            self.log(f"\n[ERROR] Migration failed: {e}")
            import traceback
            traceback.print_exc()

        finally:
            self.reset_ui()

    def reset_ui(self):
        # Must be called from main thread, but changing button state from thread is often okay.
        # To be completely safe:
        self.after(0, lambda: self.start_btn.configure(state="normal", text="Start Migration"))

if __name__ == "__main__":
    app = TistoryMigratorApp()
    app.mainloop()
