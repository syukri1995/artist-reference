"""Layout algorithms for workspace items."""

import math
from PyQt5.QtCore import QPointF
from ui.workspace_items import GraphicsPixmapItem

def sort_items(items: list[GraphicsPixmapItem], sort_by: str, image_mgr) -> list[GraphicsPixmapItem]:
    if sort_by == "date":
        def get_date(item):
            if item.image_id:
                detail = image_mgr.get_image_detail(item.image_id)
                return detail.get("date_added", "") if detail else ""
            return ""
        return sorted(items, key=get_date)
    elif sort_by == "size":
        def get_size(item):
            rect = item.pixmap().rect()
            return rect.width() * rect.height() * (item.scale() ** 2)
        return sorted(items, key=get_size, reverse=True)
    return items

def grid_layout(items: list[GraphicsPixmapItem], spacing: float = 20.0) -> list[QPointF]:
    if not items:
        return []
    
    n = len(items)
    cols = math.ceil(math.sqrt(n))
    
    new_positions = []
    current_x = 0.0
    current_y = 0.0
    row_height = 0.0
    
    for i, item in enumerate(items):
        if i > 0 and i % cols == 0:
            current_x = 0.0
            current_y += row_height + spacing
            row_height = 0.0
        
        new_positions.append(QPointF(current_x, current_y))
        
        item_width = item.pixmap().width() * item.scale()
        item_height = item.pixmap().height() * item.scale()
        
        current_x += item_width + spacing
        row_height = max(row_height, item_height)
        
    return new_positions

def horizontal_layout(items: list[GraphicsPixmapItem], spacing: float = 20.0) -> list[QPointF]:
    new_positions = []
    current_x = 0.0
    
    for item in items:
        new_positions.append(QPointF(current_x, 0.0))
        current_x += (item.pixmap().width() * item.scale()) + spacing
        
    return new_positions

def vertical_layout(items: list[GraphicsPixmapItem], spacing: float = 20.0) -> list[QPointF]:
    new_positions = []
    current_y = 0.0
    
    for item in items:
        new_positions.append(QPointF(0.0, current_y))
        current_y += (item.pixmap().height() * item.scale()) + spacing
        
    return new_positions

def pack_layout(items: list[GraphicsPixmapItem], max_width: float = 2000.0, spacing: float = 20.0) -> list[QPointF]:
    """A simple shelf-packing algorithm."""
    if not items:
        return []
    
    # Sort by height descending for better packing
    sorted_items = sorted(items, key=lambda i: i.pixmap().height() * i.scale(), reverse=True)
    item_to_index = {item: i for i, item in enumerate(items)}
    
    positions = [QPointF(0, 0)] * len(items)
    current_x = 0.0
    current_y = 0.0
    shelf_height = 0.0
    
    for item in sorted_items:
        w = item.pixmap().width() * item.scale()
        h = item.pixmap().height() * item.scale()
        
        if current_x + w > max_width and current_x > 0:
            current_x = 0.0
            current_y += shelf_height + spacing
            shelf_height = 0.0
            
        positions[item_to_index[item]] = QPointF(current_x, current_y)
        current_x += w + spacing
        shelf_height = max(shelf_height, h)
        
    return positions

def grouped_layout(items: list[GraphicsPixmapItem], tag_mgr, spacing: float = 40.0) -> list[QPointF]:
    """Group items by tag and arrange each group."""
    groups = {}
    for item in items:
        tags = tag_mgr.get_tags_for_image(item.image_id) if item.image_id else []
        primary_tag = tags[0]["name"] if tags else "Untagged"
        groups.setdefault(primary_tag, []).append(item)
    
    positions = [QPointF(0, 0)] * len(items)
    item_to_index = {item: i for i, item in enumerate(items)}
    
    group_y = 0.0
    for tag in sorted(groups.keys()):
        group_items = groups[tag]
        # Arrange group items in a grid
        group_positions = grid_layout(group_items, spacing=20.0)
        
        # Shift group positions by current group_y
        max_h = 0.0
        for i, item in enumerate(group_items):
            pos = group_positions[i]
            final_pos = QPointF(pos.x(), pos.y() + group_y)
            positions[item_to_index[item]] = final_pos
            
            h = pos.y() + (item.pixmap().height() * item.scale())
            max_h = max(max_h, h)
        
        group_y += max_h + spacing
        
    return positions
