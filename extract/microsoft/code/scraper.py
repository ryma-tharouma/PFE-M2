import asyncio
import json
import re
import sys
import os
from playwright.async_api import async_playwright

BASE_URL = "https://learn.microsoft.com/fr-fr/troubleshoot/microsoft-365-apps/office-client-welcome"


async def scrape_app_articles(app_name: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"\n{'='*60}")
        print(f"  Scraping sidebar for app: '{app_name}'")
        print(f"{'='*60}")

        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector(".content", timeout=30000)
        await page.wait_for_timeout(2000)
        print(f"  ✓ Sidebar page loaded")

        category_buttons = await page.query_selector_all(
            "li.tree-item[aria-expanded] > span.tree-expander"
        )
        print(f"  ✓ Found {len(category_buttons)} categories")

        target_btn = None
        for btn in category_buttons:
            label = await btn.inner_text()
            if label.strip().lower() == app_name.lower():
                target_btn = btn
                break
        if not target_btn:
            for btn in category_buttons:
                label = await btn.inner_text()
                if app_name.lower() in label.strip().lower():
                    target_btn = btn
                    break

        if not target_btn:
            print(f"  ✗ Could not find '{app_name}'")
            await browser.close()
            return []

        parent = await target_btn.evaluate_handle("el => el.parentElement")
        if await parent.get_attribute("aria-expanded") == "false":
            await target_btn.click()
            await page.wait_for_selector("ul.tree-group a.tree-item", timeout=10000)
            await page.wait_for_timeout(300)

        links = await parent.eval_on_selector_all(
            "ul.tree-group a.tree-item",
            """els => els.map(el => ({
                title: el.innerText.trim(),
                href: el.getAttribute("href")
            }))"""
        )
        print(f"  ✓ Found {len(links)} articles")
        await browser.close()

        articles = []
        for link in links:
            href = link["href"]
            if href.startswith("/en-us/"):
                href = href.replace("/en-us/", "/fr-fr/", 1)
            full_url = f"https://learn.microsoft.com{href}" if href.startswith("/") else href
            articles.append({
                "sidebar_title": link["title"],
                "en_url": f"https://learn.microsoft.com{link['href']}" if link["href"].startswith("/") else link["href"],
                "fr_url": full_url,
            })
        return articles


def clean_applies_to(raw: str) -> str:
    cleaned = re.sub(r"^s[\u2019']applique\s+\u00e0\s*[:：]?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"^applies\s+to\s*[:：]?\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().lower()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:60]


