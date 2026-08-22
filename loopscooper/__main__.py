import logging

from loopscooper.cli import cli_main


def cli():
    try:
        cli_main()
    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    cli()
