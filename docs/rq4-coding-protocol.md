# Coding protocol of the qualitative analysis (RQ4)

This protocol says how to code the conflicts of RQ4. RQ4 asks what distinguishes the conflicts in which one approach's candidate is closer to the developers' resolution than the other's. For each conflict, the coding answers a narrower question: why one candidate is closer to the resolution than the other, or, when the two are about equally close, what makes them so. The coding does not judge whether a candidate or the resolution is correct, which would require compiling the projects and running their tests.

Two human coders label a stratified sample by consensus. An automatic annotator labels the same conflicts, and if its agreement with the coders reaches a threshold, it labels every conflict of the analysis. Sections 1 to 10 give the steps in the order they are run. Section 11 records how they were applied in this study: the dates, the counts and the results. In this study the coders were the two authors.

## Fixed values

| Parameter | Value |
|---|---|
| Similarity of a candidate to the resolution | `2·\|LCS(c', r')\| / (\|c'\| + \|r'\|)`, where `c'` and `r'` are the candidate and the resolution with all whitespace removed |
| SBCR's candidate | seed 3022024 |
| Seed of the draw | 1417861201 |
| Human sample | 10 conflicts per dataset and band, 150 in all, in 3 blocks of 50, plus 10 pilot conflicts |
| Seed of the labeling at scale | 68461812 |
| Agreement threshold | Cohen's kappa of 0.61 or above, in both dimensions |
| Bootstrap of the kappa | 2,000 resamples of conflicts, seed 559479682 |
| Residual limit | 10% of the cases, per dimension, cumulative over the blocks |
| Limit of a large conflict (C4) | more than 30 lines that are not blank |
| Derivation model | Claude Opus 5.5 (`claude-opus-5-5`), effort `high` |
| Annotator | Claude Fable 5.1 (`claude-fable-5-1`), effort `high`, at most 16,000 output tokens per call |

The seeds, the threshold, the residual limit and the stopping rule are fixed before the data they apply to are read.

## 1. Define the population and the bands

1. Take the combination conflicts in the test partitions of split 1 of the merge-grouped design, in the five datasets: Dataset1, Dataset2Java, Dataset2C#, Dataset2JavaScript and Dataset2TypeScript. The project-disjoint and chronological designs and the other two splits are not part of the analysis.
2. For each conflict, compute `d = Sim_SBCR − Sim_MergeGen`, the difference between the similarities of the two candidates to the developers' resolution, positive when SBCR's candidate is closer. A conflict in which a version has 20,000 characters or more is above SBCR's size limit and has no SBCR candidate. Score it 0 for SBCR, so that its `d` is `−Sim_MergeGen`, and keep it in the population.
3. Within each dataset, assign the conflicts to three bands by quartiles of `d`:

| Band | Definition | What it investigates |
|---|---|---|
| Clear SBCR win | `d > 0`, in the upper quartile of the positive values of `d` in the dataset | why search wins by a wide margin |
| Clear MergeGen win | `d < 0`, with `\|d\|` in the upper quartile of the absolute negative values of `d` in the dataset | why generation wins by a wide margin |
| Near tie | `\|d\|` in the lower quartile of `\|d\|` in the dataset, exact ties included | when the two converge |

4. Assign a conflict that falls in two bands to the clear-win band. Do not code the conflicts between the bands.

The limits come from quartiles, and not from a fixed value of `d`, because no difference in this similarity has an established practical meaning. The bands are chosen regions of the distribution of `d`, so every frequency of the analysis refers to a band and not to the population.

## 2. Draw the human sample

1. In each combination of dataset and band, draw ten conflicts by simple random sampling within the cell, 150 in all. Take a cell with fewer than ten conflicts whole. Fix the seed in the draw script before it reads the data.
2. Draw ten more conflicts for the pilot, two per dataset, spread across the bands and kept outside the sample.
3. Split the 150 into three blocks of 50, coded in that order. Stratify the split: each cell of ten gives three conflicts to each block, and its tenth goes to one of the blocks, so that each block holds the five datasets and the three bands.
4. Record the seed, the date and the identifier of each drawn conflict in the output of the draw. Record the band, `d` and the approach behind each candidate in a sealed file, which the coders do not open.

