import requests
from bs4 import BeautifulSoup
import re
import cssutils
from PIL import ImageColor
import time
import urllib.request
import ssl
import os

# For optional PDF conversion
try:
    import pdfkit
    PDF_EXPORT_AVAILABLE = True
except ImportError:
    PDF_EXPORT_AVAILABLE = False

# SUPPORTED_LANGUAGES = {
#     'en': 'English',
#     'es': 'Español'
# }

HTML_FILE_PATH = 'website_content.txt'

#def get_user_language():
    # use_multi = input("Enable multi-language support? (Y/N): ").strip().lower()
    # if use_multi == 'y':
    #     print("Supported Languages:")
    #     for code, lang_name in SUPPORTED_LANGUAGES.items():
    #         print(f"{code} - {lang_name}")
    #     chosen = input("Enter language code (default: 'en'): ").strip().lower()
    #     return chosen if chosen in SUPPORTED_LANGUAGES else 'en'
    # return 'en'

def load_html_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
    return BeautifulSoup(html_content, 'html.parser'), html_content

def get_report_author():
    """
    Override user input to fix brand:
    'Report generated by: NOVAMKR, LLC'
    """
    return "NOVAMKR, LLC"

def get_title_and_url(soup):
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

    if not re.match(r'^https:\/\/.*\.(com|org|gov|edu|net)(\/.*)?$', url):
        if 'URL not found' in url or url.startswith('#'):
            url = "Valid URL not found"
    return title, url

def check_missing_alt(soup):
    missing_alt = []
    images = soup.find_all('img')
    for img in images:
        alt_text = img.get('alt')
        aria_hidden = img.get('aria-hidden') == 'true'
        role_presentation = img.get('role') == 'presentation'
        if (alt_text is None or alt_text.strip() == '') and not aria_hidden and not role_presentation:
            missing_alt.append(f"Image missing alt text: {img.get('src')}")
    return missing_alt

def check_clickable_images(soup):
    """
    Identify images that appear clickable (onclick/parent anchor) but no real link.
    """
    issues = []
    images = soup.find_all('img')
    for img in images:
        onclick_attr = img.get('onclick')
        parent_anchor = img.find_parent('a')
        if (onclick_attr or parent_anchor) and not (parent_anchor and parent_anchor.get('href')):
            issues.append(f"Clickable image not linked or actionable: {img.get('src')}")
    return issues

def check_responsive_viewport(soup):
    """
    Check for <meta name="viewport" content="width=device-width, ...">
    """
    issues = []
    meta_viewport = soup.find('meta', attrs={'name': 'viewport'})
    if not meta_viewport:
        issues.append("No responsive 'viewport' meta tag. Site may have zoom/scale issues.")
    else:
        content = meta_viewport.get('content', '').lower()
        if "width=device-width" not in content:
            issues.append(f"Viewport meta tag is present but may be misconfigured: '{content}'")
    return issues

def check_modern_doctype(html_text):
    """
    Check for <!DOCTYPE html> near the start (HTML5).
    """
    issues = []
    snippet = html_text[:200].lower()
    if "<!doctype html>" not in snippet:
        issues.append("Site not using modern HTML5 doctype.")
    return issues

def check_layout_tables(soup):
    """
    If many <table> elements are found, site may be using them for layout.
    """
    issues = []
    tables = soup.find_all('table')
    if len(tables) > 5:
        issues.append("Excessive <table> usage; possible legacy layout approach.")
    return issues

def calculate_score(results):
    score = 100
    # Major issues
    exposed_count = len(results.get('exposed_keys', []))
    broken_404_count = len([b for b in results.get('broken_links', []) if b[1] == "404"])
    accessibility_count = len(results.get('accessibility', []))
    keyboard_count = len(results.get('keyboard_accessibility', []))
    clickable_images_count = len(results.get('clickable_images', []))

    # Deduct major
    score -= min(exposed_count * 17, 35)
    score -= min(broken_404_count * 5, 25)
    score -= min(accessibility_count * 10, 20)
    score -= min(keyboard_count * 10, 20)
    score -= min(clickable_images_count * 5, 10)

    # Minor
    if results.get('missing_aria'):
        score -= 5
    if results.get('missing_alt'):
        score -= 5
    if results.get('https'):
        score -= 5
    if results.get('outdated_html'):
        score -= 5
    if results.get('large_images'):
        score -= 5
    if results.get('color_contrast'):
        score -= 5

    # Design checks
    if results.get('responsive_viewport'):
        score -= 5
    if results.get('modern_doctype'):
        score -= 5
    if results.get('layout_tables'):
        score -= 5

    return max(min(score, 100), 0)

