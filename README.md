<div align="center">

# BPFetcher

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![curl-cffi](https://img.shields.io/badge/curl--cffi-HTTP-informational)
![patchright](https://img.shields.io/badge/patchright-browser-informational)
![pandas](https://img.shields.io/badge/pandas-CSV-informational)
![License](https://img.shields.io/badge/license-MIT-green)

A **web scraping** CLI tool for price comparison across Portuguese bookstores.

Scrapes book prices and availability from **Wook**, **Bertrand**, **Fnac** and **Almedina**, searching by ISBN or by title + author.

[Getting Started](#getting-started) •
[Usage](#usage) •
[Output](#output) •
[How it works](#how-it-works) •
[Architecture](#architecture)

</div>

## Getting Started

Requires **Python 3.10+**.

```bash
git clone https://github.com/akaTatago/BPFetcher.git
cd BPFetcher

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e .
```

Fnac is scraped with a real browser. If you do not have Google Chrome installed, download the bundled Chromium:

```bash
patchright install chromium
```

Run it:

```bash
bpfetcher input.csv --output results.csv
# or, without installing the command:
python -m src.main input.csv --output results.csv
```

<br />

## Usage

```
bpfetcher [--mode {isbn,text}] [--stores STORE [STORE ...]] [--output FILE]
          [--no-fallback] [--no-interactive] input_file
```

| Option             | Default            | Description                                                                          |
|--------------------|--------------------|--------------------------------------------------------------------------------------|
| `input_file`       | (required)         | CSV with the books to look up                                                        |
| `--mode`           | `isbn`             | `isbn` or `text` (title + author)                                                    |
| `--stores`         | `all`              | Any of `wook`, `bertrand`, `fnac`, `almedina`, or `all`                              |
| `--output`         | `data/results.csv` | Where to save the results                                                            |
| `--no-fallback`    | off                | Do not try the other search mode when nothing is found                               |
| `--no-interactive` | off                | Never ask for help (CAPTCHA, IP block): treat it as a failure and move on            |

### Input CSV

**ISBN mode** needs a column named `ISBN13` (or `ISBN`):

| ISBN13        | Title                  | Author        |
|---------------|------------------------|---------------|
| 9780316769174 | The Catcher in the Rye | J.D. Salinger |

**Text mode** needs `Title` and `Author` columns (`Titulo` and `Autor` also work).

Any other columns are kept and copied to the output. If the CSV has both an ISBN and a title + author, BPFetcher uses the other one as a fallback when the first finds nothing.

### Examples

```bash
bpfetcher books.csv --mode text --stores wook bertrand
bpfetcher books.csv --stores fnac --no-interactive     # unattended run
bpfetcher books.csv --no-fallback                      # ISBN only, no title + author retry
```

Press `Ctrl+C` at any time: the results collected so far are saved before exiting.

<br />

## Output

A CSV with your input columns followed by:

| Column         | Meaning                                                  |
|----------------|----------------------------------------------------------|
| `Store`        | Bookstore name                                           |
| `Title Found`  | Title as shown by the store                              |
| `Author Found` | Author(s) as shown by the store                          |
| `Status`       | See below                                                |
| `Price`        | Current price in €                                       |
| `Pages`        | Number of pages, when the store provides it              |
| `On Sale`      | `Yes` if the price is discounted                         |
| `Link`         | Link to the book on the store                            |

There is **one row per store per book**. In text mode a store can return several rows for the same book (one per matching edition).

| Status        | Meaning                                                              |
|---------------|----------------------------------------------------------------------|
| `Available`   | Found and can be bought                                              |
| `Unavailable` | Found but out of stock                                               |
| `Not found`   | The store was read correctly and does not list the book              |
| `Blocked`     | The store refused the request (HTTP 403/429, CAPTCHA, IP block)      |
| `Error`       | Network failure, timeout or unexpected error                         |
| `Skipped`     | Store disabled after 3 failed books in a row                         |

`Blocked`, `Error` and `Skipped` mean the book could not be checked there, not that the store does not sell it. A summary of these is printed at the end of each run.

<br />

## How it works

- **Request-based stores** (Wook, Bertrand, Almedina) use `curl-cffi` with browser impersonation and run concurrently, with a randomized delay between requests to the same domain.
- **Fnac** has anti-bot protection (DataDome), so it is driven with a real browser through `patchright`. The browser window opens visibly; if a CAPTCHA or IP block appears you are asked to solve it, unless you pass `--no-interactive`. Its session is stored in `.fnac_browser_profile/`.
- **Retries**: network errors, HTTP 5xx and 429 are retried up to 2 times with exponential backoff (and `Retry-After` is respected). 403 is not retried.
- **Smart matching**: results are validated with normalized titles and authors, so sequels, box sets and unrelated books are discarded.
- **Fallbacks**: if the ISBN finds nothing, title + author is tried (and vice versa); a store that fails repeatedly is skipped for the rest of the run.

<br />

## Architecture

```
BPFetcher/
├── pyproject.toml
├── input.csv                  # Example input
└── src/
    ├── main.py                # CLI entry point
    ├── models.py              # BookOffer, Status
    ├── errors.py              # BlockedError, NetworkError
    ├── scrapers/
    │   ├── base_scraper.py    # Shared search flow (template method)
    │   ├── wook.py
    │   ├── bertrand.py
    │   ├── fnac.py            # Browser-based (patchright)
    │   └── almedina.py
    └── utils/
        ├── scraping_helper.py # HTTP with retries, parsing helpers
        └── csv_helper.py      # CSV loading/saving
```

To add a store, subclass `BaseScraper`, implement its hooks (URLs and HTML selectors) and register it in `src/scrapers/__init__.py`.

<br />

## License

[MIT](LICENSE)