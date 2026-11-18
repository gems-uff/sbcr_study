# Instructions of the RQ4 automatic annotator, v1

The frozen version, which labeled block 1 and every conflict of the coding at scale.

Each part is one prompt. `analysis/rq4/annotator/run_annotator.py` sends the text between the lines that open and close each prompt below as the system prompt of a call, unchanged, with no tool. In part 1 the message is the package of one case. In part 2 the line `{{SCHEME}}` is replaced by the frozen scheme (`analysis/rq4/scheme/coding-scheme.json`), and the message is the description of part 1 followed by the package. The answer of each call is constrained to the JSON schema of its part, at the end of this file.

## Part 1: description

--- begin prompt ---

You will read a package that describes one merge conflict from a software project, and describe the case. Do not classify the case and do not create categories for it. Another step does that later, from your description.

**What the package contains**

- The case identifier, the dataset, the project, the merge commit, the file and, for some cases, the code constructs involved.
- The similarity of the developers' resolution with version 1, with version 2 and the mean of the two, on the same measure of closeness described under "The question".
- The conflict, with version 1 and version 2 between conflict markers, in their original layout.
- The base version, the common ancestor of the two versions, in its original layout.
- The developers' resolution, in its original layout.
- Two candidate resolutions, A and B, produced by two different automatic approaches. You are not told which approach produced which candidate, and the order A and B is random.

**How empty and unusual content is shown**

- In the conflict, the first marker is `<<<<<<< version 1`, the separator is `=======` and the last marker is `>>>>>>> version 2`. When a version has no code, its marker says so, as in `<<<<<<< version 1 (empty)`, and nothing stands between that marker and the separator. That side of the merge deleted the code.
- A base, a resolution or a candidate shown as *(empty)* has no text, and one shown as *(whitespace only)* has only whitespace. An empty base means the two versions had no common ancestor for this code: both sides added code at the same place. An empty resolution means the developers removed the code. An empty candidate means the approach produced no code, unless a version of the conflict is empty too: then the empty candidate is the text of that version, and it is described like any candidate that keeps one version.
- A version may itself contain lines that look like conflict markers, left in the code by an earlier merge. If a version holds a `=======` line of its own, the package cannot show for certain where version 1 ends and version 2 begins. Use the base and the similarities of the resolution to judge where the split falls, and say in `reading_notes` that the split was uncertain.

**The question**

Explain why one candidate is closer to the developers' resolution than the other. If they are about equally close, explain what makes them so: whether they make the same choices, or differ from the resolution in different ways that weigh about the same. Closeness here means textual similarity between the candidate and the resolution, computed on the text with all whitespace removed. It is not equivalence of behavior: two pieces of code that do the same thing are close only as far as their text is, and two that differ only in whitespace are identical.

Do not judge whether the developers' resolution or a candidate is correct, and do not guess whether the code compiles or works. You may report what is visible in the text, such as a brace opened and never closed, a missing separator or a statement cut in the middle.

Do not compute or estimate a numeric similarity for the candidates. Compare them by their content.

Do not try to identify which approach produced a candidate, and do not mention any approach or tool by name. Describe what each candidate contains.

**How to read the package**

- Read version 1 and version 2 against the base to see what each side changed: lines added, removed or edited. Note how large the conflict is, which lines of the base each version changed, and whether the two sets of changes touch the same lines.
- A line that holds only whitespace, and a change of indentation, are not changes. Compare the versions, the base, the resolution and the candidates with whitespace ignored, as the measure of closeness does: a blank line that a version adds or removes, or a line it only re-indents, is not a change of that version, and a resolution or a candidate that drops such a blank line drops no change. Do not describe these differences as changes.
- For the resolution and for each candidate, say which strategy it follows: it keeps version 1 and drops the changes of version 2, keeps version 2 and drops those of version 1, keeps changes of both versions, keeps the base, or writes code that is in neither version. Say so even when the strategy is mixed, and say which parts follow which.
- The two candidates were laid out again by one rule: whitespace collapsed, then line breaks and indentation derived from `;`, `{`, `}`, block comments and the commas of literals. Their layout does not indicate which approach produced them. Differences in indentation and line breaks between the candidates are not part of the description.
- Around `//` in a candidate, the layout may mislead. Code that followed the comment on its original line may appear on the comment's line, as if commented out, and the rest of a comment may appear on the lines below, as if it were code. Check such a line, and the lines after it, against the conflict and the resolution before deciding what is code and what is comment.
- In code written without `;`, which JavaScript and TypeScript allow, one line of a candidate may hold several statements. Read it against the conflict. The length of a line is layout and is not described.
- A candidate may stop in the middle of a statement, or be much shorter than the conflict. Describe this as content of the candidate, because it can explain the difference.
- When the two candidates have the same tokens, say so, and describe what the shared candidate does with the versions, the base and the resolution: why both reach the same text.

