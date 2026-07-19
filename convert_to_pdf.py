"""
Handbook Markdown → HTML Converter
Creates a single beautiful HTML file from all handbook markdown files.
No heavy dependencies — just the 'markdown' package.
"""
import os
import sys

# Try to install markdown if not available
try:
    import markdown
except ImportError:
    print("Installing markdown package...")
    os.system(f'"{sys.executable}" -m pip install markdown')
    import markdown

HANDBOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handbook")
OUTPUT_HTML = os.path.join(HANDBOOK_DIR, "MLE_GenAI_Agentic_AI_Interview_Handbook.html")

FILES = [
    "00_table_of_contents.md",
    "01_llm_foundations.md",
    "02_prompt_engineering.md",
    "03_rag.md",
    "04_agentic_ai.md",
    "05_production_llm_systems.md",
    "06_system_design_playbook.md",
    "07_comparison_tables.md",
    "08_revision_cheat_sheet.md",
    "09_mock_interview_questions.md",
]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg: #ffffff;
    --text: #1a1a2e;
    --heading: #0f0f23;
    --accent: #4338ca;
    --accent-light: #eef2ff;
    --accent-dark: #3730a3;
    --border: #e2e4f0;
    --code-bg: #1e1e2e;
    --code-text: #cdd6f4;
    --table-header: #4338ca;
    --table-even: #f8f9fc;
    --blockquote-bg: #eef2ff;
    --blockquote-border: #6366f1;
}

@media print {
    body { font-size: 9.5pt; }
    .cover-page { page-break-after: always; }
    .chapter { page-break-before: always; }
    .chapter:first-of-type { page-break-before: avoid; }
    pre, table, blockquote { page-break-inside: avoid; }
    h1, h2, h3 { page-break-after: avoid; }
    @page { margin: 1.8cm 2cm; size: A4; }
    @page:first { margin-top: 0; }
    .no-print { display: none; }
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 11pt;
    line-height: 1.65;
    color: var(--text);
    background: var(--bg);
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem;
}