The size of the sample does not come from a sample-size formula. It is bounded by the coders' time, which fits blocks of 50 conflicts and at most three blocks. Ten conflicts per cell balance the five languages and do not support a percentage per dataset.

## 3. Build the packages

The unit of analysis is the conflict chunk. Each chunk reaches the coders and the annotator as a package that holds:

- the case identifier, the dataset, the project, the merge commit, the file and, for some cases, the code constructs in the chunk;
- the similarity of the developers' resolution with version 1, with version 2 and the mean of the two;
- the conflict, with the two versions between conflict markers, in their original layout;
- the base version, the common ancestor of the two versions, in its original layout;
- the developers' resolution, in its original layout;
- the two candidates, named A and B.

**What to hide.** Leave out of the package the band, the approach that produced each candidate and the similarity of each candidate to the resolution, since the difference between the two similarities is `d`. Draw the order of the two candidates per case. Join the band and the approach to the labels by script, from the sealed files, only after the human coding ends. Leave out the commit message as well. Neither approach reads it when it produces its candidate, so it would let the coders explain the difference between the candidates with information neither approach had.

**One layout for both candidates.** MergeGen returns its candidate on a single line without indentation, and SBCR keeps the original lines, so showing the candidates as produced would identify the approach in every case. Show both in one layout: collapse their whitespace, then derive line breaks and indentation from `;`, `{`, `}`, block comments and the commas of initializers and object literals, with no break inside a string literal. The layout is for display only, and every similarity is computed on the candidates as produced.

The layout has two limits. Once whitespace is collapsed, nothing marks where a `//` comment ended, so code that followed a comment on its original line can appear on the comment's line, and the text of a comment can appear on the lines below as code. In JavaScript and TypeScript written without `;`, one line can hold several statements. Put a note before the candidates, the same in every package and naming no approach, that states both limits and says that the conflict keeps the original layout. The coders and the annotator check a line with `//`, and the lines after it, against the conflict and the resolution, and they do not code indentation or line breaks, which the similarity ignores as well.

**Empty candidates.** For a conflict above SBCR's size limit, show an empty candidate in SBCR's slot, like any empty candidate, with no note. MergeGen can also return an empty candidate, so an empty candidate alone does not identify the approach.

**Cues the blinding leaves.** The blinding is partial. An empty candidate in a very large conflict points to SBCR's size limit. MergeGen reads at most 500 tokens of the conflict and generates at most 400, so in a large conflict its candidate is short next to the versions, and when it reaches the generation limit it stops in the middle of a statement. Code a cut-off candidate like any other content: unlike the layout, it can explain the difference in similarity.

**Reading the packages.** The human coders read each package in a local application, built from the packages and the coding sheet alone, with no access to the band, to `d` or to the approach. It shows the base and the two versions side by side, and the two candidates side by side, with reading aids that mark tokens and show no number: the tokens each version added to the base or removed from it, the tokens that differ between the two versions and the tokens that differ between the two candidates. Two further aids start off each time the application opens: the tokens of each candidate against the resolution, and the origin of each token of the candidates and of the resolution in the two versions. The application also marks the tokens that differ between any two texts of the case chosen by the reader. The aids compare only texts of the package and add no information to it. The annotator receives the same packages as text, without the reading aids.

## 4. Describe the pilot

Before the sample, have the two coders describe the ten pilot conflicts together, in a session that is recorded and transcribed like those of Section 5. The session checks that each package holds what a coder needs, settles how the descriptions are recorded and measures the time per case. Write the annotator's instructions (Section 8) after this session. The pilot is labeled after the scheme is frozen (Sections 7 and 8), and no agreement of the pilot counts as a result.

## 5. Derive the categories from block 1

