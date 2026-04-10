from database import get_connection, init_db
from managers.image_manager import ImageManager
from managers.collection_manager import CollectionManager
from managers.tag_manager import TagManager
import os
from PIL import Image

init_db()

im = ImageManager()
cm = CollectionManager()
tm = TagManager()

# Create dummy image
img_path = "dummy.jpg"
Image.new('RGB', (100, 100), color='blue').save(img_path)

im.import_image(img_path)

# Create a collection
cm.create_collection("Test Col")
cols = cm.get_collections()
col_id = cols[0]['id']

# Get images
imgs = im.query_images()
img_id = imgs[0]['id']

# Add to collection
cm.add_image_to_collection(img_id, col_id)

print("Images in col:", im.query_images(collection_id=col_id))

# Now try querying after "reopen"
print("Tags:", tm.get_tags())
