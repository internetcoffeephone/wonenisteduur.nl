# wonenisteduur.nl

Hugo static site advocating for grondwaardebelasting (land value tax) in the Netherlands.

## Build & Preview

- `hugo` — build the site to `public/`
- `hugo server` — local preview at http://localhost:1313

## Pre-commit

Always run `pre-commit run --all-files` before creating git commits. Fix any issues found before committing.

## Structure

- `content/_index.md` — homepage content (Dutch advocacy text)
- `content/politici/_index.md` — politicians contact page
- `layouts/` — custom Hugo templates (no theme)
- `assets/css/style.css` — all styles, processed via Hugo Pipes
- `static/` — favicon and other static assets
- `hugo.toml` — site configuration
