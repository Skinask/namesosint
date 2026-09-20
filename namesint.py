import os
import re
import sys
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Selenium imports for dynamic JavaScript handling
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class OSINTTargetChecker:
    def __init__(self, target_name: str, url: str, use_headless_browser: bool = False):
        self.target_name = target_name.strip()
        self.url = self._format_url(url)
        self.use_headless_browser = use_headless_browser
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        }

    @staticmethod
    def _format_url(raw_url: str) -> str:
        """Ensures the URL has a valid HTTP/HTTPS scheme."""
        raw_url = raw_url.strip()
        if not raw_url.startswith(('http://', 'https://')):
            return 'https://' + raw_url
        return raw_url

    def fetch_static_html() -> str:
        """Fetches HTML using requests for static websites."""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"[!] Standard HTTP fetch failed: {e}")
            return None

    def fetch_dynamic_html(self) -> str:
        """Renders JavaScript using Selenium headless Chrome driver."""
        if not SELENIUM_AVAILABLE:
            print("[!] Selenium/webdriver-manager is not installed. Falling back to static request.")
            return self.fetch_static_html()

        print("[*] Launching headless browser to execute JavaScript and dynamic content...")
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={self.headers['User-Agent']}")

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(25)
            driver.get(self.url)

            # Auto-scroll down to trigger lazy loading (comments, reactions, infinite scroll)
            print("[*] Scrolling page to reveal dynamic content and hidden comments...")
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            html_content = driver.page_source
            driver.quit()
            return html_content
        except Exception as e:
            print(f"[!] Browser automation error: {e}")
            print("[*] Attempting standard HTTP request fallback...")
            return self.fetch_static_html()

    def analyze(self):
        """Fetches webpage content and performs OSINT mention/probability analysis."""
        if self.use_headless_browser:
            html_content = self.fetch_dynamic_html()
        else:
            html_content = self.fetch_static_html()

        if not html_content:
            return None

        soup = BeautifulSoup(html_content, 'html.parser')

        # Regex for word boundary matching (case insensitive)
        pattern = re.compile(rf'\b{re.escape(self.target_name)}\b', re.IGNORECASE)

        # Content targets: text nodes, user fields, metadata, aria-labels
        matched_elements = []
        exact_matches_count = 0

        # 1. Search through standard textual elements
        text_tags = ['article', 'blockquote', 'p', 'span', 'div', 'li', 'section', 'a', 'h1', 'h2', 'h3']
        
        for tag in soup.find_all(text_tags):
            if tag.name in ['script', 'style']:
                continue

            text = tag.get_text(" ", strip=True)
            if not text:
                continue

            matches = pattern.findall(text)
            if matches:
                exact_matches_count += len(matches)

                # Classify the type of content area
                classes_ids = " ".join(tag.get('class', []) + [tag.get('id', '')]).lower()
                context_type = "General Body Text"

                if any(k in classes_ids for k in ['comment', 'reply', 'review', 'discussion']):
                    context_type = "Comment / Reply"
                elif any(k in classes_ids for k in ['post', 'entry', 'article', 'feed', 'tweet']):
                    context_type = "Post Content"
                elif any(k in classes_ids for k in ['reaction', 'like', 'author', 'user', 'profile', 'byline', 'avatar']):
                    context_type = "User Interaction / Reaction / Profile"

                # Avoid adding redundant duplicate strings from parent/child tags
                if not any(text[:100] in item['text'] for item in matched_elements):
                    matched_elements.append({
                        'type': context_type,
                        'tag': tag.name,
                        'text': text[:180] + ('...' if len(text) > 180 else '')
                    })

        # 2. Check interactive attributes (e.g. alt text, aria-labels for reactions)
        for tag in soup.find_all(True):
            aria_label = tag.get('aria-label', '')
            alt_text = tag.get('alt', '')
            title_text = tag.get('title', '')

            combined_attr = f"{aria_label} {alt_text} {title_text}".strip()
            if combined_attr and pattern.search(combined_attr):
                exact_matches_count += len(pattern.findall(combined_attr))
                matched_elements.append({
                    'type': "UI Attribute / Reaction / Alt Label",
                    'tag': tag.name,
                    'text': combined_attr[:180]
                })

        # Calculate Probability Score
        probability_score = 0
        if exact_matches_count > 0:
            probability_score = 35  # Base confidence score for finding matches
            
            # Frequency weight (up to +35%)
            frequency_weight = min(35, exact_matches_count * 7)
            
            # Context diversity weight (up to +29%)
            detected_types = set(item['type'] for item in matched_elements)
            context_weight = 0
            if "Post Content" in detected_types:
                context_weight += 12
            if "Comment / Reply" in detected_types:
                context_weight += 12
            if "User Interaction / Reaction / Profile" in detected_types or "UI Attribute / Reaction / Alt Label" in detected_types:
                context_weight += 10

            probability_score = min(99, probability_score + frequency_weight + context_weight)

        return {
            'target_name': self.target_name,
            'url': self.url,
            'probability_score': probability_score,
            'total_matches': exact_matches_count,
            'occurrences': matched_elements
        }


def main():
    print("=" * 65)
    print("        OSINT TARGET PROBABILITY & MENTION CHECKER      ")
    print("=" * 65)

    target_name = input("\n[+] Enter Target Name (e.g., 'John Doe' or 'Username'): ").strip()
    target_url = input("[+] Enter Webpage/Post URL to check: ").strip()

    if not target_name or not target_url:
        print("[!] Target name and URL are required.")
        sys.exit(1)

    print("\n[?] Select mode:")
    print("    1) Standard Fast Fetch (Best for news, blogs, standard HTML)")
    print("    2) Dynamic Headless Browser (Best for social media, dynamic comments, SPAs)")
    choice = input("Choice [1/2] (Default: 1): ").strip()

    use_browser = True if choice == "2" else False

    print(f"\n[*] Target  : {target_name}")
    print(f"[*] Analysis URL : {target_url}")
    print("[*] Running inspection...\n")

    checker = OSINTTargetChecker(target_name=target_name, url=target_url, use_headless_browser=use_browser)
    results = checker.analyze()

    if not results:
        print("[!] Failed to analyze the URL or content was unreachable.")
        return

    print("=" * 65)
    print("                       ANALYSIS RESULTS                        ")
    print("=" * 65)
    print(f" Target Name        : {results['target_name']}")
    print(f" Target URL         : {results['url']}")
    print(f" Total Matches      : {results['total_matches']}")
    print(f" Target Probability : {results['probability_score']}%\n")

    if results['occurrences']:
        print("--- Context Highlights ---")
        for idx, match in enumerate(results['occurrences'][:12], start=1):
            print(f"\n[{idx}] Category: {match['type']} (<{match['tag']}>)")
            print(f"    Content : \"{match['text']}\"")

        if len(results['occurrences']) > 12:
            print(f"\n... and {len(results['occurrences']) - 12} additional occurrences found.")
    else:
        print("[-] No mentions or context matches were found for this target name.")


if __name__ == "__main__":
    main()
                                   
