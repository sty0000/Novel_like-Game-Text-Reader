# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a small Python command-line project for fetching raw story source text from PRTS wiki and exporting it for later novel-like game text processing.

The code currently has no declared dependency file (`requirements.txt`, `pyproject.toml`, or `package.json`). It uses only the Python standard library for CLI parsing, HTTP requests, JSON parsing, path handling, and text extraction.

## Common commands

Use commands from the repository root.

```bash
# Fetch one story by page title and write it to a file
python get_text.py "W2G/BEG" -o beg.txt

# Fetch one story by edit-page URL
python get_text.py "https://prts.wiki/index.php?title=W2G/BEG&action=edit" -o beg.txt

# Print fetched raw story source to stdout
python get_text.py "W2G/BEG"

# Open the interactive story picker and export the selected story
python story_reader.py

# List all selectable stories from the overview page
python story_reader.py --list

# Bypass selection and export a known story title or URL
python story_reader.py "W2G/BEG"
```

There is no test suite configured yet. For a lightweight smoke check after edits, run the relevant CLI help command and, if network access is appropriate, one focused fetch/list command:

```bash
python get_text.py --help
python story_reader.py --help
python story_reader.py --list
```

`story_reader.py --list` and story fetching contact `https://prts.wiki/api.php`; avoid using them as offline validation.

## Architecture

- `get_text.py` is the low-level fetcher module and CLI.
  - Accepts a PRTS page title, normal wiki URL, or edit-page URL.
  - Resolves titles from URLs, prefers MediaWiki API revision content via `extract_from_api()`, and falls back to parsing the edit page `<textarea id="wpTextbox1">` when needed.
  - Exposes `fetch_story_text()` as the main importable function and `get_story_source` as a backward-compatible alias.
  - Raises `CrawlError` for expected fetch/parse failures and returns CLI exit code `1` for handled crawl or JSON errors.

- `story_reader.py` is the user-facing picker/exporter.
  - Imports `fetch_story_text`, `fetch_text`, and `CrawlError` from `get_text.py`.
  - Loads the story catalog from the PRTS “剧情一览” page through the MediaWiki parse API, keeping namespace-0 links whose titles end in `/BEG`, `/END`, `/NBT`, `/AFTER`, `/BEFORE`, or `/STORY`.
  - Provides interactive filtering/selection in `choose_story_entry()` and writes selected stories to a default sanitized `.txt` filename unless `-o/--output` is provided.
  - Re-exports useful functions for a future GUI or other callers through `__all__`.

## Development notes

- Keep `get_text.py` independent and reusable; place catalog browsing or interactive behavior in `story_reader.py` rather than in the fetcher.
- Network functions should continue to raise `CrawlError` with user-readable Chinese messages for expected failures.
- Generated story `.txt` outputs are user artifacts; do not delete or overwrite them unless explicitly requested.
- The README includes a Conventional Commits guide. If committing changes, follow the documented `<type>(<optional scope>): <description>` style.
