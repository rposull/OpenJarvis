# Trivia Crossing

Cross-generational trivia for ages **16–70**: medium-to-challenging multiple-choice questions rated **4–10** across history, science, geography, movies & TV, music, sports, literature, food, technology, and general knowledge.

Easy 1–3 questions are omitted on purpose.

## Play

Serve the folder (browsers block local `fetch` of JSON from `file://`):

```bash
cd examples/trivia_game
python3 -m http.server 8765
```

Open [http://localhost:8765](http://localhost:8765).

## Question bank

`questions.json` is the source of truth. Each item has:

| Field | Meaning |
|---|---|
| `category` | Topic bucket |
| `difficulty` | Integer **4–10** (4–6 medium, 7–8 tough, 9–10 deep cuts) |
| `question` | Prompt |
| `choices` | Four options |
| `answer` | Zero-based index of the correct choice |
| `era_note` | Hint about cultural era / audience fit |

Mix eras so a teen who knows Kendrick and a grandparent who knows Mozart both get turns in the spotlight.
