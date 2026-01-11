#!/usr/bin/env python3
"""
DOORKICKER - A high-speed directory and file brute forcer
Author: xtony.exe
GitHub: https://github.com/xtony-exe/doorkicker
License: MIT
"""

import argparse
import asyncio
import aiohttp
import sys
import time
import os
from typing import List, Tuple, Optional, Generator, Dict, Any
import signal
import random
from collections import Counter
import ssl
from urllib.parse import urlparse
import gc

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    MAGENTA = '\033[95m'
    ORANGE = '\033[33m'
    BOLD = '\033[1m'
    END = '\033[0m'

class DoorKicker:
    def __init__(self, target: str, wordlist: List[str], extensions: List[str], 
                 threads: int, timeout: int, delay: float, user_agent: str,
                 output_file: str, verbose: bool, follow_redirects: bool,
                 check_common: bool = True, proxy: str = None,
                 show_all: bool = False):
        
        self.target = target.rstrip('/')
        if not self.target.startswith(('http://', 'https://')):
            self.target = f'http://{self.target}'
        
        parsed = urlparse(self.target)
        self.domain = parsed.netloc
        
        if not self.domain:
            raise ValueError(f"Invalid URL: {target}")
        
        self.wordlist = wordlist
        self.extensions = extensions
        self.threads = max(1, threads)
        self.timeout = max(1, timeout)
        self.delay = max(0.0, delay)
        self.user_agent = user_agent or self._random_agent()
        self.output_file = output_file
        self.verbose = verbose
        self.follow_redirects = follow_redirects
        self.check_common = check_common
        self.proxy = proxy
        self.show_all = show_all
        
        self.found_paths = []
        self.attempted = 0
        self.start_time = None
        self.successful_requests = 0
        self.failed_requests = 0
        
        self.interesting_codes = {200, 201, 204, 301, 302, 307, 308, 401, 403, 500}
        
        self.common_paths = [
            'admin', 'administrator', 'login', 'panel', 'dashboard', 'wp-admin',
            'backend', 'secure', 'private', 'hidden', 'api', 'docs', 'test',
            'config', 'backup', 'old', 'new', 'temp', 'tmp', 'cgi-bin',
            'wp-login.php', 'administrator/index.php', 'phpmyadmin', 'mysql',
            'db', 'database', 'sql', 'archive', 'logs', 'debug', 'console',
            'robots.txt', 'sitemap.xml', 'crossdomain.xml', 'phpinfo.php'
        ]
        
        self.semaphore = asyncio.Semaphore(self.threads)
        self.should_stop = False
        self.running_tasks = set()
        
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.ssl_context.options |= ssl.OP_NO_SSLv2
        self.ssl_context.options |= ssl.OP_NO_SSLv3
        self.ssl_context.options |= ssl.OP_NO_TLSv1
        
        self.last_progress_update = 0
        
    @staticmethod
    def _random_agent() -> str:
        agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'DOORKICKER/1.2.1 (+https://github.com/xtony-exe/doorkicker)',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0'
        ]
        return random.choice(agents)
    
    def _signal_handler_sync(self):
        """Signal handler for graceful shutdown"""
        if not self.should_stop:
            self.should_stop = True
    
    def _print_banner(self):
        banner = f"""
{Colors.BOLD}{Colors.RED}
╔══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                  ║
║   ██████╗  ██████╗  ██████╗ ██████╗ ██╗  ██╗██╗ ██████╗██╗  ██╗███████╗██████╗   ║
║   ██╔══██╗██╔═══██╗██╔═══██╗██╔══██╗██║ ██╔╝██║██╔════╝██║ ██╔╝██╔════╝██╔══██╗  ║
║   ██║  ██║██║   ██║██║   ██║██████╔╝█████╔╝ ██║██║     █████╔╝ █████╗  ██████╔╝  ║
║   ██║  ██║██║   ██║██║   ██║██╔══██╗██╔═██╗ ██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗  ║
║   ██████╔╝╚██████╔╝╚██████╔╝██║  ██║██║  ██╗██║╚██████╗██║  ██╗███████╗██║  ██║  ║
║   ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝  ║
║                                                                                  ║
║                     {Colors.WHITE}High-Speed Directory Bruteforcer v1.2.1{Colors.RED}                     ║
║                             {Colors.WHITE}Author: xtony.exe{Colors.RED}                                    ║
╚══════════════════════════════════════════════════════════════════════════════════╝
{Colors.END}
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Target:{Colors.WHITE} {self.target}
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Domain:{Colors.WHITE} {self.domain}
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Wordlist:{Colors.WHITE} {len(self.wordlist):,} paths
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Threads:{Colors.WHITE} {self.threads}
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Timeout:{Colors.WHITE} {self.timeout}s
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Delay:{Colors.WHITE} {self.delay}s
{Colors.CYAN}[{Colors.WHITE}*{Colors.CYAN}] Extensions:{Colors.WHITE} {', '.join(self.extensions) if self.extensions else 'none'}
{Colors.END}{'-'*60}
"""
        print(banner)
    
    def _generate_paths(self) -> Generator[str, None, None]:
        """Generate all paths to test with extensions"""
        yielded_paths = set()
        
        def add_path(path: str) -> Generator[str, None, None]:
            if path not in yielded_paths:
                yielded_paths.add(path)
                yield path
        
        if self.check_common:
            for base_path in self.common_paths:
                yield from add_path(f"/{base_path}")
                
                if self.extensions:
                    for ext in self.extensions:
                        if not base_path.endswith(f".{ext}"):
                            yield from add_path(f"/{base_path}.{ext}")
        
        for base_path in self.wordlist:
            base_path = base_path.strip()
            if not base_path:
                continue
                
            if not base_path.startswith('/'):
                base_path = f"/{base_path}"
            
            yield from add_path(base_path)
            
            if self.extensions:
                for ext in self.extensions:
                    if not base_path.endswith(f".{ext}"):
                        yield from add_path(f"{base_path}.{ext}")
    
    async def _check_path(self, session: aiohttp.ClientSession, path: str) -> Tuple[Optional[str], int, int]:
        """Check a single path asynchronously"""
        if self.should_stop:
            return (None, 0, 0)
        
        url = f"{self.target}{path}"
        
        if self.delay > 0:
            await asyncio.sleep(random.uniform(self.delay * 0.5, self.delay * 1.5))
        
        async with self.semaphore:
            try:
                timeout = aiohttp.ClientTimeout(
                    total=self.timeout,
                    connect=5,
                    sock_read=10
                )
                
                async with session.get(
                    url, 
                    timeout=timeout,
                    allow_redirects=self.follow_redirects,
                    ssl=self.ssl_context,
                    proxy=self.proxy
                ) as response:
                    
                    self.successful_requests += 1
                    
                    content_length = 0
                    try:
                        cl_header = response.headers.get('Content-Length')
                        if cl_header:
                            content_length = int(cl_header)
                    except (ValueError, TypeError):
                        pass
                    
                    if content_length == 0 and response.chunked:
                        content_length = -1
                    
                    elif content_length == 0 and response.status in self.interesting_codes:
                        try:
                            chunk = await response.content.read(512)
                            content_length = len(chunk)
                            if len(chunk) < 512:
                                if not response.content.at_eof():
                                    await response.content.read()
                            else:
                                content_length = -1
                                await response.release()
                        except:
                            content_length = 0
                            await response.release()
                    else:
                        await response.release()
                    
                    return (path, response.status, content_length)
                    
            except asyncio.TimeoutError:
                self.failed_requests += 1
                if self.verbose:
                    print(f"{Colors.YELLOW}[!] Timeout: {path}{Colors.END}")
            except aiohttp.ClientConnectorError as e:
                self.failed_requests += 1
                if self.verbose:
                    print(f"{Colors.RED}[!] Connection failed: {path} - {str(e)[:50]}{Colors.END}")
                if "Cannot connect to host" in str(e):
                    self.should_stop = True
            except aiohttp.ClientError as e:
                self.failed_requests += 1
                if self.verbose:
                    print(f"{Colors.RED}[!] Client error on {path}: {str(e)[:50]}{Colors.END}")
            except Exception as e:
                self.failed_requests += 1
                if self.verbose:
                    print(f"{Colors.RED}[!] Error on {path}: {str(e)[:50]}{Colors.END}")
        
        return (None, 0, 0)
    
    def _should_display(self, status: int) -> bool:
        """Determine if we should display this result"""
        if self.show_all:
            return True
        return status in self.interesting_codes
    
    def _format_result(self, path: str, status: int, length: int) -> str:
        """Format the result with colors based on status code"""
        timestamp = time.strftime("%H:%M:%S")
        
        if status == 200:
            color = Colors.GREEN
            symbol = "✓"
        elif status in (301, 302, 307, 308):
            color = Colors.BLUE
            symbol = "→"
        elif status == 403:
            color = Colors.YELLOW
            symbol = "🔒"
        elif status == 401:
            color = Colors.PURPLE
            symbol = "🔐"
        elif status == 500:
            color = Colors.RED
            symbol = "💥"
        elif status == 404:
            color = Colors.GRAY
            symbol = "✗"
        elif status == 201:
            color = Colors.GREEN
            symbol = "✓"
        elif status == 204:
            color = Colors.CYAN
            symbol = "○"
        else:
            color = Colors.CYAN
            symbol = "•"
        
        if length > 0:
            length_str = f" [{length:,} bytes]"
        elif length == -1:
            length_str = " [streaming]"
        else:
            length_str = ""
        
        return f"{color}[{symbol} {status}] {path}{length_str}{Colors.END}"
    
    def _update_progress(self, current: int, total: int, force: bool = False):
        """Update progress display"""
        current_time = time.time()
        
        if not force and current_time - self.last_progress_update < 0.1:
            return
        
        self.last_progress_update = current_time
        
        elapsed = current_time - self.start_time
        rate = current / elapsed if elapsed > 0 else 0
        interesting = len([p for p in self.found_paths if self._should_display(p[1])])
        
        progress = f"[{current:,}/{total:,}] {rate:.1f} req/sec | Found: {interesting}"
        sys.stdout.write(f"\r{Colors.CYAN}{progress:<70}{Colors.END}")
        sys.stdout.flush()
    
    def _display_result(self, path: str, status: int, length: int):
        """Display a single result"""
        print(f"  {self._format_result(path, status, length)}")
    
    def _save_progress(self):
        """Save found paths to output file"""
        if not self.output_file or not self.found_paths:
            return
        
        try:
            if os.path.dirname(self.output_file):
                os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(f"# DOORKICKER Results v1.2.1\n")
                f.write(f"# Target: {self.target}\n")
                f.write(f"# Scan started: {time.ctime(self.start_time)}\n")
                f.write(f"# Total attempted: {self.attempted}\n")
                f.write(f"# Total responses: {len(self.found_paths)}\n")
                f.write(f"{'='*60}\n\n")
                
                if self.show_all:
                    display_paths = self.found_paths
                else:
                    display_paths = [(p, s, l) for p, s, l in self.found_paths if self._should_display(s)]
                
                for path, status, length in sorted(display_paths, key=lambda x: (x[1], x[0])):
                    if length == -1:
                        length_str = "streaming"
                    else:
                        length_str = f"{length:,} bytes"
                    f.write(f"{status:3d} | {length_str:>12} | {self.target}{path}\n")
            
            if self.verbose and display_paths:
                print(f"{Colors.GREEN}[+] Saved {len(display_paths)} paths to {self.output_file}{Colors.END}")
        except Exception as e:
            print(f"\n{Colors.RED}[-] Failed to save results: {e}{Colors.END}")
    
    def _print_stats(self, interrupted: bool = False):
        """Print statistics"""
        sys.stdout.write('\r' + ' ' * 80 + '\r')
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        rate = self.attempted / elapsed if elapsed > 0 else 0
        
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        
        if interrupted:
            print(f"{Colors.YELLOW}[!] SCAN INTERRUPTED{Colors.END}")
        else:
            print(f"{Colors.GREEN}[✓] SCAN COMPLETED{Colors.END}")
        
        print(f"{Colors.CYAN}[*] Time elapsed:{Colors.WHITE} {elapsed:.2f}s")
        print(f"{Colors.CYAN}[*] Total requests:{Colors.WHITE} {self.attempted:,}")
        print(f"{Colors.CYAN}[*] Successful:{Colors.WHITE} {self.successful_requests:,}")
        print(f"{Colors.CYAN}[*] Failed:{Colors.WHITE} {self.failed_requests:,}")
        print(f"{Colors.CYAN}[*] Requests/sec:{Colors.WHITE} {rate:.1f}")
        
        if self.show_all:
            interesting_count = len(self.found_paths)
        else:
            interesting_count = sum(1 for _, status, _ in self.found_paths if status in self.interesting_codes)
        
        print(f"{Colors.CYAN}[*] Interesting paths found:{Colors.WHITE} {interesting_count}")
        print(f"{Colors.CYAN}[*] Total responses:{Colors.WHITE} {len(self.found_paths)}")
        
        if self.found_paths:
            status_counts = Counter([status for _, status, _ in self.found_paths])
            
            codes_to_show = sorted(status_counts.keys())
            if not self.show_all:
                codes_to_show = [code for code in codes_to_show if code in self.interesting_codes]
            
            if codes_to_show:
                print(f"{Colors.CYAN}[*] Status breakdown:{Colors.END}")
                for code in codes_to_show:
                    count = status_counts[code]
                    if code == 200:
                        color = Colors.GREEN
                    elif code in (301, 302, 307, 308):
                        color = Colors.BLUE
                    elif code == 403:
                        color = Colors.YELLOW
                    elif code == 401:
                        color = Colors.PURPLE
                    elif code == 500:
                        color = Colors.RED
                    elif code == 404:
                        color = Colors.GRAY
                    else:
                        color = Colors.CYAN
                    print(f"    {color}{code:3d}: {count:4d} paths{Colors.END}")
        
        if self.output_file:
            print(f"{Colors.CYAN}[*] Results saved to:{Colors.WHITE} {os.path.abspath(self.output_file)}")
    
    async def kick(self):
        """Main bruteforcing method"""
        self.start_time = time.time()
        self._print_banner()
        
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: self._signal_handler_sync())
        
        all_paths = list(self._generate_paths())
        total_paths = len(all_paths)
        
        if total_paths == 0:
            print(f"{Colors.RED}[-] No paths to test! Check your wordlist.{Colors.END}")
            return
        
        print(f"{Colors.CYAN}[*] Generated {Colors.WHITE}{total_paths:,}{Colors.CYAN} total paths to test{Colors.END}")
        if not self.show_all:
            print(f"{Colors.CYAN}[*] Showing only: 200, 201, 204, 3xx, 401, 403, 500 responses{Colors.END}")
            print(f"{Colors.CYAN}[*] Use --show-all to see all responses including 404{Colors.END}")
        print()
        
        connector = aiohttp.TCPConnector(
            limit=self.threads * 2,
            limit_per_host=self.threads,
            force_close=True,
            enable_cleanup_closed=True,
            use_dns_cache=True,
            ttl_dns_cache=300
        )
        
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'close',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache'
        }
        
        async with aiohttp.ClientSession(
            connector=connector,
            headers=headers,
            cookie_jar=aiohttp.DummyCookieJar()
        ) as session:
            
            try:
                print(f"{Colors.CYAN}[*] Testing base URL...{Colors.END}", end=' ')
                async with session.get(
                    self.target,
                    timeout=aiohttp.ClientTimeout(total=5),
                    ssl=self.ssl_context,
                    proxy=self.proxy
                ) as response:
                    if response.status == 200:
                        print(f"{Colors.GREEN}✓ {response.status}{Colors.END}")
                    elif response.status in self.interesting_codes:
                        print(f"{self._format_result('/', response.status, 0)}")
                    else:
                        print(f"{Colors.GRAY}{response.status}{Colors.END}")
                    await response.release()
            except Exception as e:
                print(f"{Colors.YELLOW}[!] Base URL error: {str(e)[:50]}{Colors.END}")
            
            print(f"{Colors.CYAN}[*] Starting scan...{Colors.END}")
            
            batch_size = min(self.threads * 10, 1000)
            paths_processed = 0
            
            for batch_start in range(0, total_paths, batch_size):
                if self.should_stop:
                    print(f"\n{Colors.YELLOW}[!] Stopping scan...{Colors.END}")
                    break
                
                batch_end = min(batch_start + batch_size, total_paths)
                batch_paths = all_paths[batch_start:batch_end]
                
                tasks = []
                for path in batch_paths:
                    if self.should_stop:
                        break
                    task = asyncio.create_task(self._check_path(session, path))
                    tasks.append(task)
                    self.attempted += 1
                
                for task in asyncio.as_completed(tasks):
                    if self.should_stop:
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        break
                    
                    try:
                        path, status, length = await task
                        
                        if path and status:
                            self.found_paths.append((path, status, length))
                            
                            if self._should_display(status):
                                self._display_result(path, status, length)
                    
                    except Exception as e:
                        if self.verbose:
                            print(f"{Colors.RED}[!] Task error: {e}{Colors.END}")
                
                paths_processed += len(batch_paths)
                self._update_progress(paths_processed, total_paths)
                
                tasks.clear()
                
                if batch_end % (batch_size * 5) == 0:
                    gc.collect()
            
            self._update_progress(paths_processed, total_paths, force=True)
            print()
        
        interesting_found = sum(1 for _, status, _ in self.found_paths if self._should_display(status))
        if interesting_found > 0:
            print(f"\n{Colors.GREEN}[+] Found {interesting_found} interesting paths{Colors.END}")
        
        self._save_progress()
        self._print_stats(interrupted=self.should_stop)

