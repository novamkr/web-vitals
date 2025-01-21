import tkinter as tk
from tkinter import ttk, messagebox
from bs4 import BeautifulSoup
import re
import os

try:
    import pdfkit
    PDF_EXPORT_AVAILABLE = True
except ImportError:
    PDF_EXPORT_AVAILABLE = False

REPORT_FILE_PATH = 'Web_Pricer_report.html'

def parse_report(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')

    analyzed_header = soup.find('h2', string='Website Analyzed')
    if not analyzed_header:
        return {}

    title_p = analyzed_header.find_next_sibling('p')
    title = title_p.get_text().replace('Title: ', '') if title_p else 'Unknown Title'
    url_p = title_p.find_next_sibling('p') if title_p else None
    url = url_p.get_text().replace('URL: ', '') if url_p else 'Unknown URL'

    score_div = soup.find('div', class_='health-score-text')
    score = 0
    if score_div and '/' in score_div.get_text():
        score_text = score_div.get_text()
        score = float(score_text.split('/')[0])

    score_details_div = soup.find(id='score-details')
    deductions = {}
    if score_details_div:
        for li in score_details_div.find_all('li'):
            text = li.get_text()
            match = re.match(r'(.+?):\s*([\d\.]+)\s*points', text)
            if match:
                deductions[match.group(1)] = float(match.group(2))

    issue_sections = soup.find_all('button', class_='collapsible')
    issues_data = {}
    for button in issue_sections:
        issue_title = button.get_text().strip()
        count_match = re.search(r'\((\d+)\)', issue_title)
        count = int(count_match.group(1)) if count_match else 0
        category = issue_title.split('(')[0].strip()

        content_div = button.find_next_sibling('div', class_='content')
        issues = []
        if content_div:
            for li in content_div.find_all('li'):
                note_span = li.find('span', class_='note')
                note_text = note_span.get_text(strip=True) if note_span else ''
                full_issue_text = li.get_text(separator=' ', strip=True)
                if note_text and note_text in full_issue_text:
                    issue_text = full_issue_text.replace(note_text, '').strip()
                else:
                    issue_text = full_issue_text
                issues.append({'issue': issue_text, 'note': note_text})

        issues_data[category] = {'count': count, 'issues': issues}

    return {
        'title': title,
        'url': url,
        'score': score,
        'deductions': deductions,
        'issues_data': issues_data
    }

def generate_report(report_filename, report_data):
    title = report_data['title']
    url = report_data['url']
    author_name = report_data.get('author_name', 'NOVAMKR, LLC')
    score = report_data['score']
    deductions = report_data.get('deductions', {})
    issues_data = report_data['issues_data']
    notes = report_data.get('notes', {})

    # Explanation dictionary (short statements) if needed:
    explanations = {
        'Exposed API Keys/JWTs': "Leaving keys/tokens in the open can allow hackers to access private resources.",
        '508 Accessibility Issues': "Accessibility issues can make it hard for disabled users to access the site.",
        'Keyboard Accessibility Issues': "Elements must be reachable without a mouse for inclusive design.",
        'Clickable Image Issues': "Clickable-looking images without a real link confuse users.",
        'Broken Links': "Broken links frustrate users and harm site reliability.",
        'Color Contrast Issues': "Poor contrast makes text difficult to read.",
        'Missing ARIA Labels': "Assistive technologies rely on proper ARIA labels for clarity.",
        'Large Images (over 200KB)': "Large images can slow down page loading.",
        'HTTPS Compliance': "Unsecured HTTP can expose user data to attackers.",
        'Outdated HTML Tags': "Deprecated tags may not be fully supported by modern browsers.",
        'Missing Alt Text': "Screen readers need alt text to understand images.",
        'Responsive Viewport': "Lack of a proper viewport meta can cause zoom/scale issues.",
        'Modern Doctype': "HTML5 doctype is recommended for modern browsers and best practices.",
        'Layout Tables': "Using <table> for layout is considered outdated and hinders responsiveness."
    }

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
        <html lang="en">
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
                <p>This report provides a breakdown of potential issues on the website.</p>

                <h2>Website Health Score</h2>
                <div class="health-bar-container" onclick="toggleScoreDetails()">
                    <div class="health-bar"></div>
                    <div class="health-score-text">{score}/100</div>
                </div>
                <div id="score-details" style="display:none; margin-top: 10px;">
                    <p>Click on each issue category for details.</p>
                    <ul>
        """)
        for deduction_title, points in deductions.items():
            if points > 0:
                file.write(f"<li>{deduction_title}: {points} points</li>")
        file.write("""
                    </ul>
                </div>
                <p class="description">Click the bar above to see how the score was calculated.</p>
        """)

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
                # Show explanation only once per category
                cat_explanation_shown = False

                for issue_dict in issue_list:
                    issue_text = issue_dict['issue']
                    note_text = issue_dict.get('note', '')
                    file.write(f"<li>{issue_text}")

                    short_expl = explanations.get(issue_title, "")
                    if short_expl and not cat_explanation_shown:
                        file.write(f"<br><span class='note'>{short_expl}</span>")
                        cat_explanation_shown = True

                    if note_text:
                        file.write(f"<br><span class='note'>{note_text}</span>")
                    file.write("</li>")
                file.write("</ul>")
            else:
                file.write("<p>0 issue(s) found.</p><ul></ul>")

            file.write("""
                    <p class="description">If applicable, please review & update issues to remain compliant and ensure quality UX.</p>
                </div>
            """)

        file.write("""
            </main>
            <footer>
                <p>End of report.</p>
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

    if PDF_EXPORT_AVAILABLE:
        pdf_filename = os.path.splitext(report_filename)[0] + ".pdf"
        try:
            pdfkit.from_file(report_filename, pdf_filename)
        except Exception as e:
            print(f"PDF conversion failed: {e}")

def recalculate_score(issues_data):
    score = 100

    cat_counts = {
        'Exposed API Keys/JWTs': len(issues_data.get('Exposed API Keys/JWTs', {}).get('issues', [])),
        'Broken Links': len(issues_data.get('Broken Links', {}).get('issues', [])),
        '508 Accessibility Issues': len(issues_data.get('508 Accessibility Issues', {}).get('issues', [])),
        'Keyboard Accessibility Issues': len(issues_data.get('Keyboard Accessibility Issues', {}).get('issues', [])),
        'Clickable Image Issues': len(issues_data.get('Clickable Image Issues', {}).get('issues', [])),
        'Missing ARIA Labels': len(issues_data.get('Missing ARIA Labels', {}).get('issues', [])),
        'Missing Alt Text': len(issues_data.get('Missing Alt Text', {}).get('issues', [])),
        'HTTPS Compliance': len(issues_data.get('HTTPS Compliance', {}).get('issues', [])),
        'Outdated HTML Tags': len(issues_data.get('Outdated HTML Tags', {}).get('issues', [])),
        'Color Contrast Issues': len(issues_data.get('Color Contrast Issues', {}).get('issues', [])),
        'Large Images (over 200KB)': len(issues_data.get('Large Images (over 200KB)', {}).get('issues', [])),
        'Responsive Viewport': len(issues_data.get('Responsive Viewport', {}).get('issues', [])),
        'Modern Doctype': len(issues_data.get('Modern Doctype', {}).get('issues', [])),
        'Layout Tables': len(issues_data.get('Layout Tables', {}).get('issues', []))
    }

    # Major
    score -= min(cat_counts['Exposed API Keys/JWTs'] * 17, 35)
    score -= min(cat_counts['Broken Links'] * 5, 25)
    score -= min(cat_counts['508 Accessibility Issues'] * 10, 20)
    score -= min(cat_counts['Keyboard Accessibility Issues'] * 10, 20)
    score -= min(cat_counts['Clickable Image Issues'] * 5, 10)

    # Minor
    if cat_counts['Missing ARIA Labels'] > 0:
        score -= 5
    if cat_counts['Missing Alt Text'] > 0:
        score -= 5
    if cat_counts['HTTPS Compliance'] > 0:
        score -= 5
    if cat_counts['Outdated HTML Tags'] > 0:
        score -= 5
    if cat_counts['Color Contrast Issues'] > 0:
        score -= 5
    if cat_counts['Large Images (over 200KB)'] > 0:
        score -= 5

    # Design checks
    if cat_counts['Responsive Viewport'] > 0:
        score -= 5
    if cat_counts['Modern Doctype'] > 0:
        score -= 5
    if cat_counts['Layout Tables'] > 0:
        score -= 5

    return max(min(score, 100), 0)

def calculate_deductions(issues_data):
    cat_counts = {
        'Exposed API Keys/JWTs': len(issues_data.get('Exposed API Keys/JWTs', {}).get('issues', [])),
        'Broken Links': len(issues_data.get('Broken Links', {}).get('issues', [])),
        '508 Accessibility Issues': len(issues_data.get('508 Accessibility Issues', {}).get('issues', [])),
        'Keyboard Accessibility Issues': len(issues_data.get('Keyboard Accessibility Issues', {}).get('issues', [])),
        'Clickable Image Issues': len(issues_data.get('Clickable Image Issues', {}).get('issues', [])),
        'Missing ARIA Labels': len(issues_data.get('Missing ARIA Labels', {}).get('issues', [])),
        'Missing Alt Text': len(issues_data.get('Missing Alt Text', {}).get('issues', [])),
        'HTTPS Compliance': len(issues_data.get('HTTPS Compliance', {}).get('issues', [])),
        'Outdated HTML Tags': len(issues_data.get('Outdated HTML Tags', {}).get('issues', [])),
        'Color Contrast Issues': len(issues_data.get('Color Contrast Issues', {}).get('issues', [])),
        'Large Images (over 200KB)': len(issues_data.get('Large Images (over 200KB)', {}).get('issues', [])),
        'Responsive Viewport': len(issues_data.get('Responsive Viewport', {}).get('issues', [])),
        'Modern Doctype': len(issues_data.get('Modern Doctype', {}).get('issues', [])),
        'Layout Tables': len(issues_data.get('Layout Tables', {}).get('issues', []))
    }

    deductions = {}
    deductions['Exposed API Keys/JWTs Deducted'] = min(cat_counts['Exposed API Keys/JWTs'] * 17, 35)
    deductions['Broken Links Deducted'] = min(cat_counts['Broken Links'] * 5, 25)
    deductions['508 Accessibility Issues Deducted'] = min(cat_counts['508 Accessibility Issues'] * 10, 20)
    deductions['Keyboard Accessibility Issues Deducted'] = min(cat_counts['Keyboard Accessibility Issues'] * 10, 20)
    deductions['Clickable Image Issues Deducted'] = min(cat_counts['Clickable Image Issues'] * 5, 10)

    # Minor
    deductions['Missing ARIA Labels Deducted'] = 5 if cat_counts['Missing ARIA Labels'] > 0 else 0
    deductions['Missing Alt Text Deducted'] = 5 if cat_counts['Missing Alt Text'] > 0 else 0
    deductions['HTTPS Compliance Issues Deducted'] = 5 if cat_counts['HTTPS Compliance'] > 0 else 0
    deductions['Outdated HTML Tags Deducted'] = 5 if cat_counts['Outdated HTML Tags'] > 0 else 0
    deductions['Color Contrast Issues Deducted'] = 5 if cat_counts['Color Contrast Issues'] > 0 else 0
    deductions['Large Images Deducted'] = 5 if cat_counts['Large Images (over 200KB)'] > 0 else 0

    # Design checks
    deductions['Responsive Viewport Deducted'] = 5 if cat_counts['Responsive Viewport'] > 0 else 0
    deductions['Modern Doctype Deducted'] = 5 if cat_counts['Modern Doctype'] > 0 else 0
    deductions['Layout Tables Deducted'] = 5 if cat_counts['Layout Tables'] > 0 else 0

    return deductions

def regenerate_report(report_data, report_filename):
    generate_report(report_filename, report_data)

def update_report(to_remove, notes, issues_data, report_data, root):
    for category, issues_to_remove in to_remove.items():
        issues_data[category]['issues'] = [
            i for i in issues_data[category]['issues'] if i['issue'] not in issues_to_remove
        ]
        issues_data[category]['count'] = len(issues_data[category]['issues'])

    if notes:
        report_data['notes'] = notes

    new_score = recalculate_score(issues_data)
    report_data['score'] = new_score
    report_data['issues_data'] = issues_data
    report_data['deductions'] = calculate_deductions(issues_data)

    response = messagebox.askyesno("Save Report", "Do you want to overwrite the existing report?")
    if response:
        report_filename = REPORT_FILE_PATH
    else:
        base, ext = os.path.splitext(REPORT_FILE_PATH)
        report_filename = f"{base}_final{ext}"

    regenerate_report(report_data, report_filename)
    messagebox.showinfo("Report Updated", f"The report has been updated. New score: {new_score}/100")
    root.destroy()

report_data = parse_report(REPORT_FILE_PATH)
issues_data = report_data.get('issues_data', {})

root = tk.Tk()
root.title("Review Report Issues")
root.configure(bg='#1e1e1e')

style = ttk.Style()
style.theme_use('clam')
style.configure('TNotebook', background='#1e1e1e')
style.configure('TNotebook.Tab', background='#2d2d30', foreground='#c7c7c7')
style.map('TNotebook.Tab', background=[('selected', '#252526')])
style.configure('TFrame', background='#1e1e1e')
style.configure('TLabel', background='#1e1e1e', foreground='#c7c7c7')
style.configure('TCheckbutton', background='#1e1e1e', foreground='#c7c7c7')
style.configure('TButton', background='#252526', foreground='#c7c7c7')
style.map('TButton', background=[('active', '#313135')])
style.configure('Horizontal.TScrollbar', background='#2d2d30')
style.configure('Vertical.TScrollbar', background='#2d2d30')

notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True)

