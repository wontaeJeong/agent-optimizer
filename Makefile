.DEFAULT_GOAL := help
.PHONY: help setup doctor test lint demo smoke live menu setup-core doctor-core
unexport ARGS

# Preserve literal command-line data; do not export recursive ARGS or re-evaluate it.
export AGENT_OPT_MAKE_ARGS := $(value ARGS)
# Keep MAKEFILE_LIST whole: Make's dir/abspath/lastword split filenames with spaces.
help setup doctor test lint demo smoke live menu:
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	sh "$$(dirname "$$makefile")/scripts/make_args.sh" "$$(dirname "$$makefile")/scripts/bootstrap.sh" $@

setup-core doctor-core:
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	sh "$$(dirname "$$makefile")/scripts/bootstrap.sh" $(patsubst %-core,%,$@) --core
