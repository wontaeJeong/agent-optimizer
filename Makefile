.DEFAULT_GOAL := help
.PHONY: help setup doctor test lint demo smoke live menu setup-core doctor-core
unexport ARGS

# ARGS is a sequence of quoted options, not shell code.
# Keep MAKEFILE_LIST whole: Make's dir/abspath/lastword split filenames with spaces.
help setup doctor test lint demo smoke live menu:
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	args='$(subst ','"'"',$(value ARGS))'; \
	sh "$$(dirname "$$makefile")/scripts/bootstrap.sh" $@ --make-args "$$args"

setup-core doctor-core:
	@makefile='$(subst ','"'"',$(MAKEFILE_LIST))'; makefile=$${makefile# }; \
	sh "$$(dirname "$$makefile")/scripts/bootstrap.sh" $(patsubst %-core,%,$@) --core
