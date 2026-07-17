# Trivia Crossing

Cross-generational trivia for ages **16–70**: 110 multiple-choice questions across history, science, geography, movies & TV, music, sports, literature, food, technology, and general knowledge.

## Play

Serve the folder (browsers block local `fetch` of JSON from `file://`):

```bash
cd examples/trivia_game
python -m http.server 8765
```

Open [http://localhost:8765](http://localhost:8765).

## Question bank

`questions.json` is the source of truth. Each item has:

| Field | Meaning |
|---|---|
| `category` | Topic bucket |
| `difficulty` | `easy` / `medium` / `hard` |
| `question` | Prompt |
| `choices` | Four options |
| `answer` | Zero-based index of the correct choice |
| `era_note` | Hint about cultural era / audience fit |

Mix eras so a teen who knows Taylor Swift and a grandparent who knows Vivaldi both get turns in the spotlight.
