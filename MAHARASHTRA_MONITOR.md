# Maharashtra NEET PG notice alerts

Monitors both public News and Notification lists at https://medical2026.mahacet.org/NEET-PGM-2026/login every ten minutes using GitHub Actions cron. Reuses repository secrets TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. No credentials belong in source files.

The five notices present on 29 October 2026 are the baseline; future new titles or links trigger Telegram messages. Removed/reordered notices do not trigger alerts. An existing PDF replaced without changing its title or URL is not detected.

Open Actions > Maharashtra NEET PG Notices > Run workflow and select send_test for a delivery test. The installation push also sends one test. Check failed runs if no alerts arrive. Fetch/layout failures preserve state and fail the run. Successful deliveries are saved even if a later delivery fails. A rare duplicate remains possible if Telegram accepts a message but its response or the Git state save is lost.

Standard Ubuntu Actions runners are free for this public repository. Scheduled runs may be delayed. GitHub may disable public-repository schedules after 60 days without repository activity; re-enable in Actions if necessary. No paid service or external cron account is required.
