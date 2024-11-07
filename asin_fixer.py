# ASIN Fixer for Kindle Colorsoft Cover Issues
# Since the new Kindle Colorsoft only loads book covers from Amazon servers, having the correct Kindle ASIN is crucial for covers to display properly.
# Calibre doesn’t always fetch the correct Kindle ASIN, which is the only way for the Kindle to download the cover.
# This tool extracts ASINs from Calibre `.opf` files, scrapes Amazon for Kindle variants, and updates the `.opf` files with the correct Kindle ASIN.
#
# How It Works:
# 1. Extract ASINs: Pulls existing ASINs from `.opf` files in your Calibre library.
# 2. Scrape Amazon: Uses Selenium to visit Amazon and scrape the correct Kindle ASIN.
# 3. Update Metadata: Writes the Kindle ASIN back into the `.opf` files for accurate cover fetching.
#
# How to Run:
# - Extract ASINs: `python asin_fixer.py extract <root_dir> <output_file>`
# - Scrape Amazon for Kindle ASINs: `python asin_fixer.py scrape <input_file>`
# - Update `.opf` files: `python asin_fixer.py update <mapping_file>`
# - Clean temporary data: `python asin_fixer.py clean <input_file>`
#
# This tool ensures your Kindle properly displays book covers by updating metadata with the right Kindle ASIN.

import os
import time
import xml.etree.ElementTree as ET
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import argparse
import tempfile

def fetch_kindle_asin(driver, old_asin):
    """
    Fetch the Kindle ASIN from Amazon using Selenium.

    Args:
        driver (webdriver.Chrome): The Selenium WebDriver instance.
        old_asin (str): The old ASIN to search for.

    Returns:
        str: The new Kindle ASIN if found, otherwise None.
    """
    url = f'https://www.amazon.com/dp/{old_asin}'
    
    print(f"Accessing URL: {url}")
    driver.get(url)
    
    print("Fetched URL")
    
    try:
        print("Waiting for page load...")
        # Wait for the Kindle Format span to be present
        WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, "//span[@aria-label='Kindle Format:']")))
        print("Looking for ASIN")
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        kindle_span = soup.find('span', {'aria-label': 'Kindle Format:'})

        if kindle_span:
            print("Found Kindle Format span")
            slot_title_span = kindle_span.find_parent('span', class_='slot-title')
            if slot_title_span:
                print("Found slot title span")
                parent_anchor = slot_title_span.find_parent('a', href=True)
                if parent_anchor and '/dp/' in parent_anchor['href']:
                    href = parent_anchor['href']
                    new_asin = href.split('/dp/')[1].split('/')[0]
                    print(f"Extracted new ASIN: {new_asin}")
                else:
                    print("No valid parent anchor found or href does not contain '/dp/'. Assuming the Kindle variant is already selected.")
                    new_asin = old_asin
                    print(f"Using old ASIN as new ASIN: {new_asin}")
            else:
                print("No slot title span found")
                new_asin = None
        else:
            print("The book does not seem to have a Kindle variant.")
            new_asin = None
    except Exception as e:
        print("The book does not seem to have a Kindle variant.")
        new_asin = None

    return new_asin

def update_amazon_ids(input_file):
    """
    Update the input file with new Kindle ASINs from Amazon.

    Args:
        input_file (str): File containing old AMAZON IDs and paths.
    """
    options = Options()
    # options.add_argument('--headless')  # Uncomment this line to run in headless mode
    options.add_argument("--window-size=1920,1200")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    temp_file_path = f"{input_file}.tmp"
    try:
        with open(input_file, 'r') as f:
            lines = f.readlines()

        mappings = {}
        updated_lines = []
        captcha_solved = False
        for line in lines:
            old_asin, file_path_and_new_asin = line.strip().split(',', 1)

            if ',' in file_path_and_new_asin:
                file_path, new_asin = file_path_and_new_asin.rsplit(',', 1)
            else:
                file_path = file_path_and_new_asin
                # If CAPTCHA has not been solved yet, wait for user input
                if not captcha_solved:
                    driver.get(f'https://www.amazon.com/dp/{old_asin}')
                    print("Please complete the captcha if required. Press Enter to continue after completing the captcha...")
                    input()  # Wait for user input to continue after CAPTCHA
                    captcha_solved = True
                new_asin = fetch_kindle_asin(driver, old_asin)
                print("Waiting for 3 seconds before the next request...")
                time.sleep(3)  # Allow the page to load
            
            if new_asin:
                mappings[old_asin] = new_asin
                new_line = f'{old_asin},"{file_path}",{new_asin}\n'
                updated_lines.append(new_line)
                print(f"Appending updated line: {new_line.strip()}")
                print(f"Fetched new ASIN for {old_asin}: {new_asin}")
            else:
                updated_lines.append(line)
                print(f"Failed to fetch new ASIN for {old_asin}")

            # Write intermediate results to a temp file
            with open(temp_file_path, 'w') as temp_file:
                temp_file.writelines(updated_lines)

        with open(input_file, 'w') as f:
            f.writelines(updated_lines)
        print("Finished updating file")
    finally:
        driver.quit()
        # Remove temp file after completion
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