selected_issues = {}
select_all_vars = {}

for category, data in issues_data.items():
    frame = tk.Frame(notebook, bg='#1e1e1e')
    notebook.add(frame, text=f"{category} ({data['count']})")

    canvas = tk.Canvas(frame, bg='#1e1e1e', highlightthickness=0)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    scrollable_frame = tk.Frame(canvas, bg='#1e1e1e')
    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    select_all_var = tk.BooleanVar()
    select_all_vars[category] = select_all_var
    selected_issues[category] = []

    def select_all(var, cat):
        for issue_tuple in selected_issues[cat]:
            issue_tuple[1].set(var.get())

    chk_all = tk.Checkbutton(scrollable_frame, text="Select All",
                             variable=select_all_var, bg='#1e1e1e', fg='#c7c7c7',
                             activebackground='#1e1e1e', activeforeground='#c7c7c7',
                             selectcolor='#2d2d2d',
                             command=lambda v=select_all_var, c=category: select_all(v, c))
    chk_all.pack(anchor='w')

    for issue_dict in data['issues']:
        issue = issue_dict['issue']
        existing_note = issue_dict.get('note', '')
        var = tk.BooleanVar()
        note_var = tk.StringVar(value=existing_note)

        frame_issue = tk.Frame(scrollable_frame, bg='#2d2d2d')
        chk = tk.Checkbutton(frame_issue, text=issue, variable=var,
                             bg='#2d2d2d', fg='#c7c7c7',
                             activebackground='#2d2d2d',
                             activeforeground='#c7c7c7',
                             selectcolor='#3e3e42')
        chk.pack(anchor='w')

        note_entry = tk.Entry(frame_issue, textvariable=note_var, width=70,
                              bg='#3e3e42', fg='#c7c7c7', insertbackground='#c7c7c7')
        note_entry.pack(anchor='w', padx=20, pady=(2, 5))

        frame_issue.pack(anchor='w', pady=2, fill='x')
        selected_issues[category].append((issue, var, note_var, frame_issue))

