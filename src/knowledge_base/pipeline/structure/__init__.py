"""Document structure detection.

Consumes extraction output and detects chapters, sections, pages, paragraphs
and blocks using outline, font-size, pattern and basmala signals. Footnotes
are modelled as separate elements; uncertain signals carry review flags.
"""