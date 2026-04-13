import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
from PIL import Image
from pathlib import Path
import hashlib
import threading
from tkinterdnd2 import DND_FILES
from managers.image_manager import ImageManager
import os

class UploadView(ctk.CTkFrame):
    def __init__(self, master, cancel_callback, on_upload_success_callback):
        super().__init__(master)

        self.cancel_callback = cancel_callback
        self.on_upload_success_callback = on_upload_success_callback

        self.image_mgr = ImageManager()

        # State
        self.pending_files = [] # list of dicts: {'path': Path, 'hash': str, 'status': 'pending'|'new'|'duplicate', 'duplicate_name': str, 'ctk_img': CTkImage, 'frame': frame, 'ui_row': label}
        self.upload_anyway_var = ctk.BooleanVar(value=False)

        self._setup_ui()

    def reset(self):
        """Clears the upload queue and resets UI state for a new upload session."""
        for item in self.pending_files:
            if item['frame']: item['frame'].destroy()
            if item['ui_row']: item['ui_row'].destroy()
        self.pending_files.clear()

        self.upload_anyway_var.set(False)
        self.upload_btn.configure(state="disabled", text="Upload 0 images")
        self.cancel_btn.configure(state="normal")
        self._update_summary()

    def _setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Main Layout Frames ---
        self.left_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=(24, 12))

        self.right_frame = ctk.CTkFrame(self)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=24, pady=(24, 12))

        # --- Left Side: Drop Zone ---
        self.left_frame.grid_rowconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)

        self.drop_zone = ctk.CTkFrame(self.left_frame, corner_radius=12, border_width=2, border_color="#334155", fg_color="#1E293B")
        self.drop_zone.grid(row=0, column=0, sticky="nsew", pady=(0, 16))

        self.drop_zone.pack_propagate(False)
        self.drop_icon_lbl = ctk.CTkLabel(self.drop_zone, text="☁️", font=ctk.CTkFont(size=64))
        self.drop_icon_lbl.pack(pady=(60, 10))

        self.drop_title = ctk.CTkLabel(self.drop_zone, text="Drag & drop images here", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"))
        self.drop_title.pack(pady=(0, 5))

        self.drop_subtext = ctk.CTkLabel(self.drop_zone, text="Supports JPG, PNG, WEBP, GIF", text_color="#94A3B8", font=ctk.CTkFont(family="Segoe UI", size=14))
        self.drop_subtext.pack(pady=(0, 20))

        self.browse_btn = ctk.CTkButton(self.drop_zone, text="Browse Files", font=ctk.CTkFont(family="Segoe UI", size=14), height=40, command=self._browse_files)
        self.browse_btn.pack()

        # Register drop zone
        # We bind to the top-level app assuming it's the DnD wrapper
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind('<<Drop>>', self._on_drop)

        # Thumbnail strip below drop zone
        self.thumb_strip = ctk.CTkScrollableFrame(self.left_frame, orientation="horizontal", height=120, fg_color="transparent")
        self.thumb_strip.grid(row=1, column=0, sticky="ew")

        # --- Right Side: Duplicate Detection Panel ---
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        self.summary_lbl = ctk.CTkLabel(self.right_frame, text="0 new, 0 duplicate found", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), anchor="w")
        self.summary_lbl.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")

        self.status_scroll = ctk.CTkScrollableFrame(self.right_frame, fg_color="transparent")
        self.status_scroll.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.upload_anyway_chk = ctk.CTkCheckBox(self.right_frame, text="Upload duplicates anyway", variable=self.upload_anyway_var, font=ctk.CTkFont(family="Segoe UI", size=13))
        self.upload_anyway_chk.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="w")

        # --- Bottom Action Bar ---
        self.action_bar = ctk.CTkFrame(self, height=64, fg_color="#1E293B", corner_radius=0)
        self.action_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.action_bar.grid_columnconfigure(0, weight=1)

        self.cancel_btn = ctk.CTkButton(self.action_bar, text="Cancel", fg_color="transparent", border_width=1, hover_color="#334155", font=ctk.CTkFont(family="Segoe UI", size=14), height=40, width=100, command=self.cancel_callback)
        self.cancel_btn.grid(row=0, column=1, padx=10, pady=12)

        self.upload_btn = ctk.CTkButton(self.action_bar, text="Upload 0 images", font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"), height=40, width=160, state="disabled", command=self._perform_upload)
        self.upload_btn.grid(row=0, column=2, padx=20, pady=12)

    def _browse_files(self):
        filetypes = (
            ('Image files', '*.jpg *.jpeg *.jfif *.png *.webp *.bmp *.gif'),
            ('All files', '*.*')
        )
        filenames = filedialog.askopenfilenames(
            title='Select Reference Images',
            filetypes=filetypes
        )
        self._add_files(filenames)

    def _on_drop(self, event):
        # Handle tkdnd weirdness where multiple files come space-separated or wrapped in braces
        data = event.data
        if not data: return

        paths = []
        if '{' in data:
            import re
            paths = re.findall(r'{([^}]+)}', data)
            # Remove matched from data
            data = re.sub(r'{[^}]+}', '', data).strip()
            if data:
                paths.extend(data.split())
        else:
            paths = data.split()

        self._add_files(paths)

    def _add_files(self, filepaths):
        new_files = []
        for fp in filepaths:
            path = Path(fp)
            if not path.is_file(): continue
            if path.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']: continue

            # Prevent adding same file twice to the pending list
            if any(f['path'] == path for f in self.pending_files):
                continue

            item = {
                'path': path,
                'status': 'pending',
                'hash': None,
                'duplicate_name': None,
                'ctk_img': None,
                'frame': None,
                'ui_row': None
            }
            new_files.append(item)
            self.pending_files.append(item)

        if not new_files:
            return

        # UI updates
        for item in new_files:
            self._render_thumbnail_placeholder(item)
            self._render_status_row(item)

        # Start async hash calculation
        threading.Thread(target=self._process_files, args=(new_files,), daemon=True).start()

    def _render_thumbnail_placeholder(self, item):
        frame = ctk.CTkFrame(self.thumb_strip, corner_radius=6, fg_color="transparent")
        frame.pack(side="left", padx=5, pady=5)

        lbl = ctk.CTkLabel(frame, text="⏳", font=ctk.CTkFont(size=24), width=80, height=80, fg_color="#334155", corner_radius=6)
        lbl.pack()

        del_btn = ctk.CTkButton(frame, text="✕", width=20, height=20, fg_color="red", hover_color="darkred", command=lambda i=item: self._remove_file(i))
        del_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-2, y=2)

        item['frame'] = frame
        item['thumb_lbl'] = lbl

    def _render_status_row(self, item):
        lbl = ctk.CTkLabel(self.status_scroll, text=f"⏳ Checking {item['path'].name}...", font=ctk.CTkFont(family="Segoe UI", size=13), anchor="w", justify="left")
        lbl.pack(fill="x", pady=2)
        item['ui_row'] = lbl

    def _process_files(self, items):
        for item in items:
            try:
                # 1. Generate small thumbnail
                img = Image.open(item['path'])
                img.thumbnail((100, 100))
                item['ctk_img'] = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 80))

                # 2. Compute hash
                hash_md5 = hashlib.md5()
                with open(item['path'], "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                item['hash'] = hash_md5.hexdigest()

                # 3. Check duplicate
                dup = self.image_mgr.check_duplicate_by_hash(item['hash'])
                if dup:
                    item['status'] = 'duplicate'
                    item['duplicate_name'] = dup
                else:
                    item['status'] = 'new'

                # Schedule UI update
                self.after(0, self._update_item_ui, item)
            except Exception as e:
                print(f"Error processing {item['path']}: {e}")
                item['status'] = 'error'
                self.after(0, self._update_item_ui, item)

    def _update_item_ui(self, item):
        # Thumbnail
        if item['ctk_img']:
            item['thumb_lbl'].configure(image=item['ctk_img'], text="", fg_color="transparent")

        # Status Row
        if item['status'] == 'new':
            text = f"✅ {item['path'].name} - New image, ready to upload"
            color = "#10B981" # Emerald
        elif item['status'] == 'duplicate':
            text = f"⚠️ {item['path'].name} - Duplicate detected (matches '{item['duplicate_name']}')"
            color = "#F59E0B" # Amber
        else:
            text = f"❌ {item['path'].name} - Error processing"
            color = "#EF4444" # Red

        item['ui_row'].configure(text=text, text_color=color)

        self._update_summary()

    def _remove_file(self, item):
        if item in self.pending_files:
            self.pending_files.remove(item)
        if item['frame']:
            item['frame'].destroy()
        if item['ui_row']:
            item['ui_row'].destroy()
        self._update_summary()

    def _update_summary(self):
        new_count = sum(1 for f in self.pending_files if f['status'] == 'new')
        dup_count = sum(1 for f in self.pending_files if f['status'] == 'duplicate')

        self.summary_lbl.configure(text=f"{new_count} new, {dup_count} duplicate found")

        # Determine how many will upload
        total_upload = new_count
        if self.upload_anyway_var.get():
            total_upload += dup_count

        if total_upload > 0:
            self.upload_btn.configure(state="normal", text=f"Upload {total_upload} images")
        else:
            self.upload_btn.configure(state="disabled", text="Upload 0 images")

        # Re-bind checkbox to update summary if toggled
        self.upload_anyway_chk.configure(command=self._update_summary)

    def _perform_upload(self):
        self.upload_btn.configure(state="disabled", text="Uploading...")
        self.cancel_btn.configure(state="disabled")

        # Gather files to upload
        files_to_upload = []
        for item in self.pending_files:
            if item['status'] == 'new' or (item['status'] == 'duplicate' and self.upload_anyway_var.get()):
                files_to_upload.append(item['path'])

        if not files_to_upload:
            return

        # Run upload in background
        threading.Thread(target=self._upload_worker, args=(files_to_upload,), daemon=True).start()

    def _upload_worker(self, paths):
        for path in paths:
            self.image_mgr.import_image(str(path))

        self.after(0, self.on_upload_success_callback)
