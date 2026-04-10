## 2026-04-10 - Image Transformation Ordering
**Learning:** Performing image operations (like flips, grayscale, etc.) on a full-resolution image *before* downscaling it for UI display causes massive, blocking CPU spikes. Resizing a 4k image and *then* applying effects drops the time from ~0.8s to ~0.04s.
**Action:** Always resize images to their target viewport dimensions *before* applying pixel-level transformations (flips, color adjustments) in rendering loops.
