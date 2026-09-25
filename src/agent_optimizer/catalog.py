"""Read-only descriptions of opt-in first-party datasets; implementations are separate."""

DATASETS = {
    "cvdp": {"name": "cvdp", "task_form": "rtl-generation", "evaluator": "cvdp",
             "revision": "8e894cf74414ab1eaea1e2b4e80a02f123df07b6", "requires_preparation": True},
    "verilog-spec": {"name": "verilog-spec", "task_form": "spec-to-rtl",
                     "evaluator": "verilog_eval",
                     "revision": "c498220d0a52248f8e3fdffe279075215bde2da6",
                     "requires_preparation": True},
    "verilog-completion": {"name": "verilog-completion", "task_form": "code-complete-iccad2023",
                           "evaluator": "verilog_eval",
                           "revision": "c498220d0a52248f8e3fdffe279075215bde2da6",
                           "requires_preparation": True},
}
