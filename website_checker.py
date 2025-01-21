import os
import re
import ssl
import logging
import urllib.request
import requests
import cssutils
from bs4 import BeautifulSoup
from PIL import ImageColor

# Optional PDF conversion
try:
    import pdfkit
    PDF_EXPORT_AVAILABLE = True
except ImportError:
    PDF_EXPORT_AVAILABLE = False

# Suppress cssutils warnings/errors to handle modern CSS (var, calc, etc.)
cssutils.log.setLevel(logging.CRITICAL)

HTML_FILE_PATH = 'website_content.txt'

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

def load_html_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
    return BeautifulSoup(html_content, 'html.parser'), html_content

def get_report_author():
    """Return a fixed brand/author."""
    return "NOVAMKR, LLC"

def get_title_and_url(soup):
    """Extract <title> and best guess at canonical or representative URL."""
    title_tag = soup.find('title')
    title = title_tag.get_text().strip() if title_tag else "Untitled Website"

    canonical_url_tag = soup.find('link', rel='canonical')
    if canonical_url_tag:
        url = canonical_url_tag.get('href', 'URL not found')
    else:
        base_url_tag = soup.find('meta', attrs={'property': 'og:url'})
        if base_url_tag:
            url = base_url_tag.get('content', 'URL not found')
        else:
            first_link = soup.find('a', href=True)
            url = first_link['href'] if first_link else 'URL not found'

    # Basic check for a valid https TLD; fallback otherwise
    if not re.match(r'^https:\/\/.*\.(com|org|gov|edu|net)(\/.*)?$', url):
        if 'URL not found' in url or url.startswith('#'):
            url = "Valid URL not found"
    return title, url

def check_missing_alt(soup):
    issues = []
    for img in soup.find_all('img'):
        alt_text = img.get('alt')
        aria_hidden = img.get('aria-hidden') == 'true'
        role_presentation = img.get('role') == 'presentation'
        if not alt_text and not aria_hidden and not role_presentation:
            issues.append(f"Image missing alt text: {img.get('src')}")
    return issues

def check_clickable_images(soup):
    """Images that appear clickable but aren't properly linked."""
    issues = []
    for img in soup.find_all('img'):
        if img.get('onclick') or img.find_parent('a'):
            parent_a = img.find_parent('a')
            if parent_a and not parent_a.get('href'):
                issues.append(f"Clickable image without real link: {img.get('src')}")
            elif not parent_a:
                issues.append(f"Image onclick without anchor/href: {img.get('src')}")
    return issues

def check_responsive_viewport(soup):
    issues = []
    mv = soup.find('meta', attrs={'name': 'viewport'})
    if not mv:
        issues.append("No responsive 'viewport' meta tag.")
    else:
        content = mv.get('content', '').lower()
        if "width=device-width" not in content:
            issues.append(f"Viewport meta tag present but possibly misconfigured: '{content}'")
    return issues

def check_modern_doctype(html_text):
    issues = []
    # Look only at first few hundred chars
    snippet = html_text[:300].lower()
    if "<!doctype html>" not in snippet:
        issues.append("Site not using modern HTML5 doctype.")
    return issues

def check_layout_tables(soup):
    """Detect multiple <table> usage indicating old layout techniques."""
    issues = []
    tables = soup.find_all('table')
    if len(tables) > 5:
        issues.append("Excessive <table> usage; possible legacy layout approach.")
    return issues

def check_exposed_keys(html_content):
    """Look for common API key/JWT patterns in text."""
    patterns = {
        'AWS Access Key': r'AKIA[0-9A-Z]{16}',
        'JWT': r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
        'Google API Key': r'AIza[0-9A-Za-z-_]{35}',
        'Generic API Key': r'api_key\s*=\s*[\'"][A-Za-z0-9-_]{16,}[\'"]',
        'Slack Token': r'xox[baprs]-[A-Za-z0-9-]{10,48}'
    }
    found = []
    for key_type, pattern in patterns.items():
        matches = re.findall(pattern, html_content)
        for match in matches:
            found.append(f"Exposed {key_type}: {match}")
    return found

