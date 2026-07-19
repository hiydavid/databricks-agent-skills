from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_space_json.py"
SPEC = importlib.util.spec_from_file_location("validate_space_json", SCRIPT_PATH)
assert SPEC and SPEC.loader
validate_space_json = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_space_json)


def hid(value: int) -> str:
    return f"{value:032x}"


def base_config() -> dict:
    benchmarks = []
    for index in range(10):
        benchmarks.append(
            {
                "id": hid(200 + index),
                "question": [f"What is total revenue test {index}?"],
                "answer": [
                    {
                        "format": "SQL",
                        "content": ["SELECT SUM(amount) AS total_revenue FROM cat.sch.orders"],
                    }
                ],
            }
        )

    return {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": hid(100 + index), "question": [f"Sample question {index}?"]}
                for index in range(5)
            ]
        },
        "data_sources": {
            "tables": [
                {
                    "id": hid(1),
                    "identifier": "cat.sch.orders",
                    "description": ["Orders with one row per order for revenue analysis."],
                    "column_configs": [
                        {
                            "id": hid(10),
                            "column_name": "amount",
                            "description": ["Order revenue amount in USD."],
                            "synonyms": ["revenue", "sales"],
                            "enable_format_assistance": False,
                            "enable_entity_matching": False,
                        },
                        {
                            "id": hid(11),
                            "column_name": "order_date",
                            "description": ["Date when the order was placed."],
                            "synonyms": ["date", "order day"],
                            "enable_format_assistance": False,
                            "enable_entity_matching": False,
                        },
                        {
                            "id": hid(12),
                            "column_name": "region",
                            "description": ["Sales region for the order."],
                            "synonyms": ["area", "territory"],
                            "enable_format_assistance": True,
                            "enable_entity_matching": True,
                        },
                    ],
                }
            ],
            "metric_views": [],
        },
        "instructions": {
            "text_instructions": [
                {
                    "id": hid(50),
                    "content": [
                        "## PURPOSE\n- Answer order revenue questions for sales operations users.\n\n",
                        "## DISAMBIGUATION\n- When no time range is provided, ask the user to clarify the period.\n\n",
                        "## Instructions you must follow when providing summaries\n- Always state the date range used.\n",
                    ],
                }
            ],
            "example_question_sqls": [
                {
                    "id": hid(60),
                    "question": ["Show revenue by region for EMEA"],
                    "sql": [
                        "SELECT region, SUM(amount) AS total_revenue FROM cat.sch.orders "
                        "WHERE region = :region_name GROUP BY region"
                    ],
                    "usage_guidance": ["Use for revenue filtered by a specific region."],
                    "parameters": [
                        {
                            "name": "region_name",
                            "description": ["The sales region. Values include EMEA and AMER."],
                            "type_hint": "STRING",
                            "default_value": {"values": ["EMEA"]},
                        }
                    ],
                }
            ],
            "sql_functions": [],
            "join_specs": [],
            "sql_snippets": {"filters": [], "expressions": [], "measures": []},
        },
        "benchmarks": {"questions": benchmarks},
    }


class ValidateSpaceJsonTest(unittest.TestCase):
    def assert_has(self, messages: list[str], needle: str) -> None:
        self.assertTrue(any(needle in message for message in messages), messages)

    def test_base_config_has_no_errors(self) -> None:
        errors, _warnings = validate_space_json.validate(base_config())
        self.assertEqual([], errors)

    def test_metric_view_select_star_is_error(self) -> None:
        config = base_config()
        config["data_sources"]["tables"] = []
        config["data_sources"]["metric_views"] = [
            {
                "id": hid(2),
                "identifier": "cat.sch.sales_mv",
                "description": ["Revenue Metric View with sales measures by region."],
            }
        ]
        config["instructions"]["example_question_sqls"][0]["sql"] = ["SELECT * FROM cat.sch.sales_mv"]

        errors, warnings = validate_space_json.validate(config)

        self.assert_has(errors, "SELECT * against Metric View")
        self.assert_has(warnings, "does not use MEASURE()")

    def test_benchmark_answer_copied_into_example_is_error(self) -> None:
        config = base_config()
        answer_sql = config["benchmarks"]["questions"][0]["answer"][0]["content"][0]
        config["instructions"]["example_question_sqls"][0]["sql"] = [answer_sql]

        errors, _warnings = validate_space_json.validate(config)

        self.assert_has(errors, "appears to copy benchmark answer")

    def test_text_instruction_gsl_and_sql_warnings(self) -> None:
        config = base_config()
        config["instructions"]["text_instructions"][0]["content"] = [
            "## Terminology\n- Use SELECT * FROM cat.sch.orders when debugging.\n"
        ]

        _errors, warnings = validate_space_json.validate(config)

        self.assert_has(warnings, "non-canonical GSL header")
        self.assert_has(warnings, "appears to contain SQL")

    def test_parameter_metadata_warnings(self) -> None:
        config = base_config()
        config["instructions"]["example_question_sqls"][0]["parameters"] = [
            {"name": "region_name", "type_hint": "STRING"}
        ]

        _errors, warnings = validate_space_json.validate(config)

        self.assert_has(warnings, "description should describe")
        self.assert_has(warnings, "default_value should contain a real profiled value")

    def test_duplicate_ids_are_errors(self) -> None:
        config = base_config()
        config["config"]["sample_questions"][1]["id"] = config["config"]["sample_questions"][0]["id"]

        errors, _warnings = validate_space_json.validate(config)

        self.assert_has(errors, "duplicate IDs")

    def test_too_many_data_sources_is_error(self) -> None:
        config = base_config()
        config["data_sources"]["tables"] = [
            {
                "id": hid(300 + index),
                "identifier": f"cat.sch.t{index:02d}",
                "description": [f"Table {index}."],
                "column_configs": [],
            }
            for index in range(31)
        ]

        errors, _warnings = validate_space_json.validate(config)

        self.assert_has(errors, "more than 30 total")

    def test_entity_matching_requires_format_assistance(self) -> None:
        config = base_config()
        region = config["data_sources"]["tables"][0]["column_configs"][2]
        region["enable_format_assistance"] = False

        errors, _warnings = validate_space_json.validate(config)

        self.assert_has(errors, "enable_entity_matching requires enable_format_assistance")

    def test_missing_business_question_surface_warns(self) -> None:
        config = base_config()
        config["config"]["sample_questions"] = []

        _errors, warnings = validate_space_json.validate(config)

        self.assert_has(warnings, "sample_questions is empty")

    def test_knowledge_store_snippet_limit_warns(self) -> None:
        config = base_config()
        config["instructions"]["join_specs"] = [
            {
                "id": hid(400 + index),
                "sql": ["`a`.`id` = `b`.`id`", "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"],
                "comment": ["test join"],
            }
            for index in range(200)
        ]

        _errors, warnings = validate_space_json.validate(config)

        self.assert_has(warnings, "knowledge-store snippets total")

    def test_benchmark_question_limit_warns(self) -> None:
        config = base_config()
        config["benchmarks"]["questions"] = [
            {
                "id": hid(1000 + index),
                "question": [f"Benchmark question {index}?"],
                "answer": [
                    {
                        "format": "SQL",
                        "content": [f"SELECT {index} AS value"],
                    }
                ],
            }
            for index in range(501)
        ]

        _errors, warnings = validate_space_json.validate(config)

        self.assert_has(warnings, "up to 500 benchmark questions")


if __name__ == "__main__":
    unittest.main()
