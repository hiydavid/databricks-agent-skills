# Skill Update Guide

A repeatable playbook for reviewing and updating agent skills in this project
(the `genie-code` skill bundle, and other skills in `databricks-agent-skills`).
Distilled from a multi-agent review/update of the `diagnose-genie-space` skill.

Each skill is prose: a `SKILL.md` (YAML frontmatter + body) plus optional
`references/*.md`. Because skills are prose, **the orchestrator edits them
directly** — review and research are delegated to sub-agents, but the actual
text edits are made in place. Source code and tests are never edited this way.

---

## Core principles

1. **Cross-vendor review beats single-reviewer review.** Run multiple
   reviewers from different model vendors, each with a *distinct lens*. Where
   independent reviewers agree, confidence is high; where they conflict, you
   have found a real design decision.
2. **Never guess at product behavior.** If a claim depends on how a product
   (e.g. Genie, Unity Catalog) actually behaves, research it against official
   docs before writing it into the skill. Label every claim **DOCUMENTED** vs
   **INFERRED**.
3. **Reconcile before you edit.** Turn findings into a written reconciliation
   plan and get sign-off. Don't start editing on the first finding.
4. **One rule, one home.** Each rule lives in exactly one place; everything
   else cross-references it. Duplication is a drift hazard and wastes the
   agent's context budget.
5. **Progressive disclosure.** `SKILL.md` stays a lean procedure; detailed
   checklists and decision logic live in `references/`. `SKILL.md` points to
   them, it does not re-enumerate them.
6. **Trigger precision over keyword recall.** The frontmatter `description`
   is a what/when statement, not a keyword dump. Generic keywords cause false
   triggers and collisions with sibling skills.
7. **Verify, then hand off.** Re-grep for the issues you fixed, check the
   diff, and leave the change uncommitted for the human to review. Confirm the
   target branch before committing or opening a PR.

---

## The workflow

### Phase 0 — Scope and inventory
- Locate the skill directory and list its files (`SKILL.md`, `references/*`).
  Beware duplicate copies in git worktrees; confirm which path is canonical.
- Read all files yourself so you can write focused, non-overlapping review
  briefs. Note sibling skills it hands off to (verify they exist).

### Phase 1 — Multi-lens cross-vendor review
Dispatch one reviewer per lens, each a *different vendor* where possible, each
read-only (review and report, **no edits, no PR**). Lenses that worked well:

| Lens | Looks for |
|---|---|
| **Mechanics / authoring** | Frontmatter validity, `description` triggering quality, progressive disclosure, naming/structure conventions, load blockers |
| **Content correctness** | Domain accuracy, internal consistency across files, terminology drift, coverage gaps, handoff coherence |
| **Clarity / token economy** | Redundancy across files, run-on/verbose passages, actionability of each step, ambiguity |

Require each reviewer to return findings with a **severity** (see rubric),
file+location, the problem, and a concrete suggested fix, ending with a
prioritized summary.

### Phase 2 — Consolidate and rank
Merge the reports into ONE de-duplicated, severity-ranked list. For each item
note **which reviewer(s) raised it** — items flagged independently by two
reviewers are your highest-confidence fixes. Separate correctness findings
(affect behavior/safety) from style findings (affect clarity/cost).

### Phase 3 — Surface and reconcile reviewer conflicts
Explicitly cross-examine the reports for *disagreements*, not just overlap.
Classify each as:
- **True disagreement** — reviewers recommend opposing end states (resolve with
  a stated principle, picking the stronger argument).
- **Directional tension** — orthogonal axes pulling opposite ways (e.g. trim vs.
  expand); usually reconcilable by doing both in the right places.
- **Judgment call** — stylistic, low-stakes; state your default and move on.

### Phase 4 — Draft the reconciliation for sign-off
Before editing, produce: (a) any reworded artifacts (e.g. the new
`description`), and (b) a restructure outline — a file-ownership model and a
single-home table assigning each duplicated rule to its canonical file.
Get explicit sign-off on the high-impact / invasive changes (renames,
description rewrites, large restructures).

### Phase 5 — Apply edits (prose, in place)
- `SKILL.md` = procedure + boundaries + write-up template. Collapse
  re-enumerated checklists to one-line pointers.
- `references/` = the detail. Give each reference one clear job (e.g. one file
  is the *static checklist*, another is the *decision logic*).
- Apply the single-home rule: state each rule once, cross-reference elsewhere.
- **Exception — safety/guardrail rules** stay visibly stated in `SKILL.md`
  Boundaries even if detailed in a reference. Cheap insurance.