def check_https(soup):
    """Check for 'http://' usage in 'src' or 'href' (insecure)."""
    insecure_links = set()
    for tag in soup.find_all(['a','img','link','script']):
        url = tag.get('href') or tag.get('src')
        if url and url.startswith('http://'):
            insecure_links.add(url)
    return list(insecure_links)

def check_broken_links(soup):
    """Attempt HEAD requests for found links to see if 404 or other error."""
    broken = set()
    links = soup.find_all('a', href=True)
    for link in links:
        href = link['href']
        if href.startswith('http'):
            try:
                req = urllib.request.Request(href, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req, context=ssl_context, timeout=5)
                if not (200 <= response.status < 300):
                    broken.add((href, str(response.status)))
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 600:
                    broken.add((href, str(e.code)))
            except urllib.error.URLError as e:
                if "SSL" in str(e.reason):
                    broken.add((href, "security"))
            except ssl.SSLError:
                broken.add((href, "security"))
            except TimeoutError:
                broken.add((href, "timeout"))
            except Exception:
                broken.add((href, "unexpected_error"))
    return list(broken)

def check_image_sizes(soup):
    """Flag images over ~200KB."""
    large = []
    session = requests.Session()
    session.headers.update({'User-Agent': 'WebsiteChecker/1.0'})
    for img in soup.find_all('img', src=True):
        src = img['src']
        if src.startswith('http'):
            try:
                r = session.head(src, allow_redirects=True, timeout=10)
                if r.status_code == 200 and 'Content-Length' in r.headers:
                    kb = int(r.headers['Content-Length'])/1024
                    if kb > 200:
                        large.append((src, kb))
            except requests.exceptions.RequestException:
                pass
    return large

def check_accessibility(soup):
    """Basic checks: <html lang>, main content."""
    issues = []
    html_tag = soup.find('html')
    if html_tag and not html_tag.get('lang'):
        issues.append("Missing 'lang' attribute in <html>.")
    main_area = soup.find('main') or soup.find(attrs={"role": "main"})
    if not main_area:
        issues.append("Missing <main> or role='main' for primary content.")
    return issues

def check_missing_aria(soup):
    """Check interactive elements lacking aria-label/title/inner text."""
    issues = []
    interactive = soup.find_all(['button','a','input','select','textarea'])
    for elem in interactive:
        if elem.name == 'a' and not elem.get('href'):
            continue
        accessible_name = (
            elem.get('aria-label') or
            elem.get('aria-labelledby') or
            elem.get('alt') or
            elem.get('title') or
            elem.get_text(strip=True)
        )
        if not accessible_name:
            e_id = elem.get('id','')
            e_cls = ' '.join(elem.get('class',[]))
            issues.append(f"Missing accessible name: <{elem.name} id='{e_id}' class='{e_cls}'>")
    return issues

def check_keyboard_accessibility(soup):
    """Elements with onclick but no tabIndex might not be keyboard-accessible."""
    issues = []
    clickable_elems = soup.find_all(attrs={'onclick': True})
    for elem in clickable_elems:
        # If not a default interactive tag:
        if elem.name not in ['a','button','input','textarea','select'] and not elem.has_attr('tabindex'):
            issues.append(f"Possible keyboard trap: <{elem.name}> has onclick, no tabIndex.")
    return issues

def check_outdated_html(soup):
    """Look for deprecated tags."""
    issues = []
    for tag in ['font','center','marquee','blink']:
        found = soup.find_all(tag)
        for f in found:
            issues.append(f"Deprecated tag <{tag}> found.")
    return issues

