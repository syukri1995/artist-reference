import customtkinter as ctk
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def resource_path(relative_path: str) -> str:
    """Resolve a resource path that works both in dev and when frozen by PyInstaller."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

from database import init_db
from ui.gallery_view import GalleryView
from version import APP_VERSION, UPDATE_URL
from managers.update_manager import UpdateManager
from ui.update_dialog import UpdateDialog

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme(resource_path("ui/theme.json"))

class Application(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Artist Reference Manager")
        self.geometry("1440x900")
        self.minsize(1200, 800)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Database initialization
        init_db()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Initialize views
        self.workspace_view = None
        self.gallery_view = None
        
        self.gallery_view = GalleryView(self, self.show_workspace)

        # Start with Gallery
        self.show_gallery()
        
        # Check for updates silently in the background
        self.update_manager = UpdateManager(APP_VERSION, UPDATE_URL)
        # Wait until UI mounts to start the background request
        self.after(1000, lambda: self.update_manager.check_for_updates(self.on_update_available))

    def on_update_available(self, latest_version, release_notes, download_url):
        # Schedule the UI update safely on the main thread
        self.after(0, lambda: UpdateDialog(self, APP_VERSION, latest_version, release_notes, download_url))
        
    def on_closing(self):
        self.destroy()

    def toggle_topmost(self, state):
        self.attributes("-topmost", state)
        
    def toggle_fullscreen(self, state):
        self.attributes("-fullscreen", state)

    def show_gallery(self):
        if self.workspace_view:
            self.workspace_view.grid_forget()
            
        if self.gallery_view:
            self.gallery_view.grid(row=0, column=0, sticky="nsew")

    def show_workspace(self, selected_images=None):
        if self.gallery_view:
            self.gallery_view.grid_forget()
            
        if not self.workspace_view:
            from ui.workspace_view import WorkspaceView
            self.workspace_view = WorkspaceView(self, self.show_gallery, self.toggle_topmost, self.toggle_fullscreen)
            
        self.workspace_view.grid(row=0, column=0, sticky="nsew")
        # Always pass either the new images or an empty list to load
        self.workspace_view.load_images(selected_images or [])

if __name__ == "__main__":
    app = Application()
    app.mainloop()
