Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\PC\Documents\antigravity\resilient-pasteur\tmp\job-accelerator-actions-migration"
WshShell.Run "python run.py", 0, False
