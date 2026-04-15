import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
from PIL import Image
from pathlib import Path
from managers.image_manager import ImageManager
from managers.collection_manager import CollectionManager
from managers.tag_manager import TagManager
import concurrent.futures
import gc
from ui.settings_dialog import SettingsDialog

class GalleryView(ctk.CTkFrame):

    def __init__(self, master, switch_to_workspace_callback, show_upload_callback=None):
        super().__init__(master)
        
        self.switch_to_workspace_callback = switch_to_workspace_callback
        self.show_upload_callback = show_upload_callback
        
        self.image_mgr = ImageManager()
        self.collection_mgr = CollectionManager()
        self.tag_mgr = TagManager()
        
        self.selected_images = set()
        self.path_to_id = {}
        self.current_collection_id = None
        self.current_tag_id = None
        self.current_search_term = None
        self.only_favorites = False
        self.current_page = 1
        self.items_per_page = 50
        
        self._current_load_id = 0
        # 2 workers keeps concurrent PIL decompression buffers low
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        
        self._setup_ui()
        self.refresh_collections_list()
        self.refresh_tags_list()
        self.load_gallery()
        
    def _setup_ui(self):
        self.grid_rowconfigure(0, weight=0)  # Top Navigation Bar
        self.grid_rowconfigure(1, weight=1)  # Main Content Area
        self.grid_columnconfigure(1, weight=1)
        
        # Top Navigation Bar
        self.topbar = ctk.CTkFrame(self, height=64, fg_color="#1E293B", corner_radius=0)
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        self.logo_label = ctk.CTkLabel(self.topbar, text="Artist Reference", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=24, pady=16, sticky="w")

        self.search_entry = ctk.CTkEntry(self.topbar, placeholder_text="Search filenames or tags...", width=300, font=ctk.CTkFont(family="Segoe UI", size=14), height=36, corner_radius=6)
        self.search_entry.grid(row=0, column=1, padx=20, pady=14)
        self.search_entry.bind("<Return>", self._on_search)

        # Right Side of Top Bar
        self.top_right_frame = ctk.CTkFrame(self.topbar, fg_color="transparent")
        self.top_right_frame.grid(row=0, column=2, sticky="e", padx=24)

        self.columns_label = ctk.CTkLabel(self.top_right_frame, text="Columns:", font=ctk.CTkFont(family="Segoe UI", size=12))
        self.columns_label.pack(side="left", padx=(0, 5))
        
        self.columns_var = ctk.IntVar(value=4)
        self.columns_slider = ctk.CTkSlider(self.top_right_frame, from_=2, to=6, number_of_steps=4, width=100, variable=self.columns_var, command=self._on_columns_changed)
        self.columns_slider.pack(side="left", padx=(0, 20))
        
        self.settings_btn = ctk.CTkButton(self.top_right_frame, text="⚙", font=ctk.CTkFont(family="Segoe UI", size=20), width=40, height=36, corner_radius=6, fg_color="#334155", hover_color="#475569", command=self._open_settings)
        self.settings_btn.pack(side="left", padx=(0, 12))

        self.upload_btn = ctk.CTkButton(self.top_right_frame, text="+ Upload", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), fg_color="#7C3AED", hover_color="#6D28D9", width=100, height=36, corner_radius=6, command=self._show_upload)
        self.upload_btn.pack(side="left")

        # Sidebar
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=1, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.sidebar_frame.grid_rowconfigure(7, weight=1)
        
        self.all_images_btn = ctk.CTkButton(self.sidebar_frame, text="All Images", font=ctk.CTkFont(family="Segoe UI", size=13), fg_color="transparent", border_width=1, height=36, corner_radius=6, command=self.reset_filters)
        self.all_images_btn.grid(row=1, column=0, padx=24, pady=(24, 4))
        
        self.favorites_btn = ctk.CTkButton(self.sidebar_frame, text="★ Favorites", font=ctk.CTkFont(family="Segoe UI", size=13), text_color="#F59E0B", fg_color="transparent", border_width=1, height=36, corner_radius=6, command=self.set_favorites_filter)
        self.favorites_btn.grid(row=2, column=0, padx=24, pady=4)
        
        self.collections_label = ctk.CTkLabel(self.sidebar_frame, text="Collections", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#94A3B8", anchor="w")
        self.collections_label.grid(row=3, column=0, padx=24, pady=(16, 4), sticky="ew")
        
        self.collections_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent", height=120)
        self.collections_scroll.grid(row=4, column=0, padx=16, pady=4, sticky="nsew")
        
        self.new_collection_btn = ctk.CTkButton(self.sidebar_frame, text="+ New Collection", font=ctk.CTkFont(family="Segoe UI", size=12), fg_color="transparent", text_color="#CBD5E1", height=28, command=self._create_collection)
        self.new_collection_btn.grid(row=5, column=0, padx=24, pady=(0,16))
        
        self.tags_label = ctk.CTkLabel(self.sidebar_frame, text="Tags", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#94A3B8", anchor="w")
        self.tags_label.grid(row=6, column=0, padx=24, pady=(16, 4), sticky="ew")
        
        self.tags_scroll = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent", height=120)
        self.tags_scroll.grid(row=7, column=0, padx=16, pady=4, sticky="nsew")
        
        self.new_tag_btn = ctk.CTkButton(self.sidebar_frame, text="+ New Tag", font=ctk.CTkFont(family="Segoe UI", size=12), fg_color="transparent", text_color="#CBD5E1", height=28, command=self._create_tag)
        self.new_tag_btn.grid(row=8, column=0, padx=24, pady=(0,16))
        
        self.workspace_button = ctk.CTkButton(self.sidebar_frame, text="Open Workspace", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), height=40, command=self._open_workspace)
        self.workspace_button.grid(row=9, column=0, padx=24, pady=24, sticky="s")
        
        # Main Gallery Area
        self.main_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_area.grid(row=1, column=1, sticky="nsew", padx=10, pady=(10, 0))

        # Pagination Bar
        self.pagination_frame = ctk.CTkFrame(self, height=40, fg_color="#1E293B", corner_radius=0)
        self.pagination_frame.grid(row=2, column=1, sticky="ew")

        self.prev_page_btn = ctk.CTkButton(self.pagination_frame, text="< Previous", width=100, command=self._prev_page)
        self.prev_page_btn.pack(side="left", padx=20, pady=10)

        self.page_label = ctk.CTkLabel(self.pagination_frame, text="Page 1", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"))
        self.page_label.pack(side="left", expand=True)

        self.next_page_btn = ctk.CTkButton(self.pagination_frame, text="Next >", width=100, command=self._next_page)
        self.next_page_btn.pack(side="right", padx=20, pady=10)
        
        self.columns = int(self.columns_var.get())
        self.masonry_columns = []
        self._setup_masonry_columns()

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_gallery()

    def _next_page(self):
        if hasattr(self, 'has_next_page') and self.has_next_page:
            self.current_page += 1
            self.load_gallery()

    def _setup_masonry_columns(self):
        # Clear existing columns
        for col_frame in self.masonry_columns:
            col_frame.destroy()
        self.masonry_columns.clear()
        self.masonry_heights = []

        # Set weight
        for i in range(6):
            self.main_area.grid_columnconfigure(i, weight=0)

        for i in range(self.columns):
            self.main_area.grid_columnconfigure(i, weight=1)
            col_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
            col_frame.grid(row=0, column=i, sticky="nw", padx=5)
            self.masonry_columns.append(col_frame)
            self.masonry_heights.append(0)

    def _on_columns_changed(self, value):
        new_cols = int(value)
        if new_cols != self.columns:
            self.columns = new_cols
            self.load_gallery()

    def _show_upload(self):
        if self.show_upload_callback:
            self.show_upload_callback()

    # ------------------------------------------------------------------ filters

    def _on_search(self, event=None):
        self.current_search_term = self.search_entry.get().strip() or None
        self.current_page = 1
        self.load_gallery()
        
    def reset_filters(self):
        self.current_collection_id = None
        self.current_tag_id = None
        self.current_search_term = None
        self.only_favorites = False
        self.current_page = 1
        self.search_entry.delete(0, 'end')
        self.load_gallery()

    def set_favorites_filter(self):
        self.only_favorites = True
        self.current_collection_id = None
        self.current_tag_id = None
        self.current_page = 1
        self.load_gallery()

    def set_collection(self, collection_id):
        self.current_collection_id = collection_id
        self.current_tag_id = None
        self.only_favorites = False
        self.current_page = 1
        self.load_gallery()
        
    def set_tag(self, tag_id):
        self.current_tag_id = tag_id
        self.current_collection_id = None
        self.only_favorites = False
        self.current_page = 1
        self.load_gallery()

    # ------------------------------------------------------------------ settings / dialogs

    def _open_settings(self):
        if not hasattr(self, "_settings_win") or not self._settings_win.winfo_exists():
            self._settings_win = SettingsDialog(self)
        else:
            self._settings_win.focus()
        
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

    # ------------------------------------------------------------------ sidebar lists

    def refresh_collections_list(self):
        for widget in self.collections_scroll.winfo_children():
            widget.destroy()
            
        collections = self.collection_mgr.get_collections()
        for c in collections:
            cid, cname = c['id'], c['name']
            display_name = cname if len(cname) <= 20 else cname[:17] + "..."
            btn = ctk.CTkButton(
                self.collections_scroll, text=display_name,
                fg_color="transparent", anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda id=cid: self.set_collection(id)
            )
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
            display_name = tname if len(tname) <= 20 else tname[:17] + "..."
            btn = ctk.CTkButton(
                self.tags_scroll, text=display_name,
                fg_color="transparent", anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                command=lambda id=tid: self.set_tag(id)
            )
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
        self.switch_to_workspace_callback(list(self.selected_images))

    # ------------------------------------------------------------------ gallery loading

    def _clear_gallery(self):
        """Destroy all thumbnail widgets and force GC to reclaim PIL/Tk image memory."""
        self._setup_masonry_columns()
        self.selected_images.clear()
        self.path_to_id.clear()

        if hasattr(self, 'empty_state_frame'):
            self.empty_state_frame.destroy()

        gc.collect()

    def load_gallery(self):
        self._current_load_id += 1
        load_id = self._current_load_id
        
        self._clear_gallery()
        
        offset = (self.current_page - 1) * self.items_per_page

        # Fetch all matching metadata on the main thread (pure SQL, no image I/O — fast)
        # Fetch items_per_page + 1 to determine if there's a next page
        images = self.image_mgr.query_images(
            self.current_collection_id, self.current_tag_id,
            self.current_search_term, self.only_favorites,
            limit=self.items_per_page + 1, offset=offset
        )
        
        self.has_next_page = len(images) > self.items_per_page
        if self.has_next_page:
            images = images[:self.items_per_page]

        self.prev_page_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.next_page_btn.configure(state="normal" if self.has_next_page else "disabled")
        self.page_label.configure(text=f"Page {self.current_page}")

        if not images and self.current_page == 1:
            self._show_empty_state()
            return
        elif not images:
            return

        def _load_image_task(img_data):
            try:
                thumb_path = img_data['thumbnail_path']
                if not Path(thumb_path).exists():
                    return None
                img = Image.open(thumb_path)
                img.load()
                return (img_data, img)
            except Exception as e:
                print(f"Error loading thumbnail: {e}")
                return None

        def _on_image_loaded(future):
            result = future.result()
            if result:
                self.after(0, self._render_thumbnail, result[0], result[1], load_id)

        # Stream in batches — keeps the UI responsive while images trickle in
        batch_size = 24
        def _schedule_batch(start_idx):
            if load_id != self._current_load_id:
                return  # Abort if a new load was triggered
            
            end_idx = min(start_idx + batch_size, len(images))
            for i in range(start_idx, end_idx):
                img_data = images[i]
                future = self._thread_pool.submit(_load_image_task, img_data)
                future.add_done_callback(_on_image_loaded)
            
            if end_idx < len(images):
                # Yield to the event loop before firing the next batch
                self.after(80, _schedule_batch, end_idx)

        _schedule_batch(0)

    def _show_empty_state(self):
        self.empty_state_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.empty_state_frame.grid(row=0, column=0, columnspan=self.columns, pady=100)

        icon = ctk.CTkLabel(self.empty_state_frame, text="🖼️", font=ctk.CTkFont(size=64))
        icon.pack(pady=(0, 10))

        title = ctk.CTkLabel(self.empty_state_frame, text="No images yet", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"))
        title.pack(pady=(0, 5))

        sub = ctk.CTkLabel(self.empty_state_frame, text="Upload reference images to get started.", text_color="#94A3B8", font=ctk.CTkFont(family="Segoe UI", size=14))
        sub.pack(pady=(0, 20))

        btn = ctk.CTkButton(self.empty_state_frame, text="Upload your first reference", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), fg_color="#7C3AED", hover_color="#6D28D9", height=40, command=self._show_upload)
        btn.pack()

    # ------------------------------------------------------------------ rendering

    def _get_shortest_column_index(self):
        min_height = self.masonry_heights[0]
        min_idx = 0
        for i, h in enumerate(self.masonry_heights):
            if h < min_height:
                min_height = h
                min_idx = i
        return min_idx

    def _render_thumbnail(self, img_data, img, load_id):
        if load_id != self._current_load_id:
            return
            
        file_path = img_data['file_path']

        # Calculate proportional height based on fixed column width
        # Assuming a reasonable default width for calculation before full layout
        target_width = max(200, (self.main_area.winfo_width() // self.columns) - 20)
        orig_width, orig_height = img.size

        if orig_width > 0:
            ratio = target_width / orig_width
            target_height = int(orig_height * ratio)
        else:
            target_height = target_width

        target_height = max(100, target_height) # minimum height

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(target_width, target_height))
        del img  # Release the PIL pixel buffer — CTkImage already has its own copy

        col_idx = self._get_shortest_column_index()
        col_frame = self.masonry_columns[col_idx]
        self.masonry_heights[col_idx] += target_height + 20 # Add card padding padding

        card = ctk.CTkFrame(col_frame, fg_color="#1E293B", corner_radius=10)
        card.pack(fill="x", pady=10)

        # We need a container for the image to handle overlays easily
        img_container = ctk.CTkFrame(card, fg_color="transparent", corner_radius=10)
        img_container.pack(fill="both", expand=True, padx=0, pady=0)
        
        lbl = ctk.CTkLabel(img_container, image=ctk_img, text="")
        lbl.image = ctk_img  # Keep strong Tk reference
        lbl.pack(fill="both", expand=True)

        # Hover Overlay
        overlay = ctk.CTkFrame(img_container, fg_color="#000000", corner_radius=10)
        # We don't pack the overlay initially

        overlay_buttons_frame = ctk.CTkFrame(overlay, fg_color="transparent")
        overlay_buttons_frame.place(relx=0.5, rely=0.5, anchor="center")

        ws_btn = ctk.CTkButton(overlay_buttons_frame, text="▶ Open in Workspace", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), fg_color="#7C3AED", hover_color="#6D28D9", height=32, command=lambda p=file_path: self.switch_to_workspace_callback([p]))
        ws_btn.pack(pady=5)

        del_btn = ctk.CTkButton(overlay_buttons_frame, text="🗑 Delete", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), fg_color="#EF4444", hover_color="#DC2626", height=32, command=lambda p=file_path: self._delete_images({p}))
        del_btn.pack(pady=5)

        # Transparent pixel to handle overlay transparency simulation via standard colors
        # Since Tkinter transparency is tricky, we use a dark semi-transparent-looking color via stipple or just dark bg
        # A workaround in CTk is just to set fg_color to a very dark color and rely on the UI
        # But we must capture enter/leave events correctly.

        def on_enter(e):
            overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            # Make overlay background slightly transparent on Windows/Mac if supported, else just solid dark
            try:
                overlay.configure(fg_color=("gray20", "gray10"))
            except:
                pass

        def on_leave(e):
            # Check if mouse is actually outside the container
            x, y = e.x_root, e.y_root
            x1, y1 = img_container.winfo_rootx(), img_container.winfo_rooty()
            x2, y2 = x1 + img_container.winfo_width(), y1 + img_container.winfo_height()

            if not (x1 <= x <= x2 and y1 <= y <= y2):
                overlay.place_forget()

        img_container.bind("<Enter>", on_enter)
        overlay.bind("<Leave>", on_leave)
        img_container.bind("<Leave>", on_leave)
        
        # Bottom Label
        filename = Path(file_path).name
        name_lbl = ctk.CTkLabel(
            card, text=filename,
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#94A3B8"
        )
        name_lbl.pack(pady=(4, 8), padx=10, anchor="w")
        
        if img_data['is_favorite']:
            fav_lbl = ctk.CTkLabel(img_container, text="★", text_color="gold",
                                   font=ctk.CTkFont(size=24, weight="bold"))
            fav_lbl.place(relx=0.9, rely=0.05, anchor="ne")
        
        self.path_to_id[file_path] = img_data['id']
        
        lbl.bind("<Button-1>", lambda e, p=file_path, f=card: self.toggle_selection(p, f))
        lbl.bind("<Button-3>", lambda e, p=file_path: self.show_context_menu(e, p))

    # ------------------------------------------------------------------ selection / context menu

    def toggle_selection(self, file_path, frame_widget):
        if file_path in self.selected_images:
            self.selected_images.remove(file_path)
            frame_widget.configure(fg_color="#1E293B")
        else:
            self.selected_images.add(file_path)
            frame_widget.configure(fg_color="#7C3AED")

    def show_context_menu(self, event, file_path):
        target_paths = set(self.selected_images)
        target_paths.add(file_path)
            
        menu = tk.Menu(self, tearoff=0)
        
        col_menu = tk.Menu(menu, tearoff=0)
        collections = self.collection_mgr.get_collections()
        for c in collections:
            col_menu.add_command(
                label=c['name'],
                command=lambda cid=c['id']: self._add_to_collection(target_paths, cid)
            )
            
        if collections:
            menu.add_cascade(label="Add to Collection", menu=col_menu)
        else:
            menu.add_command(label="No Collections exist", state="disabled")
            
        if self.current_collection_id:
            menu.add_command(
                label="Remove from this Collection",
                command=lambda: self._remove_from_collection(target_paths)
            )
            
        menu.add_separator()
        menu.add_command(label="Toggle Favorite", command=lambda: self._toggle_favorites(target_paths))
        
        tag_menu = tk.Menu(menu, tearoff=0)
        untag_menu = tk.Menu(menu, tearoff=0)
        
        tags = self.tag_mgr.get_tags()
        for t in tags:
            tid = t['id']
            tag_menu.add_command(
                label=t['name'],
                command=lambda tid=tid: self._tag_images(target_paths, tid)
            )
            untag_menu.add_command(
                label=t['name'],
                command=lambda tid=tid: self._untag_images(target_paths, tid)
            )
            
        if tags:
            menu.add_cascade(label="Tag Image As...", menu=tag_menu)
            menu.add_cascade(label="Remove Tag...", menu=untag_menu)
        else:
            menu.add_command(label="No Tags exist", state="disabled")
            
        menu.add_separator()
        menu.add_command(
            label="Delete Permanently",
            command=lambda: self._delete_images(target_paths)
        )
        
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------ mutations

    def _add_to_collection(self, paths, cid):
        image_ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if image_ids:
            self.collection_mgr.add_images_to_collection(image_ids, cid)
                
    def _remove_from_collection(self, paths):
        image_ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if image_ids:
            self.collection_mgr.remove_images_from_collection(
                image_ids, self.current_collection_id
            )
        self.load_gallery()
        
    def _tag_images(self, paths, tid):
        image_ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if image_ids:
            self.tag_mgr.tag_images(image_ids, tid)
                
    def _untag_images(self, paths, tid):
        image_ids = [self.path_to_id[p] for p in paths if p in self.path_to_id]
        if image_ids:
            self.tag_mgr.remove_tag_from_images(image_ids, tid)
        if self.current_tag_id == tid:
            self.load_gallery()
            
    def _toggle_favorites(self, paths):
        self.image_mgr.toggle_favorites(list(paths))
        self.load_gallery()
        
    def _delete_images(self, paths):
        for p in paths:
            self.image_mgr.delete_image(p)
        self.load_gallery()
