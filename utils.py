import time
from pathlib import Path


def make_output_dir(dataset_name=None):
    stamp = time.strftime("%Y_%m_%d_%H_%M_%S")
    name = f"run_{dataset_name}_{stamp}" if dataset_name else f"run_{stamp}"
    d = Path("output") / name
    d.mkdir(parents=True, exist_ok=True)
    return d

def weighted_median(values_weights):
    """
    Compute weighted median equivalent to statistics.median on expanded list.
    (Reduces cost of calculating median on large lists with many duplicates)   
    """
    sorted_vw = sorted(values_weights, key=lambda x: x[0])
    total = sum(w for _, w in sorted_vw)

    if total == 0:
        return 0
    
    if total % 2 == 1:
        target = total // 2
        cumulative = 0
        for val, w in sorted_vw:
            cumulative += w
            if cumulative > target:
                return val
    else:
        t1 = total // 2 - 1
        t2 = total // 2

        v1 = v2 = None
        cumulative = 0
        for val, w in sorted_vw:
            cumulative += w
            if v1 is None and cumulative > t1:
                v1 = val
            if v2 is None and cumulative > t2:
                v2 = val
                break
            
        return (v1 + v2) / 2
