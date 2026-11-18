# Prompt of the derivation of the RQ4 categories

The call that proposed the categories of the coding scheme from the transcripts of the authors' discussion of block 1. The system prompt is the text between the lines that open and close the prompt below, unchanged. The message held the transcripts of block 1, in Brazilian Portuguese, split by case under a header `## Case <id>`, with the passages that named an approach replaced by the line `[passage removed]`, and the authors' written note of each case, if any. The transcripts are not published and are available on request (`docs/rq4-coding-protocol.md`). The model, its effort and the dates of the call are in the coding protocol, and its outputs in the RQ4 archive. The answer was checked against the JSON schema below.

## Prompt

--- begin prompt ---

You will read transcripts of a coding session in which two software engineering researchers examined merge conflict cases together and described each one aloud. Your task is to propose a coding scheme from what they said: a small set of categories, each with a definition, that a coder could later use to label each case. You do not label the cases. You propose the categories, and the researchers review, change and approve them.

**The study**

Each case is one merge conflict from an open-source project. Two automatic approaches each produced a candidate resolution for the conflict. Each candidate was compared with the resolution the developers committed, by textual similarity computed on the text with all whitespace removed. The question the coding answers is why one candidate is closer to the developers' resolution than the other, in a given conflict, or, when the two are about equally close, what makes them so. The coding does not judge whether the code is correct or whether it works.

For each case the researchers saw the two conflicting versions (version 1 and version 2), the base version from which both descend, the developers' resolution, and the two candidates, called A and B in random order. They were not told which approach produced which candidate. They saw no similarity between a candidate and the resolution, only the similarity of the resolution with each version.

They read the cases in an application that marks tokens and shows no number. It marks the tokens each version added to the base or removed from it, the tokens that differ between the two versions and the tokens that differ between the two candidates. On request, it also marks the tokens of each candidate that differ from the resolution, where each token of the candidates and of the resolution comes from in the two versions, and the tokens that differ between any two texts of the case. When the researchers speak of colors, highlights or marked tokens, they are describing these marks.

**The transcripts**

The message holds the transcripts of the session, one part per case, each under a header `## Case <id>`. The speech is in Brazilian Portuguese and was transcribed automatically. Words can be wrong, technical terms are often misspelled or split, and turns can be cut. Read for what the researchers meant.

Under the transcript of some cases comes a short note in English that the researchers wrote during the session, after the line `Written note of the researchers:`. It is part of what they observed, like the speech. A line `[passage removed]` marks a passage taken out before you received the transcripts, because it was not about the case.

- "V1", "versão um" and "a esquerda" usually mean version 1, and "V2", "versão dois" and "a direita" version 2. "Esquerda" and "direita" sometimes mean candidate A and candidate B instead, as they were shown side by side. Decide from the context.
- The researchers sometimes speculate about which approach produced a candidate, or talk about the study, about the application itself (how it works, what it lacks) or about other matters. These passages are not observations about the case. Do not use them, and do not let a category depend on which approach produced a candidate. What the researchers see through the marks of the application is an observation about the case.
- The candidates were shown in a common layout, with line breaks and indentation redone by one rule. What the researchers say about layout, indentation or line breaks is not a difference between the candidates.

**What to propose**

- **Ground every category in the transcripts.** A category names a reason the researchers gave, or a pattern in what they observed, for one candidate being closer to the resolution than the other. Do not add categories from general knowledge of merge conflicts or merge tools that the transcripts do not support.
- **Keep the scheme compact.** Propose as few categories as the material supports. There is no target number. Merge two categories when a coder reading the description of a case could not reliably tell which one applies. Agreement between coders falls when categories are many and close to each other.
- **One dominant code per case.** Each case will receive exactly one code in each dimension, the category that explains most of the difference between the two candidates, and possibly a secondary one noted as free text. Write each definition so that the dominant category can be chosen: say what the category includes and where its boundary with the nearest other category lies.
- **No approach in a category.** No name or definition mentions an approach, a tool, or the letters A and B. A category describes what happened in the conflict and in the candidates, so that it can be assigned without knowing which approach produced which candidate.
- **Two structures.** The researchers' observations may mix two kinds of reason, a characteristic of the conflict and the way the candidate further from the resolution fails. The researchers decide whether the scheme separates the two, so propose two structures. The first has a single dimension, with one code per case. The second has two dimensions, one for the characteristic of the conflict and one for the failure of the candidate further from the resolution, with exactly one code per case in each. Then say which structure the transcripts support better, and why, with what the researchers observed. Two dimensions fit when most cases can be described by one code in each.
- **Categories already defined.** Do not propose these again, and do not define a category that overlaps them.
  - *No candidate*: at least one of the two candidates is empty. In the two-dimension structure, it belongs to the failure dimension.
  - *No difference between the candidates*: only in the two-dimension structure, in the failure dimension, for a case in which the two candidates have the same text, whitespace aside.
  - *No candidate clearly further from the resolution*: only in the two-dimension structure, in the failure dimension, for a case in which the two candidates have code and differ, but the reading of the case does not show which one is further from the resolution.
  - A residual category, for a case that no category fits, which the coder describes in free text. In the two-dimension structure, each dimension has its own.