People decide which categories exist. A language model takes part in two separate roles: in the derivation, a model organizes what the coders observed into proposed categories, and the coders decide. In the labeling, another model applies the frozen categories (Section 8). The two never share a call, a prompt or an output, and the annotator never receives the transcripts of the coders' sessions.

1. **Describe block 1.** Have the two coders go through the 50 conflicts of block 1 together, discussing each one until they agree, and describe aloud what they observe about why one candidate is closer to the resolution than the other. Record the sessions and transcribe them automatically. For each case, the coders may write a short note in English in the application. Ask the coders not to guess aloud which approach produced a candidate.
2. **Prepare the input.** Split the transcripts by case at the case identifier the coders say aloud when they open each case, and check each cut against the times at which the application saved the case. List by script the passages of the transcripts and of the notes with words that name or describe an approach. Have the coders decide, passage by passage, which ones to remove, and replace each removed passage with the line `[passage removed]`. Do not use the meeting summary that the transcription service writes.
3. **Test the call on the pilot.** Before the first call on block 1, run the call once on the transcript of the pilot. Let no one read the categories it proposes, so that the coders describe block 1 without a proposal in mind.
4. **Propose categories.** Send the transcripts of block 1, each under the header of its case and followed by the coders' note on that case, if they wrote one, to the derivation model through Claude Code in non-interactive mode, with every tool disabled, in a call of its own. Run the call twice. The model sees no conflict, package, band or approach.
5. **Review and freeze.** Have the coders read both proposals and decide the scheme: its structure, its categories, their names and their definitions. Have an assistant (Claude Opus 5.5, in a separate session) compare the two proposals and list the points to decide, each with its alternatives. Freeze the scheme with the approval of both coders.

**What the derivation prompt asks.** A compact scheme, with no target number of categories, because agreement falls when categories are many and close to each other. Every category grounded in the transcripts, and none that names or depends on an approach. Two structures: a single dimension, and two dimensions that separate a characteristic of the conflict from the way the candidate further from the resolution departs from it, with the model saying which structure the transcripts support better. The prompt gives four categories as already defined, so that the model does not propose them again: *no candidate*, *no difference between the candidates*, *no candidate clearly further from the resolution*, and one residual category per dimension. The output names no case, so that the coders' labels of block 1 do not lean on the model's, and gives counts per category, which the runner checks to add up to the cases of the block.

The prompt is published as it ran. It defines *no candidate* as a case in which at least one candidate is empty, and the frozen scheme restricts it to a case in which a candidate is empty and neither version is (Section 6.3).

## 6. The coding scheme

### 6.1 Rules of the scheme

Each case receives exactly one code in each of two dimensions. A dimension's own rules say which code wins when more than one category fits: the merge dimension takes the first category that fits in the order C4, C3, C2, C1, and the candidate dimension tries the predefined values first, in the order FN, FD, FU. Otherwise the code is the dominant category, the one that explains most of the difference between the further candidate and the resolution. Write every other category that also fits, in either dimension, with its code in a free-text field for secondary categories, so that a C4 case keeps the structure of its changes beside its other codes. The frequencies use only the code of each dimension. A residual category requires a free description of the case.

The further candidate is the one whose text, with all whitespace removed, is less similar to the developers' resolution, judged by reading the texts, since neither the coders nor the annotator see the similarity.

### 6.2 Merge characteristic (`merge`)

What the two versions did to the base, and what the developers' resolution did with their changes. The merge covers the two conflicting versions and the resolution. Apply the first category that fits, in the order C4, C3, C2, C1. CR is for a case none of them fits.

