"""Parse the manually saved wiki HTML to extract item images."""
import json
import re
from bs4 import BeautifulSoup

def parse_html():
    print("Reading HTML from extracted_manually_wiki.html...")
    with open('extracted_manually_wiki.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    image_cache = {}
    
    # Find all images with alt text (not backgrounds)
    for img in soup.find_all('img'):
        alt = img.get('alt', '')
        
        # Skip background images
        if alt.startswith('Bg') or not alt:
            continue
        
        # Get the item name from alt
        item_name = alt.strip()
        
        # Get the image URL - prefer data-src over src
        img_url = img.get('data-src') or img.get('src', '')
        
        if not img_url:
            continue
        
        # Clean the URL - remove scaling parameters
        img_url = re.sub(r'/scale-to-width-down/\d+', '', img_url)
        
        # Ensure it starts with https
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif not img_url.startswith('http'):
            continue
        
        # Store the image URL
        image_cache[item_name] = img_url
        print(f"  {item_name}: {img_url[:80]}...")
    
    return image_cache

def main():
    import os
    
    print("Parsing HTML for item images...")
    cache = parse_html()
    
    if not cache:
        print("\nNo images found!")
        return
    
    print(f"\nFound {len(cache)} item images from HTML")
    
    # Now load the items.csv to map to all item names
    import csv
    with open('data/items.csv', 'r', encoding='utf-8') as f:
        items = list(csv.DictReader(f))
    
    print(f"Have {len(items)} items in CSV")
    
    # Check which items are missing
    missing = []
    for item in items:
        name = item['Name']
        if name not in cache:
            missing.append(name)
    
    if missing:
        print(f"\nMissing {len(missing)} items from HTML:")
        for m in missing[:10]:
            print(f"  - {m}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
        print("(These items will have empty images - likely debug or consumed items)")
    
    # Save the cache
    os.makedirs('cache', exist_ok=True)
    with open('cache/item_images.json', 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(cache)} images to cache/item_images.json")
    print(f"  - All from HTML parsing")
    if missing:
        print(f"  - {len(missing)} items have no images (debug/consumed items)")

if __name__ == '__main__':
    main()
