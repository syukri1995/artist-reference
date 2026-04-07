import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
from PIL import Image
from pathlib import Path
from managers.image_manager import ImageManager
from managers.collection_manager import CollectionManager
from managers.tag_manager import TagManager

class GalleryView(ctk.CTkFrame):
    def __init__(self, master, switch_to_workspace_callback):
        super().__init__(master)
        
        self.switch_to_workspace_callback = switch_to_workspace_callback
        
        self.image_mgr = ImageManager()
        self.collection_mgr = CollectionManager()
        self.tag_mgr = TagManager()
        
        self.selected_images = set() # Store file paths of selected images
        self.path_to_id = {} # Store path -> db id
        self.current_collection_id = None
        self.current_tag_id = None
        self.current_search_term = None
        self.only_favorites = False
        
        self._setup_ui()
        self.refresh_collections_list()
        self.refresh_tags_list()
        self.load_gallery()
        
    def _setup_ui(self):
        self.grid_rowconfigure(0, weight=0) # Top Search Bar
        self.grid_rowconfigure(1, weight=1) # Image Grid
        self.grid_columnconfigure(1, weight=1)
        
        # Sidebar
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.sidebar_frame.grid_rowconfigure(7, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Reference Manager", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.import_button = ctk.CTkButton(self.sidebar_frame, text="Import Images", command=self._import_images)
        self.import_button.grid(row=1, column=0, padx=20, pady=10)
        
        self.all_images_btn = ctk.CTkButton(self.sidebar_frame, text="All Images", fg_color="transparent", border_width=2, command=self.reset_filters)
        self.all_images_btn.grid(row=2, column=0, padx=20, pady=5)
        
        self.favorites_btn = ctk.CTkButton(self.sidebar_frame, text="★ Favorites", text_color="gold", fg_color="transparent", border_width=2, command=self.set_favorites_filter)
        self.favorites_btn.grid(row=3, column=0, padx=20, pady=5)
        
        self.collections_label = ctk.CTkLabel(self.sidebar_frame, text="Collections:", anchor="w")
        self.collections_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="ew")
        
        self.collections_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent", height=100)
        self.collections_scroll.grid(row=5, column=0, padx=10, pady=5, sticky="nsew")
        
        self.new_collection_btn = ctk.CTkButton(self.sidebar_frame, text="+ New Collection", fg_color="transparent", command=self._create_collection)
        self.new_collection_btn.grid(row=6, column=0, padx=20, pady=(0,10))
        
        self.tags_label = ctk.CTkLabel(self.sidebar_frame, text="Tags:", anchor="w")
        self.tags_label.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="ew")
        
        self.tags_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent", height=100)
        self.tags_scroll.grid(row=8, column=0, padx=10, pady=5, sticky="nsew")
        
        self.new_tag_btn = ctk.CTkButton(self.sidebar_frame, text="+ New Tag", fg_color="transparent", command=self._create_tag)
        self.new_tag_btn.grid(row=9, column=0, padx=20, pady=(0,10))
        
        self.workspace_button = ctk.CTkButton(self.sidebar_frame, text="Open Workspace", command=self._open_workspace)
        self.workspace_button.grid(row=10, column=0, padx=20, pady=20, sticky="s")
        
        # Top Bar (Search & Settings)
        self.topbar = ctk.CTkFrame(self, height=45, fg_color="transparent")
        self.topbar.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 0))
        
        self.settings_btn = ctk.CTkButton(self.topbar, text="⚙ Settings", width=80, command=self._open_settings)
        self.settings_btn.pack(side="right", padx=(5, 0))
        
        self.search_entry = ctk.CTkEntry(self.topbar, placeholder_text="Search filenames or tags...")
        self.search_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.search_entry.bind("<Return>", self._on_search)
        
        # Main Gallery Area
        self.main_area = ctk.CTkScrollableFrame(self)
        self.main_area.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        
        # Grid parameters
        self.columns = 4
        for i in range(self.columns):
            self.main_area.grid_columnconfigure(i, weight=1)
            
    def _import_images(self):
        filetypes = (
            ('Image files', '*.jpg *.jpeg *.jfif *.png *.webp *.bmp'),
            ('All files', '*.*')
        )
        filenames = filedialog.askopenfilenames(
            title='Select Reference Images',
            filetypes=filetypes
        )
        for f in filenames:
            self.image_mgr.import_image(f)
            
        self.load_gallery()
        
    def _on_search(self, event):
        self.current_search_term = self.search_entry.get().strip() or None
        self.load_gallery()
        
    def reset_filters(self):
        self.current_collection_id = None
        self.current_tag_id = None
        self.current_search_term = None
        self.only_favorites = False
        self.search_entry.delete(0, 'end')
        self.load_gallery()

    def set_favorites_filter(self):
        self.only_favorites = True
        self.current_collection_id = None
        self.current_tag_id = None
        self.load_gallery()

    def set_collection(self, collection_id):
        self.current_collection_id = collection_id
        self.current_tag_id = None
        self.only_favorites = False
        self.load_gallery()
        
    def set_tag(self, tag_id):
        self.current_tag_id = tag_id
        self.current_collection_id = None
        self.only_favorites = False
        self.load_gallery()
        
    def _open_settings(self):
        settings_win = ctk.CTkToplevel(self)
        settings_win.title("App Settings")
        settings_win.geometry("300x150")
        settings_win.attributes("-topmost", True)
        
        mode_label = ctk.CTkLabel(settings_win, text="Appearance Mode:")
        mode_label.pack(pady=(20, 5))
        
        mode_menu = ctk.CTkOptionMenu(settings_win, values=["System", "Dark", "Light"],
                                      command=ctk.set_appearance_mode)
        mode_menu.pack(pady=5)
        
    def _create_collection(self):
        dialog = ctk.CTkInputDialog(text="Enter collection name:", title="New Collection")
        name = dialog.get_input()
        if name:
            if self.collection_mgr.create_collection(name):
                self.refresh_collections_list()
                
    def _create_tag(self):
        dialog = ctk.CTkInputDialog(text="Enter tag name:", title="New Tag")
        name = dialog.get_input()
        if name:
            if self.tag_mgr.create_tag(name):
                self.refresh_tags_list()
                
    def refresh_collections_list(self):
        for widget in self.collections_scroll.winfo_children():
            widget.destroy()
            
        collections = self.collection_mgr.get_collections()
        for c in collections:
            cid, cname = c['id'], c['name']
            btn = ctk.CTkButton(self.collections_scroll, text=cname, fg_color="transparent",
                                command=lambda id=cid: self.set_collection(id))
            btn.bind("<Button-3>", lambda e, id=cid: self._delete_collection_prompt(e, id))
            btn.pack(pady=2, fill="x")
            
    def _delete_collection_prompt(self, event, col_id):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Delete Collection", command=lambda: self._execute_col_delete(col_id))
        menu.tk_popup(event.x_root, event.y_root)
        
    def _execute_col_delete(self, col_id):
        self.collection_mgr.delete_collection(col_id)
        if self.current_collection_id == col_id:
            self.set_collection(None)
        self.refresh_collections_list()
            
    def refresh_tags_list(self):
        for widget in self.tags_scroll.winfo_children():
            widget.destroy()
            
        tags = self.tag_mgr.get_tags()
        for t in tags:
            tid, tname = t['id'], t['name']
            btn = ctk.CTkButton(self.tags_scroll, text=tname, fg_color="transparent",
                                command=lambda id=tid: self.set_tag(id))
            btn.bind("<Button-3>", lambda e, id=tid: self._delete_tag_prompt(e, id))
            btn.pack(pady=2, fill="x")
            
    def _delete_tag_prompt(self, event, tag_id):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Delete Tag", command=lambda: self._execute_tag_delete(tag_id))
        menu.tk_popup(event.x_root, event.y_root)
        
    def _execute_tag_delete(self, tag_id):
        self.tag_mgr.delete_tag(tag_id)
        if self.current_tag_id == tag_id:
            self.set_tag(None)
        self.refresh_tags_list()
        self.load_gallery()

    def _open_workspace(self):
        # Pass selected images securely
        self.switch_to_workspace_callback(list(self.selected_images))

    def load_gallery(self):
        # Clear existing
        for widget in self.main_area.winfo_children():
            widget.destroy()
        
        # Reset selection on load
        self.selected_images.clear()
        self.path_to_id.clear()
            
        images = self.image_mgr.query_images(self.current_collection_id, self.current_tag_id, self.current_search_term, self.only_favorites)
        
        row = 0
        col = 0
        
        for img_data in images:
            try:
                thumb_path = img_data['thumbnail_path']
                file_path = img_data['file_path']
                if not Path(thumb_path).exists():
                    continue
                    
                img = Image.open(thumb_path)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(150, 150))
                
                # Wrap label in a frame to act as a border
                frame = ctk.CTkFrame(self.main_area, fg_color="transparent", corner_radius=5)
                frame.grid(row=row, column=col, padx=10, pady=10)
                
                lbl = ctk.CTkLabel(frame, image=ctk_img, text="")
                lbl.image = ctk_img # Keep reference
                lbl.pack(padx=4, pady=4)
                
                # Star icon if favorite
                if img_data['is_favorite']:
                    fav_lbl = ctk.CTkLabel(frame, text="★", text_color="gold", font=ctk.CTkFont(size=24, weight="bold"))
                    fav_lbl.place(relx=0.9, rely=0.1, anchor="ne")
                
                self.path_to_id[file_path] = img_data['id']
                
                # Bind events
                lbl.bind("<Button-1>", lambda e, p=file_path, f=frame: self.toggle_selection(p, f))
                # Right click binds
                lbl.bind("<Button-3>", lambda e, p=file_path: self.show_context_menu(e, p))
                
                col += 1
                if col >= self.columns:
                    col = 0
                    row += 1
            except Exception as e:
                print(f"Error loading thumbnail {thumb_path}: {e}")

    def toggle_selection(self, file_path, frame_widget):
        if file_path in self.selected_images:
            self.selected_images.remove(file_path)
            frame_widget.configure(fg_color="transparent")
        else:
            self.selected_images.add(file_path)
            frame_widget.configure(fg_color="#3B8ED0") # CustomTkinter default blue

    def show_context_menu(self, event, file_path):
        target_paths = set(self.selected_images)
        target_paths.add(file_path) # Include the rigidly clicked one
            
        menu = tk.Menu(self, tearoff=0)
        
        # Submenu for Add to Collection
        col_menu = tk.Menu(menu, tearoff=0)
        collections = self.collection_mgr.get_collections()
        for c in collections:
            col_menu.add_command(label=c['name'], command=lambda cid=c['id']: self._add_to_collection(target_paths, cid))
            
        if collections:
            menu.add_cascade(label="Add to Collection", menu=col_menu)
        else:
            menu.add_command(label="No Collections exist", state="disabled")
            
        if self.current_collection_id:
            menu.add_command(label="Remove from this Collection", command=lambda: self._remove_from_collection(target_paths))
            
        menu.add_separator()
        menu.add_command(label="Toggle Favorite", command=lambda: self._toggle_favorites(target_paths))
        
        # Submenu for Tags
        tag_menu = tk.Menu(menu, tearoff=0)
        untag_menu = tk.Menu(menu, tearoff=0)
        
        tags = self.tag_mgr.get_tags()
        for t in tags:
            tid = t['id']
            tag_menu.add_command(label=t['name'], command=lambda tid=tid: self._tag_images(target_paths, tid))
            untag_menu.add_command(label=t['name'], command=lambda tid=tid: self._untag_images(target_paths, tid))
            
        if tags:
            menu.add_cascade(label="Tag Image As...", menu=tag_menu)
            menu.add_cascade(label="Remove Tag...", menu=untag_menu)
        else:
            menu.add_command(label="No Tags exist", state="disabled")
            
        menu.add_separator()
        menu.add_command(label="Delete Permanently", command=lambda: self._delete_images(target_paths))
        
        menu.tk_popup(event.x_root, event.y_root)
        
    def _add_to_collection(self, paths, cid):
        for p in paths:
            if p in self.path_to_id:
                self.collection_mgr.add_image_to_collection(self.path_to_id[p], cid)
                
    def _remove_from_collection(self, paths):
        for p in paths:
            if p in self.path_to_id:
                self.collection_mgr.remove_image_from_collection(self.path_to_id[p], self.current_collection_id)
        self.load_gallery()
        
    def _tag_images(self, paths, tid):
        for p in paths:
            if p in self.path_to_id:
                self.tag_mgr.tag_image(self.path_to_id[p], tid)
                
    def _untag_images(self, paths, tid):
        for p in paths:
            if p in self.path_to_id:
                self.tag_mgr.remove_tag_from_image(self.path_to_id[p], tid)
        # only force reload if we are actively filtering by this tag
        if self.current_tag_id == tid:
            self.load_gallery()
            
    def _toggle_favorites(self, paths):
        for p in paths:
            self.image_mgr.toggle_favorite(p)
        self.load_gallery()
        
    def _delete_images(self, paths):
        for p in paths:
            self.image_mgr.delete_image(p)
        self.load_gallery()
