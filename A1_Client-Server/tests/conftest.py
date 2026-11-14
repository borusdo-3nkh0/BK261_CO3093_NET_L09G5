"""Legacy checkouts run only in explicitly selected, separate pytest processes."""

import os


def pytest_collection_modifyitems(config, items):
    groups = {"test_p1_files.py": "p1", "test_p2_file_dependency.py": "p2"}
    deselected = [
        item
        for item in items
        if item.path.name in groups
        and os.environ.get("CONNECT_REFERENCE_SUITE") != groups[item.path.name]
    ]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = [item for item in items if item not in deselected]
