# Website Tour Recorder

A standalone Python + Playwright website tour recorder with timestamped MP4 output. It can run locally on Windows or in GitHub Actions so you can start a recording from your phone.

## Features

- Config-driven homepage and route tour.
- 1920x1080 browser viewport and video recording.
- Smooth ease-in-out scrolling and interpolated mouse movement.
- Sample text typing, submit clicks, optional result selector wait.
- Network-idle and finite-animation settling waits.
- WebM capture finalized by closing the browser context, then FFmpeg H.264 MP4 export.
- Manual GitHub Actions workflow with downloadable artifacts.

## Run locally (Windows PowerShell)

Install Python 3.10+, then from this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
winget install Gyan.FFmpeg
python recorder.py
```

Edit `config.json` first. Set `base_url`, `landing_scroll`, and each route. Interactive routes can specify:

```json
{
  "name": "Example generator",
  "path": "/tool",
  "interaction": {
    "input_selector": "textarea",
    "sample_text": "Write a short study plan.",
    "submit_selector": "button[type='submit']",
    "result_selector": "[data-testid='result']"
  }
}
```

Selectors must match the target website. The default config targets `https://haryomix.eu.cc`, tours the homepage, and safely discovers up to 10 same-origin pages linked from it. You can still add explicit routes in `config.json`.

## Run from mobile using GitHub Actions

1. Push/keep this repository on GitHub.
2. Open the repository in GitHub mobile or a browser.
3. Go to **Actions** → **Record website tour** → **Run workflow**.
4. The website URL is pre-filled with `https://haryomix.eu.cc`. You can leave it as-is or enter another full URL. Optional route paths can be comma-separated, such as `/tools,/pdf-editor`.
5. Start the workflow and wait for it to finish.
6. Open the successful workflow run and download the `website-tour-video` artifact. Extract it to get the MP4.

A recording also starts automatically when recording code, its config, dependencies, or the workflow file is pushed to `main`. The run validates Python syntax/config before opening the site.

The GitHub workflow runs headless Chromium on an Ubuntu runner, installs FFmpeg, and uploads the MP4 plus original WebM. It does not require your laptop to be on.

## Limitations

- GitHub-hosted runners have usage quotas, execution time limits and artifact retention policies.
- The recorder discovers up to 10 same-origin links from the homepage by default and skips common auth/admin/destructive paths. Explicit workflow route paths are also visited. Tool-specific input/submit/result interactions still require selectors in `config.json`.
- 60fps is the output encoding frame rate, not a guarantee that the browser rendered every frame at 60fps.
- Some pages keep background network requests active; network-idle waits time out and the script continues.
- Use only websites you are authorized to record, and use harmless test data. Avoid entering credentials or personal data in config files.
