"""
ai_manager.py — Advanced AI image analysis using DeepDanbooru, FalconsAI, and OpenNSFW.
"""
import logging
import threading
import re
import time
import queue
import os
import gc
from pathlib import Path

# --- CRITICAL: Import ONNX Runtime BEFORE OpenCV to avoid DLL initialization conflicts ---
try:
    # Silence OpenCV C++ stderr logs to keep terminal clean
    os.environ["OPENCV_LOG_LEVEL"] = "OFF"
    import onnxruntime as ort
    ORT_AVAILABLE = True
    ORT_ERROR = None
except Exception as e:
    ORT_AVAILABLE = False
    ORT_ERROR = str(e)

import cv2
import numpy as np
from PIL import Image

# Print status immediately to terminal
if not ORT_AVAILABLE:
    print(f"!!! AI INFO: ONNX Runtime (GPU) is not available on this system.")
    print("!!! AI INFO: (Tip: Installing 'Microsoft Visual C++ Redistributable 2019' usually fixes this).")
    print("!!! AI INFO: Using native OpenCV engine instead. Scanning will be slightly slower.")
else:
    # Pre-check providers to ensure DLLs are actually working
    try:
        providers = ort.get_available_providers()
    except Exception as e:
        ORT_AVAILABLE = False
        print(f"!!! AI WARNING: ONNX Runtime DLL failure: {e}")
        print("!!! AI INFO: Using native OpenCV engine instead.")

from database import get_connection, get_base_dir
from managers.tag_manager import TagManager

logger = logging.getLogger(__name__)

