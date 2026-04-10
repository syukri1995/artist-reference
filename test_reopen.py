from database import get_connection, init_db
from managers.image_manager import ImageManager
from managers.collection_manager import CollectionManager
from managers.tag_manager import TagManager

# Re-init managers to simulate reopening
im = ImageManager()
cm = CollectionManager()
tm = TagManager()

cols = cm.get_collections()
if cols:
    col_id = cols[0]['id']
    print("Col ID:", col_id)
    imgs = im.query_images(collection_id=col_id)
    print("Images in col:", imgs)
