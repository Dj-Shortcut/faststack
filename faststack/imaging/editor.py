import logging
import os
import shutil
import glob
import re
import math
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO



from faststack.models import DecodedImage
try:
    from PySide6.QtGui import QImage
except ImportError:
    QImage = None

import threading
import cv2

log = logging.getLogger(__name__)

# Aspect Ratios for cropping
INSTAGRAM_RATIOS = {
    "Freeform": None,
    "1:1 (Square)": (1, 1),
    "4:5 (Portrait)": (4, 5),
    "1.91:1 (Landscape)": (191, 100),
    "9:16 (Story)": (9, 16),
}

def create_backup_file(original_path: Path) -> Optional[Path]:
    """
    Creates a backup of the original file with naming pattern:
    filename-backup.jpg, filename-backup2.jpg, etc.
    
    Returns:
        Path to the backup file on success, None on failure.
    """
    if not original_path.exists():
        return None
    
    # Extract base name without any existing -backup suffix
    stem = original_path.stem
    # Remove any existing -backup, -backup2, -backup-1, etc. (handles both old and new formats)
    base_stem = re.sub(r'-backup(-?\d+)?$', '', stem)
    
    # Try filename-backup.jpg first
    backup_path = original_path.parent / f"{base_stem}-backup{original_path.suffix}"
    
    # If that exists, try filename-backup2.jpg, filename-backup3.jpg, etc.
    i = 2
    while backup_path.exists():
        backup_path = original_path.parent / f"{base_stem}-backup{i}{original_path.suffix}"
        i += 1
    
    try:
        # Perform the backup
        shutil.copy2(original_path, backup_path)
        return backup_path
    except OSError as e:
        log.exception(f"Failed to create backup: {e}")
        return None

# ----------------------------
# sRGB ↔ Linear Conversion Helpers
# ----------------------------

def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    """Convert sRGB values to linear light.
    
    Preserves headroom (values > 1.0) for highlight recovery.
    Clamps negatives to 0 since the power function requires non-negative input.
    """
    # Clamp negatives to 0, but preserve values > 1.0 for headroom
    x = np.clip(x, 0.0, None)
    a = 0.055
    # Apply the standard sRGB transfer function - works for values > 1.0 too
    return np.where(x <= 0.04045, x / 12.92, ((x + a) / (1.0 + a)) ** 2.4)


def _linear_to_srgb(x: np.ndarray) -> np.ndarray:
    """Convert linear light values to sRGB (0-1)."""
    x = np.clip(x, 0.0, None)
    a = 0.055
    return np.where(x <= 0.0031308, 12.92 * x, (1.0 + a) * (x ** (1.0 / 2.4)) - a)


def _apply_soft_shoulder(x: np.ndarray, threshold: float = 0.9) -> np.ndarray:
    """Applies a tone-mapping shoulder to roll off highlights above the threshold.
    
    This prevents hard clipping by compressing the range [threshold, inf) into [threshold, 1.0).
    The function is monotonic and smooth.
    """
    if threshold >= 1.0:
        return x
    
    # We only apply the shoulder to values above the threshold
    mask = x > threshold
    if not np.any(mask):
        return x
        
    # Scale and compress: 1 - exp(-(x - threshold) / (1 - threshold))
    # This maps [threshold, inf) to [threshold, threshold + (1 - threshold)) = [threshold, 1.0)
    # The derivative at threshold is 1.0, matching the linear part.
    scaled = (x[mask] - threshold) / (1.0 - threshold)
    compressed = threshold + (1.0 - threshold) * (1.0 - np.exp(-scaled))
    
    out = x.copy()
    out[mask] = compressed
    return out


