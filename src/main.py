import argparse
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from src.models import BookOffer
from src.scrapers import SCRAPERS
from src.utils.csv_helper import load_books, save_results

console = Console()


def parse_args():
    parser = argparse.ArgumentParser(description='BPFetcher - Price comparison helper')

    parser.add_argument('--output', type=str, default='data/results.csv', help='CSV output file path')

    parser.add_argument('--stores', nargs='+', default=['all'],
                        choices=['all', *SCRAPERS],
                        help='Choose bookstores being scraped (ex: --stores wook fnac)')

    parser.add_argument('--mode', type=str, default='isbn', choices=['isbn', 'text'],
                        help='Search mode: "isbn" (default) or "text" (Title + Author)')

    parser.add_argument('input_file', type=str, help='CSV input file path')

    return parser.parse_args()


def create_scrapers(store_names):
    """Start the requested scrapers. A store that fails to start is skipped."""
    scrapers = []
    for name in store_names:
        try:
            scrapers.append(SCRAPERS[name]())
        except Exception as e:
            console.print(f"[red]Failed to init {name}: {e}[/red]")
    return scrapers


def scrape_book(scraper, book, mode):
    """Run one scraper on one book. Always returns a list of BookOffer."""
    if mode == 'text':
        title, author = book.get("Title"), book.get("Author")
        data = scraper.search_by_text(title, author) if title and author else None
    else:
        identifier = book.get("Identifier")
        data = scraper.scrape_by_isbn(identifier) if identifier else None

    if not data:
        return []
    return data if isinstance(data, list) else [data]


def safe_scrape(scraper, book, mode):
    """scrape_book that reports an error instead of raising, so one store never stops the others."""
    try:
        return scrape_book(scraper, book, mode)
    except Exception as e:
        console.print(f"[bold red]Error in scraper {scraper.store_name}: {e}[/bold red]")
        console.print_exception()
        return []


def save_and_report(results, output_path, completed):
    if not results:
        console.print("\n[yellow]No results to save.[/yellow]")
    elif save_results(results, output_path):
        status = "[dodger_blue1]Done![/dodger_blue1]" if completed else "[yellow]Partial results saved.[/yellow]"
        console.print(f"\n{status} Output saved in: [underline]{output_path}[/underline]")
    else:
        console.print("\n[bold red]Saving output file error.[/bold red]")


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
    scrapers = create_scrapers(store_names)

    if not scrapers:
        console.print("[bold red]No bookstore could be started.[/bold red]")
        return

    fast_scrapers = [s for s in scrapers if not s.requires_browser]
    browser_scrapers = [s for s in scrapers if s.requires_browser]

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
                    jobs = [executor.submit(safe_scrape, s, book, args.mode) for s in fast_scrapers]

                    # ...while browser scrapers run here, since a browser can't be shared between threads.
                    browser_offers = [o for s in browser_scrapers for o in safe_scrape(s, book, args.mode)]
                    fast_offers = [o for job in jobs for o in job.result()]

                    # One row per offer found, or a single "Not found" row
                    offers = fast_offers + browser_offers or [BookOffer.not_found()]
                    results.extend({**book, **offer.to_row()} for offer in offers)

                    progress.advance(task)

        completed = True

    except KeyboardInterrupt:
        console.print("\n[bold red]Process interrupted by user.[/bold red]")

    finally:
        # Save first: a failure while closing the browser must never lose the results.
        save_and_report(results, args.output, completed)
        close_all(scrapers)


if __name__ == "__main__":
    main()