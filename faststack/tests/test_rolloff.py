import numpy as np
from faststack.imaging.editor import _apply_soft_shoulder

def test_apply_soft_shoulder_threshold():
    # Test that values below threshold are unchanged
    threshold = 0.9
    x = np.array([0.0, 0.5, 0.8, 0.9])
    out = _apply_soft_shoulder(x, threshold=threshold)
    np.testing.assert_allclose(out, x)
    print("test_apply_soft_shoulder_threshold passed")

def test_apply_soft_shoulder_rolloff():
    # Test that values above threshold are compressed but stay < 1.0
    threshold = 0.9
    x = np.array([0.91, 1.0, 2.0, 10.0])
    out = _apply_soft_shoulder(x, threshold=threshold)
    
    # Check that they are compressed (out < x)
    assert np.all(out[x > threshold] < x[x > threshold])
    # Check that they stay below 1.0
    assert np.all(out < 1.0)
    # Check that they are still above threshold
    assert np.all(out[x > threshold] > threshold)
    print("test_apply_soft_shoulder_rolloff passed")

def test_apply_soft_shoulder_monotonic():
    # Test monotonicity
    threshold = 0.8
    x = np.linspace(0, 5, 100)
    out = _apply_soft_shoulder(x, threshold=threshold)
    
    # Check if strictly increasing (mostly, due to float precision)
    assert np.all(np.diff(out) > 0)
    print("test_apply_soft_shoulder_monotonic passed")

def test_apply_soft_shoulder_no_threshold():
    # Test with threshold >= 1.0
    x = np.array([0.0, 0.5, 1.2])
    out = _apply_soft_shoulder(x, threshold=1.0)
    np.testing.assert_allclose(out, x)
    print("test_apply_soft_shoulder_no_threshold passed")

def test_apply_soft_shoulder_none_above():
    # Test when no values are above threshold
    threshold = 0.9
    x = np.array([0.1, 0.5, 0.8])
    out = _apply_soft_shoulder(x, threshold=threshold)
    np.testing.assert_allclose(out, x)
    print("test_apply_soft_shoulder_none_above passed")

if __name__ == "__main__":
    try:
        test_apply_soft_shoulder_threshold()
        test_apply_soft_shoulder_rolloff()
        test_apply_soft_shoulder_monotonic()
        test_apply_soft_shoulder_no_threshold()
        test_apply_soft_shoulder_none_above()
        print("\nALL TESTS PASSED")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
