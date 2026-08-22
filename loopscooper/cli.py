import logging
import os
import sys
import tempfile
import warnings

import rich_click as click
from rich.logging import RichHandler
from rich.traceback import install as rich_traceback_handler
from rich_click.patch import patch as rich_click_patch
from yt_dlp.utils import YoutubeDLError

rich_click_patch()
# ruff: noqa: E402
from loopscooper import __version__
from loopscooper.console import rich_console
from loopscooper.handler import LoopHandler
from loopscooper.exceptions import AudioLoadError, LoopNotFoundError
from loopscooper.utils import download_audio


def resolve_filepath(filename: str) -> str:
    """Resolve the filepath by checking CWD first, then treating as given path."""
    if "/" in filename or filename.startswith("~"):
        # Treat as relative or absolute path
        import pathlib
        path = pathlib.Path(filename).expanduser()
        if path.exists():
            return str(path)
        return str(path)
    
    # Bare filename - check CWD first
    cwd_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(cwd_path):
        return os.path.abspath(cwd_path)
    
    # Not in CWD, return as-is so handler can try it
    return filename


@click.command(epilog="Full documentation and examples can be found at https://github.com/<user>/loopscooper")
@click.option("--debug", "-d", is_flag=True, default=False, help="Enables debugging mode.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enables verbose logging output.")
@click.version_option(__version__, prog_name="loopscooper", message="%(prog)s %(version)s")
@click.option("--url", type=click.STRING, default=None, help="Link to a YouTube video (or any stream supported by yt-dlp) to extract audio from.")
@click.argument("filename", required=False, default=None)
def cli_main(debug, verbose, url, filename):
    """A program for detecting and exporting seamless music loops for game audio."""
    if debug:
        os.environ["LOOPSCOOPER_DEBUG"] = "1"
        warnings.simplefilter("default")
        rich_traceback_handler(console=rich_console, suppress=[click])
    else:
        warnings.filterwarnings("ignore")

    if verbose:
        os.environ["LOOPSCOOPER_VERBOSE"] = "1"

    if verbose or debug:
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            format="%(message)s", level=level,
            handlers=[RichHandler(
                level=level, console=rich_console,
                rich_tracebacks=debug, show_path=debug,
                show_time=False, tracebacks_suppress=[click],
            )]
        )
    else:
        logging.basicConfig(
            format="%(message)s", level=logging.ERROR,
            handlers=[RichHandler(
                level=logging.ERROR, console=rich_console,
                show_time=False, show_path=False,
            )]
        )

    try:
        if url is not None:
            temp_dir = tempfile.mkdtemp()
            filepath = download_audio(url, temp_dir)
        elif filename is not None:
            filepath = resolve_filepath(filename)
            if not os.path.exists(filepath):
                # Check if it's an absolute/relative path that doesn't exist
                import pathlib
                path_obj = pathlib.Path(filepath)
                if path_obj.is_absolute() or "/" in filepath or filepath.startswith("~"):
                    rich_console.print(f"[red]Error: File not found: {filepath}[/]")
                else:
                    rich_console.print(f"[red]Error: \"{filename}\" not found in current directory.[/]")
                    rich_console.print(f"Please provide a valid file path (relative or absolute).")
                return
        else:
            rich_console.print("[red]Error: No audio file specified.[/]")
            rich_console.print("Usage: loopscooper <filename> or loopscooper --url <url>")
            return

        handler = LoopHandler(filepath=filepath)
        handler.run()

    except YoutubeDLError:
        pass
    except (AudioLoadError, LoopNotFoundError, Exception) as e:
        if "LOOPSCOOPER_DEBUG" in os.environ:
            rich_console.print_exception(suppress=[click])
        else:
            logging.error(e)


if __name__ == "__main__":
    cli_main()