- Apply terminology renames carefully: do **not** rename a term that is
  correct in one context just to be consistent in another (e.g. Metric View
  "dimensions" is correct; don't blanket-rename it). Flag any such deviation.

### Phase 6 — Research unknown product behavior (don't guess)
When a fix depends on how the product actually behaves and you're not certain:
- Dispatch read-only `explore`/`search` sub-agents (prefer 2–3 different
  vendors for triangulation on factual claims).
- Require: exact doc **URL + verbatim quote + last-updated date** for every
  claim; an explicit **DOCUMENTED vs INFERRED** label; an overall confidence;
  and a plain statement when something is *not* documented.
- Synthesize only from their reports. If reports conflict, dispatch a
  follow-up rather than resolving from memory.
- Write only what is supported. If behavior isn't documented, say so in the
  skill instead of inventing a rule.

### Phase 7 — Consistency check across the bundle
Before finalizing any new section, grep the whole bundle for terms that could
clash with it, and reconcile every hit. This is the step that guarantees the
new content doesn't contradict old content. See the command snippets below.

### Phase 8 — Verify and hand off
- Re-grep to confirm the issues you fixed are gone and the new content is
  present.
- Sanity-check the `description` length, stray stale phrasing, and the
  `git diff --stat`.
- Leave the change **uncommitted**. Confirm the target branch with the human
  before committing or opening a PR. Never merge.
- Optionally re-run the reviewers against the revised skill.

---

## Reference material

### Severity rubric
- **Blocker** — skill won't load/trigger, or guidance is unsafe/wrong in a way
  that causes harm.
- **High** — materially wrong, misleading, or a trigger/precision problem;
  fix before relying on the skill.
- **Medium** — correctness or consistency gap that degrades quality.
- **Low** — polish; improves clarity or robustness.
- **Nit** — cosmetic.

### Skill-quality checklist
**Frontmatter**
- [ ] `name` is lowercase-hyphenated and matches the directory.
- [ ] `description` is a concise what/when statement (front-load the
      differentiator vs. sibling skills); no generic-keyword dump; under the
      length ceiling. Keep domain-specific nouns, drop generic terms that
      collide with other skills.

**Structure / progressive disclosure**
- [ ] `SKILL.md` is a lean procedure; detail lives in `references/`.
- [ ] `SKILL.md` points to references at the right decision points instead of
      re-enumerating them.
- [ ] Each reference file has one clear, non-overlapping job.
- [ ] Handoff targets to sibling skills exist and are unambiguous.

**Content / consistency**
- [ ] Domain terms are accurate and current; no terminology drift across files.
- [ ] Each rule has a single canonical home; others cross-reference it.
- [ ] Safety/guardrail rules are stated in `SKILL.md` Boundaries.
- [ ] No two passages contradict; no claimed behavior is undocumented-but-stated-as-fact.

**Clarity / actionability**
- [ ] Every workflow step is concretely executable, with a decision criterion.
- [ ] Confidence/severity levels (if used) are defined once and applied
      consistently.
- [ ] No run-on sentences or comma-spliced keyword lists an agent could misparse.

**Housekeeping**
- [ ] No `.DS_Store` or OS cruft committed; it's gitignored.
- [ ] Single H1 per file; clean heading hierarchy.

### Reusable dispatch prompt — review
> READ-ONLY REVIEW. Do NOT edit any files, create a branch, or open a PR. Your
> only deliverable is a written findings report.
> Context: skill `<name>` at `<relative/path/>`, files `<list>`. It does `<one-line purpose>`.
> YOUR LENS = `<mechanics | content correctness | clarity/redundancy>`. Evaluate `<lens-specific checks>`.
> Return each finding with SEVERITY (Blocker/High/Medium/Low/Nit), file+location,
> the problem, and a concrete suggested fix. End with a prioritized summary.

### Reusable dispatch prompt — research (product behavior)
> READ-ONLY RESEARCH. Edit nothing. Return a findings report with EVIDENCE only.
> Question: `<precise behavior question>`.
> YOUR LENS = `<official docs | governance/runtime | mechanics/limits>`.
> For every claim give: exact doc URL, verbatim quote, and last-updated date.
> Label each finding DOCUMENTED vs INFERRED, give an overall confidence, and
> state plainly if a behavior is NOT documented. Do not speculate beyond evidence.

### Consistency-check command snippets
Run from the skill directory. Adapt the term lists to the change you made.

```bash
# Terms that might clash with a new "precedence/conflict" section:
grep -rn -iE 'override|overrides|\bwins?\b|authoritative|authority|priorit|precedence|hard rule|must obey|exactly as written' .

# A term you are renaming/retiring (expect zero, or only the intended sense):
grep -rn -i '<old-term>' .

# Confirm the new section/anchor exists and is referenced:
grep -rn '<New Section Title>' .

# Frontmatter description length (expect a few hundred chars, not ~900+):
awk 'NR>1 && /^description:/{sub(/^description: *"?/,""); sub(/"$/,""); print length($0)" chars"}' SKILL.md
```
```bash
# From repo root: see the scope of your change before handing off.
git diff --stat <skill/path>/
```

---

## Anti-patterns to avoid
- **Editing on the first finding** instead of consolidating and reconciling first.
- **One reviewer, one vendor** — you lose the agreement/conflict signal.
- **Writing product behavior from memory** — research and cite, or say it's undocumented.
- **Keyword-dump descriptions** — they false-trigger and collide with sibling skills.
- **Duplicating a rule "to be safe"** — it drifts; cross-reference instead.
- **Blanket find-replace renames** — they corrupt terms that were correct in context.
- **Adding a new section without a bundle-wide consistency grep** — it silently contradicts old content.
- **Committing/merging without confirming the branch** — leave it for the human.
