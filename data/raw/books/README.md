# raw/books/

Islamic books, organised by category. Each book lives in exactly one category
directory; a book spanning topics goes to its primary category.

| Category    | Contents                                                        |
| ----------- | --------------------------------------------------------------- |
| `aqeedah/`  | Creed and theology (`عقيدة`)                                    |
| `fiqh/`     | Jurisprudence and rulings (`فقه`)                               |
| `history/`  | Historical accounts and biographies of nations/events (`تاريخ`) |
| `other/`    | Anything that does not fit the above (dictionaries, general)    |
| `seerah/`   | Biography of the Prophet ﷺ (`سيرة`)                             |
| `tafsir/`   | Quranic exegesis (`تفسير`)                                      |

## Conventions

- One book per file (PDF preferred; EPUB/DOCX/TXT/HTML also accepted).
- Name files after the work, e.g. `tafsir-ibn-kathir-ar.pdf`.
- Author / edition / language metadata is captured by the pipeline from the
  file itself or user input during the metadata milestone — placeholders are
  fine at this stage.

## Rules

- Never modified in place; processed forms go to `data/processed/`.
- Only material you hold the right to process.