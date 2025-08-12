Analyze this page image and convert it to HTML.

IMPORTANT LAYOUT ANALYSIS:
- Analyze the page in distinct sections (top, middle, bottom, etc.)
- Identify if content flows in columns or single column
- Detect headers, footers, and main content areas
- Recognize tables, lists, and other structured content

LAYOUT CONTAINERS:
- For 2-column layouts: Use <div class="grid-2col"> or <div class="columns-2">
- For 3+ column layouts: Use <div class="grid-3col"> or <div class="columns-3">
- For single column: No special container needed
- Use {css_mode} mode for sections that clearly have multi-column layout
- If css_mode is 'single', force single column layout for all sections

SECTION-BASED APPROACH:
- Top section: Apply appropriate layout (single or multi-column)
- Middle section: Apply appropriate layout (single or multi-column)
- Bottom section: Apply appropriate layout (single or multi-column)
- Tables: Keep original structure, don't force into layout containers

CONTENT STRUCTURE:
- Use semantic HTML: h1-h6, p, ul/ol/li, table, etc.
- Preserve text hierarchy and formatting
- Keep tables as <table> with proper thead/tbody
- Maintain list structures with ul/ol/li

IMPORTANT RULES:
- Return ONLY the inner HTML for a single page wrapped in: <section class="page"> ... </section>
- Do NOT include <html>, <head>, or <body> tags
- Use minimal inline styles only when essential
- Preserve exact reading order and visual layout
- Tables: Keep original structure, don't force into layout containers

Focus on preserving the exact visual layout and reading order of the original document. 