def check_color_contrast(soup, html_content):
    """Use cssutils to parse color rules and measure contrast where possible."""
    issues = []
    style_sheets = []

    # 1) Inline <style> blocks
    for st in soup.find_all('style'):
        if st.string:
            style_sheets.append(st.string)

    # 2) Linked stylesheets
    session = requests.Session()
    session.headers.update({'User-Agent': 'WebsiteChecker/1.0'})
    for lk in soup.find_all('link', rel='stylesheet'):
        href = lk.get('href')
        if href and href.startswith('http'):
            try:
                resp = session.get(href, timeout=10)
                if resp.status_code == 200:
                    style_sheets.append(resp.text)
            except requests.exceptions.RequestException:
                pass

    # Parse combined CSS text
    parser = cssutils.CSSParser(raiseExceptions=False, validate=False)
    combined_css = '\n'.join(style_sheets)
    stylesheet = parser.parseString(combined_css)

    # Store selectors -> style
    styles_map = {}
    for rule in stylesheet:
        if rule.type == rule.STYLE_RULE:
            sel = rule.selectorText
            style = rule.style.cssText
            styles_map[sel] = style

    def get_computed_style(element):
        s_list = []
        if element.has_attr('style'):
            s_list.append(element['style'])
        e_id = element.get('id')
        e_cls = element.get('class', [])
        # Check possible matches
        for sel, style in styles_map.items():
            # .class
            if sel.startswith('.') and any(c == sel[1:] for c in e_cls):
                s_list.append(style)
            # #id
            elif sel.startswith('#') and e_id == sel[1:]:
                s_list.append(style)
            # element tag
            elif sel == element.name:
                s_list.append(style)
        return ';'.join(s_list)

    # Analyze text contrast in main or body
    container = soup.find('main') or soup.find(attrs={"role": "main"}) or soup.body
    if not container:
        return issues

    text_elems = container.find_all(string=True)
    for txt in text_elems:
        if txt.strip():
            par = txt.parent
            if par.name not in ['style','script','head','title','meta','[document]']:
                c_style = get_computed_style(par)
                style_obj = cssutils.parseStyle(c_style)
                fg = style_obj.getPropertyValue('color') or '#000'
                bg = style_obj.getPropertyValue('background-color') or '#fff'

                def parse_color(cstr):
                    try:
                        # Handle rgb/rgba
                        if 'rgba' in cstr:
                            return ImageColor.getcolor(cstr, "RGBA")[:3]
                        return ImageColor.getcolor(cstr, "RGB")
                    except ValueError:
                        return None

                fg_val = parse_color(fg)
                bg_val = parse_color(bg)
                if fg_val and bg_val:
                    def lum(rgb):
                        def channel(c):
                            c /= 255.0
                            return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4
                        return 0.2126*channel(rgb[0]) + 0.7152*channel(rgb[1]) + 0.0722*channel(rgb[2])
                    l1 = lum(fg_val); l2 = lum(bg_val)
                    ratio = (max(l1,l2)+0.05)/(min(l1,l2)+0.05)
                    if ratio < 4.5:
                        snippet = txt.strip()[:30]
                        issues.append(f"Low contrast ratio ({ratio:.2f}) for text: '{snippet}'")
    return issues

def check_unused_css_js(soup):
    """Placeholder for advanced usage if needed."""
    return []

def check_grammar(text_content):
    """Placeholder for grammar checks, if needed."""
    return []

def calculate_score(results):
    """Generate overall site score (100 max)."""
    score = 100
    exposed = len(results['exposed_keys'])
    broken_404 = len([b for b in results['broken_links'] if b[1] == '404'])
    a11y = len(results['accessibility'])
    kb_a11y = len(results['keyboard_accessibility'])
    clickable_imgs = len(results['clickable_images'])

    # Major
    score -= min(exposed * 17, 35)
    score -= min(broken_404 * 5, 25)
    score -= min(a11y * 10, 20)
    score -= min(kb_a11y * 10, 20)
    score -= min(clickable_imgs * 5, 10)

    # Minor
    if results['missing_aria']:   score -= 5
    if results['missing_alt']:    score -= 5
    if results['https']:          score -= 5
    if results['outdated_html']:  score -= 5
    if results['large_images']:   score -= 5
    if results['color_contrast']: score -= 5
    if results['responsive_viewport']: score -= 5
    if results['modern_doctype']:     score -= 5
    if results['layout_tables']:      score -= 5

    return max(min(score, 100), 0)

