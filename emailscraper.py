from collections import deque 
import re
import urllib.parse
from bs4 import BeautifulSoup 
import requests
import time
import html 
import io 
import csv # <--- NEW IMPORT (for saving files)
try:
    from pypdf import PdfReader 
except ImportError:
    print("[!] Failed to import 'pypdf'. Please install: pip3 install pypdf")
    exit()

# --- NEW IMPORT ---
try:
    import tldextract # <--- NEW IMPORT (for subdomains)
except ImportError:
    print("[!] Failed to import 'tldextract'. Please install: pip3 install tldextract")
    exit()
# --- END NEW IMPORT ---


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36'
}

# Better regex
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# --- MAIN SCRIPT ---

user_input = str(input('[+] Enter URL: ')).strip()

if not user_input.startswith('http://') and not user_input.startswith('https://'):
    user_url = 'https://' + user_input
    print(f'[i] Assuming HTTPS. Using: {user_url}')
else:
    user_url = user_input

while True:
    try:
        limit_input = input('[+] How many pages to search (limit)?: ')
        max_urls = int(limit_input) 
        if max_urls > 0: break
        print('[!] Please enter a positive number.')
    except ValueError:
        print('[!] That is not a valid number. Please try again.')


urls = deque([user_url])
scraped_urls = set()
count = 0
start_time = time.time() # Start timer

# Use a DICTIONARY to track emails and their sources
emails = {}

# --- NEW FEATURE: Determine the root domain ---
# This is extracted once from the user input
try:
    root_domain_to_stay_on = tldextract.extract(user_url).registered_domain
    print(f"[i] Will only scan links on the root domain: '{root_domain_to_stay_on}' (including subdomains)")
except Exception as e:
    print(f"[!] Failed to extract root domain from {user_url}. Error: {e}")
    exit()
# --- END NEW FEATURE ---

try:
    # Main loop (one-by-one)
    while urls:
        count += 1
        if count > max_urls: 
            print(f'[!] Reached user-defined limit of {max_urls} pages.')
            break
        
        url = urls.popleft()
        if url in scraped_urls:
            continue
            
        scraped_urls.add(url) # Mark as "scraped"
        
        print(f'[{count}/{max_urls}] Processing: {url}')
        
        # "Polite" delay
        time.sleep(0.1) 
        
        try:
            response = requests.get(url, timeout=15, headers=HEADERS) # 15-second timeout
            response.raise_for_status() 
            
            # Get the final URL AFTER redirection
            final_url = response.url 
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            new_emails_set = set()
            
            # --- NEW FEATURE: Scan .txt pages ---
            if 'text/plain' in content_type:
                print(f'    [i] Scanning text file: {url}')
                text = response.text
                new_emails_set.update(EMAIL_REGEX.findall(text))
            # --- END NEW FEATURE ---
            
            # Process HTML Pages (main logic)
            elif 'text/html' in content_type:
                # De-obfuscation
                text = html.unescape(response.text)
                text = text.replace('[at]', '@').replace('(at)', '@')
                text = text.replace('[dot]', '.').replace('(dot)', '.')

                # A. Find emails in ALL text
                new_emails_set.update(EMAIL_REGEX.findall(text))

                # B. Find links (mailto emails AND http links)
                soup = BeautifulSoup(text, 'html.parser')
                
                for a in soup.find_all('a', href=True):
                    href = a['href'].strip()
                    
                    if href.startswith('mailto:'):
                        email = href.replace('mailto:', '').split('?')[0]
                        if email: 
                            new_emails_set.add(email)
                    
                    # Logic for regular links
                    elif href.startswith('/'):
                        link = urllib.parse.urljoin(final_url, href) 
                    elif not href.startswith('http'): 
                        link = urllib.parse.urljoin(final_url, href)
                    else:
                        link = href # Link is already absolute
                    
                    # --- NEW FEATURE: Scan linked .txt files ---
                    if link.endswith('.txt'):
                        try:
                            txt_response = requests.get(link, timeout=10, headers=HEADERS)
                            txt_response.raise_for_status()
                            new_emails_set.update(EMAIL_REGEX.findall(txt_response.text))
                        except Exception: pass # Ignore if fails
                    # --- END NEW FEATURE ---

                    # PDF scanning logic (still here)
                    elif link.endswith('.pdf'):
                        try:
                            pdf_response = requests.get(link, timeout=10, headers=HEADERS)
                            pdf_response.raise_for_status()
                            with io.BytesIO(pdf_response.content) as pdf_file:
                                reader = PdfReader(pdf_file)
                                pdf_text = ""
                                for page in reader.pages:
                                    page_text = page.extract_text()
                                    if page_text: pdf_text += page_text
                                new_emails_set.update(EMAIL_REGEX.findall(pdf_text))
                        except Exception: pass # Ignore if fails

                    # --- NEW FEATURE: Filter links using SUBDOMAIN ---
                    try:
                        # Extract the root domain from the new link
                        link_root_domain = tldextract.extract(link).registered_domain
                        
                        # Only add to queue IF the root domain is the same
                        if link_root_domain == root_domain_to_stay_on:
                            if link not in scraped_urls and link not in urls:
                                urls.append(link) # Add to queue
                    except Exception:
                        pass # Ignore broken links
                    # --- END NEW FEATURE ---

            # --- LOGIC FOR SAVING EMAILS ---
            if new_emails_set:
                new_emails_added_count = 0
                for email in new_emails_set:
                    if email not in emails:
                        emails[email] = url  # email is key, URL is value
                        new_emails_added_count += 1
                
                if new_emails_added_count > 0:
                    print(f'    [+] Found {new_emails_added_count} new emails on this page.')
            # --- END ---

        except requests.exceptions.ReadTimeout:
            print(f'    [!] Server was too slow to respond (timeout): {url}')
            continue
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e: 
            print(f'    [!] Failed to fetch URL: {url} | Error: {e}')
            continue
            
except KeyboardInterrupt: 
    print('\n[-] Process interrupted by user!')

# --- Finished ---
end_time = time.time()
print(f'\n[+] Process Finished in {end_time - start_time:.2f} seconds.')

# --- OUTPUT FORMAT (still the same) ---
print(f'\nList of Mails ({len(emails)} found):\n==================================')
for mail, source in sorted(emails.items()): 
    print(f'      {mail} (found at: {source})')
print('\n')

# --- NEW FEATURE: SAVING RESULTS TO CSV ---
if emails:
    output_filename = 'results.csv'
    print(f'[i] Saving results to {output_filename}...')
    try:
        with open(output_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['Email', 'Source_URL'])
            # Write data
            for mail, source in sorted(emails.items()):
                writer.writerow([mail, source])
        print(f'[+] Successfully saved to {output_filename}')
    except Exception as e:
        print(f'[!] Failed to save file: {e}')
print('\n')
# --- END NEW FEATURE ---
