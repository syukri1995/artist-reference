# Software Requirements Specification (SRS)
## Artist Reference Manager Application

### Comprehensive Design Documentation

This document provides a comprehensive Software Requirements Specification (SRS) for the Artist Reference Manager application. The application is designed to help artists organize, browse, and manage large collections of reference images used for drawing, painting, illustration, and concept art. The application combines concepts from visual inspiration platforms such as Pinterest with professional reference tools used by digital artists. The primary goal is to allow artists to quickly browse image libraries and open multiple references simultaneously during creative work.

This document includes system architecture, functional requirements, non-functional requirements, UML diagrams, UI wireframes, database design, API architecture, and development considerations.

---

### 1. Product Overview

The Artist Reference Manager is a desktop software application that enables artists to store and manage reference images locally. Artists often maintain thousands of images representing anatomy, poses, lighting, clothing, scenery, and character inspiration. Managing these collections manually in folders becomes difficult and inefficient.

The proposed system provides a visual gallery interface where images can be imported, categorized into collections, tagged for search, and opened inside a workspace designed specifically for reference viewing during drawing sessions.

The software emphasizes performance and usability. The gallery must support very large image libraries while maintaining smooth browsing and fast loading. The system will generate thumbnails automatically to ensure the main gallery loads quickly regardless of original image size.

The application will operate primarily as a local desktop application. Images are stored in the local filesystem while metadata such as tags and collections are stored in an SQLite database.

---

### 2. System Architecture

The system follows a layered architecture consisting of three primary layers: User Interface Layer, Application Logic Layer, and Data Storage Layer. This separation improves maintainability and enables future extensions.

The UI Layer is responsible for rendering the gallery grid, collections view, workspace canvas, and user interaction controls. This layer communicates with the controller classes in the application logic layer.

The Application Logic Layer manages core operations including image importing, collection management, tagging, searching, and workspace layout management. Controllers coordinate requests between the UI and database repositories.

The Data Storage Layer manages persistent data. Images are stored in the filesystem while metadata is stored in an SQLite relational database.

```text
+-----------------------+
|        User           |
+-----------+-----------+
            |
            v
+-----------------------+
|       UI Layer        |
|  Gallery / Workspace  |
+-----------+-----------+
            |
            v
+-----------------------+
| Application Logic     |
| Image Manager         |
| Collection Manager    |
| Tag Manager           |
| Workspace Manager     |
+-----------+-----------+
            |
+------------+-------------+
v                          v
+-------------+           +----------------+
| SQLite DB   |           | File System    |
| Metadata    |           | Images/Thumbs  |
+-------------+           +----------------+
```

---

### 3. Use Case Model

The primary user of the system is an artist. The artist interacts with the system by importing reference images, organizing them into collections, applying tags, searching the gallery, and opening collections in a workspace.

Use cases include:
- Import Images
- Browse Gallery
- Create Collections
- Tag Images
- Search References
- Open Reference Workspace
- Arrange Images in Workspace

```text
+---------------------+
|        Artist       |
+----------+----------+
           |
--------------------------------------
|        |         |         |        |
v        v         v         v        v
Import   Browse    Create    Tag      Open
Images   Gallery   Board     Images   Workspace
```

---

### 4. Sequence Diagram – Image Import

The image import process allows the user to select one or more images from the local filesystem. The application copies the selected images into the managed image directory and generates thumbnails for fast browsing. Metadata about the image is then inserted into the database.

```text
User -> UI: Select Images
UI -> Controller: importImages()
Controller -> FileSystem: copy files
Controller -> ThumbnailService: generate thumbnail
Controller -> Database: insert metadata
Database -> Controller: success
Controller -> UI: update gallery
```

---

### 5. Class Diagram

The class diagram represents the core entities used in the system. These include images, collections, and tags. Relationships between these objects allow images to belong to multiple collections and tags.

```text
+--------------------+
| ImageModel         |
+--------------------+
| id                 |
| filePath           |
| thumbnailPath      |
| width              |
| height             |
+--------------------+

+--------------------+
| CollectionModel    |
+--------------------+
| id                 |
| name               |
| description        |
+--------------------+

+--------------------+
| TagModel           |
+--------------------+
| id                 |
| name               |
+--------------------+
```

Relationships:
- `ImageModel * --- * CollectionModel`
- `ImageModel * --- * TagModel`

---

### 6. Database Design

The system uses SQLite as its embedded database engine. SQLite provides a lightweight relational database that is suitable for desktop applications. The database stores metadata for images, collections, and tags while the actual image files remain stored in the filesystem.

#### TABLE images
- `id` INTEGER PRIMARY KEY
- `file_path` TEXT
- `thumbnail_path` TEXT
- `width` INTEGER
- `height` INTEGER
- `date_added` DATETIME

#### TABLE collections
- `id` INTEGER PRIMARY KEY
- `name` TEXT
- `description` TEXT

#### TABLE tags
- `id` INTEGER PRIMARY KEY
- `name` TEXT

#### TABLE collection_images
- `collection_id` INTEGER
- `image_id` INTEGER

#### TABLE image_tags
- `image_id` INTEGER
- `tag_id` INTEGER

---

### 7. UI Wireframes

#### Gallery Screen
```text
+----------------------------------------------------+
| Search | Import | Collections | Settings           |
+------------------+---------------------------------+
| Sidebar          | Image Grid                      |
| All Images       | [img] [img] [img] [img]         |
| Favorites        | [img] [img] [img] [img]         |
| Tags             | [img] [img] [img] [img]         |
+------------------+---------------------------------+
```

#### Workspace Screen
```text
+----------------------------------------------------+
| Zoom | Fit | Fullscreen | Always On Top            |
+----------------------------------------------------+
|                                                    |
|     [Image]         [Image]                        |
|                                                    |
|           [Large Reference Image]                  |
|                                                    |
|   [Image]                                          |
|                                                    |
+----------------------------------------------------+
```

---

### 8. Non-Functional Requirements

- **Performance Requirements:** The gallery should load thumbnails within one second even when the library contains thousands of images.
- **Usability Requirements:** The interface should be visually intuitive and allow artists to access references quickly while drawing.
- **Reliability Requirements:** The system must automatically recover workspace layouts and collections in case of application restart.
- **Scalability Requirements:** The system should support at least 100,000 stored images without significant performance degradation.

---

### 9. Extended Design Discussion

Important engineering considerations include memory management for large image libraries, thumbnail caching strategies, asynchronous file loading, and optimized rendering of image grids. The gallery should load images incrementally using lazy loading techniques to ensure that scrolling remains smooth even when browsing thousands of images.

Future development could integrate AI-based tagging systems capable of detecting pose, lighting direction, color palettes, and subject categories. Such features would significantly improve the searchability of large reference collections.

Another potential extension is cloud synchronization allowing artists to share reference libraries across devices. This feature would require a remote database service and authentication system.

Plugin architecture could also allow external developers to extend the software with additional tools such as pose detection, automatic grouping, or integration with online art reference websites.
