import time
import threading
from faststack.util.executors import create_priority_executor as PriorityExecutor

def test_priority_executor():
    print("Testing PriorityExecutor...")
    executor = PriorityExecutor(max_workers=1, thread_name_prefix="Test")
    
    results = []
    def task(name, delay=0.1):
        time.sleep(delay)
        results.append(name)
        return name

    # Fill the worker and wait a bit to ensure it STARTS
    executor.submit(task, "initial", delay=0.2)
    time.sleep(0.05) 
    
    # Submit tasks with different priorities and see execution order
    # Lower number = higher priority
    # within same priority, higher sequence = higher priority (LIFO)
    executor.submit(task, "p2_a", priority=2)
    executor.submit(task, "p2_b", priority=2)
    executor.submit(task, "p1", priority=1)
    
    print("Tasks submitted, waiting for completion...")
    # Expected order: "initial" (already running), "p1", "p2_b", "p2_a"
    
    time.sleep(1.0)
    print("Execution order:", results)
    
    expected = ["initial", "p1", "p2_b", "p2_a"]
    if results == expected:
        print("SUCCESS: Priority and LIFO ordering correct.")
    else:
        print(f"FAILURE: Expected {expected}, got {results}")

    print("\nTesting shutdown and cancellation...")
    executor = PriorityExecutor(max_workers=1, thread_name_prefix="TestShutdown")
    executor.submit(task, "long", delay=0.5)
    f1 = executor.submit(task, "queued1")
    f2 = executor.submit(task, "queued2")
    
    executor.shutdown(wait=True, cancel_futures=True)
    print(f"f1 cancelled: {f1.cancelled()}")
    print(f"f2 cancelled: {f2.cancelled()}")
    
    if f1.cancelled() and f2.cancelled():
        print("SUCCESS: Futures cancelled on shutdown.")
    else:
        print("FAILURE: Futures not cancelled.")

if __name__ == "__main__":
    test_priority_executor()
