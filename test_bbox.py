import tkinter as tk
import customtkinter as ctk

app = ctk.CTk()
canvas = ctk.CTkCanvas(app, width=400, height=400, bg="#2b2b2b")
canvas.pack()

# Create image placeholder
img_id = canvas.create_rectangle(50, 50, 200, 200, fill="gray")

# Create selection box
sel_box = canvas.create_rectangle(50, 50, 200, 200, outline="red", width=5, fill="")

# Raise
canvas.tag_raise(sel_box)

# Screenshot logic
app.update()

# We just want to see if this raises any errors.
print("App running. BBox created successfully.")
app.destroy()
