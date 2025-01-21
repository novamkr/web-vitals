
# Website Analysis Tool

A simple tool to analyze a website's HTML content for potential issues, generate a report, and review the findings using a GUI.

## Features

- **Automated Analysis**: Checks for accessibility issues, broken links, exposed API keys, and more.
- **Report Generation**: Creates an HTML report summarizing the findings.
- **Interactive Review**: Use a GUI to review, comment, and remove issues before finalizing the report.

## Requirements

- Python 3.x
- Internet connection (for checking external links and resources)

## Installation

### Clone the Repository

```bash
git clone https://github.com/yourusername/website-analysis-tool.git
cd website-analysis-tool
```

### Install Dependencies

Create a virtual environment (optional but recommended):

```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

Install required packages:

```bash
pip install -r requirements.txt
```

## Usage

### 1. Extract Website Content

- **Navigate to the Website**: Open your web browser and go to the website you want to analyze.
- **View Page Source**:
  - Right-click on the webpage and select **"View Page Source"** or press `Ctrl+U`.
- **Copy HTML Content**:
  - Select all the HTML content in the source view (`Ctrl+A`), then copy it (`Ctrl+C`).
- **Save to a File**:
  - Open a text editor (e.g., Notepad, VSCode).
  - Paste the copied HTML content (`Ctrl+V`).
  - Save the file as `website_content.txt` in the same directory as the scripts.

### 2. Run the Analysis Script

- **Open VSCode**:
  - Launch Visual Studio Code and open the project folder.
- **Run `website_checker.py`**:
  - In the terminal or command prompt inside VSCode, run:

    ```bash
    python website_checker.py
    ```

- **Enter Your Name**:
  - When prompted, enter your name. This will be included in the report.

- **Wait for Completion**:
  - The script will analyze the HTML content and generate a report.
  - Upon completion, it will display the report filename and the initial score.

### 3. Review and Modify the Report

- **Run `reviewer.py`**:

  ```bash
  python reviewer.py
  ```

- **Use the GUI**:

  - The GUI will display tabs for each category of issues found.
  - **Review Issues**:
    - Navigate through the tabs to see the issues.
    - For each issue, you can:
      - **Delete**: Check the box next to issues you want to remove.
      - **Add Comments**: Enter any comments or notes in the provided text field below each issue.
  - **Select All**:
    - Use the "Select All" checkbox at the top of each tab to select or deselect all issues in that category.
  - **Delete Selected**:
    - Click the **"Delete Selected"** button to remove the checked issues from the report.
  - **Save & Close**:
    - Once you're done reviewing, click **"Save & Close"**.
    - The report will be updated, and the score recalculated based on your modifications.

### 4. View the Final Report

- **Open the Report**:
  - Locate the updated HTML report file (e.g., `YourWebsiteTitle_report.html`) in the project directory.
- **View in Browser**:
  - Open the report in a web browser to see the analysis results.
  - **Navigate Sections**:
    - Click on each issue category to expand or collapse the details.
  - **Review Comments**:
    - Your comments will appear below the associated issues in italic and grey text.

## Troubleshooting

### Missing Dependencies

Ensure all required packages are installed by running:

```bash
pip install -r requirements.txt
```

### `tkinter` Not Found

If you encounter issues related to `tkinter`, you may need to install it separately:

#### On Ubuntu/Debian:

```bash
sudo apt-get install python3-tk
```

#### On Fedora:

```bash
sudo dnf install python3-tkinter
```

### SSL Errors

If SSL errors occur during link checking, ensure your system's SSL certificates are up to date.

---

## Requirements.txt

```txt
requests
beautifulsoup4
cssutils
Pillow
```

---

Feel free to customize and extend the tool according to your needs. If you have any questions or need further assistance, please reach out!
