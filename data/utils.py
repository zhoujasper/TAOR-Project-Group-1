import csv
import json
from pathlib import Path

# Reading CSV/JSON files -----------------------------------------------------------------

def read_csv(path):
    """
    Read a CSV file and return a list of row dicts and check existence of header row.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing CSV file: {path}")
    
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header row: {path}")
        
        return [dict(r) for r in reader]


def read_json(path):
    """
    Read a JSON file and return the parsed object.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# Field extractors ----------------------------------------------------------------------

def req(row, key, path, lineno):
    """
    Get a required string, if missing or empty, raise an error with file/line info.
    """
    v = row.get(key, "")
    if v is None or str(v).strip() == "":
        raise ValueError(f"Missing required field '{key}' in {path.name} at row {lineno}")
    
    return str(v).strip()


def get_int(row, key, default = 0):
    """
    Get an integer, if missing or empty, return 'default'.
    """
    return int(row.get(key, default) or default)


def get_str(row, key, default=""):
    """
    Get an string, if missing or empty, return 'default'.
    """
    return str(row.get(key, default) or default)


# Value converters -----------------------------------------------------------------------

def split_semicolon(s):
    """
    Convert a string with ';' separators into a list of stripped strings, or return an empty list if s is empty.
    """
    if not s:
        return []
    
    return [tok.strip() for tok in str(s).split(";") if tok.strip()]


def maybe_set_str(xs):
    """
    Convert empty list/string/dict to None, otherwise convert to set of stripped strings.
    """
    if xs is None:
        return None
    
    if isinstance(xs, set):
        return xs
    if isinstance(xs, list):
        return set(str(x).strip() for x in xs if str(x).strip() != "")
    if isinstance(xs, str):
        parts = split_semicolon(xs)
        return set(parts) if parts else None
    
    raise ValueError(f"Cannot parse set[str] from {type(xs)}: {xs}")


def maybe_set_int(xs):
    """
    Convert empty list/string/dict to None.
    """
    if not xs:
        return None
    
    return {int(x) for x in xs}


def to_tuple(v):
    """
    Convert v=(x, y) -> (int(x), int(y))
    """
    return (int(v[0]), int(v[1]))


def parse_enum(enum_cls, raw, field_name):
    """
    Check whether 'raw' in our pre-defined enums.
    """
    key = str(raw).strip()
    for e in enum_cls:
        if key in (e.value, e.name) or key.lower() in (str(e.value).lower(), e.name.lower()):
            return e
        
    raise ValueError(f"Invalid {field_name}: '{key}'. Allowed: {[e.value for e in enum_cls]}")


def parse_bool(raw):
    """
    Convert most possible representations of true/false to a boolean value.
    """
    s = str(raw).strip().lower()
    if s in ("1", "true", "t", "yes", "y"):
        return True
    if s in ("0", "false", "f", "no", "n"):
        return False
    
    raise ValueError(f"Invalid boolean: {raw}")


def to_minutes(s):
    """
    Convert 'HH:MM' to minutes.
    """
    hh, mm = s.strip().split(":")

    return 60 * int(hh) + int(mm)


def parse_timeslots(s):
    """
    Parse 'day:period;day:period;...' into a set of (day, period) tuples,
    or return None if the string is empty.
    """
    if not s or not str(s).strip():
        return None
    result = set()
    for tok in str(s).split(";"):
        tok = tok.strip()
        if not tok:
            continue
        parts = tok.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid timeslot token '{tok}', expected 'day:period'")
        result.add((int(parts[0]), int(parts[1])))
    return result if result else None
