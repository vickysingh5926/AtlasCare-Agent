"""
Pure Python PDF Generator for the Handbook
Converts handbook markdown files to PDF using xhtml2pdf.
Uses simpler CSS style compatible with reportlab/xhtml2pdf rendering constraints.
"""
import os
import sys

try:
    import markdown
except ImportError:
    print("Installing markdown...")
    os.system(f'"{sys.executable}" -m pip install markdown --break-system-packages')
    import markdown

try:
    from xhtml2pdf import pisa
except ImportError:
    print("Installing xhtml2pdf...")
    os.system(f'"{sys.executable}" -m pip install xhtml2pdf --break-system-packages')
    from xhtml2pdf import pisa

HANDBOOK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handbook")
OUTPUT_PDF = os.path.join(HANDBOOK_DIR, "MLE_GenAI_Agentic_AI_Interview_Handbook.pdf")

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

# xhtml2pdf compatible CSS styles
CSS_STYLE = """
@page {
    size: a4;
    margin: 2cm;
}

body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #1a1a2e;
}

h1 {
    font-size: 20pt;
    font-weight: bold;
    color: #0f0f23;
    margin-top: 30pt;
    margin-bottom: 12pt;
    border-bottom: 2px solid #4338ca;
    padding-bottom: 4pt;
    page-break-before: always;
}

h2 {
    font-size: 14pt;
    font-weight: bold;
    color: #1e1e3f;
    margin-top: 20pt;
    margin-bottom: 8pt;
    border-bottom: 1px solid #e2e4f0;
    padding-bottom: 2pt;
}

h3 {
    font-size: 11.5pt;
    font-weight: bold;
    color: #2d2d5e;
    margin-top: 14pt;
    margin-bottom: 6pt;
}

p {
    margin-top: 6pt;
    margin-bottom: 6pt;
}

ul, ol {
    margin-top: 6pt;
    margin-bottom: 6pt;
    padding-left: 20pt;
}

li {
    margin-bottom: 3pt;
}

code {
    font-family: Courier, monospace;
    font-size: 8.5pt;
    background-color: #f1f3f9;
    color: #4338ca;
}

pre {
    background-color: #1e1e2e;
    color: #cdd6f4;
    padding: 10pt;
    margin-top: 8pt;
    margin-bottom: 8pt;
    font-family: Courier, monospace;
    font-size: 8pt;
}

pre code {
    background-color: transparent;
    color: #cdd6f4;
    font-size: 8pt;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 10pt;
    margin-bottom: 10pt;
    font-size: 9pt;
}

th {
    background-color: #4338ca;
    color: #ffffff;
    font-weight: bold;
    text-align: left;
    padding: 6pt;
    border: 1px solid #4338ca;
}

td {
    padding: 6pt;
    border: 1px solid #e5e7eb;
}

blockquote {
    margin-top: 8pt;
    margin-bottom: 8pt;
    padding: 8pt;
    background-color: #eef2ff;
    border-left: 4px solid #6366f1;
}

hr {
    border: 0;
    border-top: 1px solid #e2e4f0;
    margin-top: 20pt;
    margin-bottom: 20pt;
}

strong {
    font-weight: bold;
    color: #111111;
}

/* Cover Page */
.cover-page {
    text-align: center;
    margin-top: 100pt;
}

.cover-title {
    font-size: 28pt;
    font-weight: bold;
    color: #0f0f23;
    margin-bottom: 10pt;
}

.cover-subtitle {
    font-size: 16pt;
    color: #4338ca;
    margin-bottom: 40pt;
}

.cover-meta {
    font-size: 10.5pt;
    color: #555555;
    line-height: 1.8;
}

.cover-badge {
    display: inline-block;
    background-color: #4338ca;
    color: #ffffff;
    padding: 6pt 14pt;
    border-radius: 12pt;
    font-size: 9.5pt;
    font-weight: bold;
    margin-top: 30pt;
}
"""

COVER_HTML = """
<div class="cover-page">
    <div class="cover-title">MLE Generative AI &amp;<br/>Agentic AI</div>
    <div class="cover-subtitle">Complete Interview Handbook</div>
    <div class="cover-meta">
        <p><strong>50+ Topics</strong> &bull; <strong>25+ Comparison Tables</strong> &bull; <strong>200+ Interview Questions</strong></p>
        <p><strong>5 System Design Playbooks</strong> &bull; <strong>Rapid Revision Cheat Sheets</strong></p>
        <br/>
        <p>Optimized for 4-day interview preparation</p>
        <p>Covers: LLM Foundations &bull; Prompt Engineering &bull; RAG &bull; Agentic AI &bull; Production Systems</p>
    </div>
    <div class="cover-badge">2025 Edition &bull; Production-Focused</div>
</div>
<div style="page-break-after: always;"></div>
"""

def convert_md_to_html(md_text):
    return markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
    )

def main():
    print("=" * 60)
    print("  Generating styled PDF with xhtml2pdf...")
    print("=" * 60)
    
    sections = []
    for i, fname in enumerate(FILES):
        fpath = os.path.join(HANDBOOK_DIR, fname)
        if not os.path.exists(fpath):
            print(f"  ⚠️  Missing: {fname}")
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            md = f.read()
            
        # Clean some markdown features that might cause xhtml2pdf layout issues
        # e.g., escape html tags in examples, clean custom markdown symbols
        # xhtml2pdf does not like raw HTML comments inside text either
        md = md.replace("<!-- slide -->", "") 
        
        html = convert_md_to_html(md)
        sections.append(html)
        print(f"  ✅ Read & converted: {fname}")

    body_content = COVER_HTML + "\n".join(sections)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
{CSS_STYLE}
</style>
</head>
<body>
{body_content}
</body>
</html>"""

    # Direct PDF conversion
    print("\n  Writing PDF...")
    try:
        with open(OUTPUT_PDF, "w+b") as result_file:
            pisa_status = pisa.CreatePDF(
                full_html,
                dest=result_file
            )
        
        if not pisa_status.err:
            pdf_size = os.path.getsize(OUTPUT_PDF) / (1024 * 1024)
            print(f"  🎉 SUCCESS! PDF created: {OUTPUT_PDF}")
            print(f"     Size: {pdf_size:.2f} MB")
        else:
            print(f"  ❌ Conversion errors: {pisa_status.err}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  ❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
