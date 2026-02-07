@echo off
cd /d C:\Users\Utilisateur\.cursor\ProcureWatch
python scripts\run_watchlists.py --send-notifications >> logs\watchlist_cron.log 2>&1
