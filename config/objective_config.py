import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ObjectiveConfig:
    desire_bonus_weight: int = 8
    activation_penalty: int = 2
    lecture_lecture_conflict_penalty: int = 18
    lecture_workshop_conflict_penalty: int = 6
    workshop_workshop_conflict_penalty: int = 2
    concurrent_open_courses_soft_limit: int = 3
    concurrent_open_courses_penalty: int = 1
    late_slot_penalty_weight: int = 0
    late_slot_start_period: int = 7


def load_objective_config(path: Path = None):
    if path is None:
        path = Path(__file__).with_name("objective_config.json")
        
    if not path.exists():
        return ObjectiveConfig()
    
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ObjectiveConfig(
        desire_bonus_weight=int(raw.get("desire_bonus_weight", 8)),
        activation_penalty=int(raw.get("activation_penalty", 2)),
        lecture_lecture_conflict_penalty=int(raw.get("lecture_lecture_conflict_penalty", 18)),
        lecture_workshop_conflict_penalty=int(raw.get("lecture_workshop_conflict_penalty", 6)),
        workshop_workshop_conflict_penalty=int(raw.get("workshop_workshop_conflict_penalty", 2)),
        concurrent_open_courses_soft_limit=int(raw.get("concurrent_open_courses_soft_limit", 10)),
        concurrent_open_courses_penalty=int(raw.get("concurrent_open_courses_penalty", 1)),
        late_slot_penalty_weight=int(raw.get("late_slot_penalty_weight", 0)),
        late_slot_start_period=int(raw.get("late_slot_start_period", 7)),
    )