/* COVER PAGE */
.cover-page {
    text-align: center;
    padding: 8rem 2rem 4rem;
    min-height: 90vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

.cover-page h1 {
    font-size: 2.8rem;
    font-weight: 900;
    color: var(--heading);
    border: none;
    margin-bottom: 0.3em;
    line-height: 1.15;
    letter-spacing: -0.02em;
    page-break-before: avoid;
}

.cover-page .gradient-text {
    background: linear-gradient(135deg, #4338ca, #7c3aed, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.cover-page .subtitle {
    font-size: 1.3rem;
    color: #6366f1;
    font-weight: 500;
    margin-bottom: 2.5em;
}

.cover-page .meta {
    font-size: 0.95rem;
    color: #666;
    line-height: 2;
}

.cover-page .badge {
    display: inline-block;
    background: linear-gradient(135deg, #4338ca, #6366f1);
    color: white;
    padding: 0.6em 1.8em;
    border-radius: 25px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-top: 2.5em;
    letter-spacing: 0.03em;
}

.cover-page .stats {
    display: flex;
    gap: 2rem;
    margin-top: 3rem;
    flex-wrap: wrap;
    justify-content: center;
}

.cover-page .stat {
    text-align: center;
}

.cover-page .stat-number {
    font-size: 2rem;
    font-weight: 800;
    color: var(--accent);
}

.cover-page .stat-label {
    font-size: 0.8rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* PRINT BUTTON */
.print-btn {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    background: linear-gradient(135deg, #4338ca, #6366f1);
    color: white;
    border: none;
    padding: 1rem 2rem;
    border-radius: 12px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 15px rgba(67, 56, 202, 0.4);
    z-index: 1000;
    transition: all 0.2s;
    font-family: 'Inter', sans-serif;
}
.print-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(67, 56, 202, 0.5);
}

/* HEADINGS */
h1 {
    font-size: 1.9rem;
    font-weight: 800;
    color: var(--heading);
    margin: 2.5rem 0 0.7rem;
    padding-bottom: 0.4em;
    border-bottom: 3px solid var(--accent);
    line-height: 1.25;
    letter-spacing: -0.01em;
}

h2 {
    font-size: 1.35rem;
    font-weight: 700;
    color: #1e1e3f;
    margin: 1.8rem 0 0.5rem;
    padding-bottom: 0.25em;
    border-bottom: 1.5px solid var(--border);
}

h3 {
    font-size: 1.1rem;
    font-weight: 600;
    color: #2d2d5e;
    margin: 1.4rem 0 0.4rem;
}

h4 {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--accent);
    margin: 1rem 0 0.3rem;
}

/* PARAGRAPHS */
p { margin: 0.6em 0; }

/* LISTS */
ul, ol { padding-left: 1.6em; margin: 0.5em 0; }
li { margin: 0.2em 0; }

/* INLINE CODE */
code {
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace;
    font-size: 0.85em;
    background: #f1f3f9;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.15em 0.4em;
    color: var(--accent);
}

/* CODE BLOCKS */
pre {
    background: var(--code-bg);
    color: var(--code-text);
    border-radius: 10px;
    padding: 1.2em 1.4em;
    overflow-x: auto;
    font-size: 0.82em;
    line-height: 1.55;
    margin: 1em 0;
    border-left: 4px solid var(--blockquote-border);
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

pre code {
    background: none;
    border: none;
    padding: 0;
    color: var(--code-text);
    font-size: 1em;
}

/* TABLES */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 0.9em;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

thead { background: var(--table-header); color: white; }

th {
    padding: 0.6em 0.8em;
    text-align: left;
    font-weight: 600;
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

td {
    padding: 0.55em 0.8em;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: top;
}

tbody tr:nth-child(even) { background: var(--table-even); }

/* BLOCKQUOTES */
blockquote {
    margin: 1em 0;
    padding: 0.8em 1.2em;
    background: var(--blockquote-bg);
    border-left: 4px solid var(--blockquote-border);
    border-radius: 0 8px 8px 0;
    font-size: 0.95em;
}

blockquote p { margin: 0.3em 0; }

/* HORIZONTAL RULES */
hr {
    border: none;
    border-top: 2px solid var(--border);
    margin: 2.5em 0;
}

/* STRONG / EM */
strong { font-weight: 700; color: #1e1e3f; }
em { font-style: italic; color: #4a4a6a; }

/* LINKS */
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* CHAPTER WRAPPER */
.chapter {
    margin-top: 3rem;
    padding-top: 1rem;
}
"""

COVER = """
<div class="cover-page">
    <h1 style="border:none; page-break-before: avoid;">
        MLE <span class="gradient-text">Generative AI</span> &<br>
        <span class="gradient-text">Agentic AI</span>
    </h1>
    <div class="subtitle">Complete Interview Handbook</div>
    <div class="stats">
        <div class="stat"><div class="stat-number">50+</div><div class="stat-label">Topics</div></div>
        <div class="stat"><div class="stat-number">25+</div><div class="stat-label">Comparisons</div></div>
        <div class="stat"><div class="stat-number">200+</div><div class="stat-label">Questions</div></div>
        <div class="stat"><div class="stat-number">5</div><div class="stat-label">System Designs</div></div>
    </div>
    <div class="meta">
        <p><strong>Covers:</strong> LLM Foundations · Prompt Engineering · RAG · Agentic AI · Production Systems</p>
        <p>Optimized for 4-day interview preparation · Production-focused · 2025 Edition</p>
    </div>
    <div class="badge">📘 Interview-Ready Handbook</div>
</div>
"""

def convert_md(md_text):
    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
    )

def main():
    print("=" * 50)
    print("  📘 Handbook → HTML/PDF Converter")
    print("=" * 50)

    sections = []
    for i, fname in enumerate(FILES):
        fpath = os.path.join(HANDBOOK_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  ⚠️  Missing: {fname}")
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            md = f.read()
        html = convert_md(md)
        cls = ' class="chapter"' if i > 0 else ""
        sections.append(f"<div{cls}>{html}</div>")
        print(f"  ✅ {fname}")

    body = COVER + "\\n".join(sections)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLE GenAI & Agentic AI Interview Handbook</title>
<style>{CSS}</style>
</head>
<body>
{body}
<button class="print-btn no-print" onclick="window.print()">📄 Save as PDF</button>
</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(full_html)

    size_kb = os.path.getsize(OUTPUT_HTML) / 1024
    print(f"\\n  ✅ HTML created: {OUTPUT_HTML}")
    print(f"     Size: {size_kb:.0f} KB")
    print()
    print("  To save as PDF:")
    print("  1. Open the HTML file in Chrome/Edge")
    print("  2. Press Ctrl+P")
    print("  3. Set 'Destination' to 'Save as PDF'")
    print("  4. Click Save")
    print()

    # Try weasyprint for direct PDF
    try:
        from weasyprint import HTML as WHTML
        pdf_path = os.path.join(HANDBOOK_DIR, "MLE_GenAI_Agentic_AI_Interview_Handbook.pdf")
        print("  📋 WeasyPrint found — generating PDF directly...")
        WHTML(filename=OUTPUT_HTML).write_pdf(pdf_path)
        pdf_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        print(f"  ✅ PDF created: {pdf_path}")
        print(f"     Size: {pdf_mb:.1f} MB")
    except ImportError:
        print("  ℹ️  WeasyPrint not available — use the HTML file to print to PDF.")
    except Exception as e:
        print(f"  ⚠️  WeasyPrint PDF failed: {e}")
        print("  ℹ️  Use the HTML file to print to PDF instead.")

    print()
    print("=" * 50)
    print("  ✅ Done!")
    print("=" * 50)

if __name__ == "__main__":
    main()
