name: Notify on New Messages

# Polls the `threads` collection for new subscriber messages
# (pendingNotify == true) every 5 minutes and emails the admin.

on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:

jobs:
  notify:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    concurrency:
      group: notify-messages
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install google-auth google-api-python-client google-cloud-firestore
      - name: Send notifications
        env:
          GMAIL_SA_JSON: ${{ secrets.GMAIL_SA_JSON }}
        run: python notify_messages.py