async def scrape_article(page, url: str, app_name: str, article_index: int) -> dict:
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

        // Convert a DOM element to Markdown (no image extraction)
        function elementToMarkdown(el, insideNestedTable = false) {
            if (!el || !el.tagName) return { text: '' };
            const tag = el.tagName.toLowerCase();

            // Skip UI remnants
            if (el.classList?.contains('code-block-header') ||
                el.classList?.contains('buttons-right') ||
                el.querySelector?.('[data-bi-name="copy"]') ||
                el.classList?.contains('anchor-link')) {
                return { text: '' };
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
                if (body) return { text: `> **${titleText}**\\n> ${body.replace(/\\n/g, '\\n> ')}` };
                return { text: '' };
            }

            // --- CODE BLOCKS ---
            if (tag === 'pre') {
                const code = el.querySelector('code');
                const lang = code?.className?.match(/lang-(\\w+)/)?.[1] || el.getAttribute('data-language') || '';
                const codeText = code ? code.innerText.trim() : el.innerText.trim();
                const cleaned = codeText.replace(/^(PowerShell|Bash|CMD|JSON|Copier)\\s*\\n?/i, '').trim();
                if (cleaned) {
                    const langLabel = lang ? lang : '';
                    return { text: '```' + langLabel + '\\n' + cleaned + '\\n```\\n' };
                }
                return { text: '' };
            }

            // --- TABLES: skip nested tables to avoid duplication ---
            if (tag === 'table') {
                if (el.closest('td, th')) return { text: '' };  // nested – skip
                const rows = el.querySelectorAll('tr');
                if (!rows.length) return { text: '' };
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
                return { text: md ? md + '\\n' : '' };
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
                            // Check if it's a code block or other block element
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
                if (items.length) return { text: items.join('\\n') + '\\n' };
                return { text: '' };
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
                            // Check if it's a code block or other block element
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
                if (items.length) return { text: items.join('\\n') + '\\n' };
                return { text: '' };
            }

            // --- BLOCKQUOTES ---
            if (tag === 'blockquote') {
                const lines = el.innerText.trim().split('\\n');
                if (lines.length) return { text: lines.map(l => `> ${l}`).join('\\n') + '\\n' };
                return { text: '' };
            }

            // --- PARAGRAPHS ---
            if (tag === 'p') {
                return { text: inlineToMarkdown(el) + '\\n' };
            }

            // --- DIV WRAPPERS (recurse) ---
            if (tag === 'div') {
                if (el.classList?.contains('table-wrapper') || el.classList?.contains('inner-focus') || el.classList?.contains('content')) {
                    let text = '';
                    for (const child of el.children) {
                        text += elementToMarkdown(child, insideNestedTable).text;
                    }
                    return { text: text };
                }
            }

            // Default: extract inner text
            const txt = el.innerText?.trim();
            if (txt) return { text: txt + '\\n' };
            return { text: '' };
        }

        // Special converter for the "Résolution rapide" table (no images)
        function convertQuickResolutionTable(tableWrapper) {
            const table = tableWrapper.querySelector('table');
            if (!table) return '';
            const rows = table.querySelectorAll('tbody > tr');
            let md = '';

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length < 2) continue;

                // Option title (first link in second cell)
                const titleLink = cells[1].querySelector('a');
                let title = titleLink ? titleLink.innerText.trim() : 'Option';
                title = title.replace(/[:\s]+$/, '');

                // Extract instructions: prefer <ol> content
                let instructions = '';
                const ol = cells[1].querySelector('ol');
                if (ol) {
                    const items = Array.from(ol.querySelectorAll('li')).map((li, idx) => {
                        // Convert any code blocks inside the list item
                        const codeBlock = li.querySelector('pre');
                        if (codeBlock) {
                            const codeText = elementToMarkdown(codeBlock).text;
                            return `${idx+1}. ${li.innerText.split('\\n')[0]}\\n\\n${codeText}`;
                        }
                        return `${idx+1}. ${li.innerText.trim()}`;
                    });
                    instructions = items.join('\\n');
                } else {
                    // No ordered list – take plain text
                    const clone = cells[1].cloneNode(true);
                    const link = clone.querySelector('a');
                    if (link) link.remove();
                    instructions = clone.innerText.trim();
                }

                // Check for nested table (version/registry) inside this cell
                const nestedTable = cells[1].querySelector('table');
                let nestedMd = '';
                if (nestedTable) {
                    // Convert nested table to Markdown
                    const nestedRows = nestedTable.querySelectorAll('tr');
                    if (nestedRows.length) {
                        let tableMd = '';
                        for (let ri = 0; ri < nestedRows.length; ri++) {
                            const cellsN = Array.from(nestedRows[ri].querySelectorAll('th, td'))
                                .map(c => c.innerText.trim().replace(/\\n/g, ' ').replace(/\\|/g, '\\\\|'));
                            if (!cellsN.length) continue;
                            tableMd += '| ' + cellsN.join(' | ') + ' |\\n';
                            if (ri === 0 && nestedRows[ri].querySelector('th')) {
                                tableMd += '| ' + cellsN.map(() => '---').join(' | ') + ' |\\n';
                            }
                        }
                        nestedMd = tableMd;
                    }
                }

                md += `### ${title}\\n\\n`;
                if (instructions) md += `${instructions}\\n\\n`;
                if (nestedMd) md += `${nestedMd}\\n\\n`;
            }
            return md;
        }

        // Process each heading
        headings.forEach(h => {
            const header = h.innerText.trim();
            if (!header) return;
            const level = parseInt(h.tagName[1]) || 2;

            let contentParts = [];
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

                let result = { text: '' };
                // Special handling for the quick-resolution table
                if (header === "Résolution rapide" && sibling.classList?.contains('table-wrapper')) {
                    result.text = convertQuickResolutionTable(sibling);
                    // Skip the entire table wrapper
                    sibling = sibling.nextElementSibling;
                    continue;
                } else {
                    result = elementToMarkdown(sibling);
                }
                if (result.text) contentParts.push(result.text);
                sibling = sibling.nextElementSibling;
            }

            if (header) {
                sections.push({
                    header,
                    level,
                    content: contentParts.join('\\n').trim()
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

    # Build sections without images
    sections = []
    article_id = article_index
    for i, sec in enumerate(raw_sections, start=1):
        sections.append({
            "article_id": article_id,
            "section_id": i,
            "header": sec["header"],
            "level": sec["level"],
            "content": sec["content"]
        })

    return {
        "article_id": article_id,
        "title": title,
        "applies_to": applies_to,
        "preamble": preamble,
        "sections": sections
    }


async def fetch_article_content(page, article: dict, index: int, total: int, app_name: str, retries: int = 3) -> dict:
    url = article["fr_url"]
    sidebar_title = article["sidebar_title"]
    print(f"\n  [{index}/{total}] {sidebar_title}")
    print(f"    URL : {url}")

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"    ↻ Attempt {attempt}/{retries}...")
            result = await scrape_article(page, url, app_name, index)

            if not result["sections"]:
                debug = await page.evaluate("""() => ({
                    content: !!document.querySelector('.content'),
                    headings: document.querySelectorAll('h2').length,
                    wrappers: document.querySelectorAll('.heading-wrapper').length
                })""")
                print(f"    ⚠️ Empty sections - page state: {debug}")
                raise ValueError(f"Empty sections — debug: {debug}")

            section_count = len(result["sections"])
            print(f"    ✓ Article ID: {result['article_id']}")
            print(f"    ✓ Title: {result['title'][:60]}...")
            print(f"    ✓ Sections: {section_count}")

            return {
                "article_id": result["article_id"],
                "title": result["title"],
                "applies_to": result["applies_to"],
                "preamble": result["preamble"],
                "sections": result["sections"],
                "fetched_url": article["fr_url"]
            }

        except Exception as e:
            last_error = e
            print(f"    ✗ Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(attempt * 2)

    print(f"    ✗ FAILED after {retries} attempts")
    # Return None instead of error dict to mark this as a failed article
    return None


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scraper.py <app_name>")
        sys.exit(1)

    app_name = sys.argv[1]
    articles = await scrape_app_articles(app_name)
    if not articles:
        sys.exit(1)

    total = len(articles)
    print(f"\n{'='*60}\n  Fetching {total} articles for '{app_name}'\n{'='*60}")

    os.makedirs("data/scraped/", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        results = []
        for i, article in enumerate(articles, 1):
            data = await fetch_article_content(page, article, i, total, app_name, retries=3)
            # Only append successful results
            if data is not None:
                results.append(data)
        await browser.close()

    output_file = f"data/scraped/{app_name}.json"
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