def load_wordlist(filepath: str) -> List[str]:
    """Load wordlist from file or use default"""
    if filepath:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                wordlist = []
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        wordlist.append(line)
                return wordlist
        except FileNotFoundError:
            print(f"{Colors.RED}[-] Wordlist file not found: {filepath}{Colors.END}")
            sys.exit(1)
        except Exception as e:
            print(f"{Colors.RED}[-] Error reading wordlist: {e}{Colors.END}")
            sys.exit(1)
    else:
        return [
            'admin', 'login', 'test', 'backup', 'config', 'api', 'docs',
            'wp-admin', 'server-status', 'phpinfo.php', 'robots.txt',
            'sitemap.xml', '.env', 'wp-login.php', 'readme.md'
        ]

def validate_proxy(proxy: str) -> Optional[str]:
    """Validate proxy URL format"""
    if not proxy:
        return None
    
    proxy = proxy.strip()
    if not proxy.startswith(('http://', 'https://', 'socks5://')):
        print(f"{Colors.YELLOW}[!] Proxy should start with http://, https://, or socks5://{Colors.END}")
        return None
    
    return proxy

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="DOORKICKER - High-speed directory bruteforcer v1.2.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{Colors.BOLD}{Colors.CYAN}Examples:{Colors.END}
  {Colors.WHITE}$ ./doorkicker.py -u https://target.com -w wordlist.txt{Colors.END}
  {Colors.WHITE}$ ./doorkicker.py -u target.com -w common.txt -t 100 -x php,html{Colors.END}
  {Colors.WHITE}$ ./doorkicker.py -u http://10.0.0.1 --delay 0.1{Colors.END}
  {Colors.WHITE}$ ./doorkicker.py -u https://example.com --show-all{Colors.END}
  {Colors.WHITE}$ ./doorkicker.py -u https://target.com --proxy http://127.0.0.1:8080{Colors.END}
        """
    )
    
    parser.add_argument('-u', '--url', required=True, help='Target URL (http/https)')
    parser.add_argument('-w', '--wordlist', help='Path to wordlist file')
    parser.add_argument('-t', '--threads', type=int, default=50, 
                       help='Number of concurrent threads (default: 50)')
    parser.add_argument('-x', '--extensions', help='File extensions to test (comma-separated: php,html,js)')
    parser.add_argument('-o', '--output', help='Output file to save results')
    parser.add_argument('--timeout', type=int, default=10, 
                       help='Request timeout in seconds (default: 10)')
    parser.add_argument('--delay', type=float, default=0, 
                       help='Delay between requests in seconds')
    parser.add_argument('--user-agent', help='Custom User-Agent string')
    parser.add_argument('--proxy', help='HTTP/HTTPS/SOCKS5 proxy')
    parser.add_argument('--no-common', action='store_true', 
                       help='Skip checking common paths first')
    parser.add_argument('--no-redirects', action='store_true', 
                       help='Do not follow redirects')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    parser.add_argument('--show-all', action='store_true',
                       help='Show all responses including 404')
    
    args = parser.parse_args()
    
    if args.threads < 1:
        print(f"{Colors.RED}[-] Threads must be at least 1{Colors.END}")
        sys.exit(1)
    
    if args.timeout < 1:
        print(f"{Colors.RED}[-] Timeout must be at least 1 second{Colors.END}")
        sys.exit(1)
    
    extensions = []
    if args.extensions:
        extensions = [ext.strip().lstrip('.') for ext in args.extensions.split(',') if ext.strip()]
    
    proxy = validate_proxy(args.proxy)
    
    wordlist = load_wordlist(args.wordlist)
    
    try:
        kicker = DoorKicker(
            target=args.url,
            wordlist=wordlist,
            extensions=extensions,
            threads=args.threads,
            timeout=args.timeout,
            delay=args.delay,
            user_agent=args.user_agent,
            output_file=args.output,
            verbose=args.verbose,
            follow_redirects=not args.no_redirects,
            check_common=not args.no_common,
            proxy=proxy,
            show_all=args.show_all
        )
        
        asyncio.run(kicker.kick())
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[!] Scan cancelled by user{Colors.END}")
        sys.exit(0)
    except ValueError as e:
        print(f"{Colors.RED}[-] Error: {e}{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}[-] Fatal error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
