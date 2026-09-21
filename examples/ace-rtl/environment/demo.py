"""Small fixed, disjoint task selection from the pinned full dataset."""
from copy import deepcopy

from agent_optimizer.contracts import ConfigurationError

TASKS = {"cvdp_copilot_8x3_priority_encoder_0001": "train", "cvdp_copilot_16qam_mapper_0001": "validation"}


def select_tasks(manifest):
    indexed = {task["id"]: task for task in manifest["tasks"]}
    if not set(TASKS) <= indexed.keys():
        raise ConfigurationError("Reviewed train/validation demo tasks absent; rerun setup with the pinned dataset")
    tasks = [deepcopy(indexed[identifier]) for identifier in TASKS]
    families = [task.get("family") for task in tasks]
    if not all(families) or len(set(families)) != len(families):
        raise ConfigurationError("Demo tasks must have distinct, nonempty families")
    for task in tasks:
        task["split"] = TASKS[task["id"]]
    return {**manifest, "tasks": tasks, "demo_selection": "priority-train-qam16-validation-v1"}
