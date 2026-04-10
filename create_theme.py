import customtkinter as ctk
import json
import os

def create_theme():
    # We load the default blue theme dictionary
    theme = ctk.ThemeManager.theme.copy()
    
    # Primary: Deep Slate
    # Light mode Deep Slate: "#CBD5E1", Dark mode Deep Slate: "#0F172A" (or "#1E293B" for slightly lighter)
    # Accent: Electric Violet "#7C3AED", hovering "#6D28D9"
    
    # Generic Window background
    theme["CTk"]["fg_color"] = ["#F8FAFC", "#0F172A"]
    theme["CTkFrame"]["fg_color"] = ["#FFFFFF", "#1E293B"]
    theme["CTkFrame"]["top_fg_color"] = ["#F1F5F9", "#334155"]
    theme["CTkFrame"]["border_color"] = ["#E2E8F0", "#334155"]
    
    theme["CTkButton"]["fg_color"] = ["#7C3AED", "#7C3AED"]
    theme["CTkButton"]["hover_color"] = ["#6D28D9", "#6D28D9"]
    theme["CTkButton"]["text_color"] = ["#FFFFFF", "#FFFFFF"]
    theme["CTkButton"]["corner_radius"] = 6
    
    theme["CTkLabel"]["text_color"] = ["#0F172A", "#F8FAFC"]
    
    theme["CTkEntry"]["fg_color"] = ["#F8FAFC", "#0F172A"]
    theme["CTkEntry"]["border_color"] = ["#CBD5E1", "#334155"]
    theme["CTkEntry"]["text_color"] = ["#0F172A", "#F8FAFC"]
    theme["CTkEntry"]["corner_radius"] = 6
    
    theme["CTkScrollbar"]["fg_color"] = "transparent"
    theme["CTkScrollbar"]["button_color"] = ["#CBD5E1", "#334155"]
    theme["CTkScrollbar"]["button_hover_color"] = ["#94A3B8", "#475569"]
    
    with open("ui/theme.json", "w") as f:
        json.dump(theme, f, indent=4)
        
    print("Theme created at ui/theme.json")

if __name__ == "__main__":
    create_theme()