def calculate_deductions(results):
    deductions = {}

    # Major
    exposed_count = len(results.get('exposed_keys', []))
    broken_404_count = len([b for b in results.get('broken_links', []) if b[1] == "404"])
    accessibility_count = len(results.get('accessibility', []))
    keyboard_count = len(results.get('keyboard_accessibility', []))
    clickable_images_count = len(results.get('clickable_images', []))

    deductions['Exposed API Keys/JWTs Deducted'] = min(exposed_count * 17, 35)
    deductions['Broken Links Deducted'] = min(broken_404_count * 5, 25)
    deductions['508 Accessibility Issues Deducted'] = min(accessibility_count * 10, 20)
    deductions['Keyboard Accessibility Issues Deducted'] = min(keyboard_count * 10, 20)
    deductions['Clickable Image Issues Deducted'] = min(clickable_images_count * 5, 10)

    # Minor
    deductions['Missing ARIA Labels Deducted'] = 5 if results.get('missing_aria') else 0
    deductions['Missing Alt Text Deducted'] = 5 if results.get('missing_alt') else 0
    deductions['HTTPS Compliance Issues Deducted'] = 5 if results.get('https') else 0
    deductions['Outdated HTML Tags Deducted'] = 5 if results.get('outdated_html') else 0
    deductions['Large Images Deducted'] = 5 if results.get('large_images') else 0
    deductions['Color Contrast Issues Deducted'] = 5 if results.get('color_contrast') else 0

    # Design checks
    deductions['Responsive Viewport Deducted'] = 5 if results.get('responsive_viewport') else 0
    deductions['Modern Doctype Deducted'] = 5 if results.get('modern_doctype') else 0
    deductions['Layout Tables Deducted'] = 5 if results.get('layout_tables') else 0

    return deductions

def generate_report_filename(soup):
    title_tag = soup.find('title')
    title = title_tag.get_text().strip() if title_tag else "website_report"
    clean_title = re.sub(r'\W+', '_', title)
    return f"{clean_title}_report.html"

def check_grammar(text_content):
    return []

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

def check_broken_links(soup):
    broken_links = set()
    links = soup.find_all('a', href=True)
    for link in links:
        href = link.get('href')
        if href.startswith('http'):
            try:
                req = urllib.request.Request(href, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req, context=ssl_context, timeout=5)
                if not (200 <= response.status < 300):
                    broken_links.add((href, str(response.status)))
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 600:
                    broken_links.add((href, str(e.code)))
            except urllib.error.URLError as e:
                if "SSL" in str(e.reason):
                    broken_links.add((href, "security"))
            except ssl.SSLError:
                broken_links.add((href, "security"))
            except TimeoutError:
                broken_links.add((href, "timeout"))
            except Exception:
                broken_links.add((href, "unexpected_error"))
    return list(broken_links)

def check_image_sizes(soup):
    large_images = []
    session = requests.Session()
    session.headers.update({'User-Agent': 'WebsiteChecker/1.0'})
    images = soup.find_all('img', src=True)
    for img in images:
        src = img.get('src')
        if src.startswith('http'):
            try:
                response = session.head(src, allow_redirects=True, timeout=10)
                if response.status_code == 200 and 'Content-Length' in response.headers:
                    size_kb = int(response.headers['Content-Length']) / 1024
                    if size_kb > 200:
                        large_images.append((src, size_kb))
            except requests.exceptions.RequestException:
                pass
    return large_images

def check_accessibility(soup):
    issues = []
    html_tag = soup.find('html')
    if html_tag and not html_tag.get('lang'):
        issues.append("Missing 'lang' attribute in <html> tag.")
    main_content = soup.find('main') or soup.find(attrs={"role": "main"})
    if not main_content:
        issues.append("Missing main content area with <main> or role='main'.")
    return issues