def calculate_deductions(results):
    d = {}
    exposed = len(results['exposed_keys'])
    broken_404 = len([b for b in results['broken_links'] if b[1] == '404'])
    a11y = len(results['accessibility'])
    kb_a11y = len(results['keyboard_accessibility'])
    clickable_imgs = len(results['clickable_images'])

    d['Exposed API Keys/JWTs Deducted']        = min(exposed * 17, 35)
    d['Broken Links Deducted']                 = min(broken_404 * 5, 25)
    d['508 Accessibility Issues Deducted']     = min(a11y * 10, 20)
    d['Keyboard Accessibility Issues Deducted']= min(kb_a11y * 10, 20)
    d['Clickable Image Issues Deducted']       = min(clickable_imgs * 5, 10)

    d['Missing ARIA Labels Deducted']         = 5 if results['missing_aria'] else 0
    d['Missing Alt Text Deducted']            = 5 if results['missing_alt'] else 0
    d['HTTPS Compliance Issues Deducted']      = 5 if results['https'] else 0
    d['Outdated HTML Tags Deducted']           = 5 if results['outdated_html'] else 0
    d['Large Images Deducted']                 = 5 if results['large_images'] else 0
    d['Color Contrast Issues Deducted']        = 5 if results['color_contrast'] else 0
    d['Responsive Viewport Deducted']          = 5 if results['responsive_viewport'] else 0
    d['Modern Doctype Deducted']               = 5 if results['modern_doctype'] else 0
    d['Layout Tables Deducted']                = 5 if results['layout_tables'] else 0

    return d

def generate_report_filename(soup):
    t = soup.find('title')
    title = t.get_text().strip() if t else "website_report"
    safe_title = re.sub(r'\W+', '_', title)
    return f"{safe_title}_report.html"

def generate_explanations():
    return {
        'Exposed API Keys/JWTs': "Exposed keys/tokens let attackers access private resources.",
        '508 Accessibility Issues': "Accessibility shortfalls affect disabled users.",
        'Keyboard Accessibility Issues': "All features must be usable without a mouse.",
        'Broken Links': "Dead links frustrate users and harm credibility.",
        'Clickable Image Issues': "Images that appear clickable but do nothing confuse visitors.",
        'Color Contrast Issues': "Low contrast text is hard to read.",
        'Missing ARIA Labels': "Screen readers rely on ARIA for clarity.",
        'Large Images (over 200KB)': "Huge images slow page loads.",
        'HTTPS Compliance': "Insecure HTTP can expose user data.",
        'Outdated HTML Tags': "Deprecated tags may break in modern browsers.",
        'Missing Alt Text': "Alt text is crucial for accessibility.",
        'Responsive Viewport': "Mobile usability requires a proper viewport tag.",
        'Modern Doctype': "HTML5 doctype recommended for modern standards.",
        'Layout Tables': "Tables for layout hamper responsiveness."
    }

