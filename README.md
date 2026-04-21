# Camp Assignment App (Frontend + Backend)

This is a local browser app with a real backend.

- Frontend: upload + run + download page
- Backend: Flask API
- Assignment logic: Python engine
- Runs on your own computer only

## Files in this folder

- `app_backend.py` - backend server
- `templates/index.html` - frontend page
- `static/app.js` - frontend logic
- `static/styles.css` - frontend styles
- `start_browser_app.command` - double-click launcher (Mac)
- `assign_tool.py` - assignment engine
- `requirements.txt` - Python packages
- `config.template.json` - default column mapping

## How to use

1. Double-click `start_browser_app.command`
2. Open `http://127.0.0.1:5001` in your browser
3. Choose one side in the app:
   - **Camper Side** (cabins)
   - **Counselor Side** (camp staffing)
4. Upload your own `.xlsx` or `.csv` file once in the shared upload area
5. Click **Step 2 - Match Fields**
6. Review/adjust field mapping
7. Click **Step 3 - Run**
8. Review cabin layout on the review screen (camper side)
9. From that screen: go back to mapping, open settings, restart, re-run, or export output workbook

## Settings tab

- Open **Settings** to tweak assignment variables without editing files.
- Save settings, return to **Results**, and re-run with the same uploaded data.
- Current settings control:
  - cabin limits and grade span rules
  - roommate max count
  - name/school fuzzy matching thresholds
  - counselor preference scoring and friend bonus

No template is required.

If helpful, template downloads are still available in each side.

Grade balancing note:
- The strict pass now allows up to a 2-grade span in a cabin before fallback logic kicks in.

## Workbook sheets by side

- Camper Side template includes:
  - `campers`
- Counselor Side template includes:
  - `counselors`
  - `camp_targets`

### Required columns in `camp_targets`

- `Camp`
- `Target Total`

Optional:

- `Target Female`
- `Target Male`

## Optional custom config

If your Excel headers are different from the defaults:

1. Copy `config.template.json` to `config.json`
2. Edit header names in `config.json`
3. Upload `config.json` in the app (optional config field)

## If Mac blocks launcher

1. Right-click `start_browser_app.command`
2. Click **Open**
3. Click **Open** again

## Notes

- One-admin workflow
- Auto-assign first, then manual edits in Excel
- Warnings are included in the output workbook
