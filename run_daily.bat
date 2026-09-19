@echo off
REM 毎朝の自動更新（タスクスケジューラから呼ばれる想定）。
REM データ収集 → 日報生成の順に1回ずつ回す。生成済みの日はgenerate側が自分でスキップする。
cd /d "%~dp0"
venv\Scripts\python.exe collect_all.py
venv\Scripts\python.exe generate_daily_report.py live