def generate_report(report_filename, report_data, generate_pdf=False):
    """Create an HTML report; optionally convert to PDF if pdfkit is available."""
    title = report_data['title']
    url = report_data['url']
    author = report_data.get('author_name', 'NOVAMKR, LLC')
    score = report_data['score']
    deductions = report_data.get('deductions', {})
    issues_data = report_data['issues_data']
    notes = report_data.get('notes', {})
    explanations = generate_explanations()

    sev_levels = {
        'Exposed API Keys/JWTs': 'high',
        '508 Accessibility Issues': 'high',
        'Keyboard Accessibility Issues': 'high',
        'Broken Links': 'high',
        'Clickable Image Issues': 'medium',
        'Color Contrast Issues': 'medium',
        'Missing ARIA Labels': 'medium',
        'Large Images (over 200KB)': 'low',
        'HTTPS Compliance': 'low',
        'Outdated HTML Tags': 'low',
        'Missing Alt Text': 'info',
        'Responsive Viewport': 'low',
        'Modern Doctype': 'low',
        'Layout Tables': 'low'
    }
    sev_colors = {
        'high': '#c0392b',
        'medium': '#b89a00',
        'low': '#27ae60',
        'info': '#2980b9',
        'none': '#b0b0b0'
    }

    # Maintain a sorted category display
    order = [
        'Exposed API Keys/JWTs',
        '508 Accessibility Issues',
        'Keyboard Accessibility Issues',
        'Broken Links',
        'Clickable Image Issues',
        'Color Contrast Issues',
        'Missing ARIA Labels',
        'Large Images (over 200KB)',
        'HTTPS Compliance',
        'Outdated HTML Tags',
        'Missing Alt Text',
        'Responsive Viewport',
        'Modern Doctype',
        'Layout Tables'
    ]

    with open(report_filename, 'w', encoding='utf-8') as f:
        f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
    <title>Website Analysis Report</title>
    <meta charset="UTF-8">
    <style>
    body {{
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background-color: #1e1e1e; color: #c7c7c7; margin: 0; padding: 0;
    }}
    h1, h2, h3 {{ color: #fff; }}
    h1 {{ background-color: #252526; padding: 20px; margin: 0; text-align: center; }}
    header, main, footer {{ margin: 0 auto; max-width: 800px; padding: 20px; }}
    ul {{ list-style-type: none; padding: 0; }}
    li {{ background-color: #2d2d2d; margin: 5px 0; padding: 10px; border-radius: 5px; }}
    .description {{ font-style: italic; color: #9b9b9b; margin-top: 10px; }}
    .health-bar-container {{
        background-color: rgba(255,255,255,0.1);
        border-radius: 5px; overflow: hidden; margin-top: 20px;
        cursor: pointer; position: relative;
    }}
    .health-bar {{
        height: 30px; width: {score}%;
        background-color: {"#c0392b" if score < 50 else "#b89a00" if score < 80 else "#27ae60"};
        transition: width 0.5s, background-color 0.5s; opacity: 0.8;
    }}
    .health-score-text {{
        position: absolute; top: 0; left: 50%; transform: translateX(-50%);
        line-height: 30px; color: #fff; font-weight: bold;
    }}
    .collapsible {{
        background-color: #252526; color: #fff; cursor: pointer; padding: 10px;
        width: 100%; border: none; text-align: left; outline: none; font-size: 15px;
        margin-top: 10px; border-radius: 5px;
    }}
    .collapsible:hover {{ background-color: #313135; }}
    .content {{
        padding: 0 18px; max-height: 0; overflow: hidden;
        transition: max-height 0.2s ease-out; background-color: #2d2d30; margin-bottom: 10px;
    }}
    .content ul {{ padding: 10px; }}
    .section-title {{ padding: 10px; border-radius: 5px; margin-top: 10px; }}
    .note {{ font-style: italic; color: #9b9b9b; display: block; margin-top: 5px; }}
    </style>
</head>
<body>
<header>
    <h1>Website Analysis Report</h1>
</header>
<main>
    <h2>Website Analyzed</h2>
    <p>Title: {title}</p>
    <p>URL: <a href="{url}" target="_blank" style="color: #c7c7c7;">{url}</a></p>
    <p>Report generated by: {author}</p>
    <h2>Summary of Issues Detected</h2>
    <p>Breakdown of potential issues. Click categories for details.</p>
    <h2>Website Health Score</h2>
    <div class="health-bar-container" onclick="toggleScoreDetails()">
        <div class="health-bar"></div>
        <div class="health-score-text">{score}/100</div>
    </div>
    <div id="score-details" style="display:none; margin-top: 10px;">
        <p>Score is based on critical vs minor issues. Deductions below:</p>
        <ul>""")
        for dtitle, points in deductions.items():
            if points > 0:
                f.write(f"<li>{dtitle}: {points} points</li>")
        f.write("""</ul>
    </div>
    <p class="description">Click the bar above to view/hide deduction breakdown.</p>
""")

        # Render each category in predefined order
        for cat in order:
            cat_issues = issues_data.get(cat, {}).get('issues', [])
            count = len(cat_issues)
            severity = sev_levels.get(cat, 'none')
            color = sev_colors.get(severity, '#fff')

            f.write(f"""
<button type="button" class="collapsible section-title"
        style="background-color:{color if count > 0 else '#555'};color:#fff;">
    {cat} ({count})
</button>
<div class="content">""")

            if count > 0:
                f.write(f"<p>{count} issue(s) found.</p><ul>")
                cat_expl_shown = False
                short_expl = explanations.get(cat, '')
                for issue in cat_issues:
                    issue_text = issue if isinstance(issue, str) else issue[0]
                    f.write(f"<li>{issue_text}")
                    if short_expl and not cat_expl_shown:
                        f.write(f"<br><span class='note'>{short_expl}</span>")
                        cat_expl_shown = True
                    # If we track user notes
                    if cat in notes and issue_text in notes[cat]:
                        f.write(f"<br><span class='note'>{notes[cat][issue_text]}</span>")
                    f.write("</li>")
                f.write("</ul>")
            else:
                f.write("<p>0 issues found.</p>")
            f.write("""<p class="description">
Please address these issues to improve security, compliance, and user experience.
</p></div>""")

        f.write("""
</main>
<footer><p>End of report.</p></footer>
<script>
function toggleScoreDetails(){
    var d = document.getElementById("score-details");
    if(d.style.display===""||d.style.display==="none"){d.style.display="block";}
    else{d.style.display="none";}
}
var coll = document.getElementsByClassName("collapsible");
for(var i=0;i<coll.length;i++){
    coll[i].addEventListener("click",function(){
        this.classList.toggle("active");
        var content=this.nextElementSibling;
        if(content.style.maxHeight){
            content.style.maxHeight=null;
        } else{
            content.style.maxHeight=content.scrollHeight+"px";
        }
    });
}
</script>
</body>
</html>""")

    if generate_pdf and PDF_EXPORT_AVAILABLE:
        pdf_filename = os.path.splitext(report_filename)[0] + ".pdf"
        pdfkit.from_file(report_filename, pdf_filename)
        print(f"PDF generated: {pdf_filename}")

def analyze_html():
    # Load
    soup, html_content = load_html_file(HTML_FILE_PATH)

    # Gather data
    results = {}
    text_content = soup.get_text()

    results['grammar'] = check_grammar(text_content)
    results['accessibility'] = check_accessibility(soup)
    results['keyboard_accessibility'] = check_keyboard_accessibility(soup)
    results['color_contrast'] = check_color_contrast(soup, html_content)
    results['missing_aria'] = check_missing_aria(soup)
    results['missing_alt'] = check_missing_alt(soup)
    results['exposed_keys'] = check_exposed_keys(html_content)
    results['https'] = check_https(soup)
    results['broken_links'] = check_broken_links(soup)
    results['large_images'] = check_image_sizes(soup)
    results['outdated_html'] = check_outdated_html(soup)
    results['unused_css_js'] = check_unused_css_js(soup)
    results['clickable_images'] = check_clickable_images(soup)
    results['responsive_viewport'] = check_responsive_viewport(soup)
    results['modern_doctype'] = check_modern_doctype(html_content)
    results['layout_tables'] = check_layout_tables(soup)

    # Score + Deductions
    score = calculate_score(results)
    deductions = calculate_deductions(results)

    # Wrap for report
    title, url = get_title_and_url(soup)
    author_name = get_report_author()

    issues_data = {
        'Exposed API Keys/JWTs': {'issues': results['exposed_keys']},
        '508 Accessibility Issues': {'issues': results['accessibility']},
        'Keyboard Accessibility Issues': {'issues': results['keyboard_accessibility']},
        'Broken Links': {'issues': results['broken_links']},
        'Clickable Image Issues': {'issues': results['clickable_images']},
        'Color Contrast Issues': {'issues': results['color_contrast']},
        'Missing ARIA Labels': {'issues': results['missing_aria']},
        'Large Images (over 200KB)': {'issues': results['large_images']},
        'HTTPS Compliance': {'issues': results['https']},
        'Outdated HTML Tags': {'issues': results['outdated_html']},
        'Missing Alt Text': {'issues': results['missing_alt']},
        'Responsive Viewport': {'issues': results['responsive_viewport']},
        'Modern Doctype': {'issues': results['modern_doctype']},
        'Layout Tables': {'issues': results['layout_tables']},
    }

    report_data = {
        'title': title,
        'url': url,
        'author_name': author_name,
        'score': score,
        'deductions': deductions,
        'issues_data': issues_data,
        'notes': {}
    }

    # Build final report
    filename = generate_report_filename(soup)
    generate_report(filename, report_data, generate_pdf=False)

    print(f"Analysis complete. Report: {filename}, Score: {score}/100")
    if not PDF_EXPORT_AVAILABLE:
        print("PDF generation requires pdfkit + wkhtmltopdf installed.")

if __name__ == "__main__":
    analyze_html()
