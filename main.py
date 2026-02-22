import argparse

from ror2tools import export_items, generate_pool


def main():
    parser = argparse.ArgumentParser(description='Risk of Rain 2 toolset')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('export', help='Export item data from the wiki')
    sub.add_parser('generate', help='Generate a random item pool (uses data/config.json) - simple mode')
    build = sub.add_parser('build', help='Build a scored pool (style/size/synergy options)')
    build.add_argument('--style', help='Preferred playstyle to include')
    build.add_argument('--size', type=int, help='Number of items in pool')
    build.add_argument('--synergy-weight', type=float, default=0, help='Weight of synergy graph when scoring')
    desc = sub.add_parser('describe', help='Show description and tips for an item')
    desc.add_argument('item', help='Name of the item to describe')
    args = parser.parse_args()

    if args.command == 'export':
        export_items()
    elif args.command == 'generate':
        generate_pool()
    elif args.command == 'build':
        from ror2tools.generator import load_config
        cfg = load_config()
        if args.style:
            cfg['style'] = args.style
        if args.size is not None:
            cfg['size'] = args.size
        if args.synergy_weight:
            cfg['synergy_weight'] = args.synergy_weight
        generate_pool(cfg)
    elif args.command == 'describe':
        from ror2tools.utils import fetch_item_description, fetch_wiki_tips
        desc_text = fetch_item_description(args.item)
        tips_text = fetch_wiki_tips(args.item)
        print(f"{args.item}\n\nDescription:\n{desc_text}\n\nTips:\n{tips_text}")


if __name__ == '__main__':
    main()