| Code | Category | Definition |
|---|---|---|
| C4 | Large conflict | The longer of the two versions, as the conflict shows it, has more than 30 lines that are not blank. This category comes before all the others of the dimension, whatever the structure of the changes. |
| C3 | Resolution departs from the union | The resolution is not what combining the changes of both versions gives. It keeps the base where a version changed it, it drops a change of a version that no change of the other version forced it to drop, or it breaks the order the lines have in a version, so that a line that comes after another in a version comes before it in the resolution. When what the resolution drops is the losing side of an overlap, as C2 defines it, the case is C2. |
| C2 | Overlapping edits | The two versions touch the same part of the base. At least one line of the base is changed or deleted by both versions, or one version deletes a block that the other version edits, or both versions insert code at the same position of the base. The resolution keeps one side of the overlap, or mixes the two, and keeps the other changes of the versions. |
| C1 | Adjacent independent edits | The two versions change different lines of the base, next to each other or near each other. No line of the base is changed by both, no block deleted by one is edited by the other, and no two insertions fall at the same position. The resolution keeps the changes of both versions, in the order their lines have in the versions. |
| CR | Other merge (residual) | Residual category. A case that none of C1 to C4 fits. The coder describes it in free text, which is mandatory. |

### 6.3 Candidate characteristic (`cand`)

What sets the further candidate apart from the resolution. In F1 to F6 this is a failure of that candidate, and in the predefined values FD and FU no candidate is further, so the dimension describes the candidates and not only a failure. The further candidate is the one whose text, with all whitespace removed, is less similar to the developers' resolution. It is judged by the text and not by what the code does: two pieces of code that behave the same are close only as far as their text is. Apply first the three predefined values, in the order FN, FD, FU. Otherwise, code the further candidate by the kind of difference between its text and the resolution: changes missing (F1, F2, F3), changes in excess (F4), text cut off at one point (F5), or changes altered (F6). When more than one applies, the code is the one that explains most of the difference, and the other is the secondary category.

| Code | Category | Definition |
|---|---|---|
| FN | No candidate (predefined) | At least one of the two candidates is empty, and neither version is. An empty candidate that is the text of an empty version is not a missing candidate, and the case is coded like any other. |
| FD | No difference between the candidates (predefined) | The two candidates have the same text, whitespace aside, so no candidate is further from the resolution. It also applies when both candidates are empty and a version is empty. |
| FU | Neither candidate clearly further from the resolution (predefined) | The two candidates have code and differ, but the reading of the case does not show which one is further from the resolution, or shows them about equally close to it. It is decided by the reading of the texts, and it can be assigned in any case. |
| F1 | Misses one version's change | The further candidate is the text of version 1 or of version 2, or differs from it only in a token or two, while the resolution has changes of the other version that the candidate lacks. It includes an empty candidate that is the text of an empty version. When the change the candidate took is itself what the resolution discarded, the code is F4. |
| F2 | Misses both versions' changes | The further candidate is the text of the base, or differs from it only in a token or two. It has no change of either version, while the resolution has at least one. |
| F3 | Misses parts of the combination | The further candidate has changes of both versions, or mixes their text, but lacks lines or elements that the resolution has, in more than one place or in a place that is not its end. It is not the text of a version or of the base (F1, F2), and its text does not stop at one point with everything after it missing (F5). |
| F4 | Adds a change the resolution discarded | The further candidate has a change of a version, an added line, an edit or a deletion, that the resolution does not have, because the developers kept the base there or dropped that change. It includes a candidate that combines both versions when the resolution keeps the base or a single version. The difference is a change the candidate has in excess, and not a change it lacks (F1 to F3). |
| F5 | Cut off before the end | The further candidate matches the start of the resolution, or of the combination of the versions, and then stops, often in the middle of a statement, so everything the resolution has after that point is missing. The gap is at the end, at a single point, unlike F3. |
| F6 | Distorted combination | The further candidate has changes of the versions in the wrong place, duplicated, nested where it does not belong or mixed line by line, or has tokens that are in no version, in the base or in the resolution. What it contains is altered, rather than missing (F1 to F3, F5) or in excess (F4). |
| FR | Other difference from the resolution (residual) | Residual category. A case that none of the categories above fits. The coder describes it in free text, which is mandatory. |

### 6.4 How to read the definitions

The coders and the annotator read the definitions in the same way on four points.