def on_delete():
    to_remove = {}
    for category, issues in selected_issues.items():
        removed = [issue_text for (issue_text, var, note_var, frm) in issues if var.get()]
        if removed:
            to_remove[category] = removed
            for t in issues:
                if t[1].get():
                    t[3].destroy()
            selected_issues[category] = [x for x in issues if not x[1].get()]
            for idx in range(notebook.index("end")):
                if notebook.tab(idx, "text").startswith(category):
                    new_count = len(selected_issues[category])
                    notebook.tab(idx, text=f"{category} ({new_count})")
                    break

    update_report(to_remove, {}, issues_data, report_data, root)

def on_update():
    notes = {}
    for category, issues in selected_issues.items():
        for (issue_text, var, note_var, frm) in issues:
            note_text = note_var.get()
            for i_dict in issues_data[category]['issues']:
                if i_dict['issue'] == issue_text:
                    i_dict['note'] = note_text
            if note_text:
                if category not in notes:
                    notes[category] = {}
                notes[category][issue_text] = note_text

    update_report({}, notes, issues_data, report_data, root)

buttons_frame = tk.Frame(root, bg='#1e1e1e')
buttons_frame.pack(pady=10)

delete_button = ttk.Button(buttons_frame, text="Delete Selected", command=on_delete)
delete_button.pack(side='left', padx=5)

update_button = ttk.Button(buttons_frame, text="Save & Close", command=on_update)
update_button.pack(side='left', padx=5)

root.mainloop()
