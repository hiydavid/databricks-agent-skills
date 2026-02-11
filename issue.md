# Genie Space API Issues & Workarounds

Issues encountered during the optimization of space `01f0627099691651968d0a92a26b06e9` on 2026-02-11.

---

## 1. `parameters[].description` must be an array, not a string

**Affected docs:** `references/space-schema.md` documents `parameters[].description` as type `string`

**Actual API behavior:** Expects `array of strings`, consistent with every other text field in the schema (`content`, `question`, `sql`, etc.).

**Error message:**
```
Invalid serialized_space: Expected an array for description but found "Ticker symbol (AAPL, BAC, or AXP)"
```

**Workaround:** Use `param["description"] = ["..."]` instead of `param["description"] = "..."`

**Suggested doc fixes:**
- `space-schema.md`: Change `parameters[].description` type from `string` to `array of strings`

---

## 2. `get_example_values` and `build_value_dictionary` are version 1 only

**Affected docs:** `references/space-schema.md` lists both as valid `column_configs` fields. The best practices checklist also recommends enabling them.

**Actual API behavior:** These fields are rejected when `serialized_space.version` is `2`. The API requires `enable_format_assistance` and `enable_entity_matching` instead.

**Error message:**
```
data_sources.tables[0].column_configs[34] uses version 1 fields (get_example_values, build_value_dictionary) but the export version is 2. Use enable_format_assistance and enable_entity_matching for version 2.
```

**Workaround:** Use `enable_entity_matching: true` on categorical columns like TICKER (closest v2 equivalent for value matching). Use `enable_format_assistance: true` for general column assistance.

**Suggested doc fixes:**
- `space-schema.md`: Document the v1 vs v2 distinction. Either remove v1-only fields or clearly label them. Add a note that `enable_format_assistance` and `enable_entity_matching` are the v2 replacements.
- `best-practices-checklist.md`: The checklist items for "Example Values Enabled" and "Value Dictionary Enabled" should be conditioned on the space version, or reframed around the v2 equivalents.

---

## 3. Join spec `sql` field cannot contain compound conditions (AND)

**Affected docs:** `references/workflow-optimize.md` step 3c explicitly recommends merging separate join specs into a single spec with both conditions: `bs.TICKER = inc.TICKER AND bs.YEAR = inc.YEAR`. The config analysis workflow also flags separate join specs as a problem.

**Actual API behavior:** The `sql` parser only accepts simple equality expressions. Compound `AND` expressions are rejected.

**Error message:**
```
Failed to parse export proto: `genie_balance_sheet`.`TICKER` = `genie_income_statement`.`TICKER` AND `genie_balance_sheet`.`YEAR` = `genie_income_statement`.`YEAR` (of class java.lang.String)
```

**Workaround:** Keep two separate join specs. Add `comment` and `instruction` fields to both, emphasizing they must always be used together.

**Suggested doc fixes:**
- `workflow-optimize.md`: Remove the recommendation to merge join specs. Instead, recommend improving separate specs with `comment` and `instruction` fields that say "always use with the other join spec."
- `workflow-analyze.md` / `best-practices-checklist.md`: The "Join Specs for Multi-Table Relationships" item should not flag separate join specs as a problem. Reframe the recommendation around adding comments/instructions to ensure co-use.
