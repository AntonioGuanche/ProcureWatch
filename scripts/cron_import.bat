@echo off
cd /d C:\Users\Utilisateur\.cursor\ProcureWatch
python scripts\import_daily.py --sources BOSA,TED --term "travaux" --days-back 1 --page-size 100 --max-pages 5 >> logs\import_cron.log 2>&1
