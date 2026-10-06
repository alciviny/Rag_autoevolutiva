import logging
import asyncio
import re
import time
import ipaddress
import socket
import threading
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("alana.qa.crawler")

class WebCrawler:
    """
    Rastreador de Web Industrial.
    Realiza coleta de dados profunda respeitando robots.txt e limites de dominio.
    """
    
    def __init__(self, user_agent: str = "AlanaEngine/1.0", max_concurrent: int = 5):
        self.user_agent = user_agent
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self.robot_parsers: Dict[str, RobotFileParser] = {}
        
        # Limites de rastejo industrial
        self.max_depth = 2
        self.max_pages_per_domain = 5
        self.max_pages_total = 15
        self.delay = 1.0 
        self.last_request = {}
        self._lock = threading.Lock()
        self.max_response_bytes = 2 * 1024 * 1024
        
        self.blocked_ext = {'.jpg', '.png', '.css', '.js', '.pdf', '.zip', '.exe'}

    async def crawl(self, start_url: str) -> str:
        """Executa rastejo profundo e retorna o texto consolidado."""
        start_url = urldefrag(start_url)[0]
        if not self._is_public_url(start_url):
            raise ValueError("A URL inicial deve apontar para um host público HTTP/HTTPS.")
        start_host = urlparse(start_url).hostname
        visited = set()
        domain_counts = {}
        queue = [(start_url, 0)]
        all_text = []
        
        logger.info(f"🕷️ Iniciando rastejo profundo: {start_url}")
        
        while queue and len(visited) < self.max_pages_total:
            url, depth = queue.pop(0)
            if url in visited or depth > self.max_depth: continue
            host = urlparse(url).hostname
            if host != start_host or domain_counts.get(host, 0) >= self.max_pages_per_domain:
                continue
            
            try:
                data = await self._scrape_page(url)
                visited.add(url)
                domain_counts[host] = domain_counts.get(host, 0) + 1
                all_text.append(data['text'])
                
                if depth < self.max_depth:
                    for link in data['links'][:100]:
                        if self._is_valid(link, visited, start_host):
                            if len(queue) < 100:
                                queue.append((link, depth + 1))
            except Exception as e:
                logger.warning(f"Falha ao rastrear {url}: {e}")
                
        return " ".join(all_text)

    async def _scrape_page(self, url: str) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._scrape_sync, url)

    def _scrape_sync(self, url: str) -> Dict[str, Any]:
        if not self._is_public_url(url) or not self._robots_allowed(url):
            raise ValueError("Robots.txt bloqueou a URL ou o host não é público.")
        domain = urlparse(url).netloc.lower()
        with self._lock:
            wait = self.delay - (time.time() - self.last_request.get(domain, 0))
            if wait > 0:
                time.sleep(wait)
            self.last_request[domain] = time.time()
        body = self._fetch_public_page(url, domain)
        soup = BeautifulSoup(body, 'html.parser')
        for s in soup(["script", "style"]): s.decompose()
        
        text = re.sub(r'\s+', ' ', soup.get_text()).strip()
        links = [urljoin(url, a['href']) for a in soup.find_all('a', href=True)]
        
        return {'text': text, 'links': links}

    def _is_public_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return False
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if port not in (80, 443):
                return False
            try:
                addresses = {ipaddress.ip_address(parsed.hostname)}
            except ValueError:
                addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
            return bool(addresses) and all(address.is_global for address in addresses)
        except (ValueError, OSError):
            return False

    def _robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            parser = self.robot_parsers.get(origin)
        if parser is None:
            robots_url = f"{origin}/robots.txt"
            if not self._is_public_url(robots_url):
                return False
            parser = RobotFileParser(robots_url)
            try:
                response = requests.get(robots_url, headers={"User-Agent": self.user_agent}, timeout=(3, 5), allow_redirects=False, stream=True)
                if response.status_code == 404:
                    lines = []
                elif response.status_code == 200:
                    content = response.raw.read(256 * 1024 + 1)
                    if len(content) > 256 * 1024:
                        return False
                    lines = content.decode(response.encoding or "utf-8", errors="replace").splitlines()
                else:
                    return False
                parser.parse(lines)
            except requests.RequestException:
                return False
            finally:
                if "response" in locals():
                    response.close()
            with self._lock:
                self.robot_parsers[origin] = parser
        return parser.can_fetch(self.user_agent, url)

    def _fetch_public_page(self, url: str, allowed_host: str) -> str:
        current_url = url
        for _ in range(6):
            if not self._is_public_url(current_url) or urlparse(current_url).hostname != allowed_host:
                raise ValueError("Redirecionamento para host não autorizado.")
            response = requests.get(current_url, headers={"User-Agent": self.user_agent}, timeout=(3, 10), allow_redirects=False, stream=True)
            try:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Redirecionamento sem destino.")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                length = response.headers.get("Content-Length")
                if length and int(length) > self.max_response_bytes:
                    raise ValueError("Resposta excede o limite de 2 MB.")
                parts, total = [], 0
                for part in response.iter_content(64 * 1024):
                    total += len(part)
                    if total > self.max_response_bytes:
                        raise ValueError("Resposta excede o limite de 2 MB.")
                    parts.append(part)
                return b"".join(parts).decode(response.encoding or "utf-8", errors="replace")
            finally:
                response.close()
        raise ValueError("Limite de redirecionamentos excedido.")

    def _is_valid(self, url: str, visited: Set[str], start_host: Optional[str] = None) -> bool:
        url = urldefrag(url)[0]
        parsed = urlparse(url)
        if not self._is_public_url(url) or url in visited:
            return False
        if start_host and parsed.hostname != start_host:
            return False
        if any(parsed.path.lower().endswith(ext) for ext in self.blocked_ext):
            return False
        return True
