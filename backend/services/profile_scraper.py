import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from io import BytesIO
from typing import Optional, Dict, List, Tuple
from PIL import Image
import imagehash
import spacy

logger = logging.getLogger(__name__)

class ProfileScraper:
    def __init__(self):
        self._nlp = None
        
    def _get_nlp(self):
        if self._nlp is None:
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except Exception as e:
                logger.error(f"Failed to load spaCy model: {e}")
        return self._nlp

    async def fetch_profile_metadata(self, url: str) -> Dict[str, Optional[str]]:
        """
        Scrape a public profile URL for og:image (avatar) and og:description (bio).
        Uses non-intrusive headers to avoid blocks where possible.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, headers=headers, timeout=10.0)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Extract Avatar
                avatar_url = None
                og_image = soup.find("meta", property="og:image")
                if og_image:
                    avatar_url = og_image.get("content")
                    
                # Extract Bio
                bio = None
                og_desc = soup.find("meta", property="og:description")
                if og_desc:
                    bio = og_desc.get("content")
                    
                return {"avatar_url": avatar_url, "bio": bio}
                
        except Exception as e:
            logger.debug(f"Failed to scrape {url}: {e}")
            return {"avatar_url": None, "bio": None}

    async def fetch_and_hash_image(self, url: str) -> Optional[imagehash.ImageHash]:
        """Download an image and compute its perceptual hash (aHash)."""
        if not url:
            return None
            
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                resp.raise_for_status()
                
                # Run image processing in thread to avoid blocking event loop
                def process_image(data):
                    img = Image.open(BytesIO(data))
                    return imagehash.average_hash(img)
                    
                return await asyncio.to_thread(process_image, resp.content)
        except Exception as e:
            logger.debug(f"Failed to hash image at {url}: {e}")
            return None

    def compare_bios(self, bio1: str, bio2: str) -> float:
        """Compare two bio strings using semantic similarity (spaCy). Returns 0.0 to 1.0."""
        if not bio1 or not bio2:
            return 0.0
            
        nlp = self._get_nlp()
        if not nlp:
            # Fallback to simple jaccard if spacy fails
            set1 = set(bio1.lower().split())
            set2 = set(bio2.lower().split())
            if not set1 or not set2:
                return 0.0
            return len(set1.intersection(set2)) / len(set1.union(set2))
            
        doc1 = nlp(bio1.lower())
        doc2 = nlp(bio2.lower())
        
        # spaCy en_core_web_sm doesn't have true word vectors, so similarity is context-based
        # but good enough for lightweight comparison.
        try:
            sim = doc1.similarity(doc2)
            return max(0.0, min(1.0, float(sim)))
        except:
            return 0.0

profile_scraper = ProfileScraper()
