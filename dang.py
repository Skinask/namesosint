import os
import re
import sys
import json
import time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

class AdvancedOSINTEngine:
    def __init__(self, target_name: str, url: str):
        self.raw_target_name = target_name.strip()
        self.url = self._format_url(url)
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        self.patterns = self._generate_name_patterns(self.raw_target_name)

    @staticmethod
    def _format_url(raw_url: str) -> str:
        """Formats URL and automatically converts Facebook links to mbasic for reliable headless fetching."""
        raw_url = raw_url.strip()
        if not raw_url.startswith(('http://', 'https://')):
            raw_url = 'https://' + raw_url
        
        if 'facebook.com' in raw_url or 'fb.com' in raw_url:
            raw_url = raw_url.replace('www.facebook.com', 'mbasic.facebook.com')
            raw_url = raw_url.replace('m.facebook.com', 'mbasic.facebook.com')

        return raw_url

    def _generate_name_patterns(self, name: str) -> list:
        """Generates OSINT variations and handles associated with the target name."""
        parts = [p.lower() for p in re.split(r'\s+', name) if p]
        patterns = []

        # 1. Full name exact match
        patterns.append({'type': 'Full Exact Name', 'regex': re.compile(rf'\b{re.escape(name)}\b', re.IGNORECASE), 'weight': 30})

        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            # 2. Combined Handles (e.g., markzuckerberg, mark_zuckerberg, mark.zuckerberg)
            handle_combinations = [
                f"{first}{last}",
                f"{first}_{last}",
                f"{first}\.{last}",
                f"{last}{first}",
                f"{first[0]}{last}",
                f"{first}{last[0]}"
            ]
            for handle in handle_combinations:
                patterns.append({
                    'type': f'Username Handle Match ({handle})',
                    'regex': re.compile(rf'\b{handle}\b', re.IGNORECASE),
                    'weight': 25
                })

        # 3. Individual First and Last Names
        for part in parts:
            if len(part) > 2:
                patterns.append({
                    'type': f'Name Segment ({part.capitalize()})',
                    'regex': re.compile(rf'\b{re.escape(part)}\b', re.IGNORECASE),
                    'weight': 10
                })

        return patterns

    def fetch_webpage(self) -> str:
        """Fetches page contents using mobile OSINT user agents."""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=12)
            if response.status_code == 200:
                return response.text
            else:
                print(f"[!] Target returned HTTP Status Code: {response.status_code}")
                return None
        except Exception as e:
            print(f"[!] Error connecting to target URL: {e}")
            return None

    def analyze_facebook(self) -> dict:
        """Scans Facebook / standard web page for targeted name patterns and context tags."""
        html_content = self.fetch_webpage()
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, 'html.parser')

        matches_found = []
        total_score = 0
        detected_patterns = set()

        # Text elements scan
        elements = soup.find_all(['article', 'blockquote', 'p', 'span', 'div', 'a', 'h1', 'h2', 'h3'])
        
        for tag in elements:
            text = tag.get_text(" ", strip=True)
            if not text or len(text) < 3:
                continue

            for p in self.patterns:
                found = p['regex'].findall(text)
                if found:
                    pattern_type = p['type']
                    if pattern_type not in detected_patterns:
                        total_score += p['weight']
                        detected_patterns.add(pattern_type)

                    classes_ids = " ".join(tag.get('class', []) + [tag.get('id', '')]).lower()
                    context = "General Context"
                    if any(k in classes_ids for k in ['comment', 'reply', 'review']):
                        context = "Comment / Reply"
                    elif any(k in classes_ids for k in ['post', 'feed', 'story']):
                        context = "Post Content"
                    elif any(k in classes_ids for k in ['actor', 'author', 'profile', 'user']):
                        context = "Profile / User ID"

                    if not any(text[:80] in item['snippet'] for item in matches_found):
                        matches_found.append({
                            'pattern': pattern_type,
                            'context': context,
                            'snippet': text[:150] + ('...' if len(text) > 150 else '')
                        })

        probability_score = min(99, total_score)

        return {
            'target_name': self.raw_target_name,
            'url': self.url,
            'probability': probability_score,
            'matches': matches_found
        }


