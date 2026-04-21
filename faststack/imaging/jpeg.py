"""High-performance JPEG decoding using PyTurboJPEG with a Pillow fallback."""

import logging
import time
import warnings
from io import BytesIO
from typing import Any, Optional, Tuple

import numpy as np
from PIL import Image

from faststack.imaging.turbo import TJPF_RGB, create_turbojpeg

log = logging.getLogger(__name__)

JPEG_DECODER, TURBO_AVAILABLE = create_turbojpeg()

_PREMATURE_EOF_RETRY_DELAY = 0.15


def _decode_with_retry(
    jpeg_bytes: bytes,
    *,
    source_path: Optional[str] = None,
    decoder: Any = None,
    **decode_kwargs: Any,
) -> Optional[np.ndarray]:
    """Call decoder.decode() with a single retry on 'Premature end of JPEG file'.

    TurboJPEG emits this as a Python warning (not an exception) when the
    file is truncated.  We treat it as a soft/retryable condition — the
    file may still be written by another process — and retry once after
    a short delay.
    """
    dec = decoder or JPEG_DECODER
    for attempt in range(2):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = dec.decode(jpeg_bytes, **decode_kwargs)

        premature = any("Premature end of JPEG file" in str(w.message) for w in caught)

        if not premature:
            return result

        if attempt == 0:
            time.sleep(_PREMATURE_EOF_RETRY_DELAY)
            continue

        label = source_path or "<unknown>"
        log.warning(
            "TurboJPEG: 'Premature end of JPEG file' for %s "
            "(retry also warned — file may be truncated)",
            label,
        )
        return result


def decode_jpeg_rgb(
    jpeg_bytes: bytes,
    fast_dct: bool = False,
    source_path: Optional[str] = None,
) -> Optional[np.ndarray]:
    """Decodes JPEG bytes into an RGB numpy array."""
    if TURBO_AVAILABLE and JPEG_DECODER:
        try:
            flags = 0
            if fast_dct:
                flags |= 2048
            return _decode_with_retry(
                jpeg_bytes,
                source_path=source_path,
                pixel_format=TJPF_RGB,
                flags=flags,
            )
        except Exception as e:
            log.exception("PyTurboJPEG failed to decode image: %s. Trying Pillow.", e)

    # Fallback to Pillow
    try:
        img = Image.open(BytesIO(jpeg_bytes)).convert("RGB")
        return np.array(img)
    except Exception as e:
        log.exception("Pillow also failed to decode image: %s", e)
        return None


def decode_jpeg_thumb_rgb(
    jpeg_bytes: bytes,
    max_dim: int = 256,
    source_path: Optional[str] = None,
) -> Optional[np.ndarray]:
    """Decodes a JPEG into a thumbnail-sized RGB numpy array."""
    if TURBO_AVAILABLE and JPEG_DECODER:
        try:
            width, height, _, _ = JPEG_DECODER.decode_header(jpeg_bytes)
            scaling_factor = _get_turbojpeg_scaling_factor(width, height, max_dim)

            decoded = _decode_with_retry(
                jpeg_bytes,
                source_path=source_path,
                scaling_factor=scaling_factor,
                pixel_format=TJPF_RGB,
                flags=0,
            )
            if decoded.shape[0] > max_dim or decoded.shape[1] > max_dim:
                img = Image.fromarray(decoded)
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                return np.array(img)
            return decoded
        except Exception as e:
            log.exception(
                "PyTurboJPEG failed to decode thumbnail: %s. Trying Pillow.", e
            )

    # Fallback to Pillow
    try:
        img = Image.open(BytesIO(jpeg_bytes))
        img.thumbnail((max_dim, max_dim))
        return np.array(img.convert("RGB"))
    except Exception as e:
        log.exception("Pillow also failed to decode thumbnail: %s", e)
        return None


def _get_turbojpeg_scaling_factor(
    width: int, height: int, max_dim: int
) -> Optional[Tuple[int, int]]:
    """Finds the best libjpeg-turbo scaling factor to get a thumbnail <= max_dim."""
    if not TURBO_AVAILABLE or not JPEG_DECODER:
        return None

    # PyTurboJPEG provides a set of supported scaling factors
    supported_factors = sorted(
        JPEG_DECODER.scaling_factors,
        key=lambda x: x[0] / x[1],
        reverse=True,
    )

    for num, den in supported_factors:
        if (width * num / den) <= max_dim and (height * num / den) <= max_dim:
            return (num, den)

    # If no suitable factor is found, return the smallest one
    return supported_factors[-1] if supported_factors else None


def decode_jpeg_resized(
    jpeg_bytes: bytes,
    width: int,
    height: int,
    fast_dct: bool = False,
    source_path: Optional[str] = None,
) -> Optional[np.ndarray]:
    """Decodes and resizes a JPEG to fit within the given dimensions."""
    if width <= 0 or height <= 0:
        return decode_jpeg_rgb(jpeg_bytes, fast_dct=fast_dct, source_path=source_path)

    if TURBO_AVAILABLE and JPEG_DECODER:
        try:
            img_width, img_height, _, _ = JPEG_DECODER.decode_header(jpeg_bytes)

            if img_width * height > img_height * width:
                max_dim = width
            else:
                max_dim = height

            scale_factor = _get_turbojpeg_scaling_factor(img_width, img_height, max_dim)

            if scale_factor:
                flags = 0
                if fast_dct:
                    flags |= 2048

                decoded = _decode_with_retry(
                    jpeg_bytes,
                    source_path=source_path,
                    scaling_factor=scale_factor,
                    pixel_format=TJPF_RGB,
                    flags=flags,
                )

                # Only use Pillow for final resize if needed
                if decoded.shape[0] > height or decoded.shape[1] > width:
                    img = Image.fromarray(decoded)
                    # Use BILINEAR for speed
                    img.thumbnail((width, height), Image.Resampling.BILINEAR)
                    return np.array(img)
                return decoded
        except Exception as e:
            log.exception("PyTurboJPEG failed: %s", e)

    # Fallback to Pillow (existing code)
    try:
        img = Image.open(BytesIO(jpeg_bytes))

        if width <= 0 or height <= 0:
            return np.array(img.convert("RGB"))

        scale_factor_ratio = min(img.width / width, img.height / height)

        # Use faster BILINEAR for large downscales, LANCZOS for smaller
        if scale_factor_ratio > 4:
            resampling = Image.Resampling.BILINEAR  # Much faster
        else:
            resampling = (
                Image.Resampling.LANCZOS
            )  # Higher quality for smaller downscales

        img.thumbnail((width, height), resampling)
        return np.array(img.convert("RGB"))
    except Exception as e:
        log.exception("Pillow failed to decode and resize image: %s", e)
        return None
