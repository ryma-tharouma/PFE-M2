import asyncio
import json
import re
import sys
import os
import aiohttp
from urllib.parse import urljoin
from playwright.async_api import async_playwright

OUTLOOK_WELCOME_URL = "https://learn.microsoft.com/fr-fr/troubleshoot/outlook/classic-outlook-windows-welcome"


def clean_applies_to(raw: str) -> str:
    cleaned = re.sub(
        r"^s[\u2019']applique\s+\u00e0\s*[:：]?\s*",
        "",
        raw.strip(),
        flags=re.IGNORECASE
    )
    cleaned = re.sub(
        r"^applies\s+to\s*[:：]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )
    return cleaned.strip().lower()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:60]


async def scrape_outlook_articles():
    """Expand all subcategory nodes in the Outlook sidebar and collect article links."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"\n{'='*60}")
        print(f"  Scraping Outlook sidebar")
        print(f"{'='*60}")

        await page.goto(OUTLOOK_WELCOME_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector(
            "li.tree-item[aria-expanded] > span.tree-expander",
            timeout=20000
        )
        await page.wait_for_timeout(500)
        print(f"  ✓ Page loaded and tree rendered")

        # Print all top-level categories so we can see the structure
        top_buttons = await page.query_selector_all(
            "li.tree-item[aria-expanded] > span.tree-expander"
        )
        print(f"  ✓ Found {len(top_buttons)} top-level categories")
        for btn in top_buttons:
            label = await btn.inner_text()
            print(f"    - {label.strip()}")

        # Expand ALL tree items that are collapsed (at any level)
        # We do multiple passes since expanding a node may reveal more collapsed children
        max_passes = 5
        for pass_num in range(1, max_passes + 1):
            collapsed = await page.query_selector_all(
                "li.tree-item[aria-expanded='false'] > span.tree-expander"
            )
            if not collapsed:
                print(f"  ✓ All nodes expanded after {pass_num - 1} pass(es)")
                break
            print(f"  ↻ Pass {pass_num}: expanding {len(collapsed)} collapsed node(s)...")
            for btn in collapsed:
                try:
                    await btn.click()
                    await page.wait_for_timeout(200)
                except Exception:
                    pass
            await page.wait_for_timeout(600)

        # Collect all leaf article links with their parent category label
        articles = await page.evaluate("""() => {
            const results = [];

            // Walk all tree-group uls — these contain the actual article links
            // Each is a child of a tree-item that has a label (the category)
            document.querySelectorAll('li.tree-item[aria-expanded]').forEach(categoryItem => {
                const expander = categoryItem.querySelector(':scope > span.tree-expander');
                if (!expander) return;
                const categoryLabel = expander.innerText.trim();

                // Find direct child tree-group
                const group = categoryItem.querySelector(':scope > ul.tree-group');
                if (!group) return;

                // Check if children are leaf links or nested categories
                group.querySelectorAll('a.tree-item.is-leaf').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const title = a.innerText.trim();
                    if (href && title) {
                        // Extract type from URL path
                        const match = href.match(/\\/troubleshoot\\/outlook\\/([^\\/]+)\\//);
                        const type = match ? match[1] : '';
                        results.push({ title, href, category: categoryLabel, type });
                    }
                });
            });

            return results;
        }""")

        await browser.close()

        # Normalize to fr-fr and deduplicate
        seen = set()
        normalized = []
        for a in articles:
            href = a["href"]
            if "/en-us/" in href:
                href = href.replace("/en-us/", "/fr-fr/")
            full_url = f"https://learn.microsoft.com{href}" if href.startswith("/") else href

            if full_url in seen:
                continue
            # Only keep actual troubleshoot/outlook articles
            if "/troubleshoot/outlook/" not in full_url:
                continue
            seen.add(full_url)

            en_href = a["href"]
            en_url = f"https://learn.microsoft.com{en_href}" if en_href.startswith("/") else en_href

            normalized.append({
                "sidebar_title": a["title"],
                "type": a["type"],
                "category": a["category"],
                "fr_url": full_url,
                "en_url": en_url,
            })

        # Summary by type
        from collections import Counter
        types = Counter(a["type"] for a in normalized)
        for t, count in sorted(types.items()):
            print(f"  ✓ {t}: {count} articles")
        print(f"  ✓ Total: {len(normalized)} articles")

        return normalized


async def download_image(session: aiohttp.ClientSession, img_url: str, save_path: str) -> bool:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://learn.microsoft.com/",
        }
        async with session.get(img_url, headers=headers) as resp:
            if resp.status == 200:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(await resp.read())
                return True
            else:
                print(f"      ✗ HTTP {resp.status} for {img_url}")
    except Exception as e:
        print(f"      ✗ Failed to download {img_url}: {e}")
    return False


async def scrape_article(page, url: str, article_index: int, image_session: aiohttp.ClientSession) -> dict:
    # Wait for full load
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await page.wait_for_selector(".content", timeout=30000)
    await page.wait_for_timeout(3000)

    # Remove UI artifacts
    await page.evaluate("""() => {
        document.querySelectorAll(`
            .code-block-header, .buttons-right, [data-bi-name="copy"],
            .alert-title .icon, .anchor-link, .heading-wrapper > a,
            .docon, button[data-dismiss], .share-facebook, .share-twitter,
            .share-linkedin, .share-email, .collection, .print-page,
            [data-copy-markdown], .thumb-rating-button, #site-user-feedback-footer,
            #right-rail-recommendations-mobile, #ms--additional-resources-mobile,
            #article-header-page-actions, #ms--inline-notifications,
            .table-wrapper .buttons-right, .table-wrapper [data-bi-name="copy"]
        `).forEach(el => el.parentNode?.removeChild(el));
    }""")

    # === EXTRACT PREAMBLE (full alert content) ===
    preamble = ""
    try:
        preamble = await page.evaluate("""() => {
            const alertDiv = document.querySelector('.content > .alert.is-info');
            if (!alertDiv) return '';
            const titleElem = alertDiv.querySelector('.alert-title');
            const title = titleElem ? titleElem.innerText.trim() : 'Remarque';
            const paragraphs = Array.from(alertDiv.querySelectorAll('p:not(.alert-title)'))
                .map(p => p.innerText.trim())
                .filter(p => p);
            const listItems = Array.from(alertDiv.querySelectorAll('ul li'))
                .map(li => '- ' + li.innerText.trim());
            let content = [...paragraphs, ...listItems].join('\\n');
            if (!content) return '';
            return '> **' + title + '**\\n> ' + content.replace(/\\n/g, '\\n> ');
        }""")
    except Exception as e:
        print(f"    Preamble extraction error: {e}")

    # === EXTRACT TITLE & APPLIES_TO ===
    title = ""
    applies_to = ""
    try:
        title = await page.eval_on_selector(".content h1", "el => el.innerText.trim()")
        raw_meta = await page.evaluate("""() => {
            const items = document.querySelectorAll('ul.metadata.page-metadata li, ul.page-metadata li');
            for (const li of items) {
                const text = li.innerText.trim();
                if (text.toLowerCase().includes("applique") || text.toLowerCase().includes("applies")) return text;
            }
            return '';
        }""")
        if raw_meta:
            applies_to = clean_applies_to(raw_meta)
    except Exception as e:
        print(f"    Title extraction error: {e}")

    # === ROBUST SECTION EXTRACTION ===
    raw_sections = await page.evaluate("""() => {
        const sections = [];
        const content = document.querySelector('.content');
        if (!content) return sections;

        // Find all h2 headings (both patterns)
        const headings = [];
        document.querySelectorAll('.heading-wrapper[data-heading-level="h2"]').forEach(wrapper => {
            const h = wrapper.querySelector('h2');
            if (h) headings.push(h);
        });
        document.querySelectorAll('.content > h2.heading-anchor, .content > a > h2').forEach(h => {
            if (!headings.includes(h)) headings.push(h);
        });
        document.querySelectorAll('h2[id^="option-"], h2[id^="restore-"], h2[id^="to-restore-"]').forEach(h => {
            if (!headings.includes(h) && h.closest('.content') && !h.closest('.heading-wrapper')) {
                headings.push(h);
            }
        });
        headings.sort((a, b) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);

        // Helper to convert inline elements to Markdown
        function inlineToMarkdown(el) {
            if (!el) return '';
            let res = '';
            for (const node of el.childNodes) {
                if (node.nodeType === 3) res += node.textContent;
                else if (node.nodeType === 1) {
                    const t = node.tagName?.toLowerCase();
                    const txt = node.innerText || '';
                    if (t === 'strong' || t === 'b') res += `**${txt}**`;
                    else if (t === 'em' || t === 'i') res += `*${txt}*`;
                    else if (t === 'code') res += `\`${txt}\``;
                    else if (t === 'a') {
                        const href = node.href || '';
                        res += href && !href.endsWith('#') ? `[${txt}](${href})` : txt;
                    } else if (t === 'br') res += '\\n';
                    else res += inlineToMarkdown(node);
                }
            }
            return res.trim();
        }

        // Convert a DOM element to Markdown
        function elementToMarkdown(el, insideNestedTable = false) {
            if (!el || !el.tagName) return { text: '', images: [] };
            const tag = el.tagName.toLowerCase();

            // Skip UI remnants
            if (el.classList?.contains('code-block-header') ||
                el.classList?.contains('buttons-right') ||
                el.querySelector?.('[data-bi-name="copy"]') ||
                el.classList?.contains('anchor-link')) {
                return { text: '', images: [] };
            }

            // --- ALERTS (except main preamble) ---
            if (el.classList?.contains('alert') && !el.classList?.contains('is-info')) {
                const titleEl = el.querySelector('.alert-title');
                const titleText = titleEl ? titleEl.innerText.replace(/[\\s\\n]+/g, ' ').trim() : 'Note';
                const bodyParts = [];
                for (const node of el.childNodes) {
                    if (node === titleEl || (titleEl && titleEl.contains(node))) continue;
                    if (node.nodeType === 3 && node.textContent.trim()) bodyParts.push(node.textContent.trim());
                    else if (node.nodeType === 1 && node.tagName === 'P' && !node.classList.contains('alert-title')) bodyParts.push(node.innerText.trim());
                    else if (node.nodeType === 1 && node.tagName === 'UL') {
                        const items = Array.from(node.querySelectorAll('li')).map(li => `- ${li.innerText.trim()}`);
                        bodyParts.push(items.join('\\n'));
                    }
                }
                const body = bodyParts.join(' ').replace(/\\n+/g, ' ');
                if (body) return { text: `> **${titleText}**\\n> ${body.replace(/\\n/g, '\\n> ')}`, images: [] };
                return { text: '', images: [] };
            }

            // --- CODE BLOCKS ---
            if (tag === 'pre') {
                const code = el.querySelector('code');
                const lang = code?.className?.match(/lang-(\\w+)/)?.[1] || el.getAttribute('data-language') || '';
                const codeText = code ? code.innerText.trim() : el.innerText.trim();
                const cleaned = codeText.replace(/^(PowerShell|Bash|CMD|JSON|Copier)\\s*\\n?/i, '').trim();
                if (cleaned) {
                    const langLabel = lang ? lang : '';
                    return { text: '```' + langLabel + '\\n' + cleaned + '\\n```\\n', images: [] };
                }
                return { text: '', images: [] };
            }

            // --- TABLES: skip nested tables to avoid duplication ---
            if (tag === 'table') {
                if (el.closest('td, th')) return { text: '', images: [] };
                const rows = el.querySelectorAll('tr');
                if (!rows.length) return { text: '', images: [] };
                let md = '';
                let hasHeader = false;
                for (let ri = 0; ri < rows.length; ri++) {
                    const cells = Array.from(rows[ri].querySelectorAll('th, td'))
                        .map(c => c.innerText.trim().replace(/\\n/g, ' ').replace(/\\|/g, '\\\\|').replace(/\\s+/g, ' '));
                    if (!cells.length) continue;
                    md += '| ' + cells.join(' | ') + ' |\\n';
                    if (ri === 0 && rows[ri].querySelector('th')) {
                        md += '| ' + cells.map(() => '---').join(' | ') + ' |\\n';
                        hasHeader = true;
                    }
                }
                if (!hasHeader && rows.length > 1) {
                    const cellCount = rows[0].querySelectorAll('td').length;
                    if (cellCount > 1) {
                        const parts = md.split('\\n').filter(l => l.trim());
                        parts.splice(1, 0, '| ' + Array(cellCount).fill('---').join(' | ') + ' |');
                        md = parts.join('\\n') + '\\n';
                    }
                }
                return { text: md ? md + '\\n' : '', images: [] };
            }

            // --- LISTS (FIXED: properly handle nested code blocks) ---
            if (tag === 'ul') {
                const items = Array.from(el.querySelectorAll(':scope > li')).map(li => {
                    let liContent = '';
                    for (const child of li.childNodes) {
                        if (child.nodeType === 3) {
                            const text = child.textContent.trim();
                            if (text) liContent += text + ' ';
                        } else if (child.nodeType === 1) {
                            const childTag = child.tagName.toLowerCase();
                            if (childTag === 'pre') {
                                if (liContent.trim()) liContent += '\\n\\n';
                                liContent += elementToMarkdown(child).text;
                                liContent += '\\n';
                            } else if (childTag === 'p' || childTag === 'div') {
                                liContent += elementToMarkdown(child).text + ' ';
                            } else {
                                liContent += elementToMarkdown(child).text;
                            }
                        }
                    }
                    return '- ' + liContent.trim();
                });
                if (items.length) return { text: items.join('\\n') + '\\n', images: [] };
                return { text: '', images: [] };
            }
            if (tag === 'ol') {
                const items = Array.from(el.querySelectorAll(':scope > li')).map((li, idx) => {
                    let liContent = '';
                    for (const child of li.childNodes) {
                        if (child.nodeType === 3) {
                            const text = child.textContent.trim();
                            if (text) liContent += text + ' ';
                        } else if (child.nodeType === 1) {
                            const childTag = child.tagName.toLowerCase();
                            if (childTag === 'pre') {
                                if (liContent.trim()) liContent += '\\n\\n';
                                liContent += elementToMarkdown(child).text;
                                liContent += '\\n';
                            } else if (childTag === 'p' || childTag === 'div') {
                                liContent += elementToMarkdown(child).text + ' ';
                            } else {
                                liContent += elementToMarkdown(child).text;
                            }
                        }
                    }
                    return `${idx + 1}. ` + liContent.trim();
                });
                if (items.length) return { text: items.join('\\n') + '\\n', images: [] };
                return { text: '', images: [] };
            }

            // --- BLOCKQUOTES ---
            if (tag === 'blockquote') {
                const lines = el.innerText.trim().split('\\n');
                if (lines.length) return { text: lines.map(l => `> ${l}`).join('\\n') + '\\n', images: [] };
                return { text: '', images: [] };
            }

            // --- PARAGRAPHS ---
            if (tag === 'p') {
                return { text: inlineToMarkdown(el) + '\\n', images: [] };
            }

            // --- IMAGES ---
            if (tag === 'img') {
                const src = el.getAttribute('src') || '';
                const alt = el.getAttribute('alt') || '';
                if (src && !src.startsWith('data:')) {
                    return { text: '', images: [{ src, alt }] };
                }
                return { text: '', images: [] };
            }

            // --- DIV WRAPPERS (recurse) ---
            if (tag === 'div') {
                if (el.classList?.contains('table-wrapper') || el.classList?.contains('inner-focus') || el.classList?.contains('content')) {
                    let text = '';
                    let allImages = [];
                    for (const child of el.children) {
                        const result = elementToMarkdown(child, insideNestedTable);
                        text += result.text;
                        allImages.push(...result.images);
                    }
                    return { text: text, images: allImages };
                }
            }

            // Default: extract inner text
            const txt = el.innerText?.trim();
            if (txt) return { text: txt + '\\n', images: [] };
            return { text: '', images: [] };
        }

        // Process each heading
        headings.forEach(h => {
            const header = h.innerText.trim();
            if (!header) return;
            const level = parseInt(h.tagName[1]) || 2;

            let contentParts = [];
            let allImages = [];
            let sibling = h.parentElement?.nextElementSibling || h.nextElementSibling;
            if (h.parentElement?.tagName === 'A') sibling = h.parentElement.nextElementSibling;

            while (sibling) {
                if (sibling.classList?.contains('heading-wrapper') && sibling.querySelector('h2')) break;
                if (sibling.tagName === 'H2' && !sibling.closest('.heading-wrapper')) break;
                if (sibling.tagName === 'A' && sibling.querySelector('h2')) break;
                if (sibling.classList?.contains('display-none-print') || sibling.id === 'article-metadata') {
                    sibling = sibling.nextElementSibling;
                    continue;
                }

                const result = elementToMarkdown(sibling);
                if (result.text) contentParts.push(result.text);
                allImages.push(...result.images);
                sibling = sibling.nextElementSibling;
            }

            if (header) {
                sections.push({
                    header,
                    level,
                    content: contentParts.join('\\n').trim(),
                    images: allImages
                });
            }
        });
        return sections;
    }""")

    # Post-process content (remove stray markers, normalize whitespace)
    for sec in raw_sections:
        if sec.get("content"):
            sec["content"] = re.sub(r'^(Copier|Agrandir le tableau|PowerShell|Bash|CMD|JSON)\s*$', '', sec["content"], flags=re.MULTILINE)
            lines = sec["content"].split('\n')
            cleaned = [l for l in lines if not ('\t' in l.strip() and l.strip().count('\t') >= 1 and not l.strip().startswith('|'))]
            sec["content"] = '\n'.join(cleaned)
            sec["content"] = re.sub(r'\\\\\|', '\\|', sec["content"])
            sec["content"] = re.sub(r'\n{3,}', '\n\n', sec["content"])

    # Download images and build sections
    sections = []
    image_dir = os.path.join("images", "outlook")
    os.makedirs(image_dir, exist_ok=True)

    for i, sec in enumerate(raw_sections, start=1):
        section_id = i
        header_slug = slugify(sec["header"])
        downloaded_images = []

        for j, img in enumerate(sec.get("images", []), 1):
            img_url = img["src"]
            if not img_url.startswith("http"):
                img_url = urljoin(url, img_url)
            img_url = img_url.split("?")[0]

            ext = os.path.splitext(img_url)[-1].lower() or ".png"
            if not ext.startswith("."):
                ext = ".png"
            filename = f"{article_index}_{section_id}_{header_slug}_{j}{ext}"
            save_path = os.path.join(image_dir, filename)

            # Run async download in sync context
            loop = asyncio.get_event_loop()
            ok = loop.run_until_complete(download_image(image_session, img_url, save_path))
            if ok:
                downloaded_images.append({
                    "file": os.path.join("images", "outlook", filename),
                    "alt": img["alt"],
                    "original_url": img_url,
                })
                print(f"      📷 {filename}")

        sections.append({
            "article_id": article_index,
            "section_id": section_id,
            "header": sec["header"],
            "level": sec["level"],
            "content": sec["content"],
            "images": downloaded_images,
        })

    return {
        "article_id": article_index,
        "title": title,
        "applies_to": applies_to,
        "preamble": preamble,
        "sections": sections,
    }


async def fetch_article_content(page, article: dict, index: int, total: int, image_session: aiohttp.ClientSession, retries: int = 3) -> dict:
    url = article["fr_url"]
    sidebar_title = article["sidebar_title"]

    print(f"\n  [{index}/{total}] {sidebar_title}")
    print(f"    URL : {url}")

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"    ↻ Attempt {attempt}/{retries}...")

            result = await scrape_article(page, url, index, image_session)

            if not result["sections"]:
                debug = await page.evaluate("""() => ({
                    content: !!document.querySelector('.content'),
                    headings: document.querySelectorAll('h2').length,
                    wrappers: document.querySelectorAll('.heading-wrapper').length
                })""")
                print(f"    ⚠️ Empty sections - page state: {debug}")
                raise ValueError(f"Empty sections — debug: {debug}")

            section_count = len(result["sections"])
            total_imgs = sum(len(s["images"]) for s in result["sections"])
            print(f"    ✓ Article ID: {result['article_id']}")
            print(f"    ✓ Title: {result['title'][:60]}...")
            print(f"    ✓ Sections: {section_count}")
            if total_imgs:
                print(f"    ✓ Images: {total_imgs} downloaded")

            return {
                "article_id": result["article_id"],
                "title": result["title"],
                "applies_to": result["applies_to"],
                "preamble": result["preamble"],
                "sections": result["sections"],
                "fetched_url": article["fr_url"],
            }

        except Exception as e:
            last_error = e
            print(f"    ✗ Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(attempt * 2)

    print(f"    ✗ FAILED after {retries} attempts")
    return None


async def main():
    articles = await scrape_outlook_articles()
    if not articles:
        sys.exit(1)

    total = len(articles)
    print(f"\n{'='*60}\n  Fetching {total} articles for Outlook\n{'='*60}")

    os.makedirs("data/scraped", exist_ok=True)
    os.makedirs(os.path.join("images", "outlook"), exist_ok=True)

    async with aiohttp.ClientSession() as image_session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            results = []
            for i, article in enumerate(articles, 1):
                data = await fetch_article_content(page, article, i, total, image_session, retries=3)
                # Only append successful results
                if data is not None:
                    results.append(data)
            await browser.close()

    output_file = "data/scraped/outlook.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    successful_count = len(results)
    failed_count = total - successful_count
    print(f"\n{'='*60}\n  Done! '{output_file}'")
    print(f"  ✓ {successful_count}/{total} succeeded")
    if failed_count > 0:
        print(f"  ✗ {failed_count} failed (not saved)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())