import argparse

from ror2tools import export_items, generate_pool


def main():
    parser = argparse.ArgumentParser(description='Risk of Rain 2 toolset')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('export', help='Export item data from the wiki')
    sub.add_parser('generate', help='Generate a random item pool (uses data/config.json)')
    args = parser.parse_args()

    if args.command == 'export':
        export_items()
    elif args.command == 'generate':
        generate_pool()


if __name__ == '__main__':
    main()
