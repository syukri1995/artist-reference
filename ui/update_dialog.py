import customtkinter as ctk
import webbrowser

class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, current_version, new_version, release_notes, download_url):
        super().__init__(master)
        
        self.download_url = download_url
        self.title("Software Update")
        self.geometry("450x350")
        self.resizable(False, False)
        
        # Center the window relative to master
        self.update_idletasks()
        if master.winfo_ismapped():
            x = master.winfo_x() + (master.winfo_width() // 2) - (450 // 2)
            y = master.winfo_y() + (master.winfo_height() // 2) - (350 // 2)
            self.geometry(f"+{x}+{y}")
            
        # Ensure it appears on top and grabs focus
        self.transient(master)
        
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # Header
        header_font = ctk.CTkFont(size=18, weight="bold")
        self.header_label = ctk.CTkLabel(self, text="A new version is available!", font=header_font)
        self.header_label.grid(row=0, column=0, columnspan=2, pady=(20, 10), sticky="n")
        
        # Version info
        version_text = f"Current Version: {current_version}   |   Latest Version: {new_version}"
        self.version_label = ctk.CTkLabel(self, text=version_text)
        self.version_label.grid(row=1, column=0, columnspan=2, pady=(0, 15))
        
        # Release Notes Text Box
        self.notes_box = ctk.CTkTextbox(self, width=400, height=180, wrap="word")
        self.notes_box.grid(row=2, column=0, columnspan=2, padx=20, pady=5, sticky="nsew")
        self.notes_box.insert("0.0", release_notes)
        self.notes_box.configure(state="disabled") # Make read-only
        
        # Buttons
        self.skip_btn = ctk.CTkButton(self, text="Remind Me Later", fg_color="gray25", hover_color="gray30", command=self.destroy)
        self.skip_btn.grid(row=3, column=0, padx=20, pady=20, sticky="w")
        
        self.download_btn = ctk.CTkButton(self, text="Download Update", command=self.download_update)
        self.download_btn.grid(row=3, column=1, padx=20, pady=20, sticky="e")
        
        # Grab focus after everything is built
        self.grab_set()
        
    def download_update(self):
        webbrowser.open(self.download_url)
        self.destroy()