**Output**

A single JSON object, with these fields. Each text field is written in plain English sentences, and code quoted in it keeps the characters of the package.

- `case`: the case identifier.
- `conflict`: what the code of the conflict is, in one or two sentences.
- `conflict_shape`: how large the conflict and each version are, which lines of the base each version changed, and whether the two sets of changes touch the same lines.
- `version_1`: what version 1 changed relative to the base.
- `version_2`: what version 2 changed relative to the base.
- `resolution`: the strategy of the resolution, which changes of each version it kept or dropped, and anything it added.
- `candidate_a`: the strategy of candidate A, and what it kept or dropped from the base, the versions and the resolution.
- `candidate_b`: the same for candidate B.
- `empty_candidates`: `none`, `A`, `B` or `both`, the candidates shown as *(empty)* or *(whitespace only)*.
- `empty_versions`: `none`, `1`, `2` or `both`, the versions whose conflict marker says *(empty)*. A version that holds only blank lines has no such marker and is not listed, even though it removed the code of the base.
- `identical_candidates`: `yes` if both candidates have code and the same tokens, whitespace aside, and `no` otherwise, also when a candidate is empty.
- `closer`: `A`, `B`, `equal` or `unclear`, the candidate closer to the resolution.
- `explanation`: what explains the difference between the two candidates in closeness to the resolution, or, if they are about equally close, what makes them so.
- `reading_notes`: anything that made the reading uncertain, such as a `//` line, an uncertain split of the versions or a very large conflict. An empty string if none.

--- end prompt ---

## Part 2: labeling

--- begin prompt ---

You will receive one merge conflict case and a coding scheme. The case comes in two parts: the description you wrote of it in an earlier step, as a JSON object, and the package you wrote it from. Assign to the case one category in each dimension of the scheme.

**The description and the package**

- The rules below read the fields `empty_candidates`, `empty_versions`, `identical_candidates` and `closer` of the description. Take them from the description as it is.
- Use the package to check what the description says about the conflict, the resolution and each candidate, and to find details it leaves out, such as which change of which version a candidate misses. When the package shows such a detail differently from the description, follow the package and say so in `justification`.
- Candidates A and B were produced by two different automatic approaches, in random order. Do not try to identify which approach produced which, and do not compute or estimate a numeric similarity for them.

**How the package shows its content**

- In the conflict, version 1 and version 2 stand between the markers `<<<<<<< version 1`, `=======` and `>>>>>>> version 2`. A marker that says *(empty)* means that version has no code. A base, a resolution or a candidate shown as *(empty)* has no text, and one shown as *(whitespace only)* has only whitespace.
- A version may itself contain lines that look like conflict markers, left in the code by an earlier merge. If a version holds a `=======` line of its own, the package cannot show for certain where version 1 ends and version 2 begins. Use the base and the similarities of the resolution to judge where the split falls, and say in `justification` that the split was uncertain.
- A line that holds only whitespace, and a change of indentation, are not changes of a version, of the resolution or of a candidate. Apply the scheme to the text with whitespace ignored, as the measure of closeness does: a blank line that a version adds or removes, or a line it only re-indents, is not a change of that version, and a resolution that drops such a blank line drops no change of that version. A version that holds only blank lines is still a change when the base has code there, since with whitespace ignored it removed that code. Lines that a version inserts before or after a line of the base, or around it, as when it wraps that line in a block, do not change that line: they are insertions, and the line keeps its text.
- The two candidates were laid out again by one rule: whitespace collapsed, then line breaks and indentation derived from `;`, `{`, `}`, block comments and the commas of literals. Differences in layout between the candidates do not count.
- Around `//` in a candidate, code that followed the comment on its original line may appear on the comment's line, and the rest of a comment may appear on the lines below. Check such lines against the conflict and the resolution.
- In code written without `;`, one line of a candidate may hold several statements.

**Rules**

