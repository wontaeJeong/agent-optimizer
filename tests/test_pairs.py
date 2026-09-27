import unittest

from agent_optimizer import config
from agent_optimizer.config import load_experiment
from agent_optimizer.contracts import ConfigurationError

from support import test_project


class PairSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary, self.root = test_project()
        self.addCleanup(self.temporary.cleanup)
        self.example = self.root / "examples/minimal"
        self.experiment = self.example / "experiment.toml"
        self.original = self.experiment.read_text(encoding="utf-8")
        harness = (self.example / "harness.toml").read_text(encoding="utf-8")
        (self.example / "fixture-alt.toml").write_text(
            harness.replace('id = "fixture"', 'id = "fixture-alt"'), encoding="utf-8"
        )
        self.matrix = self.original.replace(
            'harnesses = ["examples/minimal/harness.toml"]',
            'harnesses = ["examples/minimal/harness.toml", "examples/minimal/fixture-alt.toml"]',
        )

    def load(self, text):
        self.experiment.write_text(text, encoding="utf-8")
        return load_experiment(self.experiment)

    def test_absent_pairs_selects_agent_major_full_product(self):
        spec = self.load(self.matrix)
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-solo", "fixture"), ("rtl-solo", "fixture-alt"),
            ("rtl-team", "fixture"), ("rtl-team", "fixture-alt"),
        ])

    def test_declared_pairs_follow_order_and_keep_raw_config(self):
        spec = self.load(self.matrix + '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
                         '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n')
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-team", "fixture-alt"), ("rtl-solo", "fixture"),
        ])
        self.assertEqual(spec["pairs"], [
            {"agent": "rtl-team", "harness": "fixture-alt"},
            {"agent": "rtl-solo", "harness": "fixture"},
        ])

    def test_invalid_pair_declarations_fail_during_loading(self):
        valid = '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
        cases = {
            "empty list": 'pairs = []\n',
            "string": 'pairs = "bad"\n',
            "string item": 'pairs = ["bad"]\n',
            "extra key": valid + 'unused = true\n[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n',
            "missing id": valid + '[[pairs]]\nagent = "rtl-solo"\n',
            "empty id": valid + '[[pairs]]\nagent = "rtl-solo"\nharness = ""\n',
            "non-string id": valid + '[[pairs]]\nagent = 42\nharness = "fixture"\n',
            "duplicate": valid + '[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n',
            "unknown agent": valid + '[[pairs]]\nagent = "unknown"\nharness = "fixture"\n',
            "unknown profile": valid + '[[pairs]]\nagent = "rtl-solo"\nharness = "unknown"\n',
            "unused agent": valid + '[[pairs]]\nagent = "rtl-team"\nharness = "fixture"\n',
            "unused profile": '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n'
                              '[[pairs]]\nagent = "rtl-team"\nharness = "fixture"\n',
        }
        for label, declaration in cases.items():
            with self.subTest(label=label), self.assertRaises(ConfigurationError) as caught:
                text = (self.matrix.replace('[budget]', declaration + '\n[budget]', 1)
                        if declaration.startswith('pairs = ') else self.matrix + '\n' + declaration)
                self.load(text)
            self.assertNotIn("Unknown experiment keys", str(caught.exception))

    def test_support_is_checked_only_for_selected_pairs(self):
        solo = self.example / "solo.toml"
        solo.write_text(solo.read_text(encoding="utf-8").replace(
            '["fixture", "opencode", "command"]', '["fixture"]'), encoding="utf-8")
        alt = self.example / "fixture-alt.toml"
        alt.write_text('id = "fixture-alt"\nadapter = "command"\nallow_local = true\n'
                       '[runtime]\nkind = "local"\n', encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            self.load(self.matrix)
        spec = self.load(self.matrix + '\n[[pairs]]\nagent = "rtl-team"\nharness = "fixture-alt"\n'
                         '[[pairs]]\nagent = "rtl-solo"\nharness = "fixture"\n')
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-team", "fixture-alt"), ("rtl-solo", "fixture"),
        ])
        with self.assertRaises(ConfigurationError):
            self.load(self.matrix + '\n[[pairs]]\nagent = "rtl-solo"\nharness = "fixture-alt"\n'
                      '[[pairs]]\nagent = "rtl-team"\nharness = "fixture"\n')

    def test_default_selection_reads_current_agents_and_profiles(self):
        spec = self.load(self.original)
        other = dict(spec["_profiles"][0], id="fixture-alt")
        spec["_profiles"].append(other)
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-solo", "fixture"), ("rtl-solo", "fixture-alt"),
            ("rtl-team", "fixture"), ("rtl-team", "fixture-alt"),
        ])
        spec["_agents"] = spec["_agents"][1:]
        self.assertEqual([(agent.id, profile["id"]) for agent, profile in config.selected_pairs(spec)], [
            ("rtl-team", "fixture"), ("rtl-team", "fixture-alt"),
        ])


if __name__ == "__main__":
    unittest.main()