- **Whitespace.** A line that holds only whitespace, and a change of indentation, are not changes of a version, of the resolution or of a candidate, as the similarity removes all whitespace. A version that holds only blank lines where the base has code removed that code.
- **"A token or two"** in F1 and F2 means at most two tokens. A candidate that differs from a version or from the base in a whole line, or in more than two tokens, does not fit them.
- **"Has changes of both versions"** in F3. A deletion counts as a change of the version that made it, and a candidate that lacks the lines a version deleted has that deletion. A candidate whose changes all come from one version, deletions included, does not fit F3, and gets the residual category when nothing else fits. A category fits only when every condition of its definition holds.
- **Insertions around a line.** Lines that a version inserts before, after or around a line of the base, as when it wraps that line in a block, do not change that line, which matters for C1 and C2.

### 6.5 Empty and identical candidates

The three predefined values of the candidate dimension cover the cases in which there is no further candidate to code. They are defined before the derivation.

- When a candidate is empty and neither version is, the missing candidate explains the difference, and the code is FN. This covers SBCR above its size limit and an empty output of MergeGen alike, and the definition names neither approach.
- When a version is empty, because that side deleted the code, an empty candidate is the text of that version, and not a candidate the approach failed to produce. Code the case by what each candidate does, like any other. A version of only whitespace has no empty marker in the package and does not count as empty.
- When the two candidates have the same text, `d` is 0, and the case is in the near-tie band. Code FD in the candidate dimension, and in the merge dimension code what the shared candidate does with the versions, the base and the resolution, since why the two approaches reach the same text is what the near-tie band investigates.
- Assign FU by the reading of the texts, and not by the band, which the coders do not know.

FN, FD and FU are not residual categories, and they count in the agreement like any other code. Report the number of cases with each, and the agreement on them, apart.

### 6.6 Residual limit

The scheme does not change after it is frozen. Material that does not fit receives the residual category of its dimension, with a mandatory description.

At the end of each block, count the share of residual codes in each dimension over all the human-coded blocks up to that block, without the pilot. A case without consensus counts as residual when either coder's final reading is the residual category. If the share passes 10% in a dimension, the scheme is inadequate: stop the coding, read the residual descriptions together, revise the scheme and redo all the coding done until then under the revised scheme.

The count is cumulative, and not per block, because the three blocks come from the same stratified draw. With a true residual share of 8%, a single block of 50 passes 10% with a probability of 21%, and at least one of three blocks does with 50%, against 18% over 100 cases and 15% over 150 (binomial distribution).

## 7. Label by consensus

1. After the scheme is frozen, have the two coders label the pilot and then the block, together and by consensus, with the package of each case at hand. For block 1, give them also the transcript of its joint description, in the copy without the passages that name an approach, the copy the derivation read.
2. Record no individual label of either coder before their discussion.
3. An assistant (Claude Opus 5.5, through Claude Code) may help the coders refine their consensus labels.
4. Record the consensus labels of a block before the annotator runs on it.

**Disagreement between the coders.** It is resolved in the discussion. Consensus is reached, or not, in each dimension separately. A conflict without consensus in a dimension keeps each coder's final reading in that dimension, stays out of the frequencies from the coders' labels and out of the main kappa in that dimension only, and counts as a disagreement in the worst-case kappa (Section 9). Report the number of conflicts without consensus per dimension.

Between the coders and the annotator there is no resolution. Their disagreement is what the kappa measures.

## 8. Run the annotator

### 8.1 Two steps per conflict

The annotator follows the path of the coders in two steps, each with its own prompt, and each call receives one conflict.

1. **Description.** The model receives the package and writes a description of the case, with no category in view. The description has fixed fields: what the code of the conflict is, the shape of the conflict, what each version changed, the strategy of the resolution and of each candidate, which candidates and versions are empty, whether the candidates are identical, which candidate is closer to the resolution (`A`, `B`, `equal` or `unclear`), what explains the difference, and notes on anything that made the reading uncertain.
2. **Labeling.** The model receives its own description, the package of the case and the frozen scheme, and assigns one code per dimension, the secondary categories, a description for a residual code and a short justification. The rules of the scheme that depend on empty and identical candidates and on the closer candidate read the fields of the description. The further candidate is the one the description does not name as closer, and when the description says `equal` or `unclear`, and no rule on empty or identical candidates applies, the code is FU. The package serves to check details that the description leaves out.

