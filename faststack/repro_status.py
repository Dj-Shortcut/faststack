
import sys
import threading
import inspect
from pathlib import Path

# Try to import AppController
try:
    from faststack.app import AppController
    print(f"Imported AppController from: {inspect.getfile(AppController)}")
except ImportError as e:
    print(f"Failed to import AppController: {e}")
    sys.exit(1)

# Check source code of _delete_worker
source = inspect.getsource(AppController._delete_worker)
print("\nSource of _delete_worker:")
print(source)

# Run _delete_worker
print("\nRunning _delete_worker...")
job_id = 1
images_to_delete = []
cancel_event = threading.Event()

try:
    result = AppController._delete_worker(job_id, images_to_delete, cancel_event)
    print(f"\nResult keys: {result.keys()}")
    if "status" in result:
        print(f"Status: {result['status']}")
    else:
        print("Status KEY MISSING!")
except Exception as e:
    print(f"Error running _delete_worker: {e}")