class TikTokOSINTModule:
    """Interacts with TikTok public web endpoints to analyze user profiles and following networks."""
    def __init__(self, target_name: str):
        self.target_name = target_name
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }

    def fetch_tiktok_profile(self, tiktok_handle: str) -> dict:
        """Scans public TikTok profile for bio, following count, and follower metrics."""
        clean_handle = tiktok_handle.strip().lstrip('@')
        profile_url = f"https://www.tiktok.com/@{clean_handle}"
        
        print(f"\n[*] Requesting TikTok target data for: @{clean_handle}...")
        try:
            res = requests.get(profile_url, headers=self.headers, timeout=10)
            if res.status_code != 200:
                print(f"[!] Could not reach TikTok handle @{clean_handle} (Status: {res.status_code})")
                return None

            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Extract JSON payload from TikTok script container
            script_tag = soup.find('script', id='__UNIVERSAL_DATA_FOR_REHYDRATION__')
            bio = "N/A"
            nickname = clean_handle
            following_count = "N/A"
            followers_count = "N/A"

            if script_tag and script_tag.string:
                data = json.loads(script_tag.string)
                user_detail = data.get('__DEFAULT_SCOPE__', {}).get('webapp.user-detail', {}).get('userInfo', {})
                user_info = user_detail.get('user', {})
                stats = user_detail.get('stats', {})

                nickname = user_info.get('nickname', clean_handle)
                bio = user_info.get('signature', 'No Bio')
                following_count = stats.get('followingCount', 'Hidden')
                followers_count = stats.get('followerCount', 'Hidden')

            return {
                'handle': clean_handle,
                'nickname': nickname,
                'bio': bio,
                'following_count': following_count,
                'followers_count': followers_count,
                'url': profile_url
            }

        except Exception as e:
            print(f"[!] Failed to parse TikTok user: {e}")
            return None

    def correlate_accounts(self, fb_results: dict, tt_profile: dict) -> float:
        """Calculates cross-platform correlation score between Facebook target and TikTok target."""
        score = 0.0

        # Check name correlation
        target_tokens = set(self.target_name.lower().split())
        nickname_tokens = set(tt_profile['nickname'].lower().split())
        handle_tokens = set(tt_profile['handle'].lower().split('_'))

        if target_tokens.intersection(nickname_tokens):
            score += 45.0
        if target_tokens.intersection(handle_tokens):
            score += 35.0

        # Check if bio contains FB reference or name tokens
        if any(token in tt_profile['bio'].lower() for token in target_tokens):
            score += 20.0

        # Factor in FB target probability
        if fb_results and fb_results['probability'] > 40:
            score += (fb_results['probability'] * 0.2)

        return min(99.0, score)


def main():
    print("=" * 65)
    print("        PRO OSINT TARGET ENGINE & CROSS-PLATFORM CHECKER   ")
    print("=" * 65)

    target_name = input("\n[+] Enter Target Name (e.g., 'Mark' or 'John Doe'): ").strip()
    target_url = input("[+] Enter Webpage/Facebook Post URL to analyze: ").strip()

    if not target_name or not target_url:
        print("[!] Target name and URL are required.")
        sys.exit(1)

    print(f"\n[*] Target Name : {target_name}")
    print(f"[*] Target URL  : {target_url}")
    print("[*] Running pattern analysis engine...\n")

    engine = AdvancedOSINTEngine(target_name, target_url)
    fb_results = engine.analyze_facebook()

    if fb_results:
        print("=" * 65)
        print("                   FACEBOOK / WEB RESULTS                      ")
        print("=" * 65)
        print(f" Target Name        : {fb_results['target_name']}")
        print(f" Target URL         : {fb_results['url']}")
        print(f" Target Probability : {fb_results['probability']}%\n")

        if fb_results['matches']:
            print("--- Connected Pattern Highlights ---")
            for idx, item in enumerate(fb_results['matches'][:8], start=1):
                print(f"[{idx}] Pattern: {item['pattern']} | Context: {item['context']}")
                print(f"    Snippet: \"{item['snippet']}\"\n")
        else:
            print("[-] No direct matches or name patterns were found at this URL.")
    else:
        print("[!] Primary web analysis completed with no accessible data.")

    # TikTok Module Prompt
    print("=" * 65)
    ask_tt = input(f"\n[?] Do you want to find this person ({target_name}) on TikTok? [y/N]: ").strip().lower()

    if ask_tt in ['y', 'yes']:
        tt_handle = input("[+] Enter suspected TikTok username or handle (e.g., '@username'): ").strip()
        
        if tt_handle:
            tt_module = TikTokOSINTModule(target_name)
            tt_profile = tt_module.fetch_tiktok_profile(tt_handle)

            if tt_profile:
                correlation_score = tt_module.correlate_accounts(fb_results, tt_profile)

                print("\n" + "=" * 65)
                print("                  TIKTOK PROFILE & NETWORK DATA                 ")
                print("=" * 65)
                print(f" Handle           : @{tt_profile['handle']}")
                print(f" Display Name     : {tt_profile['nickname']}")
                print(f" Followers        : {tt_profile['followers_count']}")
                print(f" Following        : {tt_profile['following_count']}")
                print(f" Bio              : {tt_profile['bio']}")
                print(f" Profile URL      : {tt_profile['url']}")
                print("-" * 65)
                print(f" CROSS-PLATFORM CORRELATION PROBABILITY: {correlation_score:.1f}%")
                
                if correlation_score >= 60.0:
                    print(f"[!] HIGH CONFIDENCE: The Facebook post/account and @{tt_profile['handle']} on TikTok likely belong to the same person.")
                elif correlation_score >= 35.0:
                    print(f"[?] MODERATE CONFIDENCE: Possible connection found between accounts. Verify via bio or shared handles.")
                else:
                    print(f"[-] LOW CONFIDENCE: High likelihood these accounts are distinct or unlinked.")
            else:
                print("[-] Could not retrieve information for that TikTok profile.")
    
    print("\n[*] Analysis completed.")

if __name__ == "__main__":
    main()
              