def update_opf_files(mapping_file):
    """
    Update the .opf files with new ASINs based on the mapping file.

    Args:
        mapping_file (str): File containing the old and new AMAZON ID mappings.
    """
    ns = {
        'dc': 'http://purl.org/dc/elements/1.1/',
        'opf': 'http://www.idpf.org/2007/opf'
    }

    id_mapping = {}
    with open(mapping_file, 'r') as f:
        for line in f:
            parts = line.strip().split(',"')
            if len(parts) == 2:  # Only consider lines that have new ASIN mappings
                old_id, file_path_and_new_id = parts
                file_path, new_id = file_path_and_new_id.rsplit('"', 1)
                id_mapping[old_id] = (file_path, new_id)

    for old_id, (file_path, new_id) in id_mapping.items():
        if not new_id:  # Skip if new_id is None or empty
            continue
        
        tree = ET.parse(file_path)
        root = tree.getroot()
        amazon_identifier = root.find(".//dc:identifier[@opf:scheme='AMAZON']", ns)
        if amazon_identifier is not None:
            amazon_identifier.text = new_id
            tree.write(file_path, encoding='utf-8', xml_declaration=True)
            print(f"Updated {file_path} with new AMAZON ID: {new_id}")

def remove_lines_and_trailing_commas(input_file):
    """
    Remove lines with new ASINs and trailing commas from the input file.

    Args:
        input_file (str): File containing old and new AMAZON IDs and paths.
    """
    with open(input_file, 'r') as f:
        lines = f.readlines()

    remaining_lines = []
    for line in lines:
        parts = line.strip().split(',"')
        if len(parts) == 2:  # Check if there is a new ASIN
            old_id, file_path_and_new_id = parts
            file_path, new_id = file_path_and_new_id.rsplit('"', 1)
            if not new_id:  # Keep the line if new_id is empty
                remaining_lines.append(f'{old_id},"{file_path}"\n')
        else:
            remaining_lines.append(line.strip().rstrip(',') + '\n')

    with open(input_file, 'w') as f:
        f.writelines(remaining_lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='This tool lets you extract ASINs ("amazon" identifiers) for your books from the Calibre metadata, scrape Amazon for their Kindle equivalents, and update them in your metadata files.')
    subparsers = parser.add_subparsers(dest='command')

    extract_parser = subparsers.add_parser('extract', help='Extract ASINs from .opf files')
    extract_parser.add_argument('root_dir', nargs='?', default='.', help='Root directory to start the search (default: current directory)')
    extract_parser.add_argument('output_file', nargs='?', default='amazon_ids.txt', help='Output file for extracted ASINs (default: amazon_ids.txt)')

    scrape_parser = subparsers.add_parser('scrape', help='Scrape new ASINs from Amazon')
    scrape_parser.add_argument('input_file', help='File containing old AMAZON IDs and paths')

    update_parser = subparsers.add_parser('update', help='Update .opf files with new ASINs')
    update_parser.add_argument('mapping_file', help='File containing the old and new AMAZON ID mappings')

    clean_parser = subparsers.add_parser('clean', help='Remove lines with new ASINs and trailing commas')
    clean_parser.add_argument('input_file', help='File containing old and new AMAZON IDs and paths')

    args = parser.parse_args()

    if args.command == 'extract':
        extract_amazon_identifiers(args.root_dir, args.output_file)
    elif args.command == 'scrape':
        update_amazon_ids(args.input_file)
    elif args.command == 'update':
        update_opf_files(args.mapping_file)
    elif args.command == 'clean':
        remove_lines_and_trailing_commas(args.input_file)
    else:
        parser.print_help()
