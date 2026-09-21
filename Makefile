.DEFAULT_GOAL := help
.PHONY: help setup doctor test lint demo smoke live menu

# ARGS is normal shell command-line syntax, e.g. ARGS='--platform "linux/arm64"'.
# Keep MAKEFILE_LIST whole: Make's dir/abspath/lastword split filenames with spaces.
help setup doctor test lint demo smoke live menu:
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	sh "$$(dirname "$$makefile")/scripts/bootstrap.sh" $@ $(ARGS)