- **Identical candidates.** Some cases have two candidates with the same text, whitespace aside. In the single-dimension structure, they are labeled with the categories you propose, by what the shared candidate does with the versions, the base and the resolution, so your categories must cover these cases too. In the two-dimension structure, they get *no difference between the candidates* in the failure dimension and one of your categories in the conflict dimension.
- **Cases with an empty candidate.** They get *no candidate*. In the single-dimension structure, ignore them when you build the categories. In the two-dimension structure, use them only for the conflict dimension.
- **Cases with no clear loser.** In the two-dimension structure, a case in which the researchers could not tell which candidate is further from the resolution gets *no candidate clearly further from the resolution* in the failure dimension and one of your categories in the conflict dimension. Use these cases only for the conflict dimension.

**Output**

A single JSON object, with these fields. Write in English, in plain sentences. Do not quote case identifiers anywhere in the output.

- `recommended`: `one` or `two`, the structure the transcripts support better.
- `recommendation_reason`: why, in a few sentences, with what the researchers observed.
- `cases_total`: how many cases the transcripts hold.
- `empty_candidate_cases`: how many cases have at least one empty candidate.
- `identical_candidate_cases`: how many cases have two candidates with code and the same text, whitespace aside.
- `one_dimension`: the single-dimension structure, an object with:
  - `categories`: its categories, each an object as described below.
  - `unfitted_cases`: how many cases, apart from those with an empty candidate, none of its categories fits.
  - `close_pairs`: pairs of its categories that coders could confuse, and what would separate them, or an empty list.
- `two_dimensions`: the two-dimension structure, an object with:
  - `conflict`: the dimension of the characteristic of the conflict, an object with `categories` and `unfitted_cases`, the number of cases none of its categories fits.
  - `failure`: the dimension of the failure of the candidate further from the resolution, an object with `categories`, `no_clear_further_cases`, the number of cases in which the researchers could not tell which candidate is further from the resolution, and `unfitted_cases`, the number of cases, apart from those with an empty candidate, identical candidates or no candidate clearly further, none of its categories fits.
  - `close_pairs`: pairs of categories of the same dimension that coders could confuse, and what would separate them, or an empty list.
- `notes`: anything that made the proposal uncertain, such as cases the researchers did not finish discussing or passages too garbled to read. An empty string if none.

Each category is an object with:

- `name`: a short name, a few words.
- `definition`: one or two sentences a coder can apply.
- `includes`: what a case must show to receive this category.
- `boundary`: the nearest other category of the same dimension and how to tell them apart.
- `cases`: how many cases of the transcripts this category would be the dominant code of.
- `evidence`: one or two short paraphrases, in English, of what the researchers observed that supports the category, without case identifiers.

--- end prompt ---

## JSON schema of the output

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["recommended", "recommendation_reason", "cases_total", "empty_candidate_cases", "identical_candidate_cases", "one_dimension", "two_dimensions", "notes"],
  "properties": {
    "recommended": {"type": "string", "enum": ["one", "two"]},
    "recommendation_reason": {"type": "string"},
    "cases_total": {"type": "integer", "minimum": 0},
    "empty_candidate_cases": {"type": "integer", "minimum": 0},
    "identical_candidate_cases": {"type": "integer", "minimum": 0},
    "one_dimension": {
      "type": "object",
      "additionalProperties": false,
      "required": ["categories", "unfitted_cases", "close_pairs"],
      "properties": {
        "categories": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["name", "definition", "includes", "boundary", "cases", "evidence"],
            "properties": {
              "name": {"type": "string"},
              "definition": {"type": "string"},
              "includes": {"type": "string"},
              "boundary": {"type": "string"},
              "cases": {"type": "integer", "minimum": 0},
              "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 2
              }
            }
          }
        },
        "unfitted_cases": {"type": "integer", "minimum": 0},
        "close_pairs": {
          "type": "array",
          "items": {"type": "string"}
        }
      }
    },
    "two_dimensions": {
      "type": "object",
      "additionalProperties": false,
      "required": ["conflict", "failure", "close_pairs"],
      "properties": {
        "conflict": {
          "type": "object",
          "additionalProperties": false,
          "required": ["categories", "unfitted_cases"],
          "properties": {
            "categories": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": ["name", "definition", "includes", "boundary", "cases", "evidence"],
                "properties": {
                  "name": {"type": "string"},
                  "definition": {"type": "string"},
                  "includes": {"type": "string"},
                  "boundary": {"type": "string"},
                  "cases": {"type": "integer", "minimum": 0},
                  "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 2
                  }
                }
              }
            },
            "unfitted_cases": {"type": "integer", "minimum": 0}
          }
        },
        "failure": {
          "type": "object",
          "additionalProperties": false,
          "required": ["categories", "no_clear_further_cases", "unfitted_cases"],
          "properties": {
            "categories": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": ["name", "definition", "includes", "boundary", "cases", "evidence"],
                "properties": {
                  "name": {"type": "string"},
                  "definition": {"type": "string"},
                  "includes": {"type": "string"},
                  "boundary": {"type": "string"},
                  "cases": {"type": "integer", "minimum": 0},
                  "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 2
                  }
                }
              }
            },
            "no_clear_further_cases": {"type": "integer", "minimum": 0},
            "unfitted_cases": {"type": "integer", "minimum": 0}
          }
        },
        "close_pairs": {
          "type": "array",
          "items": {"type": "string"}
        }
      }
    },
    "notes": {"type": "string"}
  }
}
```
