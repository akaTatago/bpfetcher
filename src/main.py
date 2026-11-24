import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from src.utils.csv_helper import load_books, save_results

from src.scrapers.wook import WookScraper
from src.scrapers.bertrand import BertrandScraper
from src.scrapers.fnac import FnacScraper
from src.scrapers.almedina import AlmedinaScraper

console = Console()

def main():
    parser = argparse.ArgumentParser(description='BPFetcher - Price comparison helper')

    parser.add_argument('--output', type=str, default='data/results.csv', help='CSV output file path')

    parser.add_argument('--stores', nargs='+', default=['all'], 
                        choices=['all', 'wook', 'bertrand', 'fnac', 'almedina'],
                        help='Choose bookstores being scraped (ex: --stores wook fnac)')
    
    parser.add_argument('--mode', type=str, default='isbn', choices=['isbn', 'text'],
                        help='Search mode: "isbn" (default) or "text" (Title + Author)')
    
    parser.add_argument('input_file', type=str, help='CSV input file path')
    
    args = parser.parse_args()

    console.print("\n[bold yellow]--- BPFetcher CLI ---[/bold yellow]")

    books = load_books(args.input_file, mode=args.mode)

    if not books:
        console.print("[bold red]Empty input file or missing required columns.[/bold red]")
        return

    fast_scrapers = []
    browser_scrapers = []

    SCRAPER_CLASSES = {
        "wook": WookScraper,
        "bertrand": BertrandScraper,
        "fnac": FnacScraper,
        "almedina": AlmedinaScraper
    }

    target_stores = list(SCRAPER_CLASSES.keys()) if 'all' in args.stores else args.stores

    for s in target_stores:
        if s in SCRAPER_CLASSES:
            try:
                instance = SCRAPER_CLASSES[s]()
                if s == "fnac":
                    browser_scrapers.append(instance)
                else:
                    fast_scrapers.append(instance)
            except Exception as e:
                console.print(f"[red]Failed to init {s}: {e}[/red]")

    all_active_scrapers = fast_scrapers + browser_scrapers
    names = [s.store_name for s in all_active_scrapers]

    console.print(f"Mode: [dodger_blue1]{args.mode.upper()}[/dodger_blue1]")
    console.print(f"Bookstores scraped: [dodger_blue1]{', '.join(names)}[/dodger_blue1]")
    
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

            max_threads = len(fast_scrapers) if len(fast_scrapers) > 0 else 1

            with ThreadPoolExecutor(max_workers=max_threads) as executor:

                for book in books:
                    label = book.get("Identifier" if args.mode == "isbn" else "Title", "")
                    progress.update(task, description=f"[dodger_blue1]{escape(str(label))}")
                    
                    book_results = [] 
                    
                    future_to_scraper = {}
                    
                    if args.mode == 'text':
                        title = book.get("Title", "")
                        author = book.get("Author", "")
                        if title and author:
                            for scraper in fast_scrapers:
                                future = executor.submit(scraper.search_by_text, title, author)
                                future_to_scraper[future] = scraper
                    else:
                        identifier = book.get("Identifier")
                        if identifier:
                            for scraper in fast_scrapers:
                                future = executor.submit(scraper.scrape_by_isbn, identifier)
                                future_to_scraper[future] = scraper

                    for future in as_completed(future_to_scraper):
                        scraper = future_to_scraper[future]
                        try:
                            data = future.result()
                            if data:
                                if isinstance(data, list):
                                    book_results.extend(data)
                                else:
                                    book_results.append(data)
                        except Exception as e:
                            console.print(f"[bold red]Error in scraper {scraper.store_name}: {e}[/bold red]")
                            console.print_exception()

                    for scraper in browser_scrapers:
                        try:
                            data = None
                            if args.mode == 'text':
                                title = book.get("Title", "")
                                author = book.get("Author", "")
                                if title and author:
                                    data = scraper.search_by_text(title, author)
                            else:
                                identifier = book.get("Identifier")
                                if identifier:
                                    data = scraper.scrape_by_isbn(identifier)
                            
                            if data:
                                if isinstance(data, list):
                                    book_results.extend(data)
                                else:
                                    book_results.append(data)
                        except Exception as e:
                            console.print(f"[bold red]Error in scraper {scraper.store_name}: {e}[/bold red]")
                            console.print_exception()

                    
                    if book_results:
                        for item in book_results:
                            row = book.copy()
                            row['Store'] = item.get('store')
                            row['Title Found'] = item.get('title_found')
                            row['Author Found'] = item.get('author_found')
                            row['Status'] = item.get('status', 'Unavailable')
                            row['Price'] = item.get('price')
                            row['Pages'] = item.get('pages')
                            row['On Sale'] = "Yes" if item.get('on_sale') else "No"
                            row['Link'] = item.get('link', '')
                            results.append(row)
                    else:
                        row = book.copy()
                        row['Store'] = 'N/A'
                        row['Title Found'] = ''
                        row['Author Found'] = ''
                        row['Status'] = 'Not found'
                        row['Price'] = None
                        row['Pages'] = None
                        row['On Sale'] = 'No'
                        row['Link'] = ''
                        results.append(row)

                    progress.advance(task)
                    
        completed = True

    except KeyboardInterrupt:
        console.print("\n[bold red]Process interrupted by user.[/bold red]")

    finally:
        # Save first: a failure while closing the browser must never lose the results.
        if results:
            if save_results(results, args.output):
                status = "[dodger_blue1]Done![/dodger_blue1]" if completed else "[yellow]Partial results saved.[/yellow]"
                console.print(f"\n{status} Output saved in: [underline]{args.output}[/underline]")
            else:
                console.print("\n[bold red]Saving output file error.[/bold red]")
        else:
            console.print("\n[yellow]No results to save.[/yellow]")

        for scraper in all_active_scrapers:
            try:
                scraper.close()
            except Exception as e:
                console.print(f"[red]Failed to close {scraper.store_name}: {e}[/red]")

if __name__ == "__main__":
    main()