def check_color_contrast(soup, html_content):
    issues = []
    style_sheets = []

    style_tags = soup.find_all('style')
    for style_tag in style_tags:
        if style_tag.string:
            style_sheets.append(style_tag.string)

    link_tags = soup.find_all('link', rel='stylesheet')
    session = requests.Session()
    session.headers.update({'User-Agent': 'WebsiteChecker/1.0'})
    for link_tag in link_tags:
        href = link_tag.get('href')
        if href and href.startswith('http'):
            try:
                response = session.get(href, timeout=10)
                if response.status_code == 200:
                    style_sheets.append(response.text)
            except requests.exceptions.RequestException:
                pass

    css_styles = '\n'.join(style_sheets)
    css_parser = cssutils.CSSParser()
    stylesheet = css_parser.parseString(css_styles)

    styles_map = {}
    for rule in stylesheet:
        if rule.type == rule.STYLE_RULE:
            selector = rule.selectorText
            style = rule.style.cssText
            styles_map[selector] = style

    def get_computed_style(element):
        styles_list = []
        if element.has_attr('style'):
            styles_list.append(element['style'])
        class_list = element.get('class', [])
        id_attr = element.get('id')
        for selector, style in styles_map.items():
            if selector.startswith('.'):
                if selector[1:] in class_list:
                    styles_list.append(style)
            elif selector.startswith('#'):
                if selector[1:] == id_attr:
                    styles_list.append(style)
            elif selector == element.name:
                styles_list.append(style)
        return ';'.join(styles_list)

    main_content = soup.find('main') or soup.find(attrs={"role": "main"}) or soup.body
    if not main_content:
        return issues

    text_elements = main_content.find_all(string=True)
    for element in text_elements:
        parent = element.parent
        if parent.name not in ['style', 'script', 'head', 'title', 'meta', '[document]'] and element.strip():
            computed_style = get_computed_style(parent)
            style = cssutils.parseStyle(computed_style)
            fg_color = style.getPropertyValue('color') or '#000000'
            bg_color = style.getPropertyValue('background-color') or '#FFFFFF'

            def parse_color(c_str):
                try:
                    if 'rgba' in c_str:
                        return ImageColor.getcolor(c_str, "RGBA")[:3]
                    return ImageColor.getcolor(c_str, "RGB")
                except ValueError:
                    return None

            fg = parse_color(fg_color)
            bg = parse_color(bg_color)
            if fg and bg:
                def relative_luminance(rgb):
                    def channel_lum(c):
                        c = c / 255.0
                        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                    return 0.2126 * channel_lum(rgb[0]) + 0.7152 * channel_lum(rgb[1]) + 0.0722 * channel_lum(rgb[2])

                l1 = relative_luminance(fg)
                l2 = relative_luminance(bg)
                contrast_ratio = (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
                if contrast_ratio < 4.5:
                    snippet = element.strip()[:30]
                    issues.append(f"Low contrast ratio ({contrast_ratio:.2f}) for text: '{snippet}'")
    return issues

def check_missing_aria(soup):
    issues = []
    interactive_elems = soup.find_all(['button', 'a', 'input', 'select', 'textarea'])
    for elem in interactive_elems:
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
            # Provide more detail about the element
            elem_id = elem.get('id', '')
            elem_class = ' '.join(elem.get('class', []))
            issues.append(
                f"Missing accessible name for <{elem.name} id='{elem_id}' class='{elem_class}'>"
            )
    return issues

def check_keyboard_accessibility(soup):
    issues = []
    clickable_elems = soup.find_all(attrs={'onclick': True})
    for elem in clickable_elems:
        if not elem.has_attr('tabindex') and elem.name not in ['a', 'button', 'input', 'textarea', 'select']:
            issues.append(f"Element <{elem.name}> is clickable but may not be keyboard accessible.")
    return issues

def check_exposed_keys(html_content):
    issues = {}
    pattern_dict = {
        'AWS Access Key': r'AKIA[0-9A-Z]{16}',
        'JWT': r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
        'Google API Key': r'AIza[0-9A-Za-z-_]{35}',
        'Generic API Key': r'api_key\s*=\s*[\'"][A-Za-z0-9-_]{16,}[\'"]',
        'Slack Token': r'xox[baprs]-[A-Za-z0-9-]{10,48}',
    }
    found = []
    for key_type, pattern in pattern_dict.items():
        matches = re.findall(pattern, html_content)
        for match in matches:
            found.append(f"Exposed {key_type}: {match}")
    return found

def check_https(soup):
    insecure_links = set()
    tags_with_urls = soup.find_all(['a', 'img', 'link', 'script'])
    for tag in tags_with_urls:
        url = tag.get('href') or tag.get('src')
        if url and url.startswith('http://'):
            insecure_links.add(url)
    return list(insecure_links)

def check_outdated_html(soup):
    issues = []
    deprecated_tags = ['font', 'center', 'marquee', 'blink']
    for tag in deprecated_tags:
        found_tags = soup.find_all(tag)
        for ft in found_tags:
            issues.append(f"Outdated tag <{tag}> found.")
    return issues

def check_unused_css_js(soup):
    return []

def generate_explanations():
    return {
        'Exposed API Keys/JWTs': "Leaving keys/tokens in the open can allow hackers to access private resources.",
        '508 Accessibility Issues': "Accessibility issues can make it hard for disabled users to access the site.",
        'Keyboard Accessibility Issues': "Elements must be reachable without a mouse for inclusive design.",
        'Clickable Image Issues': "Clickable-looking images without a real link confuse users.",
        'Broken Links': "Broken links frustrate users and harm site reliability.",
        'Color Contrast Issues': "Poor contrast makes text difficult to read.",
        'Missing ARIA Labels': "Assistive technologies rely on proper ARIA labels for clarity.",
        'Large Images (over 200KB)': "Large images can slow down page load times.",
        'HTTPS Compliance': "Unsecured HTTP can expose user data to attackers.",
        'Outdated HTML Tags': "Deprecated tags may not be supported by modern browsers.",
        'Missing Alt Text': "Screen readers need alt text to understand images.",
        'Responsive Viewport': "Lack of a proper viewport meta can cause zoom/scale issues on mobile.",
        'Modern Doctype': "HTML5 doctype is recommended for modern browsers and best practices.",
        'Layout Tables': "Using <table> for layout is considered outdated and hinders responsiveness."
    }

def generate_report(report_filename, report_data, language_code='en', generate_pdf=False):
    title = report_data['title']
    url = report_data['url']
    author_name = report_data.get('author_name', 'NOVAMKR, LLC')
    score = report_data['score']
    deductions = report_data.get('deductions', {})
    issues_data = report_data['issues_data']
    notes = report_data.get('notes', {})
    explanations = generate_explanations()

    severity_levels = {
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
        'Missing Alt Text': 'information',
        'Responsive Viewport': 'low',
        'Modern Doctype': 'low',
        'Layout Tables': 'low'
    }

    severity_colors = {
        'high': '#c0392b',
        'medium': '#b89a00',
        'low': '#27ae60',
        'information': '#2980b9',
        'none': '#b0b0b0'
    }

    # Keep a set to avoid repeating the same explanation text multiple times
    category_explanations_shown = set()

    # Sort the categories in a certain order
    issues_order = [
        ('Exposed API Keys/JWTs', issues_data.get('Exposed API Keys/JWTs', {}).get('issues', [])),
        ('508 Accessibility Issues', issues_data.get('508 Accessibility Issues', {}).get('issues', [])),
        ('Keyboard Accessibility Issues', issues_data.get('Keyboard Accessibility Issues', {}).get('issues', [])),
        ('Broken Links', issues_data.get('Broken Links', {}).get('issues', [])),
        ('Clickable Image Issues', issues_data.get('Clickable Image Issues', {}).get('issues', [])),
        ('Color Contrast Issues', issues_data.get('Color Contrast Issues', {}).get('issues', [])),
        ('Missing ARIA Labels', issues_data.get('Missing ARIA Labels', {}).get('issues', [])),
        ('Large Images (over 200KB)', issues_data.get('Large Images (over 200KB)', {}).get('issues', [])),
        ('HTTPS Compliance', issues_data.get('HTTPS Compliance', {}).get('issues', [])),
        ('Outdated HTML Tags', issues_data.get('Outdated HTML Tags', {}).get('issues', [])),
        ('Missing Alt Text', issues_data.get('Missing Alt Text', {}).get('issues', [])),
        ('Responsive Viewport', issues_data.get('Responsive Viewport', {}).get('issues', [])),
        ('Modern Doctype', issues_data.get('Modern Doctype', {}).get('issues', [])),
        ('Layout Tables', issues_data.get('Layout Tables', {}).get('issues', []))
    ]

    with open(report_filename, 'w', encoding='utf-8') as file:
        file.write(f"""
        <!DOCTYPE html>
        <html lang="{language_code}">
        <head>
            <title>Website Analysis Report</title>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #1e1e1e;
                    color: #c7c7c7;
                    margin: 0;
                    padding: 0;
                }}
                h1, h2, h3 {{
                    color: #ffffff;
                }}
                h1 {{
                    background-color: #252526;
                    padding: 20px;
                    margin: 0;
                    text-align: center;
                }}
                header, main, footer {{
                    margin: 0 auto;
                    max-width: 800px;
                    padding: 20px;
                }}
                /* Remove hyperlink styling for non-clickable text */
                a {{
                    color: inherit;
                    text-decoration: none;
                    cursor: default;
                }}
                a:hover {{
                    text-decoration: none;
                    color: inherit;
                    cursor: default;
                }}
                ul {{
                    list-style-type: none;
                    padding: 0;
                }}
                li {{
                    background-color: #2d2d2d;
                    margin: 5px 0;
                    padding: 10px;
                    border-radius: 5px;
                }}
                .description {{
                    font-style: italic;
                    color: #9b9b9b;
                    margin-top: 10px;
                }}
                .health-bar-container {{
                    background-color: rgba(255, 255, 255, 0.1);
                    border-radius: 5px;
                    overflow: hidden;
                    margin-top: 20px;
                    cursor: pointer;
                    position: relative;
                }}
                .health-bar {{
                    height: 30px;
                    width: {score}%;
                    background-color: {"#c0392b" if score < 50 else "#b89a00" if score < 80 else "#27ae60"};
                    transition: width 0.5s, background-color 0.5s;
                    opacity: 0.8;
                }}
                .health-score-text {{
                    position: absolute;
                    top: 0;
                    left: 50%;
                    transform: translateX(-50%);
                    line-height: 30px;
                    color: #ffffff;
                    font-weight: bold;
                }}
                .issue-count {{
                    background-color: #3e3e42;
                    padding: 5px 10px;
                    border-radius: 5px;
                    display: inline-block;
                    margin-left: 10px;
                }}
                .collapsible {{
                    background-color: #252526;
                    color: #ffffff;
                    cursor: pointer;
                    padding: 10px;
                    width: 100%;
                    border: none;
                    text-align: left;
                    outline: none;
                    font-size: 15px;
                    margin-top: 10px;
                }}
                .active, .collapsible:hover {{
                    background-color: #313135;
                }}
                .content {{
                    padding: 0 18px;
                    max-height: 0;
                    overflow: hidden;
                    transition: max-height 0.2s ease-out;
                    background-color: #2d2d30;
                    margin-bottom: 10px;
                }}
                .content ul {{
                    padding: 10px;
                }}
                .section-title {{
                    padding: 10px;
                    border-radius: 5px;
                    margin-top: 10px;
                }}
                .note {{
                    font-style: italic;
                    color: #9b9b9b;
                    display: block;
                    margin-top: 5px;
                }}
            </style>
        </head>
        <body>
            <header>
                <h1>Website Analysis Report</h1>
            </header>
            <main>

                <h2>Website Analyzed</h2>
                <p>Title: {title}</p>
                <p>URL: <a href="{url}" target="_blank">{url}</a></p>

                <p>Report generated by: {author_name}</p>

                <h2>Summary of Issues Detected</h2>
                <p>This report provides a breakdown of potential issues on the website. Click any bar below to expand details.</p>

                <h2>Website Health Score</h2>
                <div class="health-bar-container" onclick="toggleScoreDetails()">
                    <div class="health-bar"></div>
                    <div class="health-score-text">{score}/100</div>
                </div>
                <div id="score-details" style="display:none; margin-top: 10px;">
                    <p>Score is based on critical vs minor issues. Click on an issue category for more details.</p>
                    <ul>
        """)

        for deduction_title, points in deductions.items():
            if points > 0:
                file.write(f"<li>{deduction_title}: {points} points</li>")

        file.write("""
                    </ul>
                </div>
                <p class="description">Click the bar above to view or hide deduction breakdown.</p>
        """)

        # Render categories
        for issue_title, issue_list in issues_order:
            severity = severity_levels.get(issue_title, 'none')
            color = severity_colors.get(severity, '#ffffff')
            count = len(issue_list)

            file.write(f"""
                <button type="button" class="collapsible section-title"
                        style="background-color: {color if count > 0 else '#ffffff'};
                               color: {'#ffffff' if count > 0 and color != '#ffffff' else '#000000'};">
                    {issue_title} ({count})
                </button>
                <div class="content">
            """)
            if count > 0:
                file.write(f"<p>{count} issue(s) found.</p><ul>")

                # We only want to show the short explanation once per category,
                # but multiple items might appear. We keep track with:
                cat_explanation_shown = False

                for item in issue_list:
                    issue_text = item if isinstance(item, str) else item[0]
                    file.write(f"<li>{issue_text}")

                    short_expl = explanations.get(issue_title, "")
                    # Show explanation only if we haven't shown it yet
                    if short_expl and not cat_explanation_shown:
                        file.write(f"<br><span class='note'>{short_expl}</span>")
                        cat_explanation_shown = True

                    # Additional user notes
                    note = notes.get(issue_title, {}).get(issue_text, '')
                    if note:
                        file.write(f"<br><span class='note'>{note}</span>")

                    file.write("</li>")
                file.write("</ul>")
            else:
                file.write("<p>0 issues found.</p><ul></ul>")

            file.write("""
                    <p class="description">Please address these to improve compliance, security, and user experience.</p>
                </div>
            """)

        file.write("""
            </main>
            <footer>
                <p>End of report. Thank you!</p>
            </footer>

            <script>
                var coll = document.getElementsByClassName("collapsible");
                for (var i = 0; i < coll.length; i++) {
                    coll[i].addEventListener("click", function() {
                        this.classList.toggle("active");
                        var content = this.nextElementSibling;
                        if (content.style.maxHeight){
                            content.style.maxHeight = null;
                        } else {
                            content.style.maxHeight = content.scrollHeight + "px";
                        }
                    });
                }

                function toggleScoreDetails() {
                    var details = document.getElementById("score-details");
                    if (details.style.display === "none" || details.style.display === "") {
                        details.style.display = "block";
                    } else {
                        details.style.display = "none";
                    }
                }
            </script>
        </body>
        </html>
        """)

    if generate_pdf and PDF_EXPORT_AVAILABLE:
        pdf_filename = os.path.splitext(report_filename)[0] + ".pdf"
        pdfkit.from_file(report_filename, pdf_filename)
        print(f"PDF generated successfully: {pdf_filename}")

def analyze_html():
    # Ask for language
    language_code = get_user_language()

    soup, html_content = load_html_file(HTML_FILE_PATH)

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

    # New design checks
    results['responsive_viewport'] = check_responsive_viewport(soup)
    results['modern_doctype'] = check_modern_doctype(html_content)
    results['layout_tables'] = check_layout_tables(soup)

    title, url = get_title_and_url(soup)
    author_name = get_report_author()

    score = calculate_score(results)
    deductions = calculate_deductions(results)

    # Build the final issues_data
    report_data = {
        'title': title,
        'url': url,
        'author_name': author_name,
        'score': score,
        'deductions': deductions,
        'issues_data': {
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
        },
        'notes': {}
    }

    report_filename = generate_report_filename(soup)
    generate_report(report_filename, report_data, generate_pdf=False)

    print(f"\nAnalysis complete. Report generated: {report_filename}, Score: {score}/100")
    if not PDF_EXPORT_AVAILABLE:
        print("Note: PDF generation requires pdfkit and wkhtmltopdf installed.")

if __name__ == "__main__":
    analyze_html()
