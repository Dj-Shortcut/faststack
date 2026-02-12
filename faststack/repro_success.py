
import sys
import threading
import shutil
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

from faststack.app import AppController

# Setup temp img_dir
img_dir = Path("debug_tmp/images")
if img_dir.exists():
    shutil.rmtree(img_dir)
img_dir.mkdir(parents=True)

# Create files
(img_dir / "test1.jpg").touch()
(img_dir / "test1.CR2").touch()
(img_dir / "test2.jpg").touch()

print(f"Created files in {img_dir.absolute()}")

# Input for worker
job_id = 123
images_to_delete = [
    (img_dir / "test1.jpg", img_dir / "test1.CR2"),
    (img_dir / "test2.jpg", None)
]
cancel_event = threading.Event()

print("Running _delete_worker...")
result = AppController._delete_worker(job_id, images_to_delete, cancel_event)

print(f"\nResult status: {result.get('status')}")
print(f"Successes: {len(result['successes'])}")
print(f"Failures: {len(result['failures'])}")

for s in result['successes']:
    print(f"Success: {s}")

for f in result['failures']:
    print(f"Failure: {f}")

# Verify file movements
for f in [img_dir / "test1.jpg", img_dir / "test1.CR2", img_dir / "test2.jpg"]:
    if f.exists():
        print(f"ERROR: File {f} still exists!")
    else:
        print(f"OK: File {f} gone.")

recycle_bin = img_dir.parent / "image recycle bin"
if recycle_bin.exists():
    print(f"Recycle bin exists at {recycle_bin}")
    for f in recycle_bin.iterdir():
        print(f"  Bin content: {f.name}")
else:
    print(f"ERROR: Recycle bin {recycle_bin} not found!")