Keep both outputs, so that a disagreement with the coders can be traced to what the model observed or to how it labeled.

### 8.2 What the instructions say

Both prompts explain how the package shows its content, empty texts and versions that contain old conflict markers. They say that closeness is textual similarity with all whitespace removed and not equivalence of behavior, forbid the model to compute or estimate a similarity, and forbid it to identify or name an approach. They state the reading of the common layout (Section 3), that whitespace is not a change, and the readings of Section 6.4. The labeling prompt states the rules of Section 6.1 on the order of the codes, the dominant category and the secondary field. The instructions hold no example and no human label of a sample conflict.

### 8.3 Adjust the instructions on the pilot

1. Run the annotator on the pilot after the coders have labeled it.
2. Correct the instructions from the annotator's disagreements with the coders on the pilot only, without changing the scheme.
3. Correct a coder's code of the pilot where a disagreement shows that it does not follow a definition.
4. Freeze the instructions before the annotator sees any conflict of block 1. The frozen version labels every block and the labeling at scale.

The replication package holds two versions of the instructions: v0, the first that ran on the pilot, and v1, the frozen version. Each is published as its two prompts and the JSON schemas of the two outputs. The SHA-256 of the v1 prompts are `430c8846ab086f58ebef3c842ab4b147b779df8667201968433cae16b92008d1` for the description prompt, `91fa7343818e946ca8d627ffda231662cad06358ffcd51bed1b666fc17a04799` for the labeling prompt before the scheme is inserted, and `aec19954c214f80bd2281d35760b2cbaee883a2d5f1d680ac69074d8daec97b0` for the labeling prompt with the scheme inserted, the `prompt_sha256` of every labeling record of block 1 and of the labeling at scale. The scheme has SHA-256 `38f1ae6b1bcd8774c7545149c0f7b3868b3748bf6e778d9e3bb304f7030863a6`.

### 8.4 How to call the model

The annotator is a model other than the one that proposed the categories. Use the same model and effort in both steps and in every run.

- Send one request to the Anthropic Messages API per conflict and step, through the official Python SDK (`anthropic` 1.15.0), with the prompt of the step as the system prompt, marked for caching, and the conflict as the only message, with no history of another call.
- Give the model no tool, so that it cannot run code, read files or reach the web, and in particular cannot compute the similarities the package hides or read the sealed files.
- Constrain the answer to the JSON schema of the step and check it against the schema again. Fix the model and the effort in each request, refuse an answer from another model and allow no fallback model.
- Send no sampling parameter and no thinking parameter: the model accepts no temperature, and its thinking is always on, with its depth set by the effort. The outputs therefore vary between runs, and only the first run of a block counts (Section 9).
- Run the annotator on a block only after the coders' consensus labels of that block are recorded, so that its output cannot reach the human labels.
- When an answer is not accepted (a refusal, an answer cut at the output limit, an output off the schema), leave the conflict without a record while the others go on, try it again up to three times and log each failed call with its raw response.

Record, for each call, the model asked for and the model that answered, the effort, the version of the SDK, the message and request ids, the stop reason, the token counts with the cache, the date, the raw response, and the SHA-256 of the instructions, of the package and, for the labeling, of the description, of the prompt and of the scheme.

## 9. Measure agreement and decide

### 9.1 Who is compared

The two coders label together, by consensus, so there is no agreement between them to report. The independent reading comes from the annotator, which does not take part in the discussion. Measure the agreement between the coders' consensus and the annotator's labels over every conflict of the block. The design trades the independence between two human coders for an agreement measured on 100% of the human-coded conflicts instead of a fraction.

### 9.2 Measure