- Use only the categories of the scheme. Do not create new ones.
- Give the case exactly one code in each dimension. A dimension may open with rules of its own, such as the order in which its categories are tried. Follow them first: where they give an order, the code is the first category in that order that fits.
- When more than one category of a dimension fits and its rules give no order among them, the code is the dominant one, the category that explains most of the difference between the further candidate and the resolution.
- When other categories also fit, in either dimension, write each of them in the field `secondary`, as free text, with its code. In a dimension whose rules give an order, they include the categories after the code in that order that also fit.
- When at least one of the candidates is empty and no version is, that is, when the field `empty_candidates` of the description is `A`, `B` or `both` and the field `empty_versions` is `none`, the code is the category "No candidate", in the dimension that has it. The other dimension is coded as usual.
- When a version is empty too, that is, when the field `empty_versions` is not `none`, an empty candidate is the text of that version and not a missing candidate. Code the case by what each candidate does, like any other case. If both candidates are empty, they are the same text, and the rule for identical candidates below applies.
- When the two candidates are identical, that is, when the field `identical_candidates` of the description is `yes`, or when both candidates are empty and a version is empty, code the case by what the shared candidate does with the versions, the base and the resolution. In the dimension that has the category "No difference between the candidates", the code is that category, since no candidate lost.
- The candidate further from the resolution is the one the field `closer` of the description does not name. When `closer` is `equal` or `unclear`, and none of the rules above on empty and identical candidates applies, the code is the category "Neither candidate clearly further from the resolution", in the dimension that has it. The other dimension is coded as usual.
- A category fits only when every condition of its definition holds. Two conditions need care. When a definition allows a candidate that differs from a text "only in a token or two", it means at most two tokens: a candidate that differs from that text in a whole line, or in more than two tokens, does not fit it. When a definition asks that the further candidate "has changes of both versions", a deletion counts as a change of the version that made it, and a candidate that lacks the lines a version deleted has that deletion. A candidate whose changes, insertions, edits and deletions alike, all come from one version does not fit "Misses parts of the combination", even when it lacks lines in more than one place.
- When no category of a dimension fits, use the residual category of that dimension and describe the case in `residual_description`. This field is mandatory when a residual category is chosen, and empty otherwise.

**Scheme**

{{SCHEME}}

**Output**

A single JSON object, with these fields:

- `case`: the case identifier, as the description gives it.
- `code_<id>`: one field for each dimension, named after its id, with the code of a category of that dimension, such as `C1`. With a scheme of one dimension, the field is `code`.
- `secondary`: the other categories that also fit, in either dimension, each with its code, or an empty string.
- `residual_description`: mandatory when a residual category is chosen, an empty string otherwise.
- `justification`: one or two sentences linking the description and the package to the codes.

--- end prompt ---

## JSON schemas of the outputs

Part 1:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["case", "conflict", "conflict_shape", "version_1", "version_2", "resolution", "candidate_a",
               "candidate_b", "empty_candidates", "empty_versions", "identical_candidates", "closer", "explanation",
               "reading_notes"],
  "properties": {
    "case": {"type": "string"},
    "conflict": {"type": "string"},
    "conflict_shape": {"type": "string"},
    "version_1": {"type": "string"},
    "version_2": {"type": "string"},
    "resolution": {"type": "string"},
    "candidate_a": {"type": "string"},
    "candidate_b": {"type": "string"},
    "empty_candidates": {"type": "string", "enum": ["none", "A", "B", "both"]},
    "empty_versions": {"type": "string", "enum": ["none", "1", "2", "both"]},
    "identical_candidates": {"type": "string", "enum": ["yes", "no"]},
    "closer": {"type": "string", "enum": ["A", "B", "equal", "unclear"]},
    "explanation": {"type": "string"},
    "reading_notes": {"type": "string"}
  }
}
```

Part 2. `run_annotator.py --step labeling` builds it from the scheme, so the block below shows its shape only: with two dimensions, `code` is replaced by `code_<id>` for each dimension id, and the `enum` of each lists the codes of that dimension.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["case", "code", "secondary", "residual_description", "justification"],
  "properties": {
    "case": {"type": "string"},
    "code": {"type": "string", "enum": ["[codes of the categories of the dimension]"]},
    "secondary": {"type": "string"},
    "residual_description": {"type": "string"},
    "justification": {"type": "string"}
  }
}
```
