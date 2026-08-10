💡 **What:** The optimization implemented
Replaced the loop of individual `INSERT` and `SELECT` queries for `tag_ids` inside `managers/tag_manager.py` (`apply_danbooru_tags_to_image`) with batched statements: an `executemany` statement for `INSERT` queries, and a chunked `IN` statement for `SELECT` queries (using batches of 900 names to safely stay within SQLite's 999 parameter limit).

🎯 **Why:** The performance problem it solves
The original method exhibited classic N+1 querying: for every single tag being applied, it ran two separate single-record queries (`INSERT`, then `SELECT`). For images with many Danbooru tags, this resulted in an exorbitant amount of unnecessary query executions, which bottlenecked performance. By batching queries, we avoid the overhead of opening and compiling so many queries over and over.

📊 **Measured Improvement:**
A benchmark was created using `benchmark_tags.py` to test appending 50,000 tags on a single image.
* **Baseline** applied 50,000 tags in roughly ~0.55s.
* **Optimized** version applied 50,000 tags in ~0.49s.

Even on an already relatively performant SQLite connection model with thread-local pooling, this change provided approximately an ~11% speed improvement in the function execution time, minimizing unneeded queries.
