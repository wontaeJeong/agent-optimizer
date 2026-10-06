import sys

# The package is imported before __main__ and before console-script loads cli.
# Doctor/plan guard startup imports as well as subsequently loaded trusted plugins.
if len(sys.argv) > 1 and sys.argv[1] in {"doctor", "plan"}:
    sys.dont_write_bytecode = True

__version__ = "0.3.0"