class AIManager:
    """
    Handles local AI processing for detailed tagging and safety detection.
    Uses DeepDanbooru (ONNX) for poses, FalconsAI (ViT) for safety, 
    and OpenNSFW (Caffe) as a secondary safety check.
    """
    
    def __init__(self, confidence_threshold: float = 0.5):
        self.threshold = confidence_threshold
        self.tag_mgr = TagManager()
        self._lock = threading.Lock()
        
        self.ai_dir = get_base_dir() / "data" / "ai"
        
        # Model Files
        self.dd_model_path = self.ai_dir / "deepdanbooru.onnx"
        self.dd_tags_path = self.ai_dir / "deepdanbooru_tags.txt"
        self.nsfw_model_path = self.ai_dir / "nsfw.caffemodel"
        self.nsfw_proto_path = self.ai_dir / "nsfw.prototxt"
        self.falcons_model_path = self.ai_dir / "falconsai_nsfw.onnx"
        
        # Runtime objects
        self.dd_net = None
        self.dd_session = None
        self.dd_tags = []
        self.nsfw_net = None
        self.falcons_session = None

        # Hardware Status
        self.active_cv2_backend = "CPU"
        self.active_ort_provider = "CPU"

        # Worker Queue System
        self._queue = queue.PriorityQueue()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._progress_callback = None
        self._processed_count = 0
        self._total_in_batch = 0
        self._idle_start_time = None
        self.IDLE_UNLOAD_TIMEOUT = 60 # seconds

    def get_hardware_status(self) -> str:
        """Returns a formatted string representing the active AI backends."""
        cv2_status = self.active_cv2_backend
        if os.environ.get("OPENCV_OCL4DNN_DISABLE_OPCL") == "1" and cv2_status == "OpenCL":
            cv2_status = "CPU (Forced)"
        return f"{cv2_status} (OpenCV) / {self.active_ort_provider} (ONNX)"

    def _set_net_gpu(self, net):
        """Attempts to enable GPU acceleration for an OpenCV DNN network."""
        # Check environment override first
        if os.environ.get("OPENCV_OCL4DNN_DISABLE_OPCL") == "1":
            logger.info("OpenCV OpenCL disabled via environment.")
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.active_cv2_backend = "CPU"
            return

        try:
            # Try CUDA first (requires opencv-python-cuda or custom build)
            if hasattr(cv2, 'cuda') and cv2.cuda.getCudaEnabledDeviceCount() > 0:
                net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                self.active_cv2_backend = "CUDA"
                logger.info("OpenCV DNN using CUDA backend.")
            else:
                # Fallback to OpenCL (available on most modern GPUs)
                net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                net.setPreferableTarget(cv2.dnn.DNN_TARGET_OPENCL)
                self.active_cv2_backend = "OpenCL"
                logger.info("OpenCV DNN using OpenCL backend.")
        except Exception as e:
            logger.warning(f"Failed to set OpenCV GPU backend, falling back to CPU: {e}")
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.active_cv2_backend = "CPU"

    def _load_models(self):
        """Lazy load AI models into memory."""
        # Reset idle timer when we need models
        self._idle_start_time = None
        
        # Ensure OpenCL logs don't clutter terminal if we haven't disabled them yet
        if os.environ.get("OPENCV_OCL4DNN_DISABLE_OPCL") != "1":
            cv2.ocl.setUseOpenCL(False) # Default to off for stability unless we explicitly want it later
        
        with self._lock:
            # 1. Load DeepDanbooru
            if self.dd_net is None and self.dd_session is None and self.dd_model_path.exists():
                try:
                    if ORT_AVAILABLE:
                        logger.info("Loading DeepDanbooru (ONNX Runtime)...")
                        # Priority: DirectML (Windows GPU) > CUDA (NVIDIA GPU) > CPU
                        providers = ['DmlExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
                        self.dd_session = ort.InferenceSession(str(self.dd_model_path), providers=providers)
                        active = self.dd_session.get_providers()
                        logger.info(f"DeepDanbooru ORT loaded with: {active}")
                    else:
                        logger.info("Loading DeepDanbooru (OpenCV DNN)...")
                        self.dd_net = cv2.dnn.readNetFromONNX(str(self.dd_model_path))
                        self._set_net_gpu(self.dd_net)
                    
                    if self.dd_tags_path.exists():
                        with open(self.dd_tags_path, 'r') as f:
                            self.dd_tags = [line.strip() for line in f.readlines()]
                except Exception as e:
                    logger.error(f"Failed to load DeepDanbooru: {e}")

            # 2. Load OpenNSFW (OpenCV DNN)
            if self.nsfw_net is None and self.nsfw_model_path.exists():
                try:
                    logger.info("Loading OpenNSFW (Caffe)...")
                    self.nsfw_net = cv2.dnn.readNetFromCaffe(str(self.nsfw_proto_path), str(self.nsfw_model_path))
                    self._set_net_gpu(self.nsfw_net)
                    logger.info("OpenNSFW loaded.")
                except Exception as e:
                    logger.error(f"Failed to load OpenNSFW: {e}")

            # 3. Load FalconsAI NSFW (ONNX Runtime)
            if ORT_AVAILABLE and self.falcons_session is None and self.falcons_model_path.exists():
                try:
                    logger.info("Loading FalconsAI NSFW (ONNX Runtime)...")
                    providers = ['DmlExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
                    self.falcons_session = ort.InferenceSession(str(self.falcons_model_path), providers=providers)
                    active_providers = self.falcons_session.get_providers()
                    if active_providers:
                        self.active_ort_provider = active_providers[0].replace("ExecutionProvider", "")
                    logger.info(f"FalconsAI loaded with providers: {active_providers}")
                except Exception as e:
                    logger.error(f"Failed to load FalconsAI: {e}")
                    self.falcons_session = None

    def unload_models(self):
        """Releases AI model objects from memory to free RAM/VRAM."""
        with self._lock:
            logger.info("Unloading AI models from memory (Idle timeout)...")
            self.dd_net = None
            self.dd_session = None
            self.nsfw_net = None
            self.falcons_session = None
            self.active_cv2_backend = "CPU"
            self.active_ort_provider = "CPU"
            # Explicit garbage collection
            gc.collect()

    def analyze_image(self, image_id: int, file_path: str) -> bool:
        """Runs the image through the tagging pipeline."""
        self._load_models()
        
        try:
            self._update_status(image_id, 'scanning')
            path = Path(file_path)
            if not path.exists():
                self._update_status(image_id, 'failed')
                return False
                
            # Force 3-channel BGR to avoid grayscale/alpha issues
            img_cv = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if img_cv is None:
                self._update_status(image_id, 'failed')
                return False
            
            applied_tags = []
            max_nsfw_score = 0.0

            # --- Stage 1: DeepDanbooru (Tags & Poses) ---
            if (self.dd_net or self.dd_session) and self.dd_tags:
                try:
                    if self.dd_session:
                        # ONNX Runtime path (High performance, supports NCHW)
                        with Image.open(path) as pil_img:
                            img_pil = pil_img.convert("RGB").resize((512, 512))
                        img_data = np.array(img_pil).astype('float32') / 255.0
                        img_data = np.transpose(img_data, (2, 0, 1)) # HWC to CHW
                        img_data = np.expand_dims(img_data, axis=0)
                        
                        input_name = self.dd_session.get_inputs()[0].name
                        outputs = self.dd_session.run(None, {input_name: img_data})
                        preds = outputs[0][0]
                    else:
                        # OpenCV path (Fixed shape NHWC for DeepDanbooru compatibility)
                        # This avoids the C++ getMemoryShapes exception entirely
                        img_resized = cv2.resize(img_cv, (512, 512))
                        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                        blob = np.expand_dims(img_rgb.astype(np.float32) / 255.0, axis=0)
                        self.dd_net.setInput(blob)
                        preds = self.dd_net.forward()[0]

                    for idx, prob in enumerate(preds):
                        tag_name = self.dd_tags[idx].replace('_', ' ').title()
                        
                        # Safety check is independent of general tag threshold
                        if tag_name.lower() == "rating:explicit":
                            max_nsfw_score = max(max_nsfw_score, float(prob))
                        elif tag_name.lower() == "rating:questionable":
                            max_nsfw_score = max(max_nsfw_score, float(prob) * 0.8)
                        
                        # General tags still respect the threshold
                        if prob >= self.threshold and not tag_name.lower().startswith("rating:"):
                            applied_tags.append((tag_name, float(prob)))
                except Exception as e:
                    logger.error(f"DeepDanbooru failed: {e}")

            # --- Stage 2: FalconsAI NSFW (ViT Primary) ---
            if self.falcons_session:
                try:
                    with Image.open(path) as pil_img:
                        img_pil = pil_img.convert("RGB").resize((224, 224))
                    img_data = np.array(img_pil).astype('float32')
                    img_data = np.transpose(img_data, (2, 0, 1))
                    img_data = np.expand_dims(img_data, axis=0)
                    img_data = (img_data / 255.0 - 0.5) / 0.5
                    
                    input_name = self.falcons_session.get_inputs()[0].name
                    outputs = self.falcons_session.run(None, {input_name: img_data})
                    logits = outputs[0][0]
                    exp_logits = np.exp(logits - np.max(logits))
                    probs = exp_logits / exp_logits.sum()
                    max_nsfw_score = max(max_nsfw_score, float(probs[1]))
                except Exception as e:
                    logger.error(f"FalconsAI failed: {e}")

            # --- Stage 3: OpenNSFW (Yahoo Secondary) ---
            if self.nsfw_net:
                try:
                    blob = cv2.dnn.blobFromImage(img_cv, 1.0, (224, 224), (104, 117, 123), swapRB=False)
                    self.nsfw_net.setInput(blob)
                    preds = self.nsfw_net.forward()
                    max_nsfw_score = max(max_nsfw_score, float(preds[0][1]))
                except Exception as e:
                    logger.error(f"OpenNSFW failed: {e}")

            # --- Safety Decision ---
            if max_nsfw_score > 0.8:
                applied_tags.append(("Sensitive", max_nsfw_score))
            elif max_nsfw_score > 0.5:
                applied_tags.append(("Questionable", max_nsfw_score))

            # --- Stage 4: Smart Metadata ---
            applied_tags.extend(self._get_smart_metadata(path))
            
            # --- Commit All Tags in One Batch ---
            if applied_tags:
                self.tag_mgr.tag_image_ai_batch(image_id, applied_tags)
            
            self._update_status(image_id, 'completed')
            return True, applied_tags
        except Exception as e:
            logger.error(f"AI Pipeline failed for {file_path}: {e}")
            self._update_status(image_id, 'failed')
            return False, []

    def _get_smart_metadata(self, path: Path) -> list[tuple[str, float]]:
        tags = []
        try:
            words = re.findall(r'[a-zA-Z]+', path.stem)
            for word in words:
                if len(word) > 3:
                    tags.append((word.title(), 0.9))
            with Image.open(path) as img:
                w, h = img.size
                if w > h * 1.5: tags.append(("Panoramic", 0.9))
                elif h > w * 1.2: tags.append(("Portrait", 0.9))
                else: tags.append(("Landscape", 0.9))
        except Exception as e:
            logger.error(f"Smart metadata extraction failed for {path.name}: {e}")
        return tags

    def _update_status(self, image_id: int, status: str):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE images SET ai_status = ? WHERE id = ?", (status, image_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to update status: {e}")

    def enqueue_images(self, image_data: list, priority: bool = False):
        """
        Adds images to the processing queue.
        image_data: list of dicts or tuples containing 'id' and 'file_path'.
        """
        prio = 0 if priority else 1
        timestamp = time.time()
        
        with self._lock:
            for item in image_data:
                if isinstance(item, dict):
                    iid, path = item['id'], item['file_path']
                else:
                    iid, path = item
                self._queue.put((prio, timestamp, iid, path))
            
            self._total_in_batch = self._queue.qsize()
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._stop_event.clear()
                self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
                self._worker_thread.start()

    def _worker_loop(self):
        """Persistent background thread that processes the priority queue."""
        logger.info("AI Worker thread started.")
        self._processed_count = 0
        self._idle_start_time = None
        
        while not self._stop_event.is_set():
            try:
                # Wait for a task (1s timeout to check stop_event and handle idle)
                try:
                    prio, ts, iid, path = self._queue.get(timeout=1.0)
                    self._idle_start_time = None # Reset idle timer on task
                except queue.Empty:
                    if self._queue.empty():
                        if self._progress_callback and self._processed_count > 0:
                            self._progress_callback(self._processed_count, self._processed_count, None, 'idle')
                            self._processed_count = 0 # Reset for next batch
                        
                        # Handle idle timeout
                        if self.dd_net or self.dd_session or self.nsfw_net or self.falcons_session:
                            if self._idle_start_time is None:
                                self._idle_start_time = time.time()
                            elif time.time() - self._idle_start_time > self.IDLE_UNLOAD_TIMEOUT:
                                self.unload_models()
                                self._idle_start_time = None
                    continue

                # Update progress (Scanning state)
                if self._progress_callback:
                    self._progress_callback(self._processed_count, self._processed_count + self._queue.qsize() + 1, iid, 'scanning')
                
                # Process the image
                success, tags = self.analyze_image(iid, path)
                self._processed_count += 1
                
                # Update progress (Result state)
                if self._progress_callback:
                    status = 'completed' if success else 'failed'
                    self._progress_callback(
                        self._processed_count, 
                        self._processed_count + self._queue.qsize(), 
                        iid, 
                        status,
                        tags=tags
                    )
                
                self._queue.task_done()
                
                # Cooling delay to prevent hardware fatigue
                time.sleep(0.15)
                
            except Exception as e:
                logger.error(f"AI Worker loop error: {e}")

    def stop_worker(self):
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)

    def scan_pending_images(self, stop_event: threading.Event = None, progress_callback=None, scan_all: bool = False):
        """Deprecated batch method - now redirects to the priority queue system."""
        if progress_callback:
            self._progress_callback = progress_callback
        try:
            conn = get_connection()
            cursor = conn.cursor()
            if scan_all:
                cursor.execute("SELECT id, file_path FROM images")
            else:
                cursor.execute("SELECT id, file_path FROM images WHERE ai_status IS NULL OR ai_status = 'pending'")
            
            rows = cursor.fetchall()
            if rows:
                self.enqueue_images([(r['id'], r['file_path']) for r in rows], priority=False)
        except Exception as e:
            logger.error(f"Failed to fetch pending images: {e}")
