import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from src.errors import BlockedError, ScraperError
from src.models import BookOffer, Status
from src.scrapers import SCRAPERS
from src.utils.csv_helper import load_books, save_results, book_isbn, book_title, book_author

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description='BPFetcher - Price comparison helper')

    parser.add_argument('--output', type=str, default='data/results.csv', help='CSV output file path')

    parser.add_argument('--stores', nargs='+', default=['all'],
                        choices=['all', *SCRAPERS],
                        help='Choose bookstores being scraped (ex: --stores wook fnac)')

    parser.add_argument('--mode', type=str, default='isbn', choices=['isbn', 'text'],
                        help='Search mode: "isbn" (default) or "text" (Title + Author)')

    parser.add_argument('--no-fallback', action='store_true',
                        help='Do not try the other search mode (ISBN <-> Title + Author) when nothing is found')

    parser.add_argument('--no-interactive', action='store_true',
                        help='Never ask for help (CAPTCHA, IP block): treat it as a failure and move on')

    parser.add_argument('input_file', type=str, help='CSV input file path')

    return parser.parse_args()


def create_scrapers(store_names, interactive=True):
    """Start the requested scrapers. A store that fails to start is skipped."""
    scrapers = []
    for name in store_names:
        try:
            scraper = SCRAPERS[name]()
            scraper.interactive = interactive
            scrapers.append(scraper)
        except Exception as e:
            console.print(f"[red]Failed to init {name}: {e}[/red]")
    return scrapers


def _by_isbn(scraper, book):
    isbn = book_isbn(book)
    offer = scraper.scrape_by_isbn(isbn) if isbn else None
    return [offer] if offer else []


def _by_text(scraper, book):
    title, author = book_title(book), book_author(book)
    return scraper.search_by_text(title, author) if title and author else []


def scrape_book(scraper, book, mode, fallback=True):
    """Run one scraper on one book. Returns a list of BookOffer (empty if nothing was found).

    With `fallback`, if the first search mode finds nothing the other one is tried
    (ISBN <-> Title + Author), as long as the CSV has the data for it.
    """
    methods = [_by_isbn, _by_text]
    if mode == 'text':
        methods.reverse()

    for method in methods if fallback else methods[:1]:
        offers = method(scraper, book)
        if offers:
            return offers
    return []


def run_store(scraper, book, mode, fallback=True):
    """Run one store on one book. Always returns at least one BookOffer: the offers
    found, or a placeholder row saying why there is none (not found, blocked, error, skipped)."""
    name = scraper.store_name

    if scraper.disabled:
        return [BookOffer.missing(name, Status.SKIPPED)]

    try:
        offers = scrape_book(scraper, book, mode, fallback)

    except ScraperError as e:
        scraper.record_failure()
        console.print(f"[yellow]{name}: {escape(str(e))}[/yellow]")
        if scraper.disabled:
            console.print(f"[bold red]{name} disabled after {scraper.failures_in_a_row} failures in a row. "
                          f"Its remaining books will be marked as skipped.[/bold red]")
        return [BookOffer.missing(name, Status.BLOCKED if isinstance(e, BlockedError) else Status.ERROR)]

    except Exception as e:
        # A bug (e.g. the store changed its HTML), not a site problem: report it, don't disable the store
        console.print(f"[bold red]Error in scraper {name}: {escape(str(e))}[/bold red]")
        console.print_exception()
        return [BookOffer.missing(name, Status.ERROR)]

    scraper.record_success()
    return offers or [BookOffer.missing(name, Status.NOT_FOUND)]


def save_and_report(results, output_path, completed):
    if not results:
        console.print("\n[yellow]No results to save.[/yellow]")
    elif save_results(results, output_path):
        status = "[dodger_blue1]Done![/dodger_blue1]" if completed else "[yellow]Partial results saved.[/yellow]"
        console.print(f"\n{status} Output saved in: [underline]{output_path}[/underline]")
    else:
        console.print("\n[bold red]Saving output file error.[/bold red]")


def report_problems(results):
    """Say which stores could not be read, so a 'missing' price is not mistaken for 'not sold there'."""
    problems = {}
    for row in results:
        if row["Status"] in (Status.BLOCKED.value, Status.ERROR.value, Status.SKIPPED.value):
            problems.setdefault(row["Store"], Counter())[row["Status"]] += 1

    for store, counts in problems.items():
        details = ", ".join(f"{n} {status.lower()}" for status, n in counts.items())
        console.print(f"[yellow]{store} could not be read for some books ({details}). Check the Status column.[/yellow]")


def close_all(scrapers):
    for scraper in scrapers:
        try:
            scraper.close()
        except Exception as e:
            console.print(f"[red]Failed to close {scraper.store_name}: {e}[/red]")


def main():
    args = parse_args()

    console.print("\n[bold yellow]--- BPFetcher CLI ---[/bold yellow]")

    books = load_books(args.input_file, mode=args.mode)

    if not books:
        console.print("[bold red]Empty input file or missing required columns.[/bold red]")
        return

    store_names = list(SCRAPERS) if 'all' in args.stores else list(dict.fromkeys(args.stores))
    scrapers = create_scrapers(store_names, interactive=not args.no_interactive)

    if not scrapers:
        console.print("[bold red]No bookstore could be started.[/bold red]")
        return

    fast_scrapers = [s for s in scrapers if not s.requires_browser]
    browser_scrapers = [s for s in scrapers if s.requires_browser]
    fallback = not args.no_fallback

    console.print(f"Mode: [dodger_blue1]{args.mode.upper()}[/dodger_blue1]")
    console.print(f"Bookstores scraped: [dodger_blue1]{', '.join(s.store_name for s in fast_scrapers + browser_scrapers)}[/dodger_blue1]")

    results = []
    completed = False

    try:
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:

            task = progress.add_task("[dodger_blue1]Starting...", total=len(books))

            with ThreadPoolExecutor(max_workers=max(len(fast_scrapers), 1)) as executor:

                for book in books:
                    label = book.get("Identifier" if args.mode == "isbn" else "Title", "")
                    progress.update(task, description=f"[dodger_blue1]{escape(str(label))}")

                    # Request-based scrapers run in worker threads, starting right away...
                    jobs = [executor.submit(run_store, s, book, args.mode, fallback) for s in fast_scrapers]

                    # ...while browser scrapers run here, since a browser can't be shared between threads.
                    browser_offers = [o for s in browser_scrapers for o in run_store(s, book, args.mode, fallback)]
                    fast_offers = [o for job in jobs for o in job.result()]

                    # One row per offer found; a store with none gets a single row saying why
                    results.extend({**book, **offer.to_row()} for offer in fast_offers + browser_offers)

                    progress.advance(task)

        completed = True

    except KeyboardInterrupt:
        console.print("\n[bold red]Process interrupted by user.[/bold red]")

    finally:
        # Save first: a failure while closing the browser must never lose the results.
        save_and_report(results, args.output, completed)
        report_problems(results)
        close_all(scrapers)


if __name__ == "__main__":
    main()