def _smoothstep01(x: np.ndarray) -> np.ndarray:
    """Hermite smoothstep: 0 at x<=0, 1 at x>=1, smooth S-curve between."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _gaussian_blur_float(arr: np.ndarray, radius: float) -> np.ndarray:
    """Apply Gaussian Blur to a float32 array using OpenCV.
    
    Preserves values outside [0, 1] range.
    """
    if radius <= 0:
        return arr
    
    # Sigma calculation matching Pillow's radius-to-sigma
    # Radius in Pillow is the radius of the kernel, sigma is approx radius / 2
    # OpenCV's GaussianBlur takes sigma.
    sigma = radius / 2.0
    
    # We use (0, 0) for ksize to let OpenCV calculate it based on sigma
    return cv2.GaussianBlur(arr, (0, 0), sigmaX=sigma, sigmaY=sigma, borderType=cv2.BORDER_REFLECT)


# ----------------------------
# Rotate + Autocrop helper
# ----------------------------

def _rotated_rect_with_max_area(w: int, h: int, angle_rad: float) -> tuple[int, int]:
    """
    Largest axis-aligned rectangle within a w x h rectangle rotated by angle_rad.
    Returns (crop_w, crop_h) in pixels.
    """
    if w <= 0 or h <= 0:
        return 0, 0

    # fold angle into [0, pi/2)
    angle_rad = abs(angle_rad) % (math.pi / 2)
    if angle_rad > math.pi / 4:
        angle_rad = (math.pi / 2) - angle_rad

    sin_a = abs(math.sin(angle_rad))
    cos_a = abs(math.cos(angle_rad))

    # if basically unrotated
    if sin_a < 1e-12:
        return w, h

    width_is_longer = w >= h
    side_long = w if width_is_longer else h
    side_short = h if width_is_longer else w

    # "half constrained" case
    if side_short <= 2.0 * sin_a * cos_a * side_long or abs(sin_a - cos_a) < 1e-12:
        x = 0.5 * side_short
        if width_is_longer:
            wr = x / sin_a
            hr = x / cos_a
        else:
            wr = x / cos_a
            hr = x / sin_a
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr = (w * cos_a - h * sin_a) / cos_2a
        hr = (h * cos_a - w * sin_a) / cos_2a

    cw = round(abs(wr))
    ch = round(abs(hr))
    cw = max(1, min(w, cw))
    ch = max(1, min(h, ch))
    return cw, ch


def rotate_autocrop_rgb(img: Image.Image, angle_deg: float, inset: int = 2) -> Image.Image:
    """
    Rotate by any angle and then crop to the largest axis-aligned rectangle that contains
    ONLY valid pixels (no wedges). Works for large angles.
    """
    if abs(angle_deg) < 0.01:
        return img.convert("RGB")

    img = img.convert("RGB")
    w, h = img.size

    # Reduce angle for rectangle math (rotation by 120° has same inscribed rect as 60°)
    a = abs(angle_deg) % 180.0
    if a > 90.0:
        a = 180.0 - a
    angle_rad = math.radians(a)

    # Largest rectangle inside the rotated original (in original pixel coordinates)
    crop_w, crop_h = _rotated_rect_with_max_area(w, h, angle_rad)
    crop_w = max(1, min(w, crop_w))
    crop_h = max(1, min(h, crop_h))

    # Rotate with expand so content is preserved
    rot = img.rotate(
        -angle_deg,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(0, 0, 0),
    )

    # Center-crop to the inscribed rectangle
    cx = rot.width / 2.0
    cy = rot.height / 2.0
    left = round(cx - crop_w / 2.0)
    top = round(cy - crop_h / 2.0)
    right = left + crop_w
    bottom = top + crop_h

    # Small inset to remove any bicubic edge contamination
    if inset > 0 and (right - left) > 2 * inset and (bottom - top) > 2 * inset:
        left += inset
        top += inset
        right -= inset
        bottom -= inset

    # Clamp defensively
    left = max(0, min(rot.width - 1, left))
    top = max(0, min(rot.height - 1, top))
    right = max(left + 1, min(rot.width, right))
    bottom = max(top + 1, min(rot.height, bottom))

    out = rot.crop((left, top, right, bottom)).convert("RGB")
    return out


class ImageEditor:
    """Handles core image manipulation using PIL."""
    def __init__(self):
        # Stores the currently loaded PIL Image object (original)
        self.original_image: Optional[Image.Image] = None
        # Float32 normalized master image (H, W, 3) range 0.0-1.0
        self.float_image: Optional[np.ndarray] = None
        # Float32 normalized preview image
        self.float_preview: Optional[np.ndarray] = None
        
        # Stores the currently applied edits (used for preview)
        self.current_edits: Dict[str, Any] = self._initial_edits()
        self.current_filepath: Optional[Path] = None
        
        # Caching support for smooth updates
        self._lock = threading.RLock()
        self._edits_rev = 0
        self._cached_rev = -1
        self._cached_preview = None
        
        # Bit depth of the loaded image (8 or 16)
        self.bit_depth: int = 8
        
        # Cached EXIF bytes from original source (e.g., paired JPEG for RAW mode)
        # Used to preserve camera metadata when saving developed JPGs
        self._source_exif_bytes: Optional[bytes] = None
        
    def clear(self):
        """Clear all editor state so the next edit starts from a clean slate."""
        with self._lock:
            self.original_image = None
            self.current_filepath = None
            self.float_image = None
            self.float_preview = None
            self._edits_rev += 1
            self._cached_preview = None
            self._cached_rev = -1
            self.bit_depth = 8
            self._source_exif_bytes = None
        # Optionally also reset edits if that matches your mental model:
        # self.current_edits = self._initial_edits()

    def set_source_exif(self, exif_bytes: Optional[bytes]):
        """Store EXIF bytes from the original source (e.g., paired JPEG).
        
        Call this when switching to RAW mode to preserve camera metadata
        in the developed JPG output.
        """
        self._source_exif_bytes = exif_bytes

    def reset_edits(self):
        """Reset edits to initial values and bump revision."""
        with self._lock:
            self.current_edits = self._initial_edits()
            self._edits_rev += 1

    def _initial_edits(self) -> Dict[str, Any]:
        return {
            'brightness': 0.0,
            'contrast': 0.0,
            'saturation': 0.0,
            'white_balance_by': 0.0, # Blue/Yellow (Cool/Warm)
            'white_balance_mg': 0.0, # Magenta/Green (Tint)
            'crop_box': None, # (left, top, right, bottom) normalized to 0-1000
            'sharpness': 0.0,
            'rotation': 0,
            'exposure': 0.0,
            'highlights': 0.0,
            'shadows': 0.0,
            'vibrance': 0.0,
            'vignette': 0.0,
            'blacks': 0.0,
            'whites': 0.0,
            'clarity': 0.0,
            'texture': 0.0,
            'straighten_angle': 0.0,
        }

    def load_image(self, filepath: str, cached_preview: Optional[DecodedImage] = None, source_exif: Optional[bytes] = None):
        """Load a new image for editing.
        
        Args:
            filepath: Path to the image file
            cached_preview: Optional byte-buffer for faster initial display
            source_exif: Optional EXIF bytes from original source (preserve camera metadata)
        """
        if not filepath or not Path(filepath).exists():
            with self._lock:
                self.original_image = None
                self.float_image = None
                self.float_preview = None
                self.current_filepath = None
                self._source_exif_bytes = None
                self._edits_rev += 1
                self._cached_preview = None
                self._cached_rev = -1
            return False
        
        load_filepath = Path(filepath)
        
        with self._lock:
            # Clear previous cached EXIF and set new one if provided
            self._source_exif_bytes = source_exif
            
        try:
            # We must load and close the original file handle immediately
            with Image.open(load_filepath) as im:
                # Keep original PIL for EXIF/Format preservation
                loaded_original = im.copy()
                
            # --- Convert to Float32 ---
            # Use OpenCV for reliable 16-bit loading as Pillow often downsamples to 8-bit RGB
            import cv2
            
            # Use IMREAD_UNCHANGED to preserve bit depth
            # Note: OpenCV loads as BGR by default
            cv_img = cv2.imread(str(load_filepath), cv2.IMREAD_UNCHANGED)
            
            # Robust validation: cv2.imread can return None or an empty/invalid array
            cv_img_valid = (
                cv_img is not None
                and isinstance(cv_img, np.ndarray)
                and cv_img.size > 0
            )
            
            loaded_bit_depth = 8
            loaded_float_image = None
            
            if cv_img_valid and cv_img.dtype == np.uint16:
                loaded_bit_depth = 16
                # Normalize 0-65535 -> 0.0-1.0
                arr = cv_img.astype(np.float32) / 65535.0
                
                # Handle channels
                if len(arr.shape) == 2:
                    # Grayscale -> RGB
                    arr = np.stack((arr,)*3, axis=-1)
                elif len(arr.shape) == 3 and arr.shape[2] == 3:
                     # BGR -> RGB (OpenCV default)
                     # Note: If IMREAD_UNCHANGED loads a TIFF, it *might* be RGB depending on backend (libtiff).
                     # But consistently OpenCV uses BGR layout for 3-channel images.
                     # Let's verify by assuming BGR and swapping.
                     arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                else:
                    # Invalid channel count, fall back to Pillow
                    cv_img_valid = False
                    loaded_bit_depth = 8
                    rgb = loaded_original.convert("RGB")
                    arr = np.array(rgb).astype(np.float32) / 255.0
                    log.warning(f"OpenCV loaded unexpected channel count, falling back to Pillow: {load_filepath}")
                
                loaded_float_image = arr
                log.info(f"Loaded 16-bit image via OpenCV: {load_filepath}")
            else:
                # Fallback to Pillow logic for 8-bit or if OpenCV failed/returned 8-bit
                loaded_bit_depth = 8
                rgb = loaded_original.convert("RGB")
                loaded_float_image = np.array(rgb).astype(np.float32) / 255.0
                log.info(f"Loaded 8-bit image via Pillow: {load_filepath}")

            # --- Create Float Preview ---
            # Use the cached, display-sized preview if available to speed up
            if cached_preview:
                # cached_preview.buffer is uint8
                preview_arr = np.frombuffer(cached_preview.buffer, dtype=np.uint8).reshape(
                    (cached_preview.height, cached_preview.width, 3)
                )
                loaded_float_preview = preview_arr.astype(np.float32) / 255.0
            else:
                # Downscale from float_image
                # Simple striding for speed or creating a PIL thumbnail from original?
                # PIL thumbnail is faster and better quality usually.
                thumb = loaded_original.copy()
                thumb.thumbnail((1920, 1080))
                thumb_rgb = thumb.convert("RGB")
                loaded_float_preview = np.array(thumb_rgb).astype(np.float32) / 255.0

            # Assign all state atomically under lock to prevent race with preview worker
            with self._lock:
                self.current_filepath = load_filepath
                self.original_image = loaded_original
                self.float_image = loaded_float_image
                self.float_preview = loaded_float_preview
                self.bit_depth = loaded_bit_depth
                # Reset edits
                self.current_edits = self._initial_edits()
                self._edits_rev += 1
                self._cached_preview = None
                self._cached_rev = -1

            return True
        except Exception as e:
            log.exception(f"Error loading image for editing: {e}")
            with self._lock:
                self.original_image = None
                self.float_image = None
                self.float_preview = None
                self.current_filepath = None
                self._edits_rev += 1
                self._cached_preview = None
                self._cached_rev = -1
            return False


    def _rotate_float_image(self, img_arr: np.ndarray, angle_deg: float, expand: bool = False) -> np.ndarray:
        """Rotates a float32 RGB image using PIL 'F' mode per channel to preserve precision."""
        if abs(angle_deg) < 0.01:
            return img_arr

        h, w, c = img_arr.shape
        channels = []
        for i in range(c):
            # Convert channel to PIL Float image
            im_c = Image.fromarray(img_arr[:, :, i], mode='F')
            # Rotate
            rot_c = im_c.rotate(
                angle_deg,
                resample=Image.Resampling.BICUBIC,
                expand=expand,
                fillcolor=0.0
            )
            channels.append(rot_c)
        
        # Merge back
        # Assume all channels rotated to same size
        nw, nh = channels[0].size
        new_arr = np.stack([np.array(ch) for ch in channels], axis=-1)
        return new_arr

    def _apply_edits(self, img_arr: np.ndarray, edits: Optional[Dict[str, Any]] = None, *, for_export: bool = False) -> np.ndarray:
        """Applies all current edits to the provided float32 numpy array.
           Returns float32 array (H, W, 3).
        """
        if edits is None:
            edits = self.current_edits

        arr = img_arr # Alias

        # 1. Rotation (90 degree steps)
        # np.rot90 rotates 90 degrees CCW k times.
        rotation = edits.get('rotation', 0)
        k = (rotation // 90) % 4
        if k > 0:
            # np.rot90 rotates first two axes by default (rows, cols)
            arr = np.rot90(arr, k=k)

        # 2. Straighten (Free Rotation)
        straighten_angle = float(edits.get('straighten_angle', 0.0))
        has_crop_box = 'crop_box' in edits and edits.get('crop_box', 0.0)

        # Apply rotation if significant
        # During preview (for_export=False), we might skip this if QML handles visuals,
        # BUT current QML implementation likely expects the buffer to be pre-transformed?
        # Actually `editor.py` says "During preview (for_export=False), QML handles the visual rotation."
        # If so, we skip free rotation here for speed?
        # But if we crop, we MUST rotate first.
        # Let's preserve logic: if only straightening and not exporting, maybe skip?
        # The previous code skipped it if NOT for_export?
        # "Only apply rotation if... and we are exporting" was the comment. implies preview logic handles it.
        # However, for accurate cropping, we need to rotate.
        
        apply_rotation = abs(straighten_angle) > 0.001 and (for_export or has_crop_box)
        
        if apply_rotation:
             # Use the float rotation helper
             # Note: rotate_autocrop_rgb logic was complex.
             # If we have crop box, we manually crop later.
             # If no crop box, we might auto-crop (remove wedges).
             # For floating point, standard 'expand' rotation + manual crop is best.
             
             # Calculate auto-crop parameters BEFORE rotation if needed
             crop_rect = None
             if not has_crop_box:
                 h, w = arr.shape[:2]
                 # Normalize angle for helper (helper expects radians, handles quadrants but ensuring positive can help)
                 angle_rad = math.radians(straighten_angle)
                 # Helper logic for crop size
                 cw, ch = _rotated_rect_with_max_area(w, h, angle_rad)
                 crop_rect = (cw, ch)

             # Perform rotation (Expanded)
             arr = self._rotate_float_image(arr, -straighten_angle, expand=True)
             
             # Apply Auto-Crop if calculated
             if crop_rect:
                cw, ch = crop_rect
                # Center crop on the new expanded image
                rh, rw = arr.shape[:2]
                cx, cy = rw / 2.0, rh / 2.0
                
                left = round(cx - cw / 2.0)
                top = round(cy - ch / 2.0)
                right = left + cw
                bottom = top + ch
                
                # Apply inset (2px) to match legacy behavior and avoid edge artifacts
                inset = 2
                if (right - left) > 2 * inset and (bottom - top) > 2 * inset:
                    left += inset
                    top += inset
                    right -= inset
                    bottom -= inset
                
                # Clamp
                left = max(0, min(rw - 1, left))
                top = max(0, min(rh - 1, top))
                right = max(left + 1, min(rw, right))
                bottom = max(top + 1, min(rh, bottom))
                
                arr = arr[top:bottom, left:right, :]

        # 3. Crop
        if has_crop_box:
            crop_box = edits.get('crop_box', 0.0)
            if len(crop_box) == 4:
                # 0-1000 relative to current size
                h, w = arr.shape[:2]
                left = int(crop_box[0] * w / 1000)
                t = int(crop_box[1] * h / 1000)
                r = int(crop_box[2] * w / 1000)
                b = int(crop_box[3] * h / 1000)

                left = max(0, left)
                t = max(0, t)
                r = min(w, r)
                b = min(h, b)

                if r > left and b > t:
                    arr = arr[t:b, left:r, :]

        # --- Color Pipeline (Linear / Float) ---
        
        # 4. Conversion to Linear Light
        # We convert once and do most color work in linear space.
        arr = _srgb_to_linear(arr)

        # 5. White Balance (Multipliers in Linear Space)
        by = edits.get('white_balance_by', 0.0) * 0.5
        mg = edits.get('white_balance_mg', 0.0) * 0.5
        if abs(by) > 0.001 or abs(mg) > 0.001:
             r_gain = 1.0 + by
             b_gain = 1.0 - by
             g_gain = 1.0 - mg
             arr[:,:,0] *= r_gain
             arr[:,:,1] *= g_gain
             arr[:,:,2] *= b_gain

        # 6. Exposure (Linear Gain for True Headroom)
        exposure = edits.get('exposure', 0.0)
        if abs(exposure) > 0.001:
             # EV units: 2^exposure
             gain = 2.0 ** exposure
             arr = arr * gain

        # 7. Highlights/Shadows - Using linear light and luminance-based processing
        highlights = float(edits.get('highlights', 0.0))
        shadows = float(edits.get('shadows', 0.0))
        if abs(highlights) > 0.001 or abs(shadows) > 0.001:
            arr = self._apply_highlights_shadows(arr, highlights, shadows)

        # 8. Clarity (Local Contrast)
        clarity = edits.get('clarity', 0.0)
        if abs(clarity) > 0.001:
             # Apply in linear space, preservation of highlights
             blurred_arr = _gaussian_blur_float(arr, radius=20.0)
             
             # Apply: (original - blurred) is high pass.
             # mask = midtones
             # mean = axis 2
             gray = arr.mean(axis=2, keepdims=True)
             midtone_mask = 1.0 - np.abs(np.clip(gray, 0, 1) - 0.5) * 2.0
             
             local_contrast = (arr - blurred_arr) * clarity * midtone_mask
             arr += local_contrast

        # 9. Texture (Fine Detail)
        texture = edits.get('texture', 0.0)
        if abs(texture) > 0.001:
             # Small radius for texture/fine detail
             blurred_arr = _gaussian_blur_float(arr, radius=3.0)
             high_pass = arr - blurred_arr
             arr += high_pass * texture

        # 10. Sharpness
        sharpness = edits.get('sharpness', 0.0)
        if abs(sharpness) > 0.001:
             # Unsharp mask with radius ~1.0
             blurred_arr = _gaussian_blur_float(arr, radius=1.0)
             high_pass = arr - blurred_arr
             arr += high_pass * sharpness

        # --- Conversion back to sRGB ---
        arr = _linear_to_srgb(arr)

        # 11. Brightness / Contrast (sRGB Space)
        # 7. Brightness
        b_val = edits.get('brightness', 0.0)
        if abs(b_val) > 0.001:
            factor = 1.0 + b_val
            arr = arr * factor

        # 8. Contrast
        c_val = edits.get('contrast', 0.0)
        if abs(c_val) > 0.001:
            factor = 1.0 + c_val
            arr = (arr - 0.5) * factor + 0.5

        # 12. Saturation / Vibrance (sRGB Space)
        # 10. Saturation
        sat_val = edits.get('saturation', 0.0)
        if abs(sat_val) > 0.001:
             factor = 1.0 + sat_val
             gray = arr.dot([0.299, 0.587, 0.114])
             gray = np.expand_dims(gray, axis=2)
             arr = gray + (arr - gray) * factor

        # 12. Vibrance (Smart Saturation)
        vibrance = edits.get('vibrance', 0.0)
        if abs(vibrance) > 0.001:
             cmax = arr.max(axis=2)
             cmin = arr.min(axis=2)
             delta = cmax - cmin
             sat = np.zeros_like(cmax)
             mask = cmax > 0.0001
             sat[mask] = delta[mask] / cmax[mask]
             
             sat_mask = np.clip(1.0 - sat, 0.0, 1.0)
             factor = 1.0 + vibrance * sat_mask
             
             gray = arr.dot([0.299, 0.587, 0.114])
             gray = np.expand_dims(gray, axis=2)
             arr = gray + (arr - gray) * np.expand_dims(factor, axis=2)

        # 13. Levels (Blacks/Whites)
        blacks = edits.get('blacks', 0.0)
        whites = edits.get('whites', 0.0)
        if abs(blacks) > 0.001 or abs(whites) > 0.001:
            bp = -blacks * 0.15
            wp = 1.0 - (whites * 0.15)
            if abs(wp - bp) < 0.0001:
                wp = bp + 0.0001
            arr = (arr - bp) / (wp - bp)

        # 14. Vignette
        vignette = edits.get('vignette', 0.0)
        if abs(vignette) > 0.001:
             h, w = arr.shape[:2]
             y, x = np.ogrid[:h, :w]
             cx = (x - w/2) / (w/2)
             cy = (y - h/2) / (h/2)
             dist_sq = cx**2 + cy**2
             
             if vignette > 0:
                 gain = 1.0 - np.clip(dist_sq * vignette, 0.0, 1.0)
                 arr *= np.expand_dims(gain, axis=2)
             else:
                 gain = 1.0 + dist_sq * (-vignette)
                 arr *= np.expand_dims(gain, axis=2)
        
        return arr  # Potentially > 1.0 if not clipped elsewhere
    def auto_levels(self, threshold_percent: float = 0.1) -> Tuple[float, float, float, float]:
        """
        Returns (blacks, whites, p_low, p_high).
        p_low/p_high are computed conservatively from RGB to avoid introducing new channel clipping.
        """
        threshold_percent = max(0.0, min(10.0, threshold_percent))
        # Use preview for speed
        img_arr = self.float_preview if self.float_preview is not None else self.float_image

        if img_arr is None:
            # Fallback for tests or cases where float data isn't initialized yet
            if hasattr(self, '_preview_image') and self._preview_image is not None:
                img_arr = np.array(self._preview_image.convert("RGB")).astype(np.float32) / 255.0
            elif self.original_image is not None:
                img_arr = np.array(self.original_image.convert("RGB")).astype(np.float32) / 255.0
            else:
                return 0.0, 0.0, 0.0, 255.0

        # Convert to unit8 (0-255) for histogram analysis
        # This preserves the logic of the original algorithm which was tuned for 0-255 bins
        rgb = (np.clip(img_arr, 0.0, 1.0) * 255).astype(np.uint8)
        # rgb shape: (H, W, 3)

        low_p = threshold_percent
        high_p = 100.0 - threshold_percent

        # --- Detect pre-clipping (per-channel) ---
        # If *any* channel already has clipped pixels, do not push that end further.
        # eps_pct strategy: "Practical" - ignore tiny hot pixels (0.01%) but pin 
        # if there is any meaningful pre-clipping, even if below the full threshold.
        eps_pct = min(threshold_percent, 0.01)

        total = rgb.shape[0] * rgb.shape[1]
        clipped_low_pct = []
        clipped_high_pct = []
        p_lows = []
        p_highs = []

        for c in range(3):
            chan = rgb[:, :, c]
            # Treat near-white/near-black as clipped (JPEG artifacts often land on 254/1)
            clipped_low_pct.append(100.0 * float(np.count_nonzero(chan <= 1)) / float(total))
            clipped_high_pct.append(100.0 * float(np.count_nonzero(chan >= 254)) / float(total))
            
            # Use discrete selection methods to avoid interpolation surprises on uint8.
            # Fallback for older numpy (<1.22) that doesn't support method=.
            try:
                p_lows.append(float(np.percentile(chan, low_p, method="lower")))
                p_highs.append(float(np.percentile(chan, high_p, method="higher")))
            except TypeError:
                p_lows.append(float(np.percentile(chan, low_p, interpolation="lower")))
                p_highs.append(float(np.percentile(chan, high_p, interpolation="higher")))

        # Conservative anchors to avoid new channel clipping
        p_low = min(p_lows)
        p_high = max(p_highs)

        # NOTE: applying this stretch uniformly to RGB can clip individual channels 
        # more than luminance predicts. That's usually acceptable, but if we 
        # ever see weird color clipping, that might be why.

        # Pin ends if pre-clipping exists (prevents making it worse)
        if max(clipped_high_pct) > eps_pct:
            p_high = 255.0
        if max(clipped_low_pct) > eps_pct:
            p_low = 0.0

        # Safety
        p_low = max(0.0, min(255.0, p_low))
        p_high = max(0.0, min(255.0, p_high))

        # Check for degenerate range (e.g. flat image) to prevent extreme stretching
        if (p_high - p_low) < 1.0:
            blacks = 0.0
            whites = 0.0
        else:
            blacks = -p_low / 40.0
            whites = (255.0 - p_high) / 40.0

        with self._lock:
            self.current_edits["blacks"] = blacks
            self.current_edits["whites"] = whites
            self._edits_rev += 1

        return blacks, whites, float(p_low), float(p_high)

    def get_preview_data_cached(self, allow_compute: bool = True) -> Optional[DecodedImage]:
        """Return cached preview if available, otherwise compute and cache.
        
        Args:
            allow_compute: If False, returns None immediately if cache is stale (avoids blocking).
        """
        with self._lock:
            # Check cache validity
            if self._cached_preview is not None and self._cached_rev == self._edits_rev:
                return self._cached_preview
            
            if not allow_compute:
                return None
            
            # Prepare for computation - snapshot data under lock
            base = self.float_preview.copy() if self.float_preview is not None else None
            edits = dict(self.current_edits)
            rev = self._edits_rev

        if base is None:
            return None

        # Heavy computation outside lock using snapshot
        # base is float32 (H, W, 3) 0-1
        arr = self._apply_edits(base, edits=edits, for_export=False)
        
        # Convert to 8-bit for display
        # TONE MAP / CLIP
        # Apply highlight roll-off shoulder
        arr = _apply_soft_shoulder(arr)
        # Clip to 0-1
        arr = np.clip(arr, 0.0, 1.0)
        # Map to 0-255
        arr_u8 = (arr * 255).astype(np.uint8)

        if QImage is None:
            raise ImportError("PySide6.QtGui.QImage is required for get_preview_data_cached")

        # Create QImage from buffer
        img_buffer = arr_u8.tobytes()
        decoded = DecodedImage(
            buffer=memoryview(img_buffer),
            width=arr_u8.shape[1],
            height=arr_u8.shape[0],
            bytes_per_line=arr_u8.shape[1] * 3,
            format=QImage.Format.Format_RGB888
        )

        with self._lock:
            # Only cache if revision hasn't changed during computation
            if self._edits_rev == rev:
                self._cached_preview = decoded
                self._cached_rev = rev
        
        return decoded

    def get_preview_data(self) -> Optional[DecodedImage]:
        """Apply current edits and return the data as a DecodedImage."""
        return self.get_preview_data_cached()

    def get_edit_value(self, key: str, default: Any = None) -> Any:
        """Thread-safe retrieval of an edit parameter."""
        with self._lock:
            return self.current_edits.get(key, default)

    def set_edit_param(self, key: str, value: Any) -> bool:
        """Update a single edit parameter."""
        with self._lock:
            if key == 'rotation':
                # Guard against arbitrary angles in 'rotation'. It expects 90-degree steps.
                # For arbitrary rotation (drag to rotate), use 'straighten_angle'.
                try:
                    # Round to nearest 90 degrees
                    val_deg = float(value)
                    rounded_deg = round(val_deg / 90.0) * 90
                    final_val = int(rounded_deg) % 360
                    
                    if abs(val_deg - rounded_deg) > 1.0:
                         log.warning(f"'rotation' received {value}. Rounding to {final_val}. Use 'straighten_angle' for free rotation.")
                    
                    self.current_edits[key] = final_val
                    self._edits_rev += 1
                    return True
                except (ValueError, TypeError) as e:
                    log.warning(f"Invalid value for rotation {value!r}: {e}")
                    return False



            if key in self.current_edits and key != 'crop_box':
                # Check for floating point equality to prevent cache thrashing
                new_val = value
                current_val = self.current_edits.get(key)
                
                # Try to compare as floats if possible
                try:
                    vf = float(new_val)
                    cf = float(current_val)
                    if math.isclose(vf, cf, rel_tol=1e-5, abs_tol=1e-7):
                        return False
                except (ValueError, TypeError):
                    # Fallback to direct equality
                    if current_val == new_val:
                        return False

                self.current_edits[key] = value
                self._edits_rev += 1
                return True
            return False

    def _apply_highlights_shadows(self, linear: np.ndarray, highlights: float, shadows: float) -> np.ndarray:
        """Apply highlights and shadows adjustments using luminance-based processing in linear light.
        
        Args:
            linear: Float32 RGB array (H, W, 3) in linear light
            highlights: -1.0 to 1.0, negative recovers highlights, positive boosts
            shadows: -1.0 to 1.0, positive lifts shadows, negative crushes
        
        Returns:
            Adjusted float32 RGB array (linear)
        """
        # Compute luminance (Rec. 709 coefficients)
        lum = linear[:, :, 0] * 0.2126 + linear[:, :, 1] * 0.7152 + linear[:, :, 2] * 0.0722
        lum = np.clip(lum, 1e-10, None)  # Avoid division by zero
        
        # Create smooth masks for highlights/shadows regions
        # Pivot point is 0.18 (mid-gray in linear)
        pivot = 0.18
        
        # Shadow mask: high for dark pixels, fades to 0 above pivot
        shadow_mask = _smoothstep01(1.0 - lum / pivot)
        
        # Highlight mask: high for bright pixels, fades to 0 below pivot
        highlight_mask = _smoothstep01((lum - pivot) / (1.0 - pivot))
        
        # Calculate adjustments
        # Shadows: positive lifts, negative crushes
        # Apply shoulder compression to avoid clipping
        shadow_adj = shadows * 0.5  # Scale factor for effect strength
        shadow_factor = 1.0 + shadow_adj * shadow_mask
        
        # Highlights: positive boosts, negative recovers (matches user expectation)
        highlight_adj = highlights * 0.5
        highlight_factor = 1.0 + highlight_adj * highlight_mask
        
        # Combine factors and apply
        combined_factor = shadow_factor * highlight_factor
        combined_factor = np.expand_dims(combined_factor, axis=2)
        
        # Apply adjustment while preserving color ratios
        adjusted = linear * combined_factor
        
        # Soft highlight recovery for negative highlights value (recover clipped highlights)
        if highlights < -0.01:
            # Apply shoulder compression to bright areas
            recovery_strength = -highlights
            bright_mask = np.expand_dims(_smoothstep01((lum - 0.5) / 0.5), axis=2)
            # Compress values above 1.0 with a soft shoulder
            # Use a simple shoulder (1 - exp(-x)) to bring values > 1 towards 1
            compressed = 1.0 - np.exp(-np.clip(adjusted, 0, 10.0))  # Soft clip
            adjusted = adjusted * (1.0 - bright_mask * recovery_strength) + compressed * bright_mask * recovery_strength
        
        return adjusted
    
    def set_crop_box(self, crop_box: Tuple[int, int, int, int]):
        """Set the normalized crop box (left, top, right, bottom) from 0-1000."""
        with self._lock:
            self.current_edits['crop_box'] = crop_box
            self._edits_rev += 1

    def _write_tiff_16bit(self, path: Path, arr_float: np.ndarray):
        """
        Writes a float32 (0-1) numpy array as an uncompressed 16-bit RGB TIFF using OpenCV.
        arr_float shape: (H, W, 3)
        """
        # Convert to 16-bit
        # Clip to safe range before scaling
        arr = (np.clip(arr_float, 0.0, 1.0) * 65535).astype(np.uint16)
        
        # OpenCv expects BGR for imwrite
        if len(arr.shape) == 3 and arr.shape[2] == 3:
             import cv2
             arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
             success = cv2.imwrite(str(path), arr_bgr)
             if not success:
                 raise IOError(f"Failed to write TIFF -> {path}")
        else:
             raise ValueError("Only RGB supported for TIFF writer")


    def _get_sanitized_exif_bytes(self) -> Optional[bytes]:
        """
        Returns EXIF bytes with Orientation reset to 1 (Normal).
        Used when we've baked rotation/straightening into the pixels.
        
        Prefers cached source EXIF (from paired JPEG) if available,
        otherwise falls back to the current original_image's EXIF.
        
        Returns:
            bytes object of EXIF data, or None if sanitization/serialization failed.
        """
        try:
            from PIL import Image, ExifTags

            exif = None

            # 1. Try to build an Exif object from raw bytes (best: preserves all tags)
            if self._source_exif_bytes and hasattr(Image, "Exif"):
                try:
                    ex = Image.Exif()
                    if hasattr(ex, "load"):
                        ex.load(self._source_exif_bytes)
                        exif = ex
                except Exception:
                    exif = None

            # 2. Fallback: pull EXIF from the loaded image (may be partial, but usually ok)
            if exif is None and self.original_image is not None:
                try:
                    exif = self.original_image.getexif()
                except Exception:
                    exif = None

            if exif is None:
                return None

            # 3. Orientation tag (0x0112)
            orientation_tag = 0x0112
            try:
                # Pillow 9.1.0+ has ExifTags.Base.Orientation
                orientation_tag = ExifTags.Base.Orientation
            except Exception:
                pass

            # 4. Reset Orientation to 1 (Normal)
            exif[orientation_tag] = 1

            # 5. Guard for tobytes()
            if not hasattr(exif, "tobytes"):
                # Fallback to source bytes even if unsanitized
                return self._source_exif_bytes or (self.original_image.info.get('exif') if self.original_image else None)

            try:
                return exif.tobytes()
            except Exception:
                # Fallback to source bytes on failure
                return self._source_exif_bytes or (self.original_image.info.get('exif') if self.original_image else None)
        except Exception as e:
            log.warning(f"Failed to sanitize EXIF orientation: {e}")
            return self._source_exif_bytes or (self.original_image.info.get('exif') if self.original_image else None)

    def save_image(self, write_developed_jpg: bool = False, developed_path: Optional[Path] = None) -> Optional[Tuple[Path, Path]]:
        """Saves the edited image, backing up the original.
        
        Args:
            write_developed_jpg: If True, also create a `-developed.jpg` sidecar file.
                                 This should be True only when editing RAW files.
            developed_path: Optional explicit path for the developed JPG. 
                            If not provided, it's derived from current_filepath.
        
        Returns:
            A tuple of (saved_path, backup_path) on success, otherwise None.
        """
        if self.float_image is None or self.current_filepath is None:
            return None
        
        # 1. Apply Edits to Full Resolution
        final_float = self._apply_edits(self.float_image.copy(), for_export=True) # (H,W,3) float32
        
        original_path = self.current_filepath
        try:
            original_stat = original_path.stat()
        except OSError as e:
            log.warning(f"Unable to read timestamps for {original_path}: {e}")
            original_stat = None
        
        # 2. Backup
        backup_path = create_backup_file(original_path)
        if backup_path is None:
            return None
            
        try:
            # 3. Save Main File
            is_tiff = original_path.suffix.lower() in ['.tif', '.tiff']
            
            if is_tiff:
                # Save as 16-bit TIFF using custom writer
                self._write_tiff_16bit(original_path, final_float)
            else:
                # Check for geometric transforms
                rotation = self.current_edits.get('rotation', 0)
                straighten_angle = float(self.current_edits.get('straighten_angle', 0.0))
                transforms_applied = (rotation != 0) or (abs(straighten_angle) > 0.001)

                # Determine EXIF bytes to write
                exif_bytes = None
                if self.original_image:
                    if transforms_applied:
                        # If we rotated pixels, we MUST sanitize orientation (set to 1).
                        # If sanitization fails, we drop EXIF to avoid "double rotation" bugs.
                        exif_bytes = self._get_sanitized_exif_bytes()
                    else:
                        # No rotation applied: Safe to preserve original EXIF as-is (including orientation).
                        exif_bytes = self.original_image.info.get('exif')

                # Save as standard format (Likely JPG) using Pillow
                # Convert to uint8
                # Apply highlight roll-off shoulder before clipping
                final_float = _apply_soft_shoulder(final_float)
                arr_u8 = (np.clip(final_float, 0.0, 1.0) * 255).astype(np.uint8)
                img_u8 = Image.fromarray(arr_u8, mode='RGB')
                
                save_kwargs = {'quality': 95}
                if exif_bytes:
                    save_kwargs['exif'] = exif_bytes
                
                try:
                    img_u8.save(original_path, **save_kwargs)
                except Exception:
                    # Fallback without EXIF
                    img_u8.save(original_path)

            if original_stat is not None:
                self._restore_file_times(original_path, original_stat)

            # 4. Save Sidecar JPG (-developed.jpg) - only when explicitly requested
            if write_developed_jpg:
                if developed_path is None:
                    stem = original_path.stem
                    if stem.lower().endswith("-working"):
                        stem = stem[:-8]
                    developed_path = original_path.with_name(f"{stem}-developed.jpg")
                
                # Check for geometric transforms (re-check not strictly needed but for clarity)
                rotation = self.current_edits.get('rotation', 0)
                straighten_angle = float(self.current_edits.get('straighten_angle', 0.0))
                transforms_applied = (rotation != 0) or (abs(straighten_angle) > 0.001)
                
                # Determine EXIF for sidecar - prefer source EXIF (from paired JPEG)
                exif_bytes = None
                if transforms_applied:
                    # Use sanitized EXIF (orientation reset to 1)
                    exif_bytes = self._get_sanitized_exif_bytes()
                elif self._source_exif_bytes:
                    # Use cached source EXIF from paired JPEG
                    exif_bytes = self._source_exif_bytes
                elif self.original_image:
                    # Fallback to current image's EXIF (may be empty for TIFFs)
                    exif_bytes = self.original_image.info.get('exif')
                
                # Use the same uint8 data
                # Apply highlight roll-off shoulder before clipping
                final_float_sidecar = _apply_soft_shoulder(final_float)
                arr_u8 = (np.clip(final_float_sidecar, 0.0, 1.0) * 255).astype(np.uint8)
                img_u8 = Image.fromarray(arr_u8)
                
                dev_kwargs = {'quality': 90}
                if exif_bytes:
                    dev_kwargs['exif'] = exif_bytes
                
                try:
                    img_u8.save(developed_path, **dev_kwargs)
                except Exception:
                    img_u8.save(developed_path)
            
            return original_path, backup_path

        except Exception as e:
            log.exception(f"Failed to save edited image or backup: {e}")
            return None


    def _restore_file_times(self, path: Path, original_stat: os.stat_result) -> None:
        """Best-effort restoration of access/modify timestamps after saving."""
        try:
            os.utime(path, (original_stat.st_atime, original_stat.st_mtime))
        except OSError as e:
            log.warning(f"Unable to restore timestamps for {path}: {e}")

    def rotate_image_cw(self):
        """Decreases the rotation edit parameter by 90° modulo 360 (clockwise)."""
        with self._lock:
            current = self.current_edits.get('rotation', 0)
            self.current_edits['rotation'] = (current - 90) % 360
            self._edits_rev += 1

    def rotate_image_ccw(self):
        """Increases the rotation edit parameter by 90° modulo 360 (counter-clockwise)."""
        with self._lock:
            current = self.current_edits.get('rotation', 0)
            self.current_edits['rotation'] = (current + 90) % 360
            self._edits_rev += 1

# Dictionary of ratios for QML dropdown
ASPECT_RATIOS = [{"name": name, "ratio": ratio} for name, ratio in INSTAGRAM_RATIOS.items()]