Compute Cohen's kappa between the coders' consensus code and the annotator's code, one kappa per dimension, over the conflicts of one block, with the five datasets and the three bands together. Measure each block on its own, without adding blocks together. Beside each kappa, report:

- a 95% percentile bootstrap interval, with the resamples and the seed of the fixed values;
- the raw agreement;
- the worst-case kappa, in which every conflict without consensus between the coders counts as a disagreement (the human label becomes the coder's final reading that differs from the annotator's label, or the first coder's if both differ), with its own bootstrap interval;
- per category, the number of conflicts the coders gave it, the number the annotator gave it and the number both gave it;
- the number of conflicts with identical candidates, with an empty candidate and no empty version, and with FU, and the agreement on each group.

The main kappa leaves out the conflicts without consensus in its dimension, since they have two human readings and no single label to compare. If the annotator labels a block more than once, only its first run counts, and report the agreement of each later run with the first as a measure of stability.

### 9.3 Decision

The threshold is an observed kappa of 0.61, the lower limit of what Landis and Koch (1977) call substantial agreement. It must be reached in both dimensions, because the labeling at scale uses both.

| Observed kappa of the measured block | What happens |
|---|---|
| 0.61 or above in both dimensions | The annotator is approved, human coding stops, and the annotator labels every conflict of the three bands (Section 10) |
| Below 0.61, with a block still to code | The coders compare the block's labels with the annotator's, discuss the disagreements and correct the instructions without changing the scheme. That block leaves the kappa count, and the next block is coded by the coders and labeled with the corrected instructions |
| Below 0.61 at the third block | No labeling at scale. The analysis rests on the 150 human-coded conflicts, the kappas of all blocks are reported, and the attempt with the annotator is reported as a note on the method |

Report the kappa of every measured block, not only of the block that passed, with its interval. A kappa observed at 0.61 on 50 conflicts has a 95% interval of about 0.43 to 0.77 (simulated), so a block that passes near the threshold does not rule out an annotator of moderate agreement. Deciding by the observed value favors a block whose kappa is high by chance: in simulation, an annotator with a true kappa of 0.55 passes a block of 50 with a probability of 23%, and one of 0.50 with 10%.

Approval on block 1 is allowed. Block 1 is less independent than the later blocks, since the categories come from the coders' descriptions of its conflicts, but approving only from block 2 on would add up to 50 human-coded conflicts.

### 9.4 What goes into each count

| Conflict | Kappa | Frequencies from the coders' labels (outcome without approval) | Frequencies from the annotator's labels (labeling at scale) |
|---|---|---|---|
| From a block that counts | in | in | in, with the annotator's label |
| From a block used to correct the instructions | out | in | in, with the annotator's label |
| Without consensus between the coders, in that dimension | out | out | in, with the annotator's label |
| From the pilot | out | out | in, with the annotator's label |

In the labeling at scale, the frequencies use the annotator's label for every conflict, including those the coders labeled, so the frequencies come from a single instrument.

## 10. Label at scale

If the annotator is approved:

1. Give every conflict of the three bands a new identifier from a drawn permutation, with the seed of the labeling at scale, a new random order of its two candidates and a new package, built by the same functions as the packages of the sample.
2. Label the conflicts of the sample that are in the bands again, with all the others. Do not reuse the annotator's labels of the block that approved it.
3. Leave out a conflict whose package does not fit the model's context, and report it.
4. Run the annotator on every other conflict with the frozen instructions, as in Section 8.4.

The frequencies are then those of the bands of split 1, with no sampling margin. The human labels are the evidence for the annotator's labels, and the error left is the annotator's, which the agreement of Section 9 measures.

## 11. Application in this study

### 11.1 Dates

| Step | Date |
|---|---|
| Description of the pilot (Section 4) | 2026-10-01 |
| Joint description of block 1 (Section 5, step 1) | 2026-10-08 and 2026-10-12 |
| Two derivation calls (Section 5, step 4) | 2026-10-12 |
| Scheme frozen (Section 5, step 5) | 2026-10-19 |
| Consensus labels of the pilot and block 1 (Section 7) | 2026-10-23 |
| Annotator on the pilot and on block 1 (Section 8) | 2026-10-23 |
| Labeling at scale (Section 10) | 2026-10-24 |

The sessions of the coders were held in Brazilian Portuguese and transcribed automatically by Google Meet (Gemini). The transcripts hold the speech of the two authors and are not published. They are available from the authors on request.

### 11.2 Population, bands and sample

The population holds 4,413 conflicts: 549 in Dataset1, 1,719 in Dataset2Java, 545 in Dataset2C#, 1,208 in Dataset2JavaScript and 392 in Dataset2TypeScript. Of these, 45 are above SBCR's size limit: 20 in Dataset2Java, 7 in Dataset2C# and 18 in Dataset2JavaScript. The bands hold 1,985 conflicts:

| Dataset | Clear SBCR win | Clear MergeGen win | Near tie |
|---|---:|---:|---:|
| Dataset1 | 28 | 78 | 138 |
| Dataset2Java | 68 | 274 | 430 |
| Dataset2C# | 25 | 76 | 142 |
| Dataset2JavaScript | 48 | 195 | 302 |
| Dataset2TypeScript | 14 | 69 | 98 |
| Total | 183 | 692 | 1,110 |

In Dataset2C# the lower quartile of `|d|` is 0, so its near-tie band holds only exact ties. No conflict fell in two bands, and no cell had fewer than ten conflicts.

The draw defined the bands with an earlier implementation of the similarity, which removed spaces and line breaks and kept tabs. The bands of the table above use the similarity with all whitespace removed, and they differ from the bands of the draw in conflicts whose resolution is indented with tabs. Of the 160 drawn conflicts, 144 are in the bands of the table: the 10 of the pilot and 134 of the sample. Of the 50 conflicts of block 1, 43 are in them. All 50 count in the agreement of block 1, which compares two labels of the same conflict and does not depend on the band.

### 11.3 Agreement on block 1

Every conflict of the pilot and block 1 has a consensus code in both dimensions, so the worst-case kappas equal the main ones. The annotator, with instructions v1, reached the threshold on block 1 in both dimensions:

| Dimension | Agreements | Kappa | 95% interval |
|---|---:|---:|---|
| Merge characteristic | 49 of 50 | 0.966 | 0.888 to 1.000 |
| Candidate characteristic | 41 of 50 | 0.788 | 0.660 to 0.902 |

Human coding stopped after block 1, and blocks 2 and 3 were not coded. The coders' residual codes over block 1 were 0 of 50 in the merge dimension and 2 of 50 in the candidate dimension. The report of block 1, with the per-category counts, is in the replication package.

### 11.4 Labeling at scale

The new identifiers run from `S0001` to `S1985`. Six conflicts were left out, because their packages would hold more than 1,000,000 characters. All six are above SBCR's size limit, with versions of 1 to 3 million characters, and all are in the near-tie band. The annotator labeled the other 1,979, in four processes. Every one of the 3,958 calls was answered by `claude-fable-5-1` at its first attempt, and no conflict was left without a label.

## 12. What the replication package holds

The replication package holds this protocol, the frozen scheme, the derivation prompt and its output schema, and versions v0 and v1 of the annotator's instructions in the repository. The RQ4 archive holds the draw with its seed and its sealed output, the 160 packages of the pilot and the sample and the 1,979 packages of the labeling at scale, the coding sheet with the final codes of each conflict (the coders' consensus for the pilot and block 1, and the annotator's labels of block 1 and of the labeling at scale), the annotator's raw requests and responses for the runs of block 1 and of the labeling at scale, the two category proposals of the derivation with the model, effort and date of each call, and the agreement report of block 1.

Not published: the coding application, the transcripts of the authors' sessions, in their original and edited forms, and the scripts that prepared the derivation input from the transcripts and ran the derivation. The transcripts and these scripts are available together on request.
