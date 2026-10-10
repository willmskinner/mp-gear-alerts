import yaml

from .matching import Watch, compile_terms


def load_config(path="config.yaml"):
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    forums = data.get("forums") or []
    if not forums:
        raise ValueError("config has no 'forums'")
    for forum in forums:
        if "id" not in forum:
            raise ValueError(f"forum is missing 'id': {forum}")

    watches = []
    seen_names = set()
    for w in data.get("watches") or []:
        name = w.get("name")
        if not name:
            raise ValueError(f"watch is missing 'name': {w}")
        if name in seen_names:
            raise ValueError(f"duplicate watch name: {name!r}")
        seen_names.add(name)
        if not w.get("keywords"):
            raise ValueError(f"watch {name!r} has no keywords")
        if not w.get("enabled", True):
            continue
        watches.append(
            Watch(
                name=name,
                keywords=compile_terms(w["keywords"]),
                require=compile_terms(w.get("require") or []),
                exclude=compile_terms(w.get("exclude") or []),
            )
        )

    exclude_titles = compile_terms(data.get("exclude_titles") or [])
    return forums, watches, exclude_titles
