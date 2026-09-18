from agent_optimizer.contracts import ConfigurationError, OptimizationResult


class FileVariantsOptimizer:
    """Executable integration reference: explicit candidate enumeration, no LLM search."""

    def optimize(self, context, seeds, config):
        unknown = set(config) - {"variants", "include_seeds"}
        if unknown:
            raise ConfigurationError(f"Unknown file_variants options: {sorted(unknown)}")
        candidates = list(seeds) if config.get("include_seeds", True) else []
        for seed in seeds:
            for variant in config.get("variants", []):
                if set(variant) - {"name", "files"} or not isinstance(variant.get("files"), dict):
                    raise ConfigurationError("Each variant requires a files mapping")
                candidates.append(context.propose(seed, variant["files"], "file_variants"))
        return OptimizationResult(candidates, {"generated": len(candidates), "llm_calls": 0})

