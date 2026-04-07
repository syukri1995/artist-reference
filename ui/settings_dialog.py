import customtkinter as ctk
import webbrowser

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "Unknown"

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        
        self.title("⚙ Settings & About")
        self.geometry("450x400")
        self.resizable(False, False)
        
        # Center the window
        self.update_idletasks()
        if master.winfo_ismapped():
            x = master.winfo_x() + (master.winfo_width() // 2) - (450 // 2)
            y = master.winfo_y() + (master.winfo_height() // 2) - (400 // 2)
            self.geometry(f"+{x}+{y}")
            
        # Removed self.transient(master) because it causes Z-order/unclickable bugs on Windows 
        # when a global CustomTkinter theme redraw occurs.        
        # Setup Tabview
        self.tabview = ctk.CTkTabview(self, width=410, height=350)
        self.tabview.pack(padx=20, pady=15, expand=True, fill="both")
        
        self.tab_settings = self.tabview.add("Settings")
        self.tab_about = self.tabview.add("About")
        
        self._build_settings_tab()
        self._build_about_tab()
        
        # Removed self.grab_set() to prevent CustomTkinter thread lock on theme change

    def _build_settings_tab(self):
        # Appearance Mode
        appearance_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        appearance_frame.pack(fill="x", padx=10, pady=20)
        
        mode_label = ctk.CTkLabel(appearance_frame, text="Appearance Mode:", font=ctk.CTkFont(weight="bold"))
        mode_label.pack(side="left", padx=10)
        
        def safe_change_mode(mode):
            # 250ms delay allows the Dropdown to completely destroy its invisible modal capture 
            # frame before the global redraw happens.
            self.after(250, lambda: ctk.set_appearance_mode(mode))
            
        mode_menu = ctk.CTkOptionMenu(appearance_frame, values=["System", "Dark", "Light"],
                                      command=safe_change_mode)
        mode_menu.set(ctk.get_appearance_mode())
        mode_menu.pack(side="right", padx=10)
        
        # Opacity Slider
        opacity_frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        opacity_frame.pack(fill="x", padx=10, pady=(10, 20))
        
        self.opacity_val_label = ctk.CTkLabel(opacity_frame, text="Window Opacity: 100%", font=ctk.CTkFont(weight="bold"))
        self.opacity_val_label.pack(side="left", padx=10)
        
        root_win = self.master.winfo_toplevel()
        try:
            current_alpha = float(root_win.attributes("-alpha"))
        except Exception:
            current_alpha = 1.0
            
        def update_opacity(val):
            val_pct = int(val * 100)
            self.opacity_val_label.configure(text=f"Window Opacity: {val_pct}%")
            try:
                root_win.attributes("-alpha", val)
                self.attributes("-alpha", val)
            except Exception:
                pass
                
        opacity_slider = ctk.CTkSlider(opacity_frame, from_=0.2, to=1.0, command=update_opacity)
        opacity_slider.set(current_alpha)
        opacity_slider.pack(side="right", padx=10)
        
        # Render initial text label gracefully
        update_opacity(current_alpha)
        
    def _build_about_tab(self):
        self.tab_about.grid_columnconfigure(0, weight=1)
        self.tab_about.grid_columnconfigure(1, weight=3)
        
        row_idx = 0
        
        def add_info_row(title, value, is_link=False, command=None):
            nonlocal row_idx
            
            lbl_title = ctk.CTkLabel(self.tab_about, text=title, font=ctk.CTkFont(weight="bold"), anchor="w")
            lbl_title.grid(row=row_idx, column=0, sticky="nw", padx=10, pady=(15, 5))
            
            if is_link:
                # Use a button or blue text for the link
                lbl_val = ctk.CTkLabel(self.tab_about, text=value, text_color="#1f6aa5", cursor="hand2", anchor="w", justify="left")
                lbl_val.bind("<Button-1>", lambda e: command())
            else:
                lbl_val = ctk.CTkLabel(self.tab_about, text=value, anchor="w", justify="left")
                
            lbl_val.grid(row=row_idx, column=1, sticky="w", padx=10, pady=(15, 5))
            
            # Divider
            divider = ctk.CTkFrame(self.tab_about, height=1, fg_color=("gray75", "gray30"))
            divider.grid(row=row_idx+1, column=0, columnspan=2, sticky="ew", padx=10)
            
            row_idx += 2
            
        # 1. Software Version
        add_info_row("Software Version:", APP_VERSION)
        
        # 2. License Information
        license_text = "MIT License (Open Source)\nFree for personal and commercial use."
        add_info_row("License Information:", license_text)
        
        # 3. System Requirements
        sys_req = "OS: Windows 10/11, macOS, Linux\nRAM: Minimum 4GB\nDisplay: 1280x720 Minimum"
        add_info_row("System Requirements:", sys_req)
        
        # 4. Contact Support
        def open_support():
            webbrowser.open("https://github.com/syukri1995/artist-reference/issues")
            
        add_info_row("Contact Support:", "Report an Issue / Request Feature", is_link=True, command=open